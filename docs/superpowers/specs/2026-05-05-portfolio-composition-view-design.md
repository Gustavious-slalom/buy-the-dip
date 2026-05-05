# Portfolio Composition View — Design Spec

**Date:** 2026-05-05
**Status:** Approved (brainstorming complete; awaiting implementation plan)
**Branch context:** authored on `feat/terminal-redesign`

## Goal

Add a dedicated `/portfolio` view that shows the user the full composition of their Alpaca paper account: account stats, open positions, multi-leg strategies grouped from local proposal history, allocation breakdown, equity curve, and a recent-activity log.

Today the only portfolio surface is a small left-rail `PortfolioPanel` in the trading dashboard that renders cash / equity / buying power, sourced opportunistically from `agent.tool_result` events when the agent happens to call `get_portfolio`. That is insufficient as a standalone surface.

## Scope

### In scope

- New Next.js route `/portfolio` reachable via a top-bar nav link from `/`.
- Two new backend endpoints: `GET /portfolio/snapshot` and `GET /portfolio/equity-curve?period=...`.
- New backend service module `app/services/portfolio_service.py` aggregating Alpaca + local DB data.
- Six new frontend components (account summary, equity curve, allocation, strategies list, positions table, history table).
- Manual refresh button + automatic refetch after approve/reject in this app.
- Fixtures for offline (`FIXTURES_MODE=1`) demo support.

### Out of scope (deliberate, YAGNI)

- No new agent tool — agent already has `get_portfolio` / `get_positions`; this is a read-only UI surface.
- No realtime WebSocket push of portfolio changes.
- No grouping of positions that did not originate from this app's `Proposal` table (those show as flat positions only).
- No CSV export, tax-lot tracking, or realized-P&L beyond what's in the proposals table.

## Decisions captured during brainstorming

| # | Question | Choice | Rationale |
|---|---|---|---|
| Q1 | Surface shape | New route at `/portfolio` | Trading dashboard at `/` stays focused; portfolio gets its own canvas. |
| Q2 | Content | All of: account, positions, allocation, options-strategy grouping, history, equity curve | Single comprehensive view. |
| Q3 | Data freshness | On-load + after every approve/reject + manual refresh button | Zero new infra; freshest data when it matters. |
| Q4 | Options grouping aggressiveness | Conservative — only group via local `Proposal` rows | Hackathon paper account; trivial join; flat positions are an acceptable fallback for non-app trades. |
| Q5 | Equity curve source | Alpaca `portfolio_history` API | Accurate broker-side time series; ~30 LoC backend. |

Approach for backend shape: **Hybrid — one bundled snapshot endpoint + a separate equity-curve endpoint** (chosen over single-bundled or fully-decomposed). The equity curve is split out because it has its own period parameter and its own Alpaca endpoint.

## Architecture

### Backend (`backend/app/`)

**New module — `app/services/portfolio_service.py`**

Pure business logic, no FastAPI imports. Functions:

- `build_snapshot() -> PortfolioSnapshot` — orchestrates the full snapshot. Calls `alpaca_service.get_portfolio()`, `alpaca_service.get_positions()`, `alpaca_service.get_latest_prices(symbols)`, queries local `Proposal` + `Execution`. Computes weights, allocations, joins positions to proposals to build strategy groupings. Returns a partial snapshot (with an `errors: list[str]` field) if any individual source fails.
- `get_equity_curve(period: Literal["1D","1W","1M","3M","ALL"]) -> EquityCurve` — wraps `alpaca_service.get_portfolio_history(period)`.
- `_group_strategies(positions, proposals) -> list[StrategyGroup]` — for each `Proposal` whose `legs_json` matches a subset of currently-held option contracts, build one strategy row. Compute cost basis (sum of leg avg-entry × qty × side-sign) and current value (sum of leg current-price × qty × side-sign).
- `_compute_allocations(positions, account) -> Allocations` — `by_kind` (stock / option / cash percentages of total equity) and `by_underlying` (sum of |market_value| grouped by underlying ticker for options, by symbol for stocks).

**Extended — `app/services/alpaca_service.py`**

Two thin additions; both honor `FIXTURES_MODE`:

- `get_portfolio_history(period: str) -> dict` — calls alpaca-py's `TradingClient.get_portfolio_history()` (or the equivalent REST GET if not exposed); returns `{period, points: [{t, equity}], base_value, profit_loss, profit_loss_pct}`.
- `get_latest_prices(symbols: list[str]) -> dict[str, float]` — batched quote fetch. For stock symbols use `StockLatestQuoteRequest` with multi-symbol; for option contracts use `OptionLatestQuoteRequest`. Returns `{symbol: mid_price}`. Missing symbols mapped to `None`.

**Extended — `app/api/http.py`**

Two new routes:

- `GET /portfolio/snapshot` → `PortfolioSnapshot` (always 200 if any source succeeds; partial failures surface in `errors`).
- `GET /portfolio/equity-curve?period=1M` → `EquityCurve`. Validates `period` against `{1D,1W,1M,3M,ALL}`; 400 on bad value.

Both endpoints sit behind the existing bearer-token auth (commit `825e55f`).

### Frontend (`frontend/src/`)

**New route — `app/portfolio/page.tsx`**

Server component shell that renders a client `<PortfolioView />`.

**New client view — `components/portfolio/portfolio-view.tsx`**

Owns the page-level data: holds snapshot + equity-curve state, exposes `refresh()`. Subscribes to a portfolio-invalidate event so approvals on `/` trigger a refetch.

**New components in `components/portfolio/`:**

- `portfolio-header.tsx` — title, last-updated timestamp, manual Refresh button, "← Trade" link back to `/`.
- `account-summary.tsx` — equity / day P&L / cash / buying power band.
- `equity-curve.tsx` — Recharts line chart with period toggle (1D / 1W / 1M / 3M / ALL). Owns its own `period` state and refetches `/portfolio/equity-curve` on toggle.
- `allocation-card.tsx` — donut (stock / option / cash) + horizontal bar list of top underlyings.
- `strategies-list.tsx` — collapsible rows for each grouped strategy.
- `positions-table.tsx` — sortable table of flat positions.
- `history-table.tsx` — last 20 rows from `Proposal` + `Execution`.

Each card owns its own skeleton/loading state and its own error fallback ("couldn't load — retry").

**Extended — `lib/api.ts`**

Add:

- `getPortfolioSnapshot(): Promise<PortfolioSnapshot>`
- `getEquityCurve(period: Period): Promise<EquityCurve>`

**New — `lib/portfolio-events.ts`**

Tiny event emitter (`window.dispatchEvent(new CustomEvent("portfolio:invalidate"))` plus a `usePortfolioInvalidation(cb)` hook). `proposal-card.tsx` fires the event on successful approve/reject; `portfolio-view.tsx` listens.

**Layout shell — `app/layout.tsx`**

Add a top-right nav link toggling between **Trade** (`/`) and **Portfolio** (`/portfolio`). Reuse existing terminal aesthetic tokens (`--hairline`, `--fg-dim`, smallcaps headings, mono fonts) — no new design system.

### Data shapes

```ts
type Period = "1D" | "1W" | "1M" | "3M" | "ALL";

type PositionKind = "stock" | "option";

type Position = {
  symbol: string;            // OCC for options, ticker for stocks
  kind: PositionKind;
  qty: number;
  avg_entry: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null; // % of total equity
  // option-only:
  underlying?: string;
  strike?: number;
  side?: "call" | "put";
  expiry?: string;           // ISO date
};

type StrategyGroup = {
  proposal_id: string;
  ticker: string;
  type: string;              // e.g. "bull-call-spread", "long-call"
  legs: { symbol: string; qty: number; side: "buy" | "sell" }[];
  cost_basis: number;
  current_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  expiry: string;
  legs_open: number;         // n open legs
  legs_total: number;        // n original legs
};

type Allocations = {
  by_kind: { stock: number; option: number; cash: number }; // percentages summing to ~100
  by_underlying: { ticker: string; weight_pct: number; market_value: number }[];
};

type HistoryRow = {
  proposal_id: string;
  ticker: string;
  status: "pending" | "approved" | "rejected" | "executed" | "failed";
  created_at: string;
  executed_at?: string;
  alpaca_order_id?: string;
};

type PortfolioSnapshot = {
  fetched_at: string;
  account: {
    cash: number;
    equity: number;
    buying_power: number;
    day_pl: number | null;
    day_pl_pct: number | null;
  };
  positions: Position[];
  strategies: StrategyGroup[];
  allocations: Allocations;
  history: HistoryRow[];
  errors: string[];          // e.g. ["positions_unavailable"]
};

type EquityCurve = {
  period: Period;
  points: { t: string; equity: number }[];
  base_value: number;
  profit_loss: number;
  profit_loss_pct: number;
};
```

## Page layout

```
┌────────────────────────────────────────────────────────────────────┐
│  PORTFOLIO          last updated 14:02:31  ⟳ Refresh   [← Trade]  │
├────────────────────────────────────────────────────────────────────┤
│  EQUITY  $124,318      DAY P/L  +$842 (+0.68%)                     │
│  CASH    $42,103       BUYING POWER  $84,206                       │
├──────────────────────────────────────┬─────────────────────────────┤
│ EQUITY CURVE       [1D 1W 1M 3M ALL] │  ALLOCATION                 │
│ (line chart, recharts)               │  (donut: stock / option /   │
│                                      │   cash + by-ticker bars)    │
├──────────────────────────────────────┴─────────────────────────────┤
│ STRATEGIES (grouped multi-leg from local Proposals)                │
│ ▸ NVDA bull-call-spread  exp 2026-06-19  cost $1,240  now $1,580  │
│   +$340 (+27%)  • 2 legs                                           │
│ ▸ AAPL long-call         exp 2026-07-18  cost $620    now $510    │
├────────────────────────────────────────────────────────────────────┤
│ POSITIONS (flat)                                                   │
│ symbol      kind  qty  avg   current  mkt val   P/L    weight     │
│ NVDA250...  opt   2   6.20   7.90     $1,580   +$340   1.27%      │
│ AAPL250...  opt   1   6.20   5.10     $510     -$110   0.41%      │
│ SPY         stk   100 480.10 482.55   $48,255  +$245   38.8%      │
├────────────────────────────────────────────────────────────────────┤
│ HISTORY (recent proposals)                                         │
│ NVDA   bull-call-spread   executed   2026-05-04 14:02   order#42  │
│ TSLA   long-put           rejected   2026-05-03 09:15             │
└────────────────────────────────────────────────────────────────────┘
```

**Grid:** 12-col responsive. Equity curve = 8 cols, Allocation = 4 cols (side-by-side on lg+; stacked on sm).

**Mobile:** single-column stack; allocation moves below curve.

## Data flow

1. User navigates to `/portfolio`. `<PortfolioView />` mounts.
2. `useEffect` triggers parallel fetches: `getPortfolioSnapshot()` and `getEquityCurve("1M")`.
3. Each card renders skeleton until its data arrives; cards never block each other.
4. User clicks **Refresh** → both fetches re-run; `last updated` timestamp advances.
5. User toggles equity curve period → only `getEquityCurve(newPeriod)` re-runs.
6. User goes back to `/`, approves a proposal. `proposal-card.tsx` fires `portfolio:invalidate`. Next time `/portfolio` mounts (or if it was kept alive), the snapshot refetches.
7. On the backend, `/portfolio/snapshot` calls `portfolio_service.build_snapshot()`, which: calls Alpaca for account + positions, batches a quote fetch for the union of held symbols, queries the DB for `Proposal` + `Execution`, computes derived fields, and returns the snapshot.

## Error handling

- **Per-card error fallback** — each frontend card renders its own retry UI; one failure doesn't blank the page.
- **Partial backend failures** — `/portfolio/snapshot` returns 200 with `errors: [...]` rather than 500ing if a single source (e.g. positions, prices) throws. Account, history, allocations still populate from what worked.
- **Stale prices** — if the quote fetch for one symbol fails, that position's `current_price` / `market_value` / `unrealized_pl` / `weight_pct` are `null`; UI shows `—`. Sort orders treat null as last.
- **Empty equity history** — fresh paper accounts have no `portfolio_history`; chart renders "not enough history yet" instead of an empty plot.
- **Expired option still reported** — filter positions with `qty == 0`.
- **Partially-closed strategy** — when only some legs of a `Proposal` remain in positions, render `(N of M legs open)` and compute current value from open legs only.
- **Bad period param** — `/portfolio/equity-curve` returns 400 with a clear message.

## Edge cases

- Fresh paper account, zero positions → strategies + positions empty states; allocation = 100% cash.
- Position exists in Alpaca but no matching `Proposal` → falls into Positions table only, never appears in Strategies.
- Multi-leg `Proposal` partially closed → strategy row shows "(1 of 2 legs open)".
- Option expired but still listed for a day → filtered out (`qty == 0`).
- `MAX_RISK_USD` and paper-only invariants are unchanged — this view is read-only; no order-submission paths touched.

## Testing

### Backend (pytest)

- `test_portfolio_snapshot_fixtures` — under `FIXTURES_MODE=1`, returns a deterministic snapshot with a stock + a 2-leg option spread; asserts weights sum ≈ 100, allocation buckets correct, strategies grouped from a seeded `Proposal`.
- `test_portfolio_snapshot_partial_failure` — mock Alpaca positions raising; assert response is 200 with `errors == ["positions_unavailable"]` and account block still populated.
- `test_equity_curve_period_param` — assert each of `1D / 1W / 1M / 3M / ALL` maps to the right alpaca-py request and returns the expected shape; assert 400 on an invalid period.
- `test_strategy_grouping` — seed two `Proposal` rows (one 2-leg spread, one single-leg) plus matching positions; assert the spread groups into one strategy row and the single-leg appears under both Strategies and Positions.
- `test_strategy_partial_close` — seed a 2-leg proposal where only one leg is in positions; assert `legs_open == 1`, `legs_total == 2`, and `current_value` reflects the single open leg.

### Frontend

- `pnpm tsc --noEmit` and `pnpm build` must stay green.
- Manual smoke (added to demo flow):
  1. Navigate to `/portfolio` → all cards render.
  2. Toggle equity-curve period through 1D/1W/1M/3M/ALL → only the curve refetches; other cards stable.
  3. Click Refresh → `last updated` advances; cards re-skeleton briefly then re-render.
  4. Go to `/`, approve a proposal, return to `/portfolio` → snapshot reflects the new strategy/position.

### Fixtures

- `backend/tests/fixtures/portfolio_snapshot.json` — canned account + positions for offline mode.
- `backend/tests/fixtures/equity_curve_1m.json` — canned 30-point curve.

## File-touch summary

**New files:**
- `backend/app/services/portfolio_service.py`
- `backend/tests/fixtures/portfolio_snapshot.json`
- `backend/tests/fixtures/equity_curve_1m.json`
- `backend/tests/test_portfolio_service.py`
- `frontend/src/app/portfolio/page.tsx`
- `frontend/src/components/portfolio/portfolio-view.tsx`
- `frontend/src/components/portfolio/portfolio-header.tsx`
- `frontend/src/components/portfolio/account-summary.tsx`
- `frontend/src/components/portfolio/equity-curve.tsx`
- `frontend/src/components/portfolio/allocation-card.tsx`
- `frontend/src/components/portfolio/strategies-list.tsx`
- `frontend/src/components/portfolio/positions-table.tsx`
- `frontend/src/components/portfolio/history-table.tsx`
- `frontend/src/lib/portfolio-events.ts`

**Modified files:**
- `backend/app/services/alpaca_service.py` — add `get_portfolio_history`, `get_latest_prices`.
- `backend/app/api/http.py` — add `/portfolio/snapshot`, `/portfolio/equity-curve` routes.
- `frontend/src/lib/api.ts` — add `getPortfolioSnapshot`, `getEquityCurve`.
- `frontend/src/app/layout.tsx` — add Trade / Portfolio nav link.
- `frontend/src/components/proposal-card.tsx` — fire `portfolio:invalidate` on approve/reject.

## Open questions

None at spec time. Implementation plan will address ordering and any further decisions surfaced during build.
