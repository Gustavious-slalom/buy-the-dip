# Buy the Dip — Trading Agent PoC

A Claude-powered options trading copilot. The agent analyzes a ticker, fetches live market data and news, then proposes an options trade with full reasoning streamed live to a Next.js dashboard. Paper trades only execute after explicit user approval.

## Architecture

```
Next.js (App Router)  ←──WebSocket──→  FastAPI backend
     │                                      │
     │  TickerInput → AgentTrace            │  Claude Sonnet (streaming)
     │  ProposalCard (Approve/Reject)        │  Alpaca paper trading
     │  PriceChart (Recharts)               │  Finnhub news + Haiku summary
     └──────────── REST (approve/reject) ───┘  SQLite (proposals, traces)
```

**Safety invariant:** `execute_trade` is never callable by the agent — paper orders only execute on `POST /proposals/approve`.

## Tech stack

| Layer | Tech |
|---|---|
| Agent | Claude Sonnet 4.5, Haiku 4.5 (news summary) |
| Backend | Python 3.11+, FastAPI, SQLModel, SQLite |
| Market data | alpaca-py (paper), Finnhub |
| Frontend | Next.js 16, TypeScript, Tailwind, shadcn/ui, Recharts |

## Setup

### 1. Clone & configure

```bash
git clone https://github.com/Gustavious-slalom/buy-the-dip.git
cd buy-the-dip
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, ALPACA_API_KEY, ALPACA_API_SECRET, FINNHUB_API_KEY
```

**Required env vars:**

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ALPACA_API_KEY` | Alpaca paper trading key |
| `ALPACA_API_SECRET` | Alpaca paper trading secret |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` (default) |
| `FINNHUB_API_KEY` | Finnhub API key (free tier works) |
| `MAX_RISK_USD` | Max risk per trade in USD (default: 5000) |
| `FIXTURES_MODE` | `1` to skip all external API calls (offline demo) |

### 3. Frontend

```bash
cd frontend
pnpm install

cp .env.local.example .env.local
# NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running

```bash
# Terminal 1 — backend
cd backend && source .venv/bin/activate
make dev          # uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
pnpm dev          # http://localhost:3000
```

### Offline / fixture mode (no API keys needed)

```bash
cd backend && source .venv/bin/activate
make smoke        # FIXTURES_MODE=1, runs one agent session via CLI
```

### Seed watchlist

```bash
cd backend && source .venv/bin/activate
python -m app.seed    # adds AAPL, NVDA, SPY to watchlist
```

## Tests

```bash
cd backend && source .venv/bin/activate
make test         # pytest -v (11 tests)

cd frontend
pnpm tsc --noEmit  # TypeScript check
pnpm build         # production build
```

## Demo (5 min)

1. Start backend (live keys) and frontend.
2. Type **NVDA** → **Analyze**. Narrate the agent trace as it streams.
3. Highlight: tool calls, news summary, proposal with risk breakdown.
4. Click **Approve** → Alpaca paper order ID appears.
5. Refresh → proposal status shows **Executed** (via `GET /proposals`).
6. Fallback: no internet → click **Replay last** to re-stream the stored trace.

## API reference

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WS | Agent session stream + replay |
| `/proposals` | GET | List all proposals |
| `/proposals/approve` | POST | Execute paper trade |
| `/proposals/reject` | POST | Reject proposal |
| `/bars/{symbol}` | GET | 30-day price bars (OHLC) |
