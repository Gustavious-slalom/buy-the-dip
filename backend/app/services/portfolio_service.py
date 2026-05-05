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
