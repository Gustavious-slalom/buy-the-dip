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
