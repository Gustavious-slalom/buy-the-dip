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


def _evt(type_: str, data: dict | None = None) -> dict:
    return {
        "type": type_,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }


async def generate_all(emit: Callable[[dict], Awaitable[None]]) -> dict:
    """Orchestrate discovery + market brief + per-ticker generation, streaming each event via emit(). Returns the persisted payload."""
    candidates = discover_candidates()
    await emit(_evt("recommendation.discovery", {"sources": candidates.to_dict()}))
    if candidates.discovery_error:
        await emit(_evt("recommendation.discovery_warning", {"message": candidates.discovery_error}))

    brief = await generate_market_brief()
    if brief is not None:
        await emit(_evt("recommendation.market_brief", brief))
    else:
        await emit(_evt("recommendation.market_brief_warning", {"message": "market_brief_unavailable"}))

    pairs = candidates.all_with_source()
    if not pairs:
        await emit(_evt("recommendation.discovery_warning", {"message": "no_candidates"}))
        run_id = str(uuid.uuid4())
        generated_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "run_id": run_id,
            "generated_at": generated_at,
            "cards": [],
            "sources": candidates.to_dict(),
            "market_brief": brief,
        }
        with get_session() as s:
            s.add(RecommendationRun(id=run_id, payload_json=json.dumps(payload)))
            s.commit()
        await emit(_evt("recommendation.complete", {"run_id": run_id, "generated_at": generated_at, "count": 0}))
        return payload

    semaphore = asyncio.Semaphore(PARALLEL_LIMIT)

    async def _bounded(symbol: str, source: str) -> dict:
        async with semaphore:
            try:
                return await generate_one(symbol, source)
            except MalformedRecommendationError:
                return {"symbol": symbol, "source": source, "error": "unparseable_response"}
            except Exception as e:
                return {"symbol": symbol, "source": source, "error": str(e)[:80] or "unknown_error"}

    tasks = [asyncio.create_task(_bounded(sym, src)) for sym, src in pairs]
    cards: list[dict] = []
    for coro in asyncio.as_completed(tasks):
        card = await coro
        cards.append(card)
        await emit(_evt("recommendation.card", card))

    run_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "cards": cards,
        "sources": candidates.to_dict(),
        "market_brief": brief,
    }
    with get_session() as s:
        s.add(RecommendationRun(id=run_id, payload_json=json.dumps(payload)))
        s.commit()
    await emit(_evt("recommendation.complete", {"run_id": run_id, "generated_at": generated_at, "count": len(cards)}))
    return payload


def get_latest_run() -> dict | None:
    with get_session() as s:
        row = s.exec(
            select(RecommendationRun).order_by(RecommendationRun.created_at.desc()).limit(1)
        ).first()
        if row is None:
            return None
        payload = json.loads(row.payload_json)
        payload.setdefault("run_id", row.id)
        return payload


INDEX_SYMBOLS = ["SPY", "QQQ", "IWM"]


def _parse_brief_json(text: str) -> dict:
    """Strict parse + shape validation for the market brief. Raises ValueError if invalid."""
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
    headline = obj.get("headline")
    if not isinstance(headline, str) or not headline.strip():
        raise ValueError("bad headline")
    drivers = obj.get("drivers")
    if not isinstance(drivers, list) or len(drivers) > 3:
        raise ValueError("bad drivers")
    if not all(isinstance(d, str) for d in drivers):
        raise ValueError("bad drivers")
    return obj


async def generate_market_brief() -> dict | None:
    """Returns {bias, headline, drivers, updated_at} or None on any failure or empty inputs."""
    loop = asyncio.get_running_loop()
    try:
        quotes = await loop.run_in_executor(None, alpaca_service.get_latest_prices, INDEX_SYMBOLS)
    except Exception:
        quotes = {s: None for s in INDEX_SYMBOLS}
    try:
        news = await loop.run_in_executor(None, news_service.get_general_news)
    except Exception:
        news = []

    have_quote = any(quotes.get(s) is not None for s in INDEX_SYMBOLS)
    have_news = bool(news)
    if not have_quote and not have_news:
        return None

    user_msg = recommendation_prompt.build_market_brief_user_message(
        index_quotes=quotes, news_items=news
    )
    messages = [{"role": "user", "content": user_msg}]

    async def call(messages_arg: list[dict]) -> str:
        try:
            resp = await _anthropic.messages.create(
                model=settings.anthropic_haiku_model,
                max_tokens=300,
                system=recommendation_prompt.MARKET_BRIEF_SYSTEM_PROMPT,
                messages=messages_arg,
            )
            return resp.content[0].text if resp.content else ""
        except Exception:
            return ""

    raw = await call(messages)
    if not raw:
        return None
    try:
        parsed = _parse_brief_json(raw)
    except (ValueError, json.JSONDecodeError):
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": recommendation_prompt.build_strict_retry_message()},
        ]
        raw2 = await call(retry_messages)
        if not raw2:
            return None
        try:
            parsed = _parse_brief_json(raw2)
        except (ValueError, json.JSONDecodeError):
            return None

    headline = parsed["headline"][:100]
    drivers = [d[:60] for d in parsed["drivers"][:3]]
    return {
        "bias": parsed["bias"],
        "headline": headline,
        "drivers": drivers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
