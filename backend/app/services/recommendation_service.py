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


def _new_anthropic() -> AsyncAnthropic:
    api_key = (settings.anthropic_api_key or "").strip()
    if api_key:
        return AsyncAnthropic(api_key=api_key)
    return AsyncAnthropic()


_anthropic: AsyncAnthropic = _new_anthropic()


def _parse_card_json(text: str) -> dict:
    """Strict parse + shape validation. Raises ValueError if invalid."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    obj = json.loads(cleaned)
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    if obj.get("bias") not in ("bullish", "bearish", "neutral"):
        raise ValueError("bad bias")
    conf = obj.get("confidence")
    if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        raise ValueError("bad confidence")
    if not isinstance(obj.get("rationale"), str):
        raise ValueError("bad rationale")
    headlines = obj.get("top_headlines")
    if not isinstance(headlines, list) or not all(isinstance(h, str) for h in headlines):
        raise ValueError("bad top_headlines")
    return obj


def _resolve_headlines(model_headlines: list[str], news_items: list[dict]) -> list[dict]:
    """Match model-returned headline strings back to {headline, url} via the news items."""
    by_text = {i["headline"]: i for i in news_items}
    out = []
    for h in model_headlines[:3]:
        item = by_text.get(h)
        if item:
            out.append({"headline": item["headline"], "url": item["url"]})
    return out


async def generate_one(symbol: str, source: str) -> dict:
    """Per-ticker mini-agent. Returns a recommendation card or raises MalformedRecommendationError."""
    loop = asyncio.get_running_loop()
    quote = await loop.run_in_executor(None, alpaca_service.get_quote, symbol)
    news = await loop.run_in_executor(None, news_service.get_news, symbol)
    items = news.get("items") or []
    user_msg = recommendation_prompt.build_user_message(
        symbol=symbol, quote_price=float(quote.get("price") or 0.0), news_items=items
    )
    messages = [{"role": "user", "content": user_msg}]

    async def call(messages_arg: list[dict]) -> str:
        resp = await _anthropic.messages.create(
            model=settings.anthropic_haiku_model,
            max_tokens=400,
            system=recommendation_prompt.SYSTEM_PROMPT,
            messages=messages_arg,
        )
        return resp.content[0].text if resp.content else ""

    raw = await call(messages)
    try:
        parsed = _parse_card_json(raw)
    except (ValueError, json.JSONDecodeError):
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": recommendation_prompt.build_strict_retry_message()},
        ]
        raw2 = await call(retry_messages)
        try:
            parsed = _parse_card_json(raw2)
        except (ValueError, json.JSONDecodeError) as e:
            raise MalformedRecommendationError(f"unparseable_response: {e}")

    return {
        "symbol": symbol,
        "source": source,
        "bias": parsed["bias"],
        "confidence": round(float(parsed["confidence"]), 2),
        "rationale": parsed["rationale"][:280],
        "top_headlines": _resolve_headlines(parsed["top_headlines"], items),
    }
