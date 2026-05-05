# Hot-News Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/recommendations` screen that produces a ranked list of lightweight trade ideas based on hot news. Each card surfaces a ticker, directional bias, confidence, rationale, and 1–3 driving headlines. Clicking a card jumps to the existing `/` agent flow with the ticker pre-filled and auto-submitted.

**Architecture:** A new backend service runs per-ticker mini-agents (Haiku) in parallel for candidates discovered from watchlist + held positions + market-wide news. Cards stream over the existing `/ws` WebSocket as each agent finishes. Each run is persisted; the page loads the most recent run on mount and offers a Generate button to refresh.

**Tech Stack:** Python 3.11 / FastAPI / SQLModel / pytest / Anthropic SDK / Finnhub (backend); Next.js App Router / TypeScript / Tailwind (frontend).

**Spec reference:** `docs/superpowers/specs/2026-05-05-hot-news-recommendations-design.md`

---

## File Structure

### New backend files
- `backend/app/agent/recommendation_prompt.py` — per-ticker prompt builder (constants + small functions only)
- `backend/app/services/recommendation_service.py` — discovery, generation, orchestration, persistence
- `backend/tests/test_recommendation_service.py` — unit tests for the service
- `backend/tests/test_recommendation_api.py` — REST + WS endpoint tests
- `backend/tests/fixtures/general_news.json` — canned market-wide news payload
- `backend/tests/fixtures/recommendation_response.json` — canned Claude JSON response

### Modified backend files
- `backend/app/models.py` — add `RecommendationRun`
- `backend/app/services/news_service.py` — add `get_general_news()`
- `backend/app/api/http.py` — add `GET /recommendations/latest`
- `backend/app/api/ws.py` — handle `recommendation.start`
- `README.md` — add new endpoints to API table

### New frontend files
- `frontend/src/types/recommendations.ts` — shared TypeScript types
- `frontend/src/lib/recommendations-ws.ts` — typed WS hook for the recommendation stream
- `frontend/src/app/recommendations/page.tsx` — route shell
- `frontend/src/components/recommendations/recommendations-view.tsx` — container, owns state
- `frontend/src/components/recommendations/recommendation-card.tsx` — single card
- `frontend/src/components/recommendations/sources-strip.tsx` — top sources strip

### Modified frontend files
- `frontend/src/lib/api.ts` — add `getLatestRecommendations()`
- `frontend/src/components/status-rail.tsx` — add IDEAS nav link
- `frontend/src/components/ticker-input.tsx` — read `?ticker=…&autosubmit=1` and prefill+autosubmit

---

## Phase 1 — Backend foundations

### Task 1: `RecommendationRun` model

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_models.py`:

```python
def test_recommendation_run_roundtrip(db_session):
    from app.models import RecommendationRun
    import uuid, json
    r = RecommendationRun(
        id=str(uuid.uuid4()),
        payload_json=json.dumps({"cards": [], "sources": {"watchlist": [], "positions": [], "discover": []}}),
    )
    db_session.add(r); db_session.commit(); db_session.refresh(r)
    assert r.id is not None
    assert r.created_at is not None
    assert json.loads(r.payload_json)["cards"] == []
```

- [ ] **Step 2: Run test, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_models.py::test_recommendation_run_roundtrip -v`
Expected: FAIL — `ImportError: cannot import name 'RecommendationRun'`

- [ ] **Step 3: Implement**

Append to `backend/app/models.py`:

```python
class RecommendationRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    payload_json: str
```

- [ ] **Step 4: Run test, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_models.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat(backend): RecommendationRun SQLModel table"
```

---

### Task 2: `get_general_news` in news_service

**Files:**
- Modify: `backend/app/services/news_service.py`
- Test: `backend/tests/test_news_service.py`
- New: `backend/tests/fixtures/general_news.json`

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/general_news.json`:

```json
[
  {"headline": "NVDA Q3 beats on data-center growth", "summary": "Nvidia reports record Q3.", "url": "https://example.com/nvda-q3", "datetime": 1714521600, "related": "NVDA"},
  {"headline": "Wall St raises NVDA target to $1,250", "summary": "Several banks lift price target.", "url": "https://example.com/nvda-target", "datetime": 1714525200, "related": "NVDA"},
  {"headline": "TSLA misses Q3 deliveries", "summary": "Below consensus by 5%.", "url": "https://example.com/tsla-deliv", "datetime": 1714528800, "related": "TSLA"},
  {"headline": "AMD launches new datacenter chip", "summary": "Targets enterprise AI workloads.", "url": "https://example.com/amd-mi400", "datetime": 1714532400, "related": "AMD"},
  {"headline": "META announces ad revenue growth", "summary": "Q3 ads up 18% YoY.", "url": "https://example.com/meta-ads", "datetime": 1714536000, "related": "META"},
  {"headline": "Coinbase partners with major bank", "summary": "Custody deal expands footprint.", "url": "https://example.com/coin-bank", "datetime": 1714539600, "related": "COIN"}
]
```

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_news_service.py`:

```python
def test_get_general_news_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import news_service; reload(news_service)
    items = news_service.get_general_news()
    assert isinstance(items, list) and len(items) >= 3
    assert {"headline", "summary", "url", "datetime", "related"}.issubset(items[0].keys())
```

- [ ] **Step 3: Run test, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_news_service.py::test_get_general_news_fixtures_mode -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_general_news'`

- [ ] **Step 4: Implement**

Append to `backend/app/services/news_service.py`:

```python
def get_general_news() -> list[dict]:
    """Market-wide news. Returns up to 30 items with {headline, summary, url, datetime, related}."""
    if settings.fixtures_mode:
        return json.loads((FIXTURES / "general_news.json").read_text())
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    raw = client.general_news("general")[:30]
    return [
        {
            "headline": i["headline"],
            "summary": i.get("summary", ""),
            "url": i["url"],
            "datetime": i["datetime"],
            "related": i.get("related", ""),
        }
        for i in raw
    ]
```

- [ ] **Step 5: Run test, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_news_service.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/news_service.py backend/tests/test_news_service.py backend/tests/fixtures/general_news.json
git commit -m "feat(backend): get_general_news for market-wide discovery"
```

---

### Task 3: Recommendation prompt builder

**Files:**
- Create: `backend/app/agent/recommendation_prompt.py`
- Test: `backend/tests/test_recommendation_service.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_recommendation_service.py`:

```python
import pytest


def test_build_user_message_lists_headlines_and_quote():
    from app.agent.recommendation_prompt import build_user_message
    msg = build_user_message(
        symbol="NVDA",
        quote_price=920.50,
        news_items=[
            {"headline": "NVDA beats Q3", "summary": "Record numbers."},
            {"headline": "Wall St raises target", "summary": "$1,250."},
        ],
    )
    assert "NVDA" in msg
    assert "920.50" in msg
    assert "NVDA beats Q3" in msg
    assert "Wall St raises target" in msg
    # JSON-only instruction
    assert "JSON" in msg


def test_strict_retry_message_explicit():
    from app.agent.recommendation_prompt import build_strict_retry_message
    msg = build_strict_retry_message()
    assert "JSON" in msg
    assert "no markdown" in msg.lower() or "no fences" in msg.lower() or "no code block" in msg.lower()
```

- [ ] **Step 2: Run tests, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.recommendation_prompt'`

- [ ] **Step 3: Implement**

Create `backend/app/agent/recommendation_prompt.py`:

```python
"""Per-ticker recommendation prompt. Strict JSON output."""

SYSTEM_PROMPT = (
    "You are an options-trading copilot generating a one-line recommendation for a single ticker "
    "based on recent news + the latest quote. Respond ONLY with a JSON object. No markdown, no "
    "code fences, no commentary. Schema: "
    '{"bias": "bullish"|"bearish"|"neutral", "confidence": float in [0,1], '
    '"rationale": string up to 280 chars, "top_headlines": array of up to 3 strings each '
    "EXACTLY matching one of the provided headlines}."
)


def build_user_message(symbol: str, quote_price: float, news_items: list[dict]) -> str:
    if not news_items:
        headlines_block = "(no recent news available)"
    else:
        headlines_block = "\n".join(
            f"- {i['headline']}: {(i.get('summary') or '')[:200]}"
            for i in news_items[:8]
        )
    return (
        f"Ticker: {symbol}\n"
        f"Latest mid price: {quote_price:.2f}\n\n"
        f"Recent headlines:\n{headlines_block}\n\n"
        "Output ONLY the JSON object as specified."
    )


def build_strict_retry_message() -> str:
    return (
        "Your previous response was not valid JSON. Respond again with ONLY the JSON object. "
        "No markdown, no code fences, no prose. Schema: "
        '{"bias": "bullish"|"bearish"|"neutral", "confidence": number in [0,1], '
        '"rationale": string, "top_headlines": string[]}.'
    )
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/recommendation_prompt.py backend/tests/test_recommendation_service.py
git commit -m "feat(backend): recommendation_prompt builder + strict retry"
```

---

### Task 4: Candidate discovery

**Files:**
- Create: `backend/app/services/recommendation_service.py`
- Modify: `backend/tests/test_recommendation_service.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_recommendation_service.py`:

```python
def test_discover_candidates_dedup_and_priority(monkeypatch):
    """watchlist > positions > discover; held options collapse to underlying; discover capped at 5."""
    from app.services import recommendation_service, news_service, alpaca_service
    from app.models import Watchlist
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Watchlist(ticker="AAPL"))
        s.add(Watchlist(ticker="NVDA"))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses

    monkeypatch.setattr(recommendation_service, "get_session", fake_session)
    # Positions: TSLA stock + an NVDA option (collapses to underlying NVDA, already in watchlist → drop)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "TSLA", "qty": 10.0, "avg_entry_price": 220.0},
        {"symbol": "NVDA260619C00800000", "qty": 1.0, "avg_entry_price": 12.40},
    ])
    # Discover: many tickers; AAPL/TSLA already covered; expect cap at 5 from remainder.
    monkeypatch.setattr(news_service, "get_general_news", lambda: [
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "AMD"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "META"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "GOOG"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "COIN"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "AVGO"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "QQQ"},
        # Already in watchlist, must be deduped:
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "AAPL"},
        # Already in positions, must be deduped:
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "TSLA"},
    ])
    cs = recommendation_service.discover_candidates()
    assert sorted(cs.watchlist) == ["AAPL", "NVDA"]
    assert cs.positions == ["TSLA"]  # NVDA option collapsed but already in watchlist
    assert len(cs.discover) == 5  # cap
    # Discover must not contain anything already in watchlist or positions:
    overlap = (set(cs.discover) & set(cs.watchlist)) | (set(cs.discover) & set(cs.positions))
    assert overlap == set()


def test_discover_candidates_handles_general_news_failure(monkeypatch):
    """Discovery falls back gracefully if general_news raises."""
    from app.services import recommendation_service, news_service, alpaca_service
    from app.models import Watchlist
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Watchlist(ticker="AAPL"))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])

    def boom():
        raise RuntimeError("finnhub down")
    monkeypatch.setattr(news_service, "get_general_news", boom)

    cs = recommendation_service.discover_candidates()
    assert cs.watchlist == ["AAPL"]
    assert cs.positions == []
    assert cs.discover == []
    assert cs.discovery_error == "general_news_unavailable"
```

- [ ] **Step 2: Run tests, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py::test_discover_candidates_dedup_and_priority -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.recommendation_service'`

- [ ] **Step 3: Implement**

Create `backend/app/services/recommendation_service.py`:

```python
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

# Ticker-shape regex used to filter `related` field values (Finnhub sometimes returns junk).
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

    # Watchlist
    with get_session() as s:
        rows = s.exec(select(Watchlist)).all()
        for w in rows:
            t = w.ticker.upper()
            if t and t not in seen:
                cs.watchlist.append(t)
                seen.add(t)

    # Positions (collapse options to underlying, dedup)
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

    # Discover via market-wide news `related` field
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
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "feat(backend): discover_candidates with watchlist/positions/discover priority"
```

---

### Task 5: `generate_one` per-ticker mini-agent

**Files:**
- Modify: `backend/app/services/recommendation_service.py`
- Modify: `backend/tests/test_recommendation_service.py`
- New: `backend/tests/fixtures/recommendation_response.json`

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/recommendation_response.json`:

```json
{
  "bias": "bullish",
  "confidence": 0.72,
  "rationale": "Earnings beat plus record data-center revenue; sell-side raises targets.",
  "top_headlines": ["NVDA Q3 beats on data-center growth", "Wall St raises NVDA target to $1,250"]
}
```

- [ ] **Step 2: Write failing tests**

Append to `backend/tests/test_recommendation_service.py`:

```python
import json as _json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _stub_anthropic_response(text: str):
    """Return an object that mimics the .messages.create() response."""
    class Block:
        def __init__(self, t): self.text = t
        type = "text"
    class Msg:
        def __init__(self, t): self.content = [Block(t)]
    async def acreate(**kwargs):
        return Msg(text)
    return acreate


@pytest.mark.asyncio
async def test_generate_one_happy_path(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    canned = (FIXTURES_DIR / "recommendation_response.json").read_text()
    monkeypatch.setattr(alpaca_service, "get_quote", lambda sym: {"symbol": sym, "price": 920.5, "bid": 920.4, "ask": 920.6, "ts": "2026-05-05T14:00:00Z"})
    monkeypatch.setattr(news_service, "get_news", lambda sym, since_days=7: {
        "symbol": sym,
        "items": [
            {"headline": "NVDA Q3 beats on data-center growth", "summary": "Record numbers.", "url": "https://example.com/a", "datetime": 1},
            {"headline": "Wall St raises NVDA target to $1,250", "summary": "Analysts bullish.", "url": "https://example.com/b", "datetime": 2},
        ],
        "summary": "",
    })

    captured = []
    class FakeMessages:
        async def create(self, **kwargs):
            captured.append(kwargs)
            class Block:
                text = canned
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    card = await recommendation_service.generate_one("NVDA", "watchlist")
    assert card["symbol"] == "NVDA"
    assert card["source"] == "watchlist"
    assert card["bias"] == "bullish"
    assert 0 <= card["confidence"] <= 1
    assert len(card["rationale"]) <= 280
    assert len(card["top_headlines"]) == 2
    assert card["top_headlines"][0]["url"] == "https://example.com/a"
    assert "error" not in card
    # Only one model call needed:
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_generate_one_retries_on_malformed(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_quote", lambda sym: {"symbol": sym, "price": 100.0, "bid": 100, "ask": 100, "ts": "x"})
    monkeypatch.setattr(news_service, "get_news", lambda sym, since_days=7: {"symbol": sym, "items": [{"headline": "X", "summary": "", "url": "u", "datetime": 1}], "summary": ""})

    canned = (FIXTURES_DIR / "recommendation_response.json").read_text()
    call_count = {"n": 0}
    class FakeMessages:
        async def create(self, **kwargs):
            call_count["n"] += 1
            class Block:
                text = "this is not json" if call_count["n"] == 1 else canned
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    card = await recommendation_service.generate_one("AAPL", "watchlist")
    assert call_count["n"] == 2
    assert card["bias"] == "bullish"


@pytest.mark.asyncio
async def test_generate_one_persistent_failure_raises(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_quote", lambda sym: {"symbol": sym, "price": 100.0, "bid": 100, "ask": 100, "ts": "x"})
    monkeypatch.setattr(news_service, "get_news", lambda sym, since_days=7: {"symbol": sym, "items": [], "summary": ""})

    class FakeMessages:
        async def create(self, **kwargs):
            class Block:
                text = "still not json"
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    with pytest.raises(recommendation_service.MalformedRecommendationError):
        await recommendation_service.generate_one("AAPL", "watchlist")
```

- [ ] **Step 3: Run tests, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v -k generate_one`
Expected: FAIL — `AttributeError: module ... has no attribute '_anthropic'` or `'generate_one'`.

- [ ] **Step 4: Implement**

In `backend/app/services/recommendation_service.py`, add module-level Anthropic client and the `generate_one` function (append after `discover_candidates`):

```python
def _new_anthropic() -> AsyncAnthropic:
    api_key = (settings.anthropic_api_key or "").strip()
    if api_key:
        return AsyncAnthropic(api_key=api_key)
    return AsyncAnthropic()


_anthropic: AsyncAnthropic = _new_anthropic()


def _parse_card_json(text: str) -> dict:
    """Strict parse + shape validation. Raises ValueError if invalid."""
    cleaned = text.strip()
    # Tolerate fenced code blocks just in case the model still wraps.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # Drop optional language tag on first line
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
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py backend/tests/fixtures/recommendation_response.json
git commit -m "feat(backend): generate_one per-ticker mini-agent + strict JSON retry"
```

---

### Task 6: `generate_all` orchestrator

**Files:**
- Modify: `backend/app/services/recommendation_service.py`
- Modify: `backend/tests/test_recommendation_service.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_recommendation_service.py`:

```python
@pytest.mark.asyncio
async def test_generate_all_streams_and_persists(monkeypatch):
    """Discovery → cards stream in finish order → run is persisted; error cards still flow through."""
    from app.services import recommendation_service
    from app.models import Watchlist, RecommendationRun
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Watchlist(ticker="AAPL"))
        s.add(Watchlist(ticker="NVDA"))
        s.add(Watchlist(ticker="TSLA"))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    # Stub discovery to bypass network entirely
    monkeypatch.setattr(recommendation_service, "discover_candidates", lambda: recommendation_service.CandidateSet(
        watchlist=["AAPL", "NVDA", "TSLA"], positions=[], discover=[],
    ))

    async def fake_generate_one(symbol, source):
        if symbol == "TSLA":
            raise recommendation_service.MalformedRecommendationError("unparseable_response")
        return {
            "symbol": symbol, "source": source, "bias": "bullish",
            "confidence": 0.6, "rationale": f"r-{symbol}", "top_headlines": [],
        }
    monkeypatch.setattr(recommendation_service, "generate_one", fake_generate_one)

    emitted: list[dict] = []
    async def emit(evt: dict):
        emitted.append(evt)

    payload = await recommendation_service.generate_all(emit)

    types = [e["type"] for e in emitted]
    assert types[0] == "recommendation.discovery"
    assert types.count("recommendation.card") == 3
    assert types[-1] == "recommendation.complete"

    # All three cards present in the persisted payload
    assert {c["symbol"] for c in payload["cards"]} == {"AAPL", "NVDA", "TSLA"}
    tsla = next(c for c in payload["cards"] if c["symbol"] == "TSLA")
    assert "error" in tsla and tsla["error"] == "unparseable_response"

    # Persisted to DB
    with Session(engine) as s:
        rows = s.exec(__import__("sqlmodel").select(RecommendationRun)).all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_generate_all_no_candidates_emits_warning(monkeypatch):
    from app.services import recommendation_service
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    monkeypatch.setattr(recommendation_service, "discover_candidates", lambda: recommendation_service.CandidateSet(
        watchlist=[], positions=[], discover=[],
    ))

    emitted: list[dict] = []
    async def emit(evt: dict):
        emitted.append(evt)

    payload = await recommendation_service.generate_all(emit)
    types = [e["type"] for e in emitted]
    assert "recommendation.discovery_warning" in types
    assert types[-1] == "recommendation.complete"
    assert payload["cards"] == []


def test_get_latest_run_returns_most_recent(monkeypatch):
    from app.services import recommendation_service
    from app.models import RecommendationRun
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager
    import time

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(RecommendationRun(id="old", payload_json='{"cards": [], "sources": {"watchlist": [], "positions": [], "discover": []}}'))
        s.commit()
        time.sleep(0.01)
        s.add(RecommendationRun(id="new", payload_json='{"cards": [{"symbol":"NVDA"}], "sources": {"watchlist": [], "positions": [], "discover": []}}'))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    latest = recommendation_service.get_latest_run()
    assert latest is not None
    assert latest["run_id"] == "new"
    assert latest["cards"][0]["symbol"] == "NVDA"


def test_get_latest_run_empty(monkeypatch):
    from app.services import recommendation_service
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    assert recommendation_service.get_latest_run() is None
```

- [ ] **Step 2: Run tests, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v -k "generate_all or get_latest"`
Expected: FAIL — `AttributeError: ... has no attribute 'generate_all'`

- [ ] **Step 3: Implement**

Append to `backend/app/services/recommendation_service.py`:

```python
def _evt(type_: str, data: dict | None = None) -> dict:
    return {
        "type": type_,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }


async def generate_all(emit: Callable[[dict], Awaitable[None]]) -> dict:
    """Orchestrate discovery + per-ticker generation, streaming each event via emit(). Returns the persisted payload."""
    candidates = discover_candidates()
    await emit(_evt("recommendation.discovery", {"sources": candidates.to_dict()}))
    if candidates.discovery_error:
        await emit(_evt("recommendation.discovery_warning", {"message": candidates.discovery_error}))

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
            except MalformedRecommendationError as e:
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
        return json.loads(row.payload_json)
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_service.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "feat(backend): generate_all orchestrator + get_latest_run"
```

---

## Phase 2 — Backend HTTP + WS wiring

### Task 7: `GET /recommendations/latest` endpoint

**Files:**
- Modify: `backend/app/api/http.py`
- Create: `backend/tests/test_recommendation_api.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_recommendation_api.py`:

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import news_service; reload(news_service)
    from app.services import recommendation_service; reload(recommendation_service)
    from app.api import http as http_module; reload(http_module)
    from app.api import ws as ws_module; reload(ws_module)
    from app import main; reload(main)
    return TestClient(main.app)


def test_recommendations_latest_empty(client, monkeypatch):
    from app.services import recommendation_service
    monkeypatch.setattr(recommendation_service, "get_latest_run", lambda: None)
    r = client.get("/recommendations/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] is None
    assert body["generated_at"] is None
    assert body["cards"] == []
    assert body["sources"] == {"watchlist": [], "positions": [], "discover": []}


def test_recommendations_latest_returns_persisted(client, monkeypatch):
    from app.services import recommendation_service
    canned = {
        "run_id": "abc",
        "generated_at": "2026-05-05T14:02:31+00:00",
        "cards": [{"symbol": "NVDA", "source": "watchlist", "bias": "bullish", "confidence": 0.7, "rationale": "x", "top_headlines": []}],
        "sources": {"watchlist": ["NVDA"], "positions": [], "discover": []},
    }
    monkeypatch.setattr(recommendation_service, "get_latest_run", lambda: canned)
    r = client.get("/recommendations/latest")
    assert r.status_code == 200
    assert r.json() == canned
```

- [ ] **Step 2: Run tests, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_api.py -v`
Expected: FAIL — 404 on the endpoint.

- [ ] **Step 3: Implement**

In `backend/app/api/http.py`, add to the existing import block at the top:

```python
from app.services import recommendation_service
```

Append at the bottom of the file:

```python
@router.get("/recommendations/latest")
def recommendations_latest():
    latest = recommendation_service.get_latest_run()
    if latest is None:
        return {
            "run_id": None,
            "generated_at": None,
            "cards": [],
            "sources": {"watchlist": [], "positions": [], "discover": []},
        }
    return latest
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_api.py -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/http.py backend/tests/test_recommendation_api.py
git commit -m "feat(backend): GET /recommendations/latest endpoint"
```

---

### Task 8: WebSocket `recommendation.start` handler

**Files:**
- Modify: `backend/app/api/ws.py`
- Modify: `backend/tests/test_recommendation_api.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_recommendation_api.py`:

```python
def test_ws_recommendation_start_flow(client, monkeypatch):
    """WS receives discovery → 2 cards (in finish order) → complete after recommendation.start."""
    from app.services import recommendation_service

    async def fake_generate_all(emit):
        await emit({"type": "recommendation.discovery", "ts": "t", "data": {"sources": {"watchlist": ["AAPL", "NVDA"], "positions": [], "discover": []}}})
        await emit({"type": "recommendation.card", "ts": "t", "data": {"symbol": "AAPL", "source": "watchlist", "bias": "bullish", "confidence": 0.6, "rationale": "r", "top_headlines": []}})
        await emit({"type": "recommendation.card", "ts": "t", "data": {"symbol": "NVDA", "source": "watchlist", "bias": "bullish", "confidence": 0.7, "rationale": "r", "top_headlines": []}})
        await emit({"type": "recommendation.complete", "ts": "t", "data": {"run_id": "rid", "generated_at": "2026-05-05T14:02:31Z", "count": 2}})
        return {"run_id": "rid", "generated_at": "2026-05-05T14:02:31Z", "cards": [], "sources": {"watchlist": [], "positions": [], "discover": []}}

    monkeypatch.setattr(recommendation_service, "generate_all", fake_generate_all)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "recommendation.start"})
        msgs = [ws.receive_json() for _ in range(4)]
    types = [m["type"] for m in msgs]
    assert types == [
        "recommendation.discovery",
        "recommendation.card",
        "recommendation.card",
        "recommendation.complete",
    ]
```

- [ ] **Step 2: Run test, confirm fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_api.py::test_ws_recommendation_start_flow -v`
Expected: FAIL — the handler doesn't recognize `recommendation.start` so nothing is sent (test will time out or the subsequent `receive_json` will hang). If pytest hangs, kill with Ctrl-C and confirm message routing is missing.

- [ ] **Step 3: Implement**

In `backend/app/api/ws.py`, add to the imports at the top:

```python
from app.services import recommendation_service
```

Inside the existing `while True:` dispatch chain, add a new branch AFTER the `if data.get("type") == "session.start":` block and BEFORE `elif data.get("type") == "replay":`:

```python
                elif data.get("type") == "recommendation.start":
                    try:
                        await recommendation_service.generate_all(emit)
                    except Exception as e:
                        await ws.send_text(json.dumps({"type": "recommendation.error", "data": {"message": str(e)}}))
```

NOTE: the existing `emit` helper writes a `Trace` row. For recommendation events we want them traceable just like agent events — leave `emit` as-is. The Trace rows will have `event_type` like `recommendation.discovery` etc. which is fine.

- [ ] **Step 4: Run test, confirm pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_recommendation_api.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Expected: ALL PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/ws.py backend/tests/test_recommendation_api.py
git commit -m "feat(backend): WS recommendation.start triggers generate_all stream"
```

---

## Phase 3 — Frontend foundation

### Task 9: Recommendation TypeScript types

**Files:**
- Create: `frontend/src/types/recommendations.ts`

- [ ] **Step 1: Create the file**

Create `frontend/src/types/recommendations.ts`:

```typescript
export type Bias = "bullish" | "bearish" | "neutral";
export type Source = "watchlist" | "positions" | "discover";

export type Headline = { headline: string; url: string };

export type RecommendationCard = {
  symbol: string;
  source: Source;
  bias: Bias;
  confidence: number;
  rationale: string;
  top_headlines: Headline[];
  error?: string;
};

export type CandidateSet = {
  watchlist: string[];
  positions: string[];
  discover: string[];
};

export type RecommendationRun = {
  run_id: string | null;
  generated_at: string | null;
  cards: RecommendationCard[];
  sources: CandidateSet;
};

export type StreamEvent =
  | { type: "recommendation.discovery"; ts?: string; data: { sources: CandidateSet } }
  | { type: "recommendation.card"; ts?: string; data: RecommendationCard }
  | { type: "recommendation.complete"; ts?: string; data: { run_id: string; generated_at: string; count: number } }
  | { type: "recommendation.discovery_warning"; ts?: string; data: { message: string } }
  | { type: "recommendation.error"; ts?: string; data: { message: string } }
  | { type: "error"; ts?: string; data: { message: string } };
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/recommendations.ts
git commit -m "feat(frontend): recommendation TypeScript types"
```

---

### Task 10: API client + WS hook for recommendations

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/recommendations-ws.ts`

- [ ] **Step 1: Add the API method**

In `frontend/src/lib/api.ts`, at the top of the imports, add the `RecommendationRun` import (alongside the existing portfolio types import):

```typescript
import type { RecommendationRun } from "@/types/recommendations";
```

Append at the bottom of the file:

```typescript
export async function getLatestRecommendations(): Promise<RecommendationRun> {
  const r = await fetch(`${BASE}/recommendations/latest`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
```

- [ ] **Step 2: Create the WS hook**

Create `frontend/src/lib/recommendations-ws.ts`:

```typescript
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { RecommendationCard, CandidateSet, StreamEvent } from "@/types/recommendations";

export type RecommendationsStatus = "idle" | "connecting" | "running" | "done" | "error";

export type RecommendationsState = {
  status: RecommendationsStatus;
  sources: CandidateSet | null;
  cards: RecommendationCard[];
  runId: string | null;
  generatedAt: string | null;
  warning: string | null;
  errorMessage: string | null;
  expectedCount: number;
};

const initial: RecommendationsState = {
  status: "idle",
  sources: null,
  cards: [],
  runId: null,
  generatedAt: null,
  warning: null,
  errorMessage: null,
  expectedCount: 0,
};

export function useRecommendationsStream() {
  const [state, setState] = useState<RecommendationsState>(initial);
  const ws = useRef<WebSocket | null>(null);

  const close = useCallback(() => {
    ws.current?.close();
    ws.current = null;
  }, []);

  useEffect(() => () => close(), [close]);

  const start = useCallback(() => {
    close();
    setState({ ...initial, status: "connecting" });

    const url = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      setState(s => ({ ...s, status: "running" }));
      socket.send(JSON.stringify({ type: "recommendation.start" }));
    };

    socket.onmessage = (m) => {
      let evt: StreamEvent;
      try {
        evt = JSON.parse(m.data) as StreamEvent;
      } catch {
        return;
      }
      setState(prev => {
        switch (evt.type) {
          case "recommendation.discovery": {
            const sources = evt.data.sources;
            const expected = sources.watchlist.length + sources.positions.length + sources.discover.length;
            return { ...prev, sources, expectedCount: expected };
          }
          case "recommendation.card":
            return { ...prev, cards: [...prev.cards, evt.data] };
          case "recommendation.discovery_warning":
            return { ...prev, warning: evt.data.message };
          case "recommendation.complete":
            return {
              ...prev,
              status: "done",
              runId: evt.data.run_id,
              generatedAt: evt.data.generated_at,
            };
          case "recommendation.error":
          case "error":
            return { ...prev, status: "error", errorMessage: evt.data.message };
          default:
            return prev;
        }
      });
    };

    socket.onerror = () => {
      setState(s => ({ ...s, status: "error", errorMessage: "WebSocket error" }));
    };

    socket.onclose = () => {
      setState(s => (s.status === "running" ? { ...s, status: "error", errorMessage: "stream interrupted" } : s));
      ws.current = null;
    };
  }, [close]);

  const reset = useCallback(() => setState(initial), []);

  return { state, start, reset };
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/recommendations-ws.ts
git commit -m "feat(frontend): getLatestRecommendations + useRecommendationsStream hook"
```

---

### Task 11: TickerInput auto-submit from search params

**Files:**
- Modify: `frontend/src/components/ticker-input.tsx`

- [ ] **Step 1: Modify the component**

Replace the entire contents of `frontend/src/components/ticker-input.tsx` with:

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useSession } from "@/lib/session-context";

export function TickerInput() {
  const { sendIdea, sendReplay, status } = useSession();
  const [v, setV] = useState("AAPL");
  const running = status === "running";
  const searchParams = useSearchParams();
  const autoSubmittedRef = useRef(false);

  useEffect(() => {
    if (autoSubmittedRef.current) return;
    const ticker = searchParams?.get("ticker");
    if (!ticker) return;
    const sym = ticker.toUpperCase().trim();
    if (!sym) return;
    setV(sym);
    if (searchParams?.get("autosubmit") === "1") {
      autoSubmittedRef.current = true;
      sendIdea(sym);
    }
  }, [searchParams, sendIdea]);

  return (
    <section className="px-4 py-5 border-b border-[color:var(--hairline)]">
      <h3 className="smallcaps panel-rule mb-4">Symbol</h3>

      <label
        className="flex items-center gap-2 px-3 py-2.5 bg-[color:var(--ink-2)] border border-[color:var(--hairline-2)] focus-within:border-[color:var(--signal)] transition-colors"
      >
        <span className="font-mono text-[color:var(--fg-mute)]">$</span>
        <input
          value={v}
          onChange={e => setV(e.target.value.toUpperCase())}
          placeholder="AAPL"
          className="flex-1 bg-transparent outline-none border-0 font-mono text-[18px] tracking-[.05em] uppercase placeholder:text-[color:var(--fg-mute)]"
          onKeyDown={(e) => { if (e.key === "Enter" && !running && v.trim()) sendIdea(v.trim()); }}
        />
        <span className="caret" />
      </label>

      <div className="flex gap-2 mt-3">
        <button
          disabled={running || !v.trim()}
          onClick={() => sendIdea(v.trim())}
          className="flex-1 py-2.5 text-[11px] font-bold tracking-[.22em] uppercase bg-[color:var(--signal)] text-[color:var(--ink)] disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-[0_0_24px_rgba(198,255,59,.30)] transition-shadow"
        >
          {running ? "Thinking…" : "Analyze ▸"}
        </button>
        <button
          disabled={running}
          onClick={() => sendReplay()}
          className="px-3 py-2.5 text-[11px] tracking-[.22em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--fg-dim)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Replay last session"
        >
          Replay
        </button>
      </div>

      <div className="mt-4 grid grid-cols-[1fr_auto] gap-y-1.5 text-[12px]">
        <span className="smallcaps">Status</span>
        <span className="num text-[color:var(--fg)]">
          {status}
        </span>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Typecheck and build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ticker-input.tsx
git commit -m "feat(frontend): TickerInput auto-submit from ?ticker= search param"
```

---

## Phase 4 — Frontend components

### Task 12: RecommendationCard component

**Files:**
- Create: `frontend/src/components/recommendations/recommendation-card.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/recommendations/recommendation-card.tsx`:

```tsx
"use client";
import Link from "next/link";
import type { RecommendationCard as Card } from "@/types/recommendations";

const BIAS_COLOR: Record<string, string> = {
  bullish: "var(--up)",
  bearish: "var(--down)",
  neutral: "var(--fg-dim)",
};

const SOURCE_LABEL: Record<string, string> = {
  watchlist: "from watchlist",
  positions: "from positions",
  discover: "from discover",
};

function ConfidenceBar({ value }: { value: number }) {
  const filled = Math.max(0, Math.min(10, Math.round(value * 10)));
  const segments = Array.from({ length: 10 }, (_, i) => i < filled);
  return (
    <span className="inline-flex gap-[2px] align-middle">
      {segments.map((on, i) => (
        <span
          key={i}
          className="block"
          style={{ width: 7, height: 9, background: on ? "var(--signal)" : "var(--ink-3)" }}
        />
      ))}
    </span>
  );
}

export function RecommendationCard({ card }: { card: Card }) {
  if (card.error) {
    return (
      <li className="px-5 py-4 border-b border-[color:var(--hairline)] flex items-center gap-3">
        <span className="font-mono text-[14px] text-[color:var(--down)]">⚠ {card.symbol}</span>
        <span className="text-[12px] text-[color:var(--fg-dim)]">
          couldn’t analyze — {card.error}
        </span>
      </li>
    );
  }
  const biasColor = BIAS_COLOR[card.bias] ?? "var(--fg-dim)";
  return (
    <li className="px-5 py-4 border-b border-[color:var(--hairline)]">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-mono text-[18px] tracking-[.04em]">{card.symbol}</span>
        <span
          className="font-mono text-[10.5px] tracking-[.22em] px-2 py-[3px]"
          style={{ background: biasColor, color: "var(--ink)", fontWeight: 700 }}
        >
          {card.bias.toUpperCase()}
        </span>
        <ConfidenceBar value={card.confidence} />
        <span className="num text-[12px] text-[color:var(--fg-dim)]">{card.confidence.toFixed(2)}</span>
        <span className="text-[11px] text-[color:var(--fg-mute)] ml-auto">{SOURCE_LABEL[card.source] ?? card.source}</span>
      </div>

      <p className="text-[13px] text-[color:var(--fg)] mt-3 leading-[1.55]">{card.rationale}</p>

      {card.top_headlines.length > 0 && (
        <ul className="mt-2 text-[11.5px] font-mono text-[color:var(--fg-mute)] space-y-1">
          {card.top_headlines.map((h, i) => (
            <li key={i}>
              •{" "}
              <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-[color:var(--signal)] underline-offset-2 hover:underline">
                {h.headline}
              </a>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3">
        <Link
          href={`/?ticker=${encodeURIComponent(card.symbol)}&autosubmit=1`}
          className="inline-block px-4 py-2 text-[11px] tracking-[.22em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] transition-colors"
        >
          Analyze →
        </Link>
      </div>
    </li>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recommendations/recommendation-card.tsx
git commit -m "feat(frontend): RecommendationCard component"
```

---

### Task 13: SourcesStrip component

**Files:**
- Create: `frontend/src/components/recommendations/sources-strip.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/recommendations/sources-strip.tsx`:

```tsx
"use client";
import type { CandidateSet } from "@/types/recommendations";

function Bucket({ label, tickers }: { label: string; tickers: string[] }) {
  if (tickers.length === 0) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className="smallcaps">{label}</span>
      <span className="font-mono text-[12px] text-[color:var(--fg-dim)]">{tickers.join(", ")}</span>
    </div>
  );
}

export function SourcesStrip({ sources }: { sources: CandidateSet | null }) {
  if (!sources) return null;
  const total = sources.watchlist.length + sources.positions.length + sources.discover.length;
  return (
    <section className="px-5 py-3 border-b border-[color:var(--hairline)]">
      <h3 className="smallcaps panel-rule mb-2">
        Sources
        <span className="num normal-case tracking-normal text-[11px] text-[color:var(--fg-dim)] ml-2">
          {total} candidate{total === 1 ? "" : "s"}
        </span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-1.5">
        <Bucket label="Watchlist" tickers={sources.watchlist} />
        <Bucket label="Positions" tickers={sources.positions} />
        <Bucket label="Discover" tickers={sources.discover} />
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recommendations/sources-strip.tsx
git commit -m "feat(frontend): SourcesStrip component"
```

---

### Task 14: RecommendationsView container

**Files:**
- Create: `frontend/src/components/recommendations/recommendations-view.tsx`

- [ ] **Step 1: Create the container**

Create `frontend/src/components/recommendations/recommendations-view.tsx`:

```tsx
"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { RecommendationCard as Card, RecommendationRun } from "@/types/recommendations";
import { getLatestRecommendations } from "@/lib/api";
import { useRecommendationsStream } from "@/lib/recommendations-ws";
import { fmtTime } from "@/lib/utils";
import { RecommendationCard } from "./recommendation-card";
import { SourcesStrip } from "./sources-strip";

const SOURCE_RANK: Record<string, number> = { watchlist: 0, positions: 1, discover: 2 };

function sortCards(cards: Card[]): Card[] {
  return [...cards].sort((a, b) => {
    const aErr = a.error ? 1 : 0;
    const bErr = b.error ? 1 : 0;
    if (aErr !== bErr) return aErr - bErr;
    const sa = SOURCE_RANK[a.source] ?? 99;
    const sb = SOURCE_RANK[b.source] ?? 99;
    if (sa !== sb) return sa - sb;
    return (b.confidence ?? 0) - (a.confidence ?? 0);
  });
}

export function RecommendationsView() {
  const [latest, setLatest] = useState<RecommendationRun | null>(null);
  const [latestError, setLatestError] = useState<string | null>(null);
  const { state, start } = useRecommendationsStream();

  useEffect(() => {
    getLatestRecommendations()
      .then(setLatest)
      .catch((e: Error) => setLatestError(e.message));
  }, []);

  // While streaming, prefer live state. Otherwise fall back to the persisted latest run.
  const liveActive = state.status === "running" || state.status === "done" || state.status === "error";
  const cards = liveActive ? state.cards : (latest?.cards ?? []);
  const sources = liveActive ? state.sources : (latest?.sources ?? null);
  const generatedAt = liveActive ? state.generatedAt : (latest?.generated_at ?? null);

  const sorted = useMemo(() => sortCards(cards), [cards]);
  const running = state.status === "running" || state.status === "connecting";
  const hasAnything = sorted.length > 0 || sources !== null;

  return (
    <div className="flex flex-col">
      <header className="flex items-center justify-between px-5 py-4 border-b border-[color:var(--hairline)]">
        <h1 className="font-mono text-[18px] tracking-[.18em]">IDEAS</h1>
        <div className="flex items-center gap-4 text-[12px] text-[color:var(--fg-dim)]">
          <span className="num">
            {running
              ? `generating ${state.cards.length} of ${state.expectedCount || "…"}`
              : generatedAt
                ? `generated ${fmtTime(generatedAt)}`
                : "—"}
          </span>
          <button
            disabled={running}
            onClick={start}
            className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] disabled:opacity-40 transition-colors"
          >
            {running ? "Generating…" : "⟳ Generate"}
          </button>
          <Link
            href="/"
            className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] transition-colors"
          >
            ← Trade
          </Link>
        </div>
      </header>

      {state.warning === "no_candidates" && (
        <div className="px-5 py-4 text-[12px] text-[color:var(--amber)]">
          Add tickers to your watchlist or open a position to get started.
        </div>
      )}

      {state.warning && state.warning !== "no_candidates" && (
        <div className="px-5 py-3 text-[11.5px] text-[color:var(--amber)] font-mono">
          ⚠ {state.warning}
        </div>
      )}

      {state.errorMessage && (
        <div className="px-5 py-3 text-[12px] text-[color:var(--down)]">
          {state.errorMessage}
        </div>
      )}

      {latestError && !liveActive && (
        <div className="px-5 py-3 text-[12px] text-[color:var(--down)]">
          Couldn’t load latest run — {latestError}
        </div>
      )}

      <SourcesStrip sources={sources} />

      {sorted.length === 0 && !running && !hasAnything && (
        <div className="px-5 py-12 text-center text-[12px] text-[color:var(--fg-mute)]">
          No ideas generated yet. Click <span className="text-[color:var(--fg-dim)]">⟳ Generate</span> to start.
        </div>
      )}

      <ul className="divide-y divide-[color:var(--hairline)]">
        {sorted.map(card => (
          <RecommendationCard key={`${card.symbol}-${card.source}`} card={card} />
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recommendations/recommendations-view.tsx
git commit -m "feat(frontend): RecommendationsView container with stream + cached fallback"
```

---

### Task 15: `/recommendations` route shell

**Files:**
- Create: `frontend/src/app/recommendations/page.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/app/recommendations/page.tsx`:

```tsx
import { RecommendationsView } from "@/components/recommendations/recommendations-view";

export default function RecommendationsPage() {
  return (
    <div style={{ minHeight: "calc(100vh - 36px)" }} className="reveal reveal-1">
      <RecommendationsView />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck and build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: PASS — `/recommendations` route should appear in the route list.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/recommendations/page.tsx
git commit -m "feat(frontend): /recommendations route shell"
```

---

### Task 16: IDEAS nav link in StatusRail

**Files:**
- Modify: `frontend/src/components/status-rail.tsx`

- [ ] **Step 1: Modify the file**

The current `StatusRail` already has a `<nav>` with two `<Link>` elements (Trade, Portfolio). Add a third link for Ideas. Open the file and find the existing nav block:

```tsx
<nav className="flex items-center gap-1">
  <Link href="/" ...>Trade</Link>
  <Link href="/portfolio" ...>Portfolio</Link>
</nav>
```

Insert a third link AFTER the Portfolio link, with the same active-state styling pattern:

```tsx
<Link
  href="/recommendations"
  className={`px-2 py-0.5 text-[10.5px] tracking-[.18em] uppercase border ${pathname === "/recommendations" ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-transparent text-[color:var(--fg-dim)] hover:text-[color:var(--fg)]"}`}
>
  Ideas
</Link>
```

The completed nav block should read:

```tsx
<nav className="flex items-center gap-1">
  <Link
    href="/"
    className={`px-2 py-0.5 text-[10.5px] tracking-[.18em] uppercase border ${pathname === "/" ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-transparent text-[color:var(--fg-dim)] hover:text-[color:var(--fg)]"}`}
  >
    Trade
  </Link>
  <Link
    href="/portfolio"
    className={`px-2 py-0.5 text-[10.5px] tracking-[.18em] uppercase border ${pathname === "/portfolio" ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-transparent text-[color:var(--fg-dim)] hover:text-[color:var(--fg)]"}`}
  >
    Portfolio
  </Link>
  <Link
    href="/recommendations"
    className={`px-2 py-0.5 text-[10.5px] tracking-[.18em] uppercase border ${pathname === "/recommendations" ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-transparent text-[color:var(--fg-dim)] hover:text-[color:var(--fg)]"}`}
  >
    Ideas
  </Link>
</nav>
```

- [ ] **Step 2: Typecheck and build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/status-rail.tsx
git commit -m "feat(frontend): IDEAS nav link in StatusRail"
```

---

## Phase 5 — End-to-end verification

### Task 17: Backend offline smoke

**Files:** none (verification only)

- [ ] **Step 1: Boot the backend in fixtures mode on port 8765**

In one terminal:

```bash
cd backend && source .venv/bin/activate
FIXTURES_MODE=1 ALPACA_BASE_URL=https://paper-api.alpaca.markets uvicorn app.main:app --port 8765 --log-level warning
```

- [ ] **Step 2: Hit the REST endpoint**

In another terminal:

```bash
curl -s http://localhost:8765/recommendations/latest | python3 -c 'import json, sys; d = json.load(sys.stdin); print("keys:", sorted(d.keys())); print("run_id:", d["run_id"]); print("cards:", len(d["cards"]))'
```

Expected initially:
- `keys: ['cards', 'generated_at', 'run_id', 'sources']`
- `run_id: None`
- `cards: 0`

- [ ] **Step 3: Stop the smoke backend**

```bash
lsof -ti :8765 | xargs -r kill -TERM
```

(No commit — verification only.)

---

### Task 18: Frontend dev smoke (manual) + production build sanity

**Files:** none (verification only)

- [ ] **Step 1: Production build**

Run: `cd frontend && pnpm build`
Expected: PASS — `/recommendations` appears in the route list alongside `/` and `/portfolio`.

- [ ] **Step 2: Manual smoke (requires real backend with API keys, or fixtures mode)**

Boot both servers (`make dev` in backend, `pnpm dev` in frontend) and verify:

1. Navigate to `/recommendations`. With no prior run, see the empty state.
2. Click **Generate**. The sources strip appears, the counter advances `generating N of M…`, cards stream in.
3. Click `Analyze →` on a card. Lands on `/` with the ticker pre-filled, agent auto-runs.
4. Click `← Trade` on a card. Lands on `/`.
5. Refresh `/recommendations`. The cached run renders with its absolute timestamp.
6. Click **Generate** again. New run replaces the cached one.
7. Disable the Finnhub key (or clear it) and re-run. Confirm error cards render in-place for failed tickers.

(No commit — verification only.)

---

### Task 19: Final tests + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run full backend tests**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Expected: PASS (all existing + 13 new tests).

- [ ] **Step 2: Final typecheck and build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: PASS

- [ ] **Step 3: Update README API reference**

In `README.md`, find the API reference table. Append a new row at the bottom of the table (after the existing `/portfolio/equity-curve` row):

```markdown
| `/recommendations/latest` | GET | Most recent persisted recommendation run |
```

Also add a one-line note about the WebSocket message:

In the same file, find the existing `/ws` row in the API table:

```markdown
| `/ws` | WS | Agent session stream + replay |
```

Replace it with:

```markdown
| `/ws` | WS | Agent session stream + replay; recommendation streaming via `recommendation.start` |
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: recommendations endpoint in API reference"
```

---

## Self-review

**Spec coverage:**
- New `/recommendations` route → Task 15 ✅
- IDEAS nav link → Task 16 ✅
- `RecommendationRun` table → Task 1 ✅
- `get_general_news()` → Task 2 ✅
- Per-ticker prompt builder → Task 3 ✅
- `discover_candidates()` (watchlist > positions > discover priority, OCC underlying collapse, discover cap of 5) → Task 4 ✅
- `generate_one()` per-ticker mini-agent + retry on malformed → Task 5 ✅
- `generate_all()` orchestrator (streaming via emit, parallel with semaphore, persistence) → Task 6 ✅
- `GET /recommendations/latest` → Task 7 ✅
- WebSocket `recommendation.start` handler → Task 8 ✅
- `RecommendationCard` (bias badge, confidence bar, headlines, error row) → Task 12 ✅
- `SourcesStrip` → Task 13 ✅
- `RecommendationsView` (cached + live, sort by source/confidence, no_candidates message) → Task 14 ✅
- TickerInput auto-submit from `?ticker=&autosubmit=1` → Task 11 ✅
- Per-ticker error fallback → Task 6 (orchestrator catches) + Task 12 (card renders) ✅
- Discovery failure fallback (general_news_unavailable warning) → Task 6 ✅
- WS disconnect mid-stream surface → Task 10 (hook treats `running → close` as `error: stream interrupted`) ✅
- Generate disabled while running → Task 14 ✅
- Persisted-run timestamp + manual Generate refresh → Task 14 ✅
- README updated → Task 19 ✅

**Placeholder scan:** none.

**Type consistency:**
- `Source = "watchlist" | "positions" | "discover"` consistent across `frontend/src/types/recommendations.ts`, the backend `CandidateSet.all_with_source()` method (returns string source values matching), and `RecommendationCard.source` field.
- `Bias = "bullish" | "bearish" | "neutral"` consistent across the prompt schema, the parser validation, and the frontend types.
- `RecommendationRun` shape (`run_id`, `generated_at`, `cards`, `sources`) consistent across backend persistence (Task 6), REST endpoint (Task 7), and frontend API client + hook (Task 10).
- `StreamEvent` discriminated union exhaustively covers what the backend emits (`discovery`, `card`, `complete`, `discovery_warning`, `recommendation.error`, `error`).
- `top_headlines` resolves backend `string[]` (model output) → `{headline, url}[]` (card payload) consistently.

**Out-of-scope confirmation:** no portfolio scoring, no save/star, no backtest, no notifications, no full options-trade proposal on this screen — matches spec.
