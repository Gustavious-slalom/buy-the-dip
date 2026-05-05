"""Hot-news recommendation orchestration: discover candidates, generate per-ticker ideas, persist runs."""
from __future__ import annotations
import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from anthropic import AsyncAnthropic
from sqlmodel import select

from app.config import settings
from app.db import get_session
from app.models import RecommendationRun, Watchlist
from app.services import alpaca_service, news_service
from app.agent import recommendation_prompt

DISCOVER_CAP = 5
PARALLEL_LIMIT = 8

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


class MalformedRecommendationError(Exception):
    pass


@dataclass
class CandidateSet:
    watchlist: list[str] = field(default_factory=list)
    positions: list[str] = field(default_factory=list)
    discover: list[str] = field(default_factory=list)
    discovery_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "watchlist": list(self.watchlist),
            "positions": list(self.positions),
            "discover": list(self.discover),
        }

    def all_with_source(self) -> list[tuple[str, str]]:
        return (
            [(t, "watchlist") for t in self.watchlist]
            + [(t, "positions") for t in self.positions]
            + [(t, "discover") for t in self.discover]
        )


def _option_underlying(symbol: str) -> str:
    """Collapse OCC option symbol to underlying ticker. Returns symbol unchanged for stocks."""
    if len(symbol) >= 15 and symbol[-9] in ("C", "P"):
        return symbol[:-15]
    return symbol


def discover_candidates() -> CandidateSet:
    """Gather tickers from watchlist + held positions + market-wide news, deduped with priority watchlist > positions > discover."""
    cs = CandidateSet()
    seen: set[str] = set()

    with get_session() as s:
        rows = s.exec(select(Watchlist)).all()
        for w in rows:
            t = w.ticker.upper()
            if t and t not in seen:
                cs.watchlist.append(t)
                seen.add(t)

    try:
        raw = alpaca_service.get_positions()
    except Exception:
        raw = []
    for p in raw:
        if float(p.get("qty") or 0) == 0:
            continue
        t = _option_underlying(p["symbol"]).upper()
        if t and t not in seen:
            cs.positions.append(t)
            seen.add(t)

    try:
        items = news_service.get_general_news()
    except Exception:
        cs.discovery_error = "general_news_unavailable"
        return cs

    for item in items:
        if len(cs.discover) >= DISCOVER_CAP:
            break
        related = item.get("related") or ""
        for raw_t in related.split(","):
            t = raw_t.strip().upper()
            if not t or not _TICKER_RE.match(t):
                continue
            if t in seen:
                continue
            cs.discover.append(t)
            seen.add(t)
            if len(cs.discover) >= DISCOVER_CAP:
                break

    return cs
