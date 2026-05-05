# Hot-News Recommendations — Design Spec

**Date:** 2026-05-05
**Status:** Approved (brainstorming complete; awaiting implementation plan)
**Branch context:** authored on `feat/terminal-redesign` (pushed to origin)

## Goal

Add a new `/recommendations` screen that produces a ranked list of lightweight trade ideas based on hot news. Each card surfaces a ticker, a directional bias (bullish / bearish / neutral), a confidence score, a short rationale, and the top 1–3 headlines that drove it. Tapping a card jumps to the existing trading flow on `/` with the ticker pre-filled and auto-submitted.

The screen is generated on demand: the user clicks **Generate**, the backend runs a small per-ticker mini-agent for each candidate in parallel, and cards stream in over WebSocket as they finish.

## Scope

### In scope

- New Next.js route `/recommendations` reachable via a top-bar nav link from `/`.
- New backend service `app/services/recommendation_service.py` with discovery + per-ticker generation + orchestration.
- Per-ticker mini-agent prompt (`app/agent/recommendation_prompt.py`) using the configured Haiku model.
- WebSocket message taxonomy on the existing `/ws`: `recommendation.start` → `recommendation.discovery` → `recommendation.card` (×N) → `recommendation.complete`.
- New REST `GET /recommendations/latest` so the page can render the last run on visit.
- New `RecommendationRun` SQLModel table to persist each run.
- Card click-through pre-fills `TickerInput` on `/` and auto-submits.
- Source bucketing: watchlist, positions, market-wide discovery (Finnhub `general_news` → ticker scan).

### Out of scope (deliberate, YAGNI)

- No portfolio-aware scoring ("you already have 30% AAPL exposure"). Portfolio view already exposes that.
- No "save this idea" / favoriting (could be a future `SavedIdea` table).
- No backtest or historical accuracy tracking.
- No notifications, alerts, or push.
- No personalization beyond watchlist + positions + discovery.
- No full options-trade proposal on this screen — only lightweight ideas. Click-through hands off to the existing agent flow.

## Decisions captured during brainstorming

| # | Question | Choice | Rationale |
|---|---|---|---|
| Q1 | Scope of "hot news" | Hybrid (watchlist + positions + market-wide discovery) | Bounded enough to keep cost predictable; broad enough to feel like real discovery. |
| Q2 | Recommendation detail level | Lightweight idea (ticker + bias + rationale + headlines), no option legs | Cheap, fits "summary" framing. The existing `/` agent owns the heavy proposal flow. |
| Q3 | Refresh model | On-demand only — explicit Generate click | Simplest infra; user controls model spend; matches the on-demand framing. |
| Q4 | Generation pipeline | Per-ticker mini-agent in parallel | Parallelizable, easy to fail-soft per ticker, easy to stream cards as they finish. |

Approach for the streaming layer: **WebSocket on the existing `/ws`** (chosen over a synchronous REST POST that returns one JSON blob) so cards pop in as each Haiku call resolves. Reuses the existing WS plumbing and matches the live-agent terminal aesthetic of the rest of the app.

## Architecture

### Backend (`backend/app/`)

**New module — `app/services/recommendation_service.py`**

Pure business logic; no FastAPI imports.

- `discover_candidates() -> CandidateSet` — gathers tickers from three sources:
  - Watchlist via `select(Watchlist)`.
  - Held positions via `alpaca_service.get_positions()`, deduped to underlying ticker (an option contract `AAPL250117C00150000` collapses to `AAPL`).
  - Market-wide news via `news_service.get_general_news()`, regex-scanning headlines + summaries for capitalized tickers in a known whitelist (a static set of ~200 large/mid-cap symbols shipped in the module).
  - Returns `CandidateSet` with three lists, each deduped, plus a global dedup using priority `watchlist > positions > discover` (a ticker only appears once across the three buckets). Caps discover at 5 tickers; total target 8–12.

- `async generate_one(symbol: str, source: Source) -> RecommendationCard` — small async function:
  1. Pull `news_service.get_news(symbol)` (already returns items + a Haiku market-themes summary; we ignore the summary here and use the raw items).
  2. Pull `alpaca_service.get_quote(symbol)` for the latest mid.
  3. Call Haiku with the prompt from `app/agent/recommendation_prompt.py`, requesting strict JSON: `{bias, confidence, rationale, top_headlines}` where `bias ∈ {"bullish","bearish","neutral"}`, `confidence ∈ [0,1]`, `rationale ≤ 280 chars`, `top_headlines = string[]` (≤3, must be exact-match substrings of the news items provided).
  4. On malformed/non-JSON response, retry once with a stricter "respond ONLY with valid JSON" reminder. On the second failure, raise `MalformedRecommendationError`.
  5. Resolve `top_headlines` strings back to `{headline, url}` pairs via the news items list (non-matches are dropped).
  6. Return `RecommendationCard`.

- `async generate_all(emit: Callable[[dict], Awaitable[None]]) -> RecommendationRun` — orchestrator:
  1. `candidates = discover_candidates()`. Emit `recommendation.discovery` event with the buckets.
  2. Build a list of coroutines `[generate_one(sym, src) for each candidate]`.
  3. Run with `asyncio.gather(..., return_exceptions=True)` under a `Semaphore(8)` to throttle.
  4. As each one resolves (use `asyncio.as_completed` to actually emit in finish order, not gather order), call `emit({"type": "recommendation.card", "data": card_or_error_card})`.
  5. After all settle, persist a `RecommendationRun(id=uuid, created_at=now, payload_json=json.dumps({cards, sources}))`.
  6. Emit `recommendation.complete` with `{run_id, generated_at, count}`.
  7. Return the `RecommendationRun` payload.

- `get_latest_run() -> RecommendationRun | None` — DB query for the most-recent `RecommendationRun` ordered by `created_at desc`.

- Failure surfacing in cards: each `generate_one` failure becomes a card with the same shape minus content fields, plus `error: "<short tag>"` (e.g., `"finnhub_429"`, `"unparseable_response"`, `"timeout"`). Frontend renders these in-place.

**New module — `app/agent/recommendation_prompt.py`**

Self-contained, terse system+user prompt builder for the per-ticker call. Returns a single user message string. Strict instructions:

- Output ONLY a JSON object, no markdown fences, no explanation.
- Schema: `{"bias": "bullish"|"bearish"|"neutral", "confidence": float, "rationale": string, "top_headlines": string[]}`.
- `rationale` ≤ 280 chars, plain prose.
- `top_headlines` MUST be exact substrings of the headlines provided in the prompt (so the backend can resolve them back to URLs without hallucinated headlines).

**Extended — `app/services/news_service.py`**

Add `get_general_news() -> list[dict]`:
- Under `FIXTURES_MODE`, read `tests/fixtures/general_news.json`.
- Otherwise call Finnhub `general_news("general")` and return up to ~30 items with `{headline, summary, url, datetime, related}`.

**Extended — `app/api/ws.py`**

The existing `/ws` handler is currently single-purpose (the analyze flow). Add message-type routing:

- On client `{"type": "analyze", ...}` (existing default) — current behavior preserved.
- On client `{"type": "recommendation.start"}` — call `recommendation_service.generate_all(emit=ws_send)` where `ws_send` serializes the dict and writes it to the socket. The handler awaits completion before closing.
- On any other message type — emit `{"type": "error", "data": {"message": "unknown type"}}` and continue.

The current handler already has a tiny dispatcher; we extend it rather than restructure.

**Extended — `app/api/http.py`**

- `GET /recommendations/latest` — returns the most recent `RecommendationRun` payload as JSON, or `{cards: [], sources: {watchlist:[],positions:[],discover:[]}, generated_at: null, run_id: null}` if none exist (200 with empty shape, not 404, so the frontend doesn't need a special case).

**Extended — `app/models.py`**

```python
class RecommendationRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    payload_json: str
```

### Frontend (`frontend/src/`)

**New route — `app/recommendations/page.tsx`**
Server component shell that renders `<RecommendationsView />`.

**New container — `components/recommendations/recommendations-view.tsx`**
Owns the page state. Behavior:
- On mount: fetch `/recommendations/latest`. If non-empty, render with `generated_at` timestamp; otherwise empty state.
- **Generate** button → opens a WS connection (reusing `useWS` from `@/lib/ws`), sends `{"type": "recommendation.start"}`, listens for the three message types.
- On `recommendation.discovery` → render the sources strip immediately + skeleton placeholder rows (one per candidate).
- On `recommendation.card` → replace the matching skeleton with the real card. Update `generating N of M…` counter.
- On `recommendation.complete` → flip status to `done`, store run_id, close WS.
- Disabled state on Generate while `status === "running"`.

**New components in `components/recommendations/`:**
- `recommendation-card.tsx` — single card render: ticker (mono, large), bias badge, confidence bar (10 segments), source pill, rationale, headlines (linked), `Analyze →` button.
- `sources-strip.tsx` — top strip listing the watchlist / positions / discover ticker buckets.

**New types — `frontend/src/types/recommendations.ts`**

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
  | { type: "recommendation.discovery"; data: { sources: CandidateSet } }
  | { type: "recommendation.card"; data: RecommendationCard }
  | { type: "recommendation.complete"; data: { run_id: string; generated_at: string; count: number } }
  | { type: "recommendation.discovery_warning"; data: { message: string } }
  | { type: "error"; data: { message: string } };
```

**New WS wrapper — `lib/recommendations-ws.ts`**
Thin layer around the existing WS hook that types the inbound payloads as `StreamEvent`.

**Extended — `lib/api.ts`**
Add `getLatestRecommendations(): Promise<RecommendationRun>`.

**Extended — `components/status-rail.tsx`**
Insert an `IDEAS` nav link between `Portfolio` and the existing AGENT/NYSE/v0.4.2 cluster, using the same active-state highlighting pattern.

**Extended — `components/ticker-input.tsx`**
Read `?ticker=<sym>&autosubmit=1` from `useSearchParams` on mount: prefill the input and dispatch the existing analyze action when `autosubmit === "1"`. Single-shot — does not re-fire on subsequent searchParam changes.

## Click-through behavior

- Each card's `Analyze →` button does `router.push("/?ticker=" + sym + "&autosubmit=1")`.
- On `/`, `TickerInput` mounts, sees the search params, populates state, and immediately calls the existing analyze handler. From here on the existing agent flow runs unchanged.

## Page layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  IDEAS         generated 14:02:31 · 11 candidates  ⟳ Generate  [← Trade] │
├──────────────────────────────────────────────────────────────────────────┤
│  SOURCES                                                                 │
│  watchlist: AAPL, NVDA, SPY    positions: TSLA, MSFT                     │
│  discover: AMD, META, GOOG, COIN, AVGO  (from market-wide news)          │
├──────────────────────────────────────────────────────────────────────────┤
│  ▸ NVDA  BULLISH  ◼◼◼◼◼◼◼◻◻◻ 0.72   from watchlist                       │
│    Earnings beat + record data-center revenue; sell-side raises          │
│    targets. Upside catalyst likely through Q4.                           │
│    • NVDA Q3 beats on data-center growth (Reuters)                       │
│    • Wall St raises NVDA target to $1,250 (Bloomberg)                    │
│    [ Analyze → ]                                                         │
├──────────────────────────────────────────────────────────────────────────┤
│  ▸ TSLA  BEARISH  ◼◼◼◼◼◻◻◻◻◻ 0.51   from positions                       │
│    Delivery miss + new tariffs on Chinese imports; analyst downgrade     │
│    cycle starting.                                                       │
│    • TSLA misses Q3 deliveries (CNBC)                                    │
│    [ Analyze → ]                                                         │
├──────────────────────────────────────────────────────────────────────────┤
│  ▸ COIN  NEUTRAL  ◼◼◼◻◻◻◻◻◻◻ 0.31   from discover                        │
│    Mixed signals: ETF inflows up, but SEC headlines weigh.               │
│    [ Analyze → ]                                                         │
├──────────────────────────────────────────────────────────────────────────┤
│  ⚠ AMD   couldn't analyze — Finnhub 429 (rate limit). Try refresh.       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Card visuals:**
- Ticker: mono, large
- Bias badge: `BULLISH` (green = `--up`), `BEARISH` (red = `--down`), `NEUTRAL` (`--fg-dim`); uppercase; styled like the BUY/SELL chips in `proposal-card.tsx`.
- Confidence: 10-segment bar in `--signal`; numeric value next to it.
- Source pill: "from watchlist" / "from positions" / "from discover" in `--fg-mute`.
- Rationale: ≤280 chars, regular body color.
- Headlines: bulleted list, each linked (target=_blank, rel=noopener).
- `Analyze →`: outlined button matching the Reject button styling in `proposal-card.tsx`.

**Card ordering:** confidence desc within each source bucket; sources ordered watchlist → positions → discover. Errored cards always last.

**Streaming feedback:** sources strip renders immediately on `recommendation.discovery`. Each candidate gets a 1-line skeleton placeholder; cards fill in their slots as `recommendation.card` events arrive. Header counter updates `generating N of M…`.

**Empty state (no run yet):** centered text `No ideas generated yet. Click ⟳ Generate to start.` plus the same Generate button.

**Mobile:** single-column stack; sources strip wraps; bias badge and confidence stay on the same row as the ticker.

## Data flow

1. User navigates to `/recommendations`. `RecommendationsView` mounts.
2. `useEffect` triggers `getLatestRecommendations()`. If a prior run exists, render its cards + timestamp; otherwise empty state.
3. User clicks **Generate**.
4. Frontend opens a WS to `/ws`, sends `{"type": "recommendation.start"}`.
5. Backend handler calls `recommendation_service.generate_all(emit=ws_send)`.
6. `generate_all` calls `discover_candidates()` → emits `recommendation.discovery` with the three ticker buckets.
7. Frontend renders sources strip + skeleton rows.
8. Backend kicks off `asyncio.gather` over `[generate_one(sym, src) for each candidate]`, throttled by `Semaphore(8)`.
9. Each `generate_one` finishes (success or caught exception → error card); orchestrator emits `recommendation.card`.
10. Frontend slots the card into its skeleton row; counter advances.
11. When all coroutines resolve, orchestrator persists a `RecommendationRun` row, emits `recommendation.complete` with `{run_id, generated_at, count}`, and the WS closes.
12. Frontend flips to `done` status; the Generate button becomes available again for a re-run.

## Error handling

- **Per-ticker failure** — `generate_one` raises → orchestrator catches → emits an error card `{symbol, source, error: "<tag>"}`. UI renders an error row in-place. One bad ticker never blanks the run.
- **Discovery failure** — if `news_service.get_general_news()` raises, orchestrator falls back to watchlist + positions only and emits `recommendation.discovery_warning` event. Run continues.
- **Empty discovery** — discover bucket is empty, no warning, sources strip just omits the "discover" row.
- **No candidates at all** — orchestrator emits `recommendation.complete` with `count: 0` after a `recommendation.discovery_warning` carrying `{message: "no_candidates"}`. UI shows "Add tickers to your watchlist or open a position to get started."
- **Malformed Claude response** — `generate_one` retries once with a stricter prompt. If still malformed, raises `MalformedRecommendationError("unparseable_response")` which becomes a per-ticker error card.
- **Rate limit (Finnhub 429)** — `generate_one` catches and raises with tag `"finnhub_429"`; same error-card path.
- **WS disconnect mid-stream** — frontend keeps the partial run rendered, header shows `stream interrupted`, Refresh button re-runs from scratch.
- **Concurrent Generate clicks** — button disabled while `status === "running"`; second click is a no-op.
- **Persisted-run is stale** — `/recommendations/latest` returns whatever exists regardless of age. UI shows the absolute `generated_at` timestamp (e.g., "generated 2 hours ago") so the user knows. Generate is the only refresh path.

## Edge cases

- **Duplicate tickers across sources** — dedupe globally with priority `watchlist > positions > discover`. Each ticker appears once.
- **Held-but-not-watchlisted positions** — appear in the "positions" bucket only.
- **Held option contracts in positions** — collapse to underlying for ticker scanning.
- **Rate-limit guardrails** — discover capped at 5 tickers; Semaphore(8) bounds parallel Claude+Finnhub calls.
- **`?ticker=` validation on `/`** — existing `TickerInput` validation handles invalid inputs; we only prefill.
- **No new agent tools, no order paths** — read-only screen; `MAX_RISK_USD` and paper invariants unchanged.

## Testing

### Backend (pytest)

- `test_recommendation_service_discover_dedup` — seed watchlist + mock `get_positions` + mock `get_general_news` with overlapping tickers; assert global dedup with priority `watchlist > positions > discover` and discover cap of 5.
- `test_recommendation_service_generate_one_fixtures` — under `FIXTURES_MODE=1` with a stubbed Anthropic call that returns canned JSON, assert `generate_one("AAPL", "watchlist")` returns the four required fields and `bias ∈ {bullish, bearish, neutral}`.
- `test_recommendation_service_generate_one_malformed_retries_once` — patch the Anthropic client to return non-JSON the first time and valid JSON the second; assert exactly one retry and a successful card.
- `test_recommendation_service_generate_one_persistent_failure` — both mocked calls return non-JSON; assert `MalformedRecommendationError` is raised.
- `test_recommendation_service_generate_all_partial_failure` — three candidates, one mocked to raise; assert orchestrator calls `emit` three times in finish-order including one error card; assert the persisted `RecommendationRun.payload_json` contains all three.
- `test_recommendation_service_persists_run` — assert a `RecommendationRun` row is written after `generate_all` and `get_latest_run()` returns it.
- `test_recommendations_latest_endpoint` — TestClient: write two runs, GET `/recommendations/latest` returns the most recent payload; with no runs, returns the empty shape (200, not 404).
- `test_ws_recommendation_start_message_flow` — TestClient WS: send `{"type":"recommendation.start"}`, mock the orchestrator to emit two cards, assert the client receives `recommendation.discovery` → 2× `recommendation.card` → `recommendation.complete` in order.

### Frontend

- `pnpm tsc --noEmit` and `pnpm build` stay green.
- Manual smoke (added to demo flow):
  1. Navigate to `/recommendations`. With no prior run, see the empty state.
  2. Click **Generate**. Sources strip appears, then cards stream in.
  3. Click `Analyze →` on a card. Lands on `/` with the ticker pre-filled, agent auto-runs.
  4. Force a backend-side error (e.g., disable the Finnhub key) — confirm cards still render with error rows for failed tickers.

### Fixtures

- `backend/tests/fixtures/general_news.json` — canned market-wide news payload (~10 items with mixed tickers).
- `backend/tests/fixtures/recommendation_response.json` — canned Claude JSON response for the per-ticker prompt.

## File-touch summary

**New files:**
- `backend/app/services/recommendation_service.py`
- `backend/app/agent/recommendation_prompt.py`
- `backend/tests/test_recommendation_service.py`
- `backend/tests/test_recommendation_api.py`
- `backend/tests/fixtures/general_news.json`
- `backend/tests/fixtures/recommendation_response.json`
- `frontend/src/app/recommendations/page.tsx`
- `frontend/src/components/recommendations/recommendations-view.tsx`
- `frontend/src/components/recommendations/recommendation-card.tsx`
- `frontend/src/components/recommendations/sources-strip.tsx`
- `frontend/src/lib/recommendations-ws.ts`
- `frontend/src/types/recommendations.ts`

**Modified files:**
- `backend/app/models.py` — add `RecommendationRun` table.
- `backend/app/services/news_service.py` — add `get_general_news()`.
- `backend/app/api/ws.py` — route `recommendation.start` to the orchestrator and emit the three streaming events.
- `backend/app/api/http.py` — add `GET /recommendations/latest`.
- `frontend/src/components/status-rail.tsx` — add IDEAS nav link.
- `frontend/src/components/ticker-input.tsx` — read `?ticker=<sym>&autosubmit=1` and prefill+autosubmit.
- `frontend/src/lib/api.ts` — add `getLatestRecommendations()`.
- `README.md` — add `/recommendations/latest` to the API table.

## Open questions

None at spec time. Implementation plan will address task ordering and any decisions surfaced during build (e.g., the exact ticker-whitelist set for discovery scanning).
