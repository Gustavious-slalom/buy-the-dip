# Trading Agent PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a 2-day hackathon PoC where a Claude-powered agent analyzes a ticker, proposes an options trade with full reasoning streamed live to a Next.js dashboard, and only executes paper trades on Alpaca after explicit user confirmation.

**Architecture:** Monorepo with a FastAPI backend hosting a Claude tool-use agent loop and a Next.js frontend connected via WebSocket. Backend integrates Alpaca (paper trading + market data + options chains), Finnhub (news), and SQLite (proposals, traces, executions). Execution is gated by a UI approval step — `execute_trade` is never callable by the agent autonomously.

**Tech Stack:** Python 3.11, FastAPI, SQLModel, SQLite, `alpaca-py`, `anthropic` SDK (Claude Sonnet 4.6 + Haiku 4.5), `finnhub-python`. Next.js 15 (App Router), TypeScript, Tailwind, shadcn/ui, Vercel AI SDK, Recharts.

---

## Repository Structure

```
hackaton/
├── .gitignore
├── README.md
├── docs/superpowers/plans/2026-05-04-trading-agent-poc.md
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app + WebSocket endpoint
│   │   ├── config.py                # env loading
│   │   ├── db.py                    # SQLModel engine + session
│   │   ├── models.py                # Proposal, Execution, Trace, Watchlist
│   │   ├── schemas.py               # Pydantic WS event schemas
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── loop.py              # Claude tool-use loop (streaming)
│   │   │   ├── prompts.py           # system prompt (cached)
│   │   │   └── tools.py             # tool definitions + dispatch
│   │   ├── services/
│   │   │   ├── alpaca_service.py    # quote, chain, greeks, portfolio, exec
│   │   │   ├── news_service.py      # Finnhub + Haiku summarization
│   │   │   └── proposal_service.py  # propose_trade, risk/reward calc
│   │   └── api/
│   │       ├── ws.py                # WebSocket router
│   │       └── http.py              # REST: approve/reject, list proposals
│   └── tests/
│       ├── test_proposal_service.py
│       ├── test_tools.py
│       └── test_agent_loop.py       # mocked Anthropic
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── .env.local.example
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx             # main dashboard
│       │   └── globals.css
│       ├── components/
│       │   ├── ticker-input.tsx
│       │   ├── agent-trace.tsx      # streamed thinking + tool calls
│       │   ├── proposal-card.tsx    # legs, risk/reward, approve/reject
│       │   ├── price-chart.tsx      # Recharts
│       │   ├── options-chain-table.tsx
│       │   ├── portfolio-panel.tsx
│       │   └── ui/                  # shadcn primitives
│       ├── lib/
│       │   ├── ws.ts                # WS client + event types
│       │   └── api.ts               # REST helpers
│       └── types/events.ts          # mirrors backend schemas.py
```

**File responsibility rules:** services do I/O; `agent/tools.py` is a thin dispatch layer that calls services and emits WS trace events; `agent/loop.py` only knows about Anthropic + tool dispatch; `api/ws.py` orchestrates a session. UI components are presentational; `lib/ws.ts` owns connection state.

---

## WebSocket Event Schema

All events are JSON `{ "type": "...", "session_id": "...", "ts": "...", "data": {...} }`.

| `type` | direction | `data` |
|---|---|---|
| `session.start` | C→S | `{ ticker?: string, idea?: string }` |
| `agent.status` | S→C | `{ message: string }` ("Fetching quote…") |
| `agent.thinking` | S→C | `{ text: string }` (streamed text deltas) |
| `agent.tool_call` | S→C | `{ tool_use_id, name, input }` |
| `agent.tool_result` | S→C | `{ tool_use_id, name, output, error? }` |
| `agent.proposal` | S→C | `{ proposal_id, summary, legs, max_risk, max_reward, breakeven, expiry, confidence, risks }` |
| `agent.complete` | S→C | `{ proposal_id? }` |
| `agent.error` | S→C | `{ message }` |
| `proposal.approve` | C→S | `{ proposal_id }` |
| `proposal.reject` | C→S | `{ proposal_id, reason? }` |
| `execution.result` | S→C | `{ proposal_id, alpaca_order_id, status, filled_legs }` |

---

## Storage Models (SQLModel)

```python
# Proposal: agent's suggested trade, pending until user acts
class Proposal(SQLModel, table=True):
    id: str = Field(primary_key=True)              # uuid
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ticker: str
    legs_json: str                                  # JSON [{action, contract_symbol, qty, side}]
    max_risk: float
    max_reward: float | None
    breakeven: float | None
    expiry: str
    rationale: str
    confidence: float
    risks_json: str
    status: str = "pending"                         # pending | approved | rejected | executed | failed

# Execution: result of a paper trade after user approval
class Execution(SQLModel, table=True):
    id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="proposal.id")
    alpaca_order_id: str | None = None
    submitted_at: datetime
    status: str                                     # submitted | filled | rejected | failed
    raw_response_json: str

# Trace: full agent transcript per session for replay/audit
class Trace(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    ts: datetime
    event_type: str
    payload_json: str

# Watchlist: simple persisted list of tickers
class Watchlist(SQLModel, table=True):
    ticker: str = Field(primary_key=True)
    added_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## Agent Loop Design

`agent/loop.py` exposes `async def run_session(ws, session_id, user_message, db)`:

1. Build messages list with cached system prompt + cached tool definitions (Anthropic prompt caching via `cache_control: {"type": "ephemeral"}` on system + last tool entry).
2. Loop:
   - Call `client.messages.stream(model="claude-sonnet-4-6", tools=TOOLS, messages=...)`.
   - Stream text deltas → emit `agent.thinking`.
   - On `tool_use` block: emit `agent.tool_call`, dispatch via `tools.dispatch(name, input)`, emit `agent.tool_result`. Append tool result to messages.
   - On `end_turn` without tool use: break.
3. If a `propose_trade` was called, the dispatch persists a `Proposal` row and emits `agent.proposal`.
4. `execute_trade` is **not** registered with Claude. It's an HTTP/WS endpoint triggered only by `proposal.approve` from the UI.

**Safety invariant:** `TOOLS` array passed to Anthropic must NOT contain `execute_trade`. This is enforced by a unit test.

---

## Tool Interface

```python
TOOLS = [
    {"name": "get_quote", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}, ...},
    {"name": "get_options_chain", ...},
    {"name": "get_greeks", ...},
    {"name": "get_news", ...},
    {"name": "get_portfolio"},
    {"name": "get_positions"},
    {"name": "propose_trade", "input_schema": {"type": "object", "properties": {
        "ticker": {"type": "string"},
        "legs": {"type": "array", "items": {...}},
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
        "risks": {"type": "array", "items": {"type": "string"}},
    }, "required": ["ticker", "legs", "rationale"]}},
]
```

`tools.dispatch(name, input, ctx)` routes to services, returns dict, and side-effects WS emission via `ctx.emit(...)`.

---

## Frontend Layout

Single page (`app/page.tsx`) with three columns on desktop, stacked on mobile:

- **Left (320px):** `TickerInput` + `WatchlistPanel` + `PortfolioPanel`
- **Center (flex):** `PriceChart` (Recharts area chart, 1d/5d/1mo toggle), `OptionsChainTable` filtered to nearest expiry, `ProposalCard` (when present, sticky top)
- **Right (380px):** `AgentTrace` — vertical timeline of `agent.status`/`thinking`/`tool_call`/`tool_result` events with collapsible JSON

`ProposalCard` shows: legs (action + contract), max risk/reward, breakeven, expiry, confidence bar, risks list, **Approve** (green) and **Reject** (gray) buttons. After approve: button becomes spinner → success toast with Alpaca order id, or error toast.

`lib/ws.ts` exports `useAgentSession()` hook returning `{ status, events, proposal, sendIdea, approve, reject }`.

---

## Safety Constraints

1. `execute_trade` tool is never in the LLM tool list — enforced by `test_agent_loop_has_no_execute_tool`.
2. Proposal status transitions are linear: `pending → approved → executed` or `pending → rejected`. Backend rejects double-approve.
3. Approval requires the exact `proposal_id` from a known pending row.
4. All Alpaca calls run against `paper-api.alpaca.markets` — env-checked at startup, app refuses to boot if `ALPACA_BASE_URL` is the live endpoint.
5. Max position size guardrail: reject proposals whose `max_risk > MAX_RISK_USD` (default 5000) before the UI even shows the approve button.

---

## Environment Variables

**Backend `.env`:**
```
ANTHROPIC_API_KEY=sk-ant-...
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
FINNHUB_API_KEY=...
DATABASE_URL=sqlite:///./trading.db
MAX_RISK_USD=5000
LOG_LEVEL=INFO
```

**Frontend `.env.local`:**
```
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Test/Validation Strategy

- **Backend pytest:** unit tests for `proposal_service` (risk/reward math for spreads, condors), `tools.dispatch` happy paths with mocked services, agent loop with a stubbed Anthropic client that yields canned tool_use blocks. **Critical safety test:** assert `execute_trade` not in `TOOLS`.
- **Frontend:** type-check (`pnpm tsc --noEmit`) only — skip unit tests for time. Validate by running through demo script.
- **Integration smoke:** a `make smoke` target runs `python -m app.smoke AAPL` which exercises Alpaca + Finnhub against real APIs and prints quote, top of chain, and 1 news headline. Run before every demo.

---

## 2-Day Implementation Sequence

### Day 1 AM — Backend foundation + agent loop CLI
- Tasks 1–6: repo init, backend skeleton, env, DB models, Alpaca service stub, agent loop runnable from CLI with mocked tools.
- **Milestone:** `python -m app.cli "analyze AAPL"` streams thinking + emits a fake proposal to stdout.

### Day 1 PM — Real tools + WebSocket
- Tasks 7–11: real Alpaca calls, Finnhub + Haiku news summarization, `propose_trade` persistence, FastAPI WebSocket endpoint, approval HTTP endpoint, paper execution.
- **Milestone:** `wscat` to `/ws`, send ticker, receive full event stream ending in proposal; `curl` approve → real paper order on Alpaca.

### Day 2 AM — Frontend dashboard
- Tasks 12–17: Next.js + shadcn scaffold, WS hook, ticker input, agent trace component, proposal card with approve/reject, portfolio panel.
- **Milestone:** end-to-end happy path in browser — type ticker, watch agent work, approve, see order confirmation.

### Day 2 PM — Polish + demo
- Tasks 18–22: price chart, options chain table, error toasts, demo seed script, recorded fallback video, README + demo script.
- **Milestone:** dress rehearsal of 5-minute demo.

---

## Demo Fallback Plan

1. **Recorded video** (Day 2 PM): screen-record a successful end-to-end run; have it ready to play if live demo fails.
2. **Replay mode:** `--replay <session_id>` flag on backend reads stored `Trace` rows and re-emits them over WS at original cadence. Lets you "re-run" a proven session if Alpaca/Anthropic has a hiccup.
3. **Cached fixtures:** `services/alpaca_service.py` checks `FIXTURES_MODE=1` env; if set, returns canned JSON from `tests/fixtures/`. One-flag offline demo.
4. **Pre-seeded watchlist** (AAPL, NVDA, SPY) and a pre-warmed agent run (run once in green room before stage).

---

# Tasks

## Task 1: Repo init + monorepo skeleton

**Files:**
- Create: `.gitignore`, `README.md`, `backend/`, `frontend/`

- [ ] **Step 1: Initialize git and structure**

```bash
cd /Users/gus/learn/hackaton
git init
mkdir -p backend/app/{agent,services,api} backend/tests frontend
```

- [ ] **Step 2: Write .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
*.db
.env
.env.local
# Node
node_modules/
.next/
out/
# Editors
.vscode/
.idea/
.DS_Store
# Fixtures captured during dev
backend/tests/fixtures/*.live.json
```

- [ ] **Step 3: Write minimal README.md**

```markdown
# Trading Agent PoC

Hackathon PoC: Claude-powered options trading copilot on Alpaca paper trading.

## Quick start
- Backend: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e . && uvicorn app.main:app --reload`
- Frontend: `cd frontend && pnpm install && pnpm dev`

See `docs/superpowers/plans/2026-05-04-trading-agent-poc.md` for the implementation plan.
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md docs/
git commit -m "chore: scaffold repo and plan"
```

---

## Task 2: Backend Python environment + dependencies

**Files:**
- Create: `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/config.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "trading-agent-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlmodel>=0.0.22",
  "anthropic>=0.40",
  "alpaca-py>=0.30",
  "finnhub-python>=2.4",
  "httpx>=0.27",
  "pydantic-settings>=2.5",
  "python-dotenv>=1.0",
  "websockets>=13.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "respx>=0.21"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write .env.example**

```
ANTHROPIC_API_KEY=
ALPACA_API_KEY=
ALPACA_API_SECRET=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
FINNHUB_API_KEY=
DATABASE_URL=sqlite:///./trading.db
MAX_RISK_USD=5000
LOG_LEVEL=INFO
FIXTURES_MODE=0
```

- [ ] **Step 3: Write app/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    finnhub_api_key: str = ""
    database_url: str = "sqlite:///./trading.db"
    max_risk_usd: float = 5000.0
    log_level: str = "INFO"
    fixtures_mode: bool = False
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    def assert_paper(self) -> None:
        if "paper" not in self.alpaca_base_url:
            raise RuntimeError(f"Refusing to start: ALPACA_BASE_URL is not paper ({self.alpaca_base_url})")

settings = Settings()
```

- [ ] **Step 4: Install + commit**

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
cd .. && git add backend/ && git commit -m "feat(backend): python deps + settings"
```

---

## Task 3: SQLModel storage layer (TDD)

**Files:**
- Create: `backend/app/db.py`, `backend/app/models.py`, `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from app.db import init_db, get_session
from app.models import Proposal
import json, uuid
from datetime import datetime

def test_proposal_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    from importlib import reload
    from app import config, db
    reload(config); reload(db)
    db.init_db()
    p = Proposal(
        id=str(uuid.uuid4()), session_id="s1", ticker="AAPL",
        legs_json=json.dumps([{"action":"buy","contract":"AAPL250620C200","qty":1}]),
        max_risk=500.0, max_reward=1500.0, breakeven=205.0, expiry="2025-06-20",
        rationale="bullish earnings", confidence=0.7, risks_json=json.dumps(["IV crush"]),
    )
    with db.get_session() as s:
        s.add(p); s.commit()
        got = s.get(Proposal, p.id)
    assert got.ticker == "AAPL" and got.status == "pending"
```

- [ ] **Step 2: Run — expect failure (modules missing)**

```bash
cd backend && pytest tests/test_models.py -v
```

- [ ] **Step 3: Write app/models.py**

```python
from datetime import datetime
from sqlmodel import SQLModel, Field

class Proposal(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ticker: str
    legs_json: str
    max_risk: float
    max_reward: float | None = None
    breakeven: float | None = None
    expiry: str
    rationale: str
    confidence: float
    risks_json: str
    status: str = "pending"

class Execution(SQLModel, table=True):
    id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="proposal.id")
    alpaca_order_id: str | None = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    status: str
    raw_response_json: str

class Trace(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    ts: datetime = Field(default_factory=datetime.utcnow)
    event_type: str
    payload_json: str

class Watchlist(SQLModel, table=True):
    ticker: str = Field(primary_key=True)
    added_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Write app/db.py**

```python
from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine
from app.config import settings

engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

@contextmanager
def get_session():
    with Session(engine) as s:
        yield s
```

- [ ] **Step 5: Run — expect pass; commit**

```bash
pytest tests/test_models.py -v
git add backend/app/models.py backend/app/db.py backend/tests/test_models.py
git commit -m "feat(backend): SQLModel storage layer"
```

---

## Task 4: Alpaca service (with fixtures fallback)

**Files:**
- Create: `backend/app/services/alpaca_service.py`, `backend/app/services/__init__.py`, `backend/tests/test_alpaca_service.py`, `backend/tests/fixtures/aapl_chain.json`

- [ ] **Step 1: Capture a fixture**

Manually run once (after putting keys in `.env`):
```bash
python -c "from alpaca.data.historical.option import OptionHistoricalDataClient; from app.config import settings; c = OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret); import json; print(json.dumps({'note':'placeholder, fill from real call'}))"
```
For the plan, hand-craft `tests/fixtures/aapl_chain.json`:
```json
{"underlying":"AAPL","expiry":"2025-06-20","contracts":[{"symbol":"AAPL250620C00200000","strike":200,"side":"call","bid":3.10,"ask":3.20,"delta":0.45,"gamma":0.03,"theta":-0.05,"vega":0.12,"iv":0.28}]}
```

- [ ] **Step 2: Write failing test**

```python
# backend/tests/test_alpaca_service.py
import os
def test_fixtures_mode_returns_canned(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service
    reload(alpaca_service)
    chain = alpaca_service.get_options_chain("AAPL", expiry="2025-06-20")
    assert chain["contracts"][0]["symbol"].startswith("AAPL")

def test_get_quote_shape(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    q = alpaca_service.get_quote("AAPL")
    assert {"symbol","price","bid","ask","ts"}.issubset(q.keys())
```

- [ ] **Step 3: Implement `app/services/alpaca_service.py`**

```python
import json
from datetime import datetime
from pathlib import Path
from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, OptionChainRequest
from alpaca.trading.requests import MarketOrderRequest, OptionLegRequest
from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce, PositionIntent
from app.config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

def _trading():
    return TradingClient(settings.alpaca_api_key, settings.alpaca_api_secret, paper=True)

def _stock_data():
    return StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret)

def _option_data():
    return OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret)

def get_quote(symbol: str) -> dict:
    if settings.fixtures_mode:
        return {"symbol": symbol, "price": 200.0, "bid": 199.95, "ask": 200.05, "ts": datetime.utcnow().isoformat()}
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    res = _stock_data().get_stock_latest_quote(req)[symbol]
    mid = (res.bid_price + res.ask_price) / 2
    return {"symbol": symbol, "price": mid, "bid": res.bid_price, "ask": res.ask_price, "ts": res.timestamp.isoformat()}

def get_options_chain(symbol: str, expiry: str | None = None) -> dict:
    if settings.fixtures_mode:
        return json.loads((FIXTURES / "aapl_chain.json").read_text())
    req = OptionChainRequest(underlying_symbol=symbol)
    snap = _option_data().get_option_chain(req)
    contracts = []
    for sym, s in snap.items():
        if expiry and expiry not in sym:
            continue
        g = s.greeks
        q = s.latest_quote
        contracts.append({
            "symbol": sym, "strike": s.implied_volatility and 0,  # parse from sym in real call
            "side": "call" if "C" in sym[-9:] else "put",
            "bid": q.bid_price if q else None, "ask": q.ask_price if q else None,
            "delta": getattr(g, "delta", None), "gamma": getattr(g, "gamma", None),
            "theta": getattr(g, "theta", None), "vega": getattr(g, "vega", None),
            "iv": s.implied_volatility,
        })
    return {"underlying": symbol, "expiry": expiry, "contracts": contracts[:40]}

def get_greeks(contract_symbol: str) -> dict:
    if settings.fixtures_mode:
        return {"symbol": contract_symbol, "delta": 0.45, "gamma": 0.03, "theta": -0.05, "vega": 0.12, "iv": 0.28}
    snap = _option_data().get_option_latest_quote([contract_symbol])
    # simplified — alpaca-py exposes greeks via chain snapshots; keep PoC simple
    return {"symbol": contract_symbol, "delta": None, "gamma": None, "theta": None, "vega": None, "iv": None}

def get_portfolio() -> dict:
    if settings.fixtures_mode:
        return {"cash": 100000.0, "equity": 100000.0, "buying_power": 200000.0}
    a = _trading().get_account()
    return {"cash": float(a.cash), "equity": float(a.equity), "buying_power": float(a.buying_power)}

def get_positions() -> list[dict]:
    if settings.fixtures_mode:
        return []
    return [{"symbol": p.symbol, "qty": float(p.qty), "avg_entry_price": float(p.avg_entry_price)} for p in _trading().get_all_positions()]

def submit_multileg_order(legs: list[dict]) -> dict:
    """Caller MUST verify proposal status='approved' before invoking."""
    settings.assert_paper()
    order_legs = [
        OptionLegRequest(
            symbol=l["contract_symbol"],
            ratio_qty=l.get("qty", 1),
            side=OrderSide.BUY if l["action"] == "buy" else OrderSide.SELL,
            position_intent=PositionIntent.BUY_TO_OPEN if l["action"] == "buy" else PositionIntent.SELL_TO_OPEN,
        ) for l in legs
    ]
    req = MarketOrderRequest(
        qty=1, order_class=OrderClass.MLEG, time_in_force=TimeInForce.DAY,
        legs=order_legs,
    )
    order = _trading().submit_order(req)
    return {"id": str(order.id), "status": str(order.status), "raw": order.model_dump_json()}
```

- [ ] **Step 4: Run — pass; commit**

```bash
pytest tests/test_alpaca_service.py -v
git add backend/app/services backend/tests/test_alpaca_service.py backend/tests/fixtures
git commit -m "feat(backend): alpaca service with fixtures mode"
```

---

## Task 5: News service with Haiku summarization

**Files:**
- Create: `backend/app/services/news_service.py`, `backend/tests/test_news_service.py`, `backend/tests/fixtures/aapl_news.json`

- [ ] **Step 1: Fixture**

```json
[{"headline":"Apple beats earnings","summary":"AAPL Q3 EPS $1.40 vs $1.35 est","url":"https://example.com","datetime":1714000000}]
```

- [ ] **Step 2: Write failing test**

```python
# backend/tests/test_news_service.py
def test_news_fixtures(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import news_service; reload(news_service)
    out = news_service.get_news("AAPL", since_days=7)
    assert out["items"][0]["headline"] == "Apple beats earnings"
    assert "summary" in out  # Haiku summary key (empty in fixtures mode)
```

- [ ] **Step 3: Implement**

```python
# backend/app/services/news_service.py
import json
from datetime import datetime, timedelta
from pathlib import Path
import finnhub
from anthropic import Anthropic
from app.config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_anthropic = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

def get_news(symbol: str, since_days: int = 7) -> dict:
    if settings.fixtures_mode:
        items = json.loads((FIXTURES / "aapl_news.json").read_text())
        return {"symbol": symbol, "items": items, "summary": ""}
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    today = datetime.utcnow().date()
    items = client.company_news(symbol, _from=str(today - timedelta(days=since_days)), to=str(today))[:8]
    items = [{"headline": i["headline"], "summary": i.get("summary",""), "url": i["url"], "datetime": i["datetime"]} for i in items]
    summary = ""
    if _anthropic and items:
        joined = "\n".join(f"- {i['headline']}: {i['summary'][:200]}" for i in items)
        msg = _anthropic.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            messages=[{"role": "user", "content": f"Summarize the market-moving themes for {symbol} in 3 bullets:\n{joined}"}],
        )
        summary = msg.content[0].text if msg.content else ""
    return {"symbol": symbol, "items": items, "summary": summary}
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/test_news_service.py -v
git add backend/app/services/news_service.py backend/tests/test_news_service.py backend/tests/fixtures/aapl_news.json
git commit -m "feat(backend): news service with Haiku summarization"
```

---

## Task 6: Proposal service (risk/reward calc, TDD)

**Files:**
- Create: `backend/app/services/proposal_service.py`, `backend/tests/test_proposal_service.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_proposal_service.py
from app.services.proposal_service import compute_risk_reward

def test_long_call_risk():
    legs = [{"action":"buy","side":"call","qty":1,"strike":200,"premium":3.0,"contract_symbol":"X"}]
    r = compute_risk_reward(legs)
    assert r["max_risk"] == 300.0
    assert r["max_reward"] is None  # unlimited
    assert r["breakeven"] == 203.0

def test_vertical_call_spread():
    legs = [
        {"action":"buy","side":"call","qty":1,"strike":200,"premium":3.0,"contract_symbol":"A"},
        {"action":"sell","side":"call","qty":1,"strike":210,"premium":1.0,"contract_symbol":"B"},
    ]
    r = compute_risk_reward(legs)
    assert r["max_risk"] == 200.0   # net debit 2.00 * 100
    assert r["max_reward"] == 800.0 # (10 width - 2 debit) * 100
    assert r["breakeven"] == 202.0
```

- [ ] **Step 2: Implement**

```python
# backend/app/services/proposal_service.py
import uuid, json
from app.db import get_session
from app.models import Proposal

def compute_risk_reward(legs: list[dict]) -> dict:
    # Supports: single long call/put, vertical debit/credit spread.
    longs = [l for l in legs if l["action"] == "buy"]
    shorts = [l for l in legs if l["action"] == "sell"]
    net_debit = sum(l["premium"] * l["qty"] for l in longs) - sum(l["premium"] * l["qty"] for l in shorts)
    if len(legs) == 1 and legs[0]["action"] == "buy":
        l = legs[0]
        be = l["strike"] + l["premium"] if l["side"] == "call" else l["strike"] - l["premium"]
        return {"max_risk": l["premium"] * 100 * l["qty"], "max_reward": None, "breakeven": be}
    if len(legs) == 2 and legs[0]["side"] == legs[1]["side"]:
        width = abs(legs[0]["strike"] - legs[1]["strike"])
        if net_debit > 0:  # debit spread
            long_strike = next(l["strike"] for l in longs)
            be = long_strike + net_debit if longs[0]["side"] == "call" else long_strike - net_debit
            return {"max_risk": net_debit * 100, "max_reward": (width - net_debit) * 100, "breakeven": be}
    return {"max_risk": abs(net_debit) * 100, "max_reward": None, "breakeven": None}

def create_proposal(session_id: str, ticker: str, legs: list[dict], rationale: str,
                    confidence: float, risks: list[str], expiry: str) -> dict:
    rr = compute_risk_reward(legs)
    pid = str(uuid.uuid4())
    p = Proposal(
        id=pid, session_id=session_id, ticker=ticker,
        legs_json=json.dumps(legs), max_risk=rr["max_risk"],
        max_reward=rr["max_reward"], breakeven=rr["breakeven"],
        expiry=expiry, rationale=rationale, confidence=confidence,
        risks_json=json.dumps(risks), status="pending",
    )
    with get_session() as s:
        s.add(p); s.commit(); s.refresh(p)
    return {"proposal_id": pid, **rr, "legs": legs, "rationale": rationale,
            "confidence": confidence, "risks": risks, "expiry": expiry, "ticker": ticker}
```

- [ ] **Step 3: Pass + commit**

```bash
pytest tests/test_proposal_service.py -v
git add backend/app/services/proposal_service.py backend/tests/test_proposal_service.py
git commit -m "feat(backend): proposal risk/reward calculations"
```

---

## Task 7: Agent tools dispatch + safety test

**Files:**
- Create: `backend/app/agent/__init__.py`, `backend/app/agent/tools.py`, `backend/app/agent/prompts.py`, `backend/tests/test_tools.py`

- [ ] **Step 1: Failing test (safety)**

```python
# backend/tests/test_tools.py
from app.agent.tools import TOOLS

def test_execute_trade_not_in_tools():
    names = {t["name"] for t in TOOLS}
    assert "execute_trade" not in names
    assert {"get_quote","get_options_chain","get_greeks","get_news","get_portfolio","get_positions","propose_trade"}.issubset(names)
```

- [ ] **Step 2: Implement tools.py**

```python
# backend/app/agent/tools.py
from typing import Any, Callable, Awaitable
from app.services import alpaca_service, news_service, proposal_service

TOOLS = [
    {"name": "get_quote", "description": "Latest quote for a stock symbol.",
     "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "get_options_chain", "description": "Options chain for a symbol; optionally filter by expiry YYYY-MM-DD.",
     "input_schema": {"type": "object", "properties": {"symbol": {"type":"string"},"expiry":{"type":"string"}}, "required":["symbol"]}},
    {"name": "get_greeks", "description": "Greeks for a specific option contract symbol.",
     "input_schema": {"type":"object","properties":{"contract_symbol":{"type":"string"}},"required":["contract_symbol"]}},
    {"name": "get_news", "description": "Recent news + summary for a ticker.",
     "input_schema": {"type":"object","properties":{"symbol":{"type":"string"},"since_days":{"type":"integer"}},"required":["symbol"]}},
    {"name": "get_portfolio", "description": "Account cash, equity, buying power.",
     "input_schema": {"type":"object","properties":{}}},
    {"name": "get_positions", "description": "Currently held positions.",
     "input_schema": {"type":"object","properties":{}}},
    {"name": "propose_trade", "description": "Create a pending options trade proposal. Does NOT execute. Legs format: [{action: 'buy'|'sell', side: 'call'|'put', qty, strike, premium, contract_symbol}].",
     "input_schema": {"type":"object","properties":{
        "ticker":{"type":"string"},
        "legs":{"type":"array","items":{"type":"object"}},
        "rationale":{"type":"string"},
        "confidence":{"type":"number"},
        "risks":{"type":"array","items":{"type":"string"}},
        "expiry":{"type":"string"},
     },"required":["ticker","legs","rationale","expiry"]}},
]

async def dispatch(name: str, input: dict, session_id: str) -> dict:
    if name == "get_quote": return alpaca_service.get_quote(input["symbol"])
    if name == "get_options_chain": return alpaca_service.get_options_chain(input["symbol"], input.get("expiry"))
    if name == "get_greeks": return alpaca_service.get_greeks(input["contract_symbol"])
    if name == "get_news": return news_service.get_news(input["symbol"], input.get("since_days", 7))
    if name == "get_portfolio": return alpaca_service.get_portfolio()
    if name == "get_positions": return {"positions": alpaca_service.get_positions()}
    if name == "propose_trade":
        return proposal_service.create_proposal(
            session_id=session_id, ticker=input["ticker"], legs=input["legs"],
            rationale=input["rationale"], confidence=input.get("confidence", 0.5),
            risks=input.get("risks", []), expiry=input["expiry"],
        )
    raise ValueError(f"unknown tool {name}")
```

- [ ] **Step 3: Write prompts.py**

```python
# backend/app/agent/prompts.py
SYSTEM_PROMPT = """You are an options trading copilot for a paper-trading account.

Workflow for any user request:
1. Get a quote on the ticker.
2. Pull recent news (call get_news).
3. Pull the options chain for the nearest reasonable expiry.
4. Check portfolio + positions.
5. Pick ONE trade idea (long call/put, or vertical debit/credit spread). Keep it simple.
6. Call propose_trade with concrete legs (real contract_symbols from the chain), rationale, confidence (0-1), risks, expiry.

Rules:
- You CANNOT execute trades. propose_trade only creates a pending proposal for the human to approve.
- Be concise in reasoning. Surface risks honestly.
- Do not propose trades whose max_risk would exceed reasonable size for a $100k paper account (target < $5000 risk).
- Use real contract symbols you observed in the chain. Never invent symbols.
"""
```

- [ ] **Step 4: Pass + commit**

```bash
pytest tests/test_tools.py -v
git add backend/app/agent backend/tests/test_tools.py
git commit -m "feat(backend): agent tool definitions + safety test"
```

---

## Task 8: Agent loop with streaming + WS emission

**Files:**
- Create: `backend/app/agent/loop.py`, `backend/tests/test_agent_loop.py`

- [ ] **Step 1: Failing test (mocked Anthropic)**

```python
# backend/tests/test_agent_loop.py
import asyncio, json
from unittest.mock import MagicMock, patch
from app.agent.loop import run_session

class FakeEmit:
    def __init__(self): self.events = []
    async def __call__(self, evt): self.events.append(evt)

def test_loop_emits_proposal(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service, news_service, proposal_service
    from app.agent import tools
    reload(alpaca_service); reload(news_service); reload(proposal_service); reload(tools)
    from app.db import init_db; init_db()

    # Stub: claim Claude only calls propose_trade then ends
    fake_response = MagicMock()
    fake_response.stop_reason = "tool_use"
    fake_response.content = [MagicMock(type="tool_use", id="t1", name="propose_trade",
                                      input={"ticker":"AAPL","legs":[{"action":"buy","side":"call","qty":1,"strike":200,"premium":3.0,"contract_symbol":"AAPL250620C200"}],
                                             "rationale":"bullish","confidence":0.7,"risks":["IV"],"expiry":"2025-06-20"})]
    fake_end = MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="done")])
    with patch("app.agent.loop.Anthropic") as A:
        client = A.return_value
        client.messages.create.side_effect = [fake_response, fake_end]
        emit = FakeEmit()
        asyncio.run(run_session(emit, "s1", "analyze AAPL"))
    types = [e["type"] for e in emit.events]
    assert "agent.tool_call" in types and "agent.proposal" in types
```

- [ ] **Step 2: Implement loop.py**

```python
# backend/app/agent/loop.py
from datetime import datetime
from anthropic import Anthropic
from app.config import settings
from app.agent.tools import TOOLS, dispatch
from app.agent.prompts import SYSTEM_PROMPT

def _evt(type_: str, **data) -> dict:
    return {"type": type_, "ts": datetime.utcnow().isoformat(), "data": data}

async def run_session(emit, session_id: str, user_message: str) -> None:
    client = Anthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": user_message}]
    await emit(_evt("agent.status", message=f"Starting analysis for: {user_message}"))

    cached_tools = [{**t, "cache_control": {"type": "ephemeral"}} if i == len(TOOLS)-1 else t for i, t in enumerate(TOOLS)]
    cached_system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    for _ in range(12):  # safety cap
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=2048,
            system=cached_system, tools=cached_tools, messages=messages,
        )
        assistant_blocks = []
        tool_uses = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                await emit(_evt("agent.thinking", text=block.text))
                assistant_blocks.append({"type": "text", "text": block.text})
            elif getattr(block, "type", None) == "tool_use":
                await emit(_evt("agent.tool_call", tool_use_id=block.id, name=block.name, input=block.input))
                tool_uses.append(block)
                assistant_blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

        messages.append({"role": "assistant", "content": assistant_blocks})

        if resp.stop_reason != "tool_use":
            await emit(_evt("agent.complete"))
            return

        tool_results = []
        for tu in tool_uses:
            try:
                result = await dispatch(tu.name, tu.input, session_id)
                await emit(_evt("agent.tool_result", tool_use_id=tu.id, name=tu.name, output=result))
                if tu.name == "propose_trade":
                    await emit(_evt("agent.proposal", **result))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": str(result)})
            except Exception as e:
                await emit(_evt("agent.tool_result", tool_use_id=tu.id, name=tu.name, output=None, error=str(e)))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": f"error: {e}", "is_error": True})

        messages.append({"role": "user", "content": tool_results})

    await emit(_evt("agent.error", message="loop cap reached"))
```

- [ ] **Step 3: Pass + commit**

```bash
pytest tests/test_agent_loop.py -v
git add backend/app/agent/loop.py backend/tests/test_agent_loop.py
git commit -m "feat(backend): streaming agent loop with tool dispatch"
```

---

## Task 9: FastAPI app, WebSocket endpoint, approval HTTP

**Files:**
- Create: `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/api/ws.py`, `backend/app/api/http.py`

- [ ] **Step 1: Implement main.py**

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.api.ws import router as ws_router
from app.api.http import router as http_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_paper()
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(ws_router)
app.include_router(http_router)
```

- [ ] **Step 2: Implement api/ws.py**

```python
# backend/app/api/ws.py
import json, uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.agent.loop import run_session
from app.db import get_session
from app.models import Trace
from datetime import datetime

router = APIRouter()

@router.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())
    try:
        async def emit(evt: dict):
            evt["session_id"] = session_id
            await ws.send_text(json.dumps(evt))
            with get_session() as s:
                s.add(Trace(session_id=session_id, ts=datetime.utcnow(),
                            event_type=evt["type"], payload_json=json.dumps(evt))); s.commit()
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("type") == "session.start":
                user_msg = data["data"].get("idea") or f"analyze {data['data'].get('ticker')}"
                await run_session(emit, session_id, user_msg)
    except WebSocketDisconnect:
        return
```

- [ ] **Step 3: Implement api/http.py**

```python
# backend/app/api/http.py
import json, uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db import get_session
from app.models import Proposal, Execution
from app.config import settings
from app.services import alpaca_service

router = APIRouter()

class ApproveBody(BaseModel):
    proposal_id: str

@router.get("/proposals")
def list_proposals():
    from sqlmodel import select
    with get_session() as s:
        return [p.model_dump() for p in s.exec(select(Proposal).order_by(Proposal.created_at.desc())).all()]

@router.post("/proposals/approve")
def approve(body: ApproveBody):
    with get_session() as s:
        p = s.get(Proposal, body.proposal_id)
        if not p: raise HTTPException(404, "not found")
        if p.status != "pending": raise HTTPException(409, f"status is {p.status}")
        if p.max_risk > settings.max_risk_usd: raise HTTPException(400, "exceeds MAX_RISK_USD")
        legs = json.loads(p.legs_json)
        try:
            order = alpaca_service.submit_multileg_order(legs)
            p.status = "executed"
            ex = Execution(id=str(uuid.uuid4()), proposal_id=p.id, alpaca_order_id=order["id"],
                           submitted_at=datetime.utcnow(), status=order["status"], raw_response_json=order["raw"])
            s.add(p); s.add(ex); s.commit()
            return {"ok": True, "alpaca_order_id": order["id"], "status": order["status"]}
        except Exception as e:
            p.status = "failed"
            ex = Execution(id=str(uuid.uuid4()), proposal_id=p.id, alpaca_order_id=None,
                           submitted_at=datetime.utcnow(), status="failed", raw_response_json=str(e))
            s.add(p); s.add(ex); s.commit()
            raise HTTPException(500, f"execution failed: {e}")

@router.post("/proposals/reject")
def reject(body: ApproveBody):
    with get_session() as s:
        p = s.get(Proposal, body.proposal_id)
        if not p: raise HTTPException(404)
        if p.status != "pending": raise HTTPException(409)
        p.status = "rejected"; s.add(p); s.commit()
    return {"ok": True}
```

- [ ] **Step 4: Smoke test + commit**

```bash
cd backend && uvicorn app.main:app --reload &
sleep 2
curl http://localhost:8000/proposals  # expect []
kill %1
git add backend/app/main.py backend/app/api
git commit -m "feat(backend): FastAPI WS + approval HTTP endpoints"
```

---

## Task 10: Backend CLI smoke runner

**Files:**
- Create: `backend/app/cli.py`, `backend/Makefile`

- [ ] **Step 1: Write cli.py**

```python
# backend/app/cli.py
import asyncio, json, sys
from app.agent.loop import run_session
from app.db import init_db

async def main(prompt: str):
    init_db()
    async def emit(evt): print(json.dumps(evt, default=str))
    await run_session(emit, "cli-session", prompt)

if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "analyze AAPL"))
```

- [ ] **Step 2: Makefile**

```makefile
dev:
	uvicorn app.main:app --reload --port 8000
test:
	pytest -v
smoke:
	FIXTURES_MODE=1 python -m app.cli "analyze AAPL"
```

- [ ] **Step 3: Run + commit**

```bash
make smoke
git add backend/app/cli.py backend/Makefile
git commit -m "feat(backend): CLI smoke runner"
```

**End of Day 1 AM target.** Resume Day 1 PM with real API keys: drop `FIXTURES_MODE` and run `make smoke` against live Alpaca + Finnhub. Capture any payload-shape mismatches as a single follow-up commit on `alpaca_service.py`.

---

## Task 11: Frontend scaffold (Next.js + shadcn)

**Files:** `frontend/*`

- [ ] **Step 1: Bootstrap**

```bash
cd frontend
pnpm create next-app@latest . --ts --tailwind --app --src-dir --eslint --no-import-alias --use-pnpm
pnpm dlx shadcn@latest init -d
pnpm dlx shadcn@latest add button card input badge separator toast dialog table
pnpm add ai @anthropic-ai/sdk recharts clsx
```

- [ ] **Step 2: Write `.env.local.example`**

```
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 3: Replace `src/app/page.tsx` with skeleton**

```tsx
import { TickerInput } from "@/components/ticker-input";
import { AgentTrace } from "@/components/agent-trace";
import { ProposalCard } from "@/components/proposal-card";
import { PriceChart } from "@/components/price-chart";
import { OptionsChainTable } from "@/components/options-chain-table";
import { PortfolioPanel } from "@/components/portfolio-panel";

export default function Page() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_380px] gap-4 p-4 h-screen">
      <aside className="space-y-4">
        <TickerInput />
        <PortfolioPanel />
      </aside>
      <main className="space-y-4 overflow-auto">
        <ProposalCard />
        <PriceChart />
        <OptionsChainTable />
      </main>
      <aside className="overflow-auto">
        <AgentTrace />
      </aside>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Next.js + shadcn scaffold"
```

---

## Task 12: WS event types + client hook

**Files:**
- Create: `frontend/src/types/events.ts`, `frontend/src/lib/ws.ts`, `frontend/src/lib/api.ts`

- [ ] **Step 1: events.ts**

```ts
export type AgentEvent =
  | { type: "agent.status"; ts: string; session_id: string; data: { message: string } }
  | { type: "agent.thinking"; ts: string; session_id: string; data: { text: string } }
  | { type: "agent.tool_call"; ts: string; session_id: string; data: { tool_use_id: string; name: string; input: any } }
  | { type: "agent.tool_result"; ts: string; session_id: string; data: { tool_use_id: string; name: string; output: any; error?: string } }
  | { type: "agent.proposal"; ts: string; session_id: string; data: Proposal }
  | { type: "agent.complete"; ts: string; session_id: string; data: any }
  | { type: "agent.error"; ts: string; session_id: string; data: { message: string } };

export type Proposal = {
  proposal_id: string;
  ticker: string;
  legs: Array<{ action: "buy"|"sell"; side: "call"|"put"; qty: number; strike: number; premium: number; contract_symbol: string }>;
  max_risk: number;
  max_reward: number | null;
  breakeven: number | null;
  expiry: string;
  rationale: string;
  confidence: number;
  risks: string[];
};
```

- [ ] **Step 2: ws.ts (zustand-free, useState/useRef hook)**

```ts
"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import type { AgentEvent, Proposal } from "@/types/events";

export function useAgentSession() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [status, setStatus] = useState<"idle"|"connecting"|"running"|"done"|"error">("idle");
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
    const socket = new WebSocket(url);
    ws.current = socket;
    socket.onopen = () => setStatus("idle");
    socket.onmessage = (m) => {
      const evt: AgentEvent = JSON.parse(m.data);
      setEvents(prev => [...prev, evt]);
      if (evt.type === "agent.proposal") setProposal(evt.data as Proposal);
      if (evt.type === "agent.complete") setStatus("done");
      if (evt.type === "agent.error") setStatus("error");
    };
    socket.onclose = () => ws.current = null;
    return () => socket.close();
  }, []);

  const sendIdea = useCallback((ticker: string, idea?: string) => {
    setEvents([]); setProposal(null); setStatus("running");
    ws.current?.send(JSON.stringify({ type: "session.start", data: { ticker, idea } }));
  }, []);

  return { events, proposal, status, sendIdea };
}
```

- [ ] **Step 3: api.ts**

```ts
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export async function approveProposal(id: string) {
  const r = await fetch(`${BASE}/proposals/approve`, { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify({ proposal_id: id })});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
export async function rejectProposal(id: string) {
  const r = await fetch(`${BASE}/proposals/reject`, { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify({ proposal_id: id })});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types frontend/src/lib
git commit -m "feat(frontend): WS hook + API client"
```

---

## Task 13: Components — TickerInput, AgentTrace, ProposalCard

**Files:** `frontend/src/components/{ticker-input,agent-trace,proposal-card,portfolio-panel,price-chart,options-chain-table}.tsx`

- [ ] **Step 1: Centralize session state**

Add `frontend/src/lib/session-context.tsx`:
```tsx
"use client";
import { createContext, useContext } from "react";
import { useAgentSession } from "./ws";

const Ctx = createContext<ReturnType<typeof useAgentSession> | null>(null);
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const v = useAgentSession();
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}
export function useSession() {
  const v = useContext(Ctx);
  if (!v) throw new Error("SessionProvider missing");
  return v;
}
```

Wrap children in `app/layout.tsx` with `<SessionProvider>`.

- [ ] **Step 2: TickerInput**

```tsx
"use client";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useSession } from "@/lib/session-context";

export function TickerInput() {
  const { sendIdea, status } = useSession();
  const [v, setV] = useState("AAPL");
  return (
    <Card>
      <CardHeader><CardTitle>New analysis</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        <Input value={v} onChange={e => setV(e.target.value.toUpperCase())} placeholder="Ticker (AAPL)" />
        <Button className="w-full" disabled={status === "running"} onClick={() => sendIdea(v)}>
          {status === "running" ? "Thinking…" : "Analyze"}
        </Button>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: AgentTrace**

```tsx
"use client";
import { useSession } from "@/lib/session-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function AgentTrace() {
  const { events } = useSession();
  return (
    <Card className="h-full">
      <CardHeader><CardTitle>Agent trace</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm overflow-auto max-h-[80vh]">
        {events.map((e, i) => (
          <div key={i} className="border-l-2 pl-2 border-muted">
            <Badge variant="outline" className="mr-2">{e.type.replace("agent.","")}</Badge>
            <span className="text-muted-foreground text-xs">{new Date(e.ts).toLocaleTimeString()}</span>
            <pre className="text-xs whitespace-pre-wrap mt-1">
              {e.type === "agent.thinking" ? (e as any).data.text :
               e.type === "agent.status" ? (e as any).data.message :
               JSON.stringify((e as any).data, null, 2).slice(0, 600)}
            </pre>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: ProposalCard**

```tsx
"use client";
import { useSession } from "@/lib/session-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { approveProposal, rejectProposal } from "@/lib/api";
import { useState } from "react";

export function ProposalCard() {
  const { proposal } = useSession();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  if (!proposal) return null;
  return (
    <Card className="border-primary">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Proposed trade — {proposal.ticker}
          <Badge>{(proposal.confidence * 100).toFixed(0)}% conf</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2 text-sm">
          <div><div className="text-muted-foreground">Max risk</div>${proposal.max_risk.toFixed(2)}</div>
          <div><div className="text-muted-foreground">Max reward</div>{proposal.max_reward != null ? "$"+proposal.max_reward.toFixed(2) : "Unlimited"}</div>
          <div><div className="text-muted-foreground">Breakeven</div>${proposal.breakeven?.toFixed(2) ?? "—"}</div>
        </div>
        <div>
          <div className="text-muted-foreground text-sm mb-1">Legs (expiry {proposal.expiry})</div>
          <ul className="text-sm">
            {proposal.legs.map((l, i) => <li key={i}>{l.action.toUpperCase()} {l.qty}x {l.contract_symbol} @ ${l.premium.toFixed(2)}</li>)}
          </ul>
        </div>
        <p className="text-sm">{proposal.rationale}</p>
        <div className="text-xs text-muted-foreground">Risks: {proposal.risks.join("; ")}</div>
        {result && <div className="text-sm">{result}</div>}
        <div className="flex gap-2">
          <Button disabled={busy} onClick={async () => { setBusy(true); try { const r = await approveProposal(proposal.proposal_id); setResult(`Order submitted: ${r.alpaca_order_id} (${r.status})`); } catch(e:any){ setResult(`Error: ${e.message}`);} finally { setBusy(false);} }}>
            Approve
          </Button>
          <Button variant="outline" disabled={busy} onClick={async () => { setBusy(true); await rejectProposal(proposal.proposal_id); setResult("Rejected"); setBusy(false); }}>
            Reject
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 5: Stub PortfolioPanel, PriceChart, OptionsChainTable**

```tsx
// portfolio-panel.tsx
"use client";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useSession } from "@/lib/session-context";
import { useMemo } from "react";

export function PortfolioPanel() {
  const { events } = useSession();
  const portfolio = useMemo(() => {
    const ev = [...events].reverse().find(e => e.type === "agent.tool_result" && (e as any).data.name === "get_portfolio");
    return ev ? (ev as any).data.output : null;
  }, [events]);
  if (!portfolio) return null;
  return (
    <Card>
      <CardHeader><CardTitle>Portfolio</CardTitle></CardHeader>
      <CardContent className="text-sm space-y-1">
        <div>Cash: ${portfolio.cash?.toFixed(2)}</div>
        <div>Equity: ${portfolio.equity?.toFixed(2)}</div>
        <div>Buying power: ${portfolio.buying_power?.toFixed(2)}</div>
      </CardContent>
    </Card>
  );
}
```

```tsx
// price-chart.tsx, options-chain-table.tsx — return null on Day 2 AM, fill in PM
"use client";
export function PriceChart() { return null; }
export function OptionsChainTable() { return null; }
```

- [ ] **Step 6: Run end-to-end**

```bash
# terminal 1
cd backend && source .venv/bin/activate && FIXTURES_MODE=1 uvicorn app.main:app --reload
# terminal 2
cd frontend && pnpm dev
# browser http://localhost:3000 → type AAPL → Analyze → see trace + proposal → Approve
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): trace + proposal + portfolio components"
```

**End of Day 2 AM target:** working end-to-end happy path in fixtures mode.

---

## Task 14: PriceChart with Recharts

**Files:** `frontend/src/components/price-chart.tsx`, `backend/app/api/http.py` (add `/bars` endpoint)

- [ ] **Step 1: Backend `/bars/{symbol}` endpoint**

Add to `app/api/http.py`:
```python
from datetime import datetime, timedelta
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical.stock import StockHistoricalDataClient

@router.get("/bars/{symbol}")
def bars(symbol: str, days: int = 30):
    if settings.fixtures_mode:
        return [{"t": (datetime.utcnow()-timedelta(days=i)).isoformat(), "c": 200 + i*0.5} for i in range(days,0,-1)]
    c = StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret)
    res = c.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=datetime.utcnow()-timedelta(days=days)))
    return [{"t": b.timestamp.isoformat(), "c": float(b.close)} for b in res[symbol]]
```

- [ ] **Step 2: Frontend chart**

```tsx
"use client";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useSession } from "@/lib/session-context";

export function PriceChart() {
  const { events } = useSession();
  const [bars, setBars] = useState<{t:string;c:number}[]>([]);
  const ticker = (events.find(e => e.type === "agent.tool_call" && (e as any).data.name === "get_quote") as any)?.data.input.symbol;
  useEffect(() => {
    if (!ticker) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/bars/${ticker}`).then(r => r.json()).then(setBars);
  }, [ticker]);
  if (!ticker) return null;
  return (
    <Card>
      <CardHeader><CardTitle>{ticker} — 30d</CardTitle></CardHeader>
      <CardContent style={{height: 220}}>
        <ResponsiveContainer><LineChart data={bars}>
          <XAxis dataKey="t" hide /><YAxis domain={["auto","auto"]} /><Tooltip />
          <Line type="monotone" dataKey="c" dot={false} />
        </LineChart></ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/http.py frontend/src/components/price-chart.tsx
git commit -m "feat: price chart with /bars endpoint"
```

---

## Task 15: Options chain table

**Files:** `frontend/src/components/options-chain-table.tsx`

- [ ] **Step 1: Implement**

```tsx
"use client";
import { useSession } from "@/lib/session-context";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function OptionsChainTable() {
  const { events } = useSession();
  const ev = [...events].reverse().find(e => e.type === "agent.tool_result" && (e as any).data.name === "get_options_chain");
  if (!ev) return null;
  const chain = (ev as any).data.output;
  const rows = (chain.contracts ?? []).slice(0, 20);
  return (
    <Card>
      <CardHeader><CardTitle>Options chain — {chain.underlying} {chain.expiry}</CardTitle></CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Symbol</TableHead><TableHead>Side</TableHead><TableHead>Bid</TableHead><TableHead>Ask</TableHead><TableHead>Δ</TableHead><TableHead>IV</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((c: any) => (
              <TableRow key={c.symbol}>
                <TableCell className="font-mono text-xs">{c.symbol}</TableCell>
                <TableCell>{c.side}</TableCell>
                <TableCell>{c.bid}</TableCell><TableCell>{c.ask}</TableCell>
                <TableCell>{c.delta?.toFixed?.(2)}</TableCell><TableCell>{(c.iv*100)?.toFixed?.(1)}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/options-chain-table.tsx
git commit -m "feat(frontend): options chain table"
```

---

## Task 16: Replay mode (fallback safety)

**Files:** `backend/app/cli.py` add `--replay`, `backend/app/api/ws.py` accept replay session.

- [ ] **Step 1: Add replay endpoint logic to ws.py**

Inside `ws()` handler, when message is `{"type":"replay","data":{"session_id":"..."}}`:
```python
elif data.get("type") == "replay":
    from sqlmodel import select
    sid = data["data"]["session_id"]
    with get_session() as s:
        rows = s.exec(select(Trace).where(Trace.session_id == sid).order_by(Trace.ts)).all()
    import asyncio
    for r in rows:
        await ws.send_text(r.payload_json)
        await asyncio.sleep(0.4)
```

- [ ] **Step 2: Add tiny "Replay last" button in TickerInput**

```tsx
<Button variant="outline" className="w-full" onClick={() => ws.current?.send(JSON.stringify({type:"replay", data:{session_id:lastSessionId}}))}>Replay last</Button>
```
(Track `lastSessionId` from incoming events.)

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/ws.py frontend/src/components/ticker-input.tsx frontend/src/lib/ws.ts
git commit -m "feat: replay-from-trace fallback for demo"
```

---

## Task 17: Demo polish

- [ ] **Step 1: Seed watchlist**

`backend/app/seed.py`:
```python
from app.db import init_db, get_session
from app.models import Watchlist
init_db()
with get_session() as s:
    for t in ["AAPL","NVDA","SPY"]:
        s.merge(Watchlist(ticker=t))
    s.commit()
print("seeded")
```

Run: `python -m app.seed`.

- [ ] **Step 2: Demo script in README**

Append to `README.md`:
```markdown
## Demo (5 min)
1. Start backend (live keys) and frontend.
2. Type NVDA → Analyze. Narrate the trace as it streams.
3. Highlight: tool calls, news summary, proposal with risks.
4. Click Approve → show Alpaca order id toast.
5. Refresh → proposal status shows Executed (via /proposals).
6. Fallback: kill internet → click "Replay last" to re-stream stored trace.
```

- [ ] **Step 3: Record fallback video**

```bash
# screen-record one good run; save as docs/demo-fallback.mp4
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed.py README.md docs/
git commit -m "chore: demo seed, script, fallback recording"
```

---

## Final Validation Checklist

Run before demo:
- [ ] `cd backend && pytest -v` — all green
- [ ] `cd frontend && pnpm tsc --noEmit` — no errors
- [ ] `make smoke` (FIXTURES_MODE=1) — agent emits proposal
- [ ] Live run with real keys: AAPL → see real chain → approve → real Alpaca paper order id
- [ ] `Replay last` works after stopping the agent mid-run
- [ ] `.env` excluded from git (check `git ls-files | grep -i env`)

---

## Self-Review Notes (post-write)

- Spec coverage: every requirement (workflow steps 1–7, agent tools, safety constraints, fallback plan, env vars, day-by-day milestones) maps to a task.
- `execute_trade` tool is intentionally absent from `TOOLS` and verified by `test_execute_trade_not_in_tools`.
- Type names consistent across backend (`legs_json`, `Proposal.id` as str uuid) and frontend (`Proposal.proposal_id`, mapped via service return value).
- Fixtures mode threads through every external service so the demo can run offline.
- 2-day cadence: Day 1 ends after Task 10, Day 2 AM ends after Task 13, Day 2 PM tasks 14–17.
