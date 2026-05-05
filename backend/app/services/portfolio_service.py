"""Aggregates Alpaca account + positions + local Proposal data into a portfolio snapshot."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlmodel import select
from app.db import get_session
from app.models import Proposal, Execution
from app.services import alpaca_service


def _compute_allocations(positions: list[dict], account: dict) -> dict:
    """by_kind percentages sum to ~100 against equity; by_underlying aggregates |market_value|."""
    equity = float(account.get("equity") or 0.0)
    cash = float(account.get("cash") or 0.0)
    stock_mv = sum(abs(p["market_value"]) for p in positions if p["kind"] == "stock" and p.get("market_value") is not None)
    option_mv = sum(abs(p["market_value"]) for p in positions if p["kind"] == "option" and p.get("market_value") is not None)

    def pct(x: float) -> float:
        return round((x / equity) * 100.0, 2) if equity > 0 else 0.0

    by_kind = {"stock": pct(stock_mv), "option": pct(option_mv), "cash": pct(cash)}

    underlying_totals: dict[str, float] = {}
    for p in positions:
        if p.get("market_value") is None:
            continue
        key = p.get("underlying") or p["symbol"]
        underlying_totals[key] = underlying_totals.get(key, 0.0) + abs(p["market_value"])
    by_underlying = sorted(
        [{"ticker": t, "market_value": round(mv, 2), "weight_pct": pct(mv)} for t, mv in underlying_totals.items()],
        key=lambda r: r["market_value"],
        reverse=True,
    )
    return {"by_kind": by_kind, "by_underlying": by_underlying}


def _parse_occ(symbol: str) -> dict | None:
    """Parse OCC option symbol. Returns None for non-options (length < 15)."""
    if len(symbol) < 15:
        return None
    # Last 8 chars: strike (3 implied decimals). Char before: C/P. Six chars before that: YYMMDD.
    strike = int(symbol[-8:]) / 1000.0
    side = "call" if symbol[-9] == "C" else "put"
    yymmdd = symbol[-15:-9]
    expiry = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    underlying = symbol[:-15]
    return {"underlying": underlying, "expiry": expiry, "side": side, "strike": strike}


def _normalize_positions(raw: list[dict], prices: dict[str, float | None], account: dict) -> list[dict]:
    """Filter qty==0; add kind, multiplier-aware market_value, unrealized_pl, weight_pct, OCC fields."""
    equity = float(account.get("equity") or 0.0)
    out: list[dict] = []
    for r in raw:
        qty = float(r.get("qty") or 0.0)
        if qty == 0:
            continue
        symbol = r["symbol"]
        avg_entry = float(r.get("avg_entry_price") or 0.0)
        occ = _parse_occ(symbol)
        kind = "option" if occ else "stock"
        multiplier = 100 if kind == "option" else 1
        cur = prices.get(symbol)
        if cur is None:
            mv = pl = pct = None
        else:
            mv = round(cur * qty * multiplier, 2)
            pl = round((cur - avg_entry) * qty * multiplier, 2)
            pct = round((mv / equity) * 100.0, 4) if equity > 0 else 0.0
        pos = {
            "symbol": symbol,
            "kind": kind,
            "qty": qty,
            "avg_entry": avg_entry,
            "current_price": cur,
            "market_value": mv,
            "unrealized_pl": pl,
            "unrealized_pl_pct": (round(pl / (avg_entry * qty * multiplier) * 100.0, 2)
                                  if pl is not None and avg_entry > 0 else None),
            "weight_pct": pct,
            "underlying": occ["underlying"] if occ else symbol,
        }
        if occ:
            pos["strike"] = occ["strike"]
            pos["side"] = occ["side"]
            pos["expiry"] = occ["expiry"]
        out.append(pos)
    return out


def _classify_strategy(legs: list[dict]) -> str:
    """Best-effort name from leg shape."""
    if len(legs) == 1:
        l = legs[0]
        if l["action"] == "buy":
            return f"long-{l.get('side', 'option')}"
        return f"short-{l.get('side', 'option')}"
    if len(legs) == 2 and legs[0].get("side") == legs[1].get("side"):
        side = legs[0].get("side", "option")
        longs = [l for l in legs if l["action"] == "buy"]
        shorts = [l for l in legs if l["action"] == "sell"]
        if longs and shorts:
            net_debit = sum(l["premium"] * l["qty"] for l in longs) - sum(l["premium"] * l["qty"] for l in shorts)
            direction = "bull" if (side == "call" and net_debit > 0) or (side == "put" and net_debit < 0) else "bear"
            return f"{direction}-{side}-spread"
    return "multi-leg"


def _group_strategies(positions: list[dict]) -> list[dict]:
    """For each executed Proposal, build one strategy row from currently-held legs."""
    pos_by_sym = {p["symbol"]: p for p in positions if p["kind"] == "option"}
    if not pos_by_sym:
        return []
    out: list[dict] = []
    with get_session() as s:
        proposals = s.exec(
            select(Proposal).where(Proposal.status == "executed").order_by(Proposal.created_at.desc())
        ).all()
    for p in proposals:
        legs = json.loads(p.legs_json)
        leg_syms = [l["contract_symbol"] for l in legs]
        held = [sym for sym in leg_syms if sym in pos_by_sym]
        if not held:
            continue
        cost_basis = 0.0
        for l in legs:
            sign = 1 if l["action"] == "buy" else -1
            cost_basis += sign * float(l["premium"]) * int(l["qty"]) * 100
        current_value = 0.0
        unrealized_pl = 0.0
        for l in legs:
            sym = l["contract_symbol"]
            if sym not in pos_by_sym:
                continue
            held_pos = pos_by_sym[sym]
            sign = 1 if l["action"] == "buy" else -1
            mv = held_pos.get("market_value")
            if mv is not None:
                current_value += sign * float(mv)
            pl = held_pos.get("unrealized_pl")
            if pl is not None:
                unrealized_pl += sign * float(pl)
        pl_pct = round((unrealized_pl / abs(cost_basis)) * 100.0, 2) if cost_basis != 0 else None
        out.append({
            "proposal_id": p.id,
            "ticker": p.ticker,
            "type": _classify_strategy(legs),
            "legs": [{"symbol": l["contract_symbol"], "qty": int(l["qty"]), "side": l["action"]} for l in legs],
            "cost_basis": round(cost_basis, 2),
            "current_value": round(current_value, 2) if current_value else 0.0,
            "unrealized_pl": round(unrealized_pl, 2),
            "unrealized_pl_pct": pl_pct,
            "expiry": p.expiry,
            "legs_open": len(held),
            "legs_total": len(legs),
        })
    return out


def _build_history(limit: int = 20) -> list[dict]:
    with get_session() as s:
        rows = s.exec(select(Proposal).order_by(Proposal.created_at.desc()).limit(limit)).all()
        out = []
        for p in rows:
            ex = s.exec(select(Execution).where(Execution.proposal_id == p.id)).first()
            out.append({
                "proposal_id": p.id,
                "ticker": p.ticker,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
                "executed_at": ex.submitted_at.isoformat() if ex else None,
                "alpaca_order_id": ex.alpaca_order_id if ex else None,
            })
        return out


def build_snapshot() -> dict:
    """Return a PortfolioSnapshot. Partial failures captured in `errors` rather than raised."""
    errors: list[str] = []
    account: dict = {"cash": None, "equity": None, "buying_power": None, "day_pl": None, "day_pl_pct": None}
    try:
        a = alpaca_service.get_portfolio()
        account.update(a)
        # day_pl/day_pl_pct not yet exposed by get_portfolio; set null defaults
        account.setdefault("day_pl", None)
        account.setdefault("day_pl_pct", None)
    except Exception:
        errors.append("account_unavailable")

    raw_positions: list[dict] = []
    try:
        raw_positions = alpaca_service.get_positions()
    except Exception:
        errors.append("positions_unavailable")

    symbols = [r["symbol"] for r in raw_positions]
    try:
        prices = alpaca_service.get_latest_prices(symbols) if symbols else {}
    except Exception:
        prices = {s: None for s in symbols}
        errors.append("prices_unavailable")

    positions = _normalize_positions(raw_positions, prices, account)
    strategies = []
    try:
        strategies = _group_strategies(positions)
    except Exception:
        errors.append("strategies_unavailable")

    allocations = _compute_allocations(positions, account)

    history: list[dict] = []
    try:
        history = _build_history()
    except Exception:
        errors.append("history_unavailable")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "positions": positions,
        "strategies": strategies,
        "allocations": allocations,
        "history": history,
        "errors": errors,
    }
