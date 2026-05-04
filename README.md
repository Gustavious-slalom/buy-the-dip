# Trading Agent PoC

Hackathon PoC: Claude-powered options trading copilot on Alpaca paper trading.

## Quick start
- Backend: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e . && uvicorn app.main:app --reload`
- Frontend: `cd frontend && pnpm install && pnpm dev`

See `docs/superpowers/plans/2026-05-04-trading-agent-poc.md` for the implementation plan.

## Demo (5 min)

1. Start backend (live keys) and frontend.
2. Type NVDA → Analyze. Narrate the trace as it streams.
3. Highlight: tool calls, news summary, proposal with risks.
4. Click Approve → show Alpaca order id toast.
5. Refresh → proposal status shows Executed (via /proposals).
6. Fallback: kill internet → click "Replay last" to re-stream stored trace.
