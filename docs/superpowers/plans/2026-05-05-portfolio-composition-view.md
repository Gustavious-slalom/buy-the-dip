# Portfolio Composition View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/portfolio` route that shows the user the full composition of their Alpaca paper account — account stats, positions, multi-leg strategies grouped from local proposals, allocation breakdown, equity curve, and proposal history.

**Architecture:** New backend service `portfolio_service.py` aggregates Alpaca account/positions + local DB proposals into a single snapshot, plus a separate equity-curve endpoint with period parameters. New `/portfolio` Next.js route renders independent cards each owning their own loading/error state. Refresh on load + after every approve/reject + manual button.

**Tech Stack:** Python 3.11 / FastAPI / SQLModel / pytest / respx (backend); Next.js App Router / TypeScript / Tailwind / Recharts / shadcn (frontend).

**Spec reference:** `docs/superpowers/specs/2026-05-05-portfolio-composition-view-design.md`

---

## File Structure

### New backend files
- `backend/app/services/portfolio_service.py` — snapshot orchestration, strategy grouping, allocations
- `backend/tests/test_portfolio_service.py` — unit tests for the service
- `backend/tests/test_portfolio_api.py` — endpoint tests
- `backend/tests/fixtures/portfolio_account.json` — canned account JSON
- `backend/tests/fixtures/portfolio_positions.json` — canned positions JSON
- `backend/tests/fixtures/portfolio_history_1m.json` — canned 30-point equity curve

### Modified backend files
- `backend/app/services/alpaca_service.py` — add `get_portfolio_history`, `get_latest_prices`
- `backend/app/api/http.py` — add `/portfolio/snapshot`, `/portfolio/equity-curve` routes

### New frontend files
- `frontend/src/app/portfolio/page.tsx` — route shell
- `frontend/src/components/portfolio/portfolio-view.tsx` — client container, owns refresh + invalidation
- `frontend/src/components/portfolio/portfolio-header.tsx`
- `frontend/src/components/portfolio/account-summary.tsx`
- `frontend/src/components/portfolio/positions-table.tsx`
- `frontend/src/components/portfolio/strategies-list.tsx`
- `frontend/src/components/portfolio/allocation-card.tsx`
- `frontend/src/components/portfolio/equity-curve.tsx`
- `frontend/src/components/portfolio/history-table.tsx`
- `frontend/src/lib/portfolio-events.ts` — invalidation event emitter
- `frontend/src/types/portfolio.ts` — shared TypeScript types

### Modified frontend files
- `frontend/src/lib/api.ts` — add `getPortfolioSnapshot`, `getEquityCurve`
- `frontend/src/components/proposal-card.tsx` — fire `portfolio:invalidate` on approve/reject
- `frontend/src/app/layout.tsx` — top-right Trade/Portfolio nav link

---

## Phase 1 — Backend service additions

### Task 1: `get_latest_prices` in `alpaca_service`

**Files:**
- Modify: `backend/app/services/alpaca_service.py`
- Test: `backend/tests/test_alpaca_service.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_alpaca_service.py`:

```python
def test_get_latest_prices_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    prices = alpaca_service.get_latest_prices(["AAPL", "NVDA"])
    assert set(prices.keys()) == {"AAPL", "NVDA"}
    assert all(isinstance(v, float) for v in prices.values())
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd backend && pytest tests/test_alpaca_service.py::test_get_latest_prices_fixtures_mode -v`
Expected: FAIL with `AttributeError: module 'app.services.alpaca_service' has no attribute 'get_latest_prices'`

- [ ] **Step 3: Implement**

Add to `backend/app/services/alpaca_service.py` (after `get_quote`):

```python
def get_latest_prices(symbols: list[str]) -> dict[str, float | None]:
    """Batched mid-price fetch. Stocks → StockLatestQuoteRequest; option contracts (OCC, len>=15) → OptionLatestQuoteRequest."""
    if not symbols:
        return {}
    if settings.fixtures_mode:
        return {s: 200.0 if len(s) < 15 else 6.50 for s in symbols}
    stocks = [s for s in symbols if len(s) < 15]
    opts = [s for s in symbols if len(s) >= 15]
    out: dict[str, float | None] = {s: None for s in symbols}
    if stocks:
        from alpaca.data.requests import StockLatestQuoteRequest
        try:
            res = _stock_data().get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=stocks))
            for sym, q in res.items():
                if q.bid_price and q.ask_price:
                    out[sym] = float((q.bid_price + q.ask_price) / 2)
        except Exception:
            pass  # leave as None
    if opts:
        from alpaca.data.requests import OptionLatestQuoteRequest
        try:
            res = _option_data().get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=opts))
            for sym, q in res.items():
                if q.bid_price and q.ask_price:
                    out[sym] = float((q.bid_price + q.ask_price) / 2)
        except Exception:
            pass
    return out
```

- [ ] **Step 4: Run test to confirm pass**

Run: `cd backend && pytest tests/test_alpaca_service.py::test_get_latest_prices_fixtures_mode -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/alpaca_service.py backend/tests/test_alpaca_service.py
git commit -m "feat(backend): batched get_latest_prices for stocks + options"
```

---

### Task 2: `get_portfolio_history` in `alpaca_service`

Alpaca's portfolio-history endpoint isn't wrapped by alpaca-py's TradingClient; use a direct httpx call to `/v2/account/portfolio/history`.

**Files:**
- Modify: `backend/app/services/alpaca_service.py`
- Test: `backend/tests/test_alpaca_service.py`
- New: `backend/tests/fixtures/portfolio_history_1m.json`

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/portfolio_history_1m.json`:

```json
{
  "timestamp": [1714521600, 1714608000, 1714694400],
  "equity": [100000.0, 100250.5, 100812.3],
  "profit_loss": [0, 250.5, 812.3],
  "profit_loss_pct": [0, 0.0025, 0.00812],
  "base_value": 100000.0,
  "timeframe": "1D"
}
```

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_alpaca_service.py`:

```python
def test_get_portfolio_history_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    res = alpaca_service.get_portfolio_history("1M")
    assert res["period"] == "1M"
    assert isinstance(res["points"], list) and len(res["points"]) > 0
    assert {"t", "equity"}.issubset(res["points"][0].keys())
    assert "base_value" in res and "profit_loss" in res and "profit_loss_pct" in res

def test_get_portfolio_history_invalid_period(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    import pytest
    with pytest.raises(ValueError):
        alpaca_service.get_portfolio_history("XYZ")
```

- [ ] **Step 3: Run tests to confirm they fail**

Run: `cd backend && pytest tests/test_alpaca_service.py::test_get_portfolio_history_fixtures_mode tests/test_alpaca_service.py::test_get_portfolio_history_invalid_period -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_portfolio_history'`

- [ ] **Step 4: Implement**

Add to `backend/app/services/alpaca_service.py`:

```python
import httpx
from datetime import datetime, timezone

_PERIOD_MAP = {"1D": ("1D", "5Min"), "1W": ("1W", "15Min"), "1M": ("1M", "1H"), "3M": ("3M", "1D"), "ALL": ("all", "1D")}

def get_portfolio_history(period: str) -> dict:
    """Returns {period, points: [{t, equity}], base_value, profit_loss, profit_loss_pct}."""
    if period not in _PERIOD_MAP:
        raise ValueError(f"invalid period: {period}")
    if settings.fixtures_mode:
        raw = json.loads((FIXTURES / "portfolio_history_1m.json").read_text())
    else:
        api_period, timeframe = _PERIOD_MAP[period]
        url = settings.alpaca_base_url.rstrip("/") + "/v2/account/portfolio/history"
        params = {"period": api_period, "timeframe": timeframe, "extended_hours": "false"}
        headers = {"APCA-API-KEY-ID": settings.alpaca_api_key, "APCA-API-SECRET-KEY": settings.alpaca_api_secret}
        with httpx.Client(timeout=10.0) as c:
            r = c.get(url, params=params, headers=headers)
            r.raise_for_status()
            raw = r.json()
    timestamps = raw.get("timestamp", [])
    equity = raw.get("equity", [])
    points = [
        {"t": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "equity": float(eq)}
        for ts, eq in zip(timestamps, equity) if eq is not None
    ]
    pl_list = [x for x in (raw.get("profit_loss") or []) if x is not None]
    pl_pct_list = [x for x in (raw.get("profit_loss_pct") or []) if x is not None]
    return {
        "period": period,
        "points": points,
        "base_value": float(raw.get("base_value", 0.0) or 0.0),
        "profit_loss": float(pl_list[-1]) if pl_list else 0.0,
        "profit_loss_pct": float(pl_pct_list[-1]) if pl_pct_list else 0.0,
    }
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `cd backend && pytest tests/test_alpaca_service.py::test_get_portfolio_history_fixtures_mode tests/test_alpaca_service.py::test_get_portfolio_history_invalid_period -v`
Expected: PASS (both)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/alpaca_service.py backend/tests/test_alpaca_service.py backend/tests/fixtures/portfolio_history_1m.json
git commit -m "feat(backend): get_portfolio_history with period mapping + fixtures"
```

---

### Task 3: `_compute_allocations` in `portfolio_service`

**Files:**
- Create: `backend/app/services/portfolio_service.py`
- Create: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_portfolio_service.py`:

```python
import pytest

from app.services.portfolio_service import _compute_allocations


def test_compute_allocations_kind_split():
    positions = [
        {"symbol": "SPY", "kind": "stock", "underlying": "SPY", "market_value": 48000.0},
        {"symbol": "AAPL250117C00150000", "kind": "option", "underlying": "AAPL", "market_value": 1500.0},
        {"symbol": "AAPL250117C00160000", "kind": "option", "underlying": "AAPL", "market_value": 500.0},
    ]
    account = {"cash": 50000.0, "equity": 100000.0}
    alloc = _compute_allocations(positions, account)

    # by_kind sums to ~100
    assert abs(alloc["by_kind"]["stock"] + alloc["by_kind"]["option"] + alloc["by_kind"]["cash"] - 100.0) < 0.01
    assert alloc["by_kind"]["stock"] == pytest.approx(48.0, abs=0.01)
    assert alloc["by_kind"]["option"] == pytest.approx(2.0, abs=0.01)
    assert alloc["by_kind"]["cash"] == pytest.approx(50.0, abs=0.01)

    # by_underlying aggregates options under underlying ticker
    by_under = {row["ticker"]: row for row in alloc["by_underlying"]}
    assert by_under["SPY"]["market_value"] == pytest.approx(48000.0)
    assert by_under["AAPL"]["market_value"] == pytest.approx(2000.0)


def test_compute_allocations_handles_none_market_value():
    positions = [
        {"symbol": "SPY", "kind": "stock", "underlying": "SPY", "market_value": None},
        {"symbol": "AAPL", "kind": "stock", "underlying": "AAPL", "market_value": 1000.0},
    ]
    account = {"cash": 9000.0, "equity": 10000.0}
    alloc = _compute_allocations(positions, account)
    # None values are excluded from totals; remaining alloc still computed against equity
    assert alloc["by_kind"]["stock"] == pytest.approx(10.0, abs=0.01)
    assert all(row["ticker"] != "SPY" or row["market_value"] == 0.0 for row in alloc["by_underlying"]) or \
           "SPY" not in {r["ticker"] for r in alloc["by_underlying"]}
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.portfolio_service'`

- [ ] **Step 3: Implement**

Create `backend/app/services/portfolio_service.py`:

```python
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
```

- [ ] **Step 4: Run test to confirm pass**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/portfolio_service.py backend/tests/test_portfolio_service.py
git commit -m "feat(backend): portfolio_service _compute_allocations"
```

---

### Task 4: Position normalization helpers (`_parse_occ`, `_normalize_positions`)

OCC option symbols like `AAPL250117C00150000` encode underlying, expiry, side, strike. We need to extract those and add derived fields (`market_value`, `unrealized_pl`, `weight_pct`).

**Files:**
- Modify: `backend/app/services/portfolio_service.py`
- Modify: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_portfolio_service.py`:

```python
from app.services.portfolio_service import _parse_occ, _normalize_positions


def test_parse_occ_call():
    parsed = _parse_occ("AAPL250117C00150000")
    assert parsed == {"underlying": "AAPL", "expiry": "2025-01-17", "side": "call", "strike": 150.0}


def test_parse_occ_put_with_decimals():
    parsed = _parse_occ("NVDA260619P00875500")
    assert parsed["side"] == "put"
    assert parsed["strike"] == 875.5
    assert parsed["expiry"] == "2026-06-19"
    assert parsed["underlying"] == "NVDA"


def test_normalize_positions_stock_and_option():
    raw = [
        {"symbol": "SPY", "qty": 100.0, "avg_entry_price": 480.0},
        {"symbol": "AAPL250117C00150000", "qty": 2.0, "avg_entry_price": 6.20},
    ]
    prices = {"SPY": 482.55, "AAPL250117C00150000": 7.90}
    account = {"equity": 100000.0}
    out = _normalize_positions(raw, prices, account)

    spy = next(p for p in out if p["symbol"] == "SPY")
    assert spy["kind"] == "stock"
    assert spy["market_value"] == pytest.approx(482.55 * 100)
    assert spy["unrealized_pl"] == pytest.approx((482.55 - 480.0) * 100)
    assert spy["weight_pct"] == pytest.approx(spy["market_value"] / 100000.0 * 100, abs=0.01)

    opt = next(p for p in out if p["symbol"].startswith("AAPL"))
    assert opt["kind"] == "option"
    # Options multiplier = 100
    assert opt["market_value"] == pytest.approx(7.90 * 2 * 100)
    assert opt["unrealized_pl"] == pytest.approx((7.90 - 6.20) * 2 * 100)
    assert opt["underlying"] == "AAPL"
    assert opt["side"] == "call"
    assert opt["strike"] == 150.0


def test_normalize_positions_filters_zero_qty():
    raw = [{"symbol": "SPY", "qty": 0.0, "avg_entry_price": 480.0}]
    out = _normalize_positions(raw, {"SPY": 482.55}, {"equity": 100000.0})
    assert out == []


def test_normalize_positions_missing_price_yields_nulls():
    raw = [{"symbol": "SPY", "qty": 100.0, "avg_entry_price": 480.0}]
    out = _normalize_positions(raw, {"SPY": None}, {"equity": 100000.0})
    assert out[0]["current_price"] is None
    assert out[0]["market_value"] is None
    assert out[0]["unrealized_pl"] is None
    assert out[0]["weight_pct"] is None
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: FAIL — `ImportError: cannot import name '_parse_occ'`

- [ ] **Step 3: Implement**

Add to `backend/app/services/portfolio_service.py`:

```python
def _parse_occ(symbol: str) -> dict | None:
    """Parse OCC option symbol. Returns None for non-options (length < 15)."""
    if len(symbol) < 15:
        return None
    # Last 8 chars: strike (3 implied decimals). Char before: C/P. Six chars before that: YYMMDD.
    strike = int(symbol[-8:]) / 1000.0
    side = "call" if symbol[-9] == "C" else "put"
    yymmdd = symbol[-15:-9]
    expiry = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    underlying = symbol[:-15]
    return {"underlying": underlying, "expiry": expiry, "side": side, "strike": strike}


def _normalize_positions(raw: list[dict], prices: dict[str, float | None], account: dict) -> list[dict]:
    """Filter qty==0; add kind, multiplier-aware market_value, unrealized_pl, weight_pct, OCC fields."""
    equity = float(account.get("equity") or 0.0)
    out: list[dict] = []
    for r in raw:
        qty = float(r.get("qty") or 0.0)
        if qty == 0:
            continue
        symbol = r["symbol"]
        avg_entry = float(r.get("avg_entry_price") or 0.0)
        occ = _parse_occ(symbol)
        kind = "option" if occ else "stock"
        multiplier = 100 if kind == "option" else 1
        cur = prices.get(symbol)
        if cur is None:
            mv = pl = pct = None
        else:
            mv = round(cur * qty * multiplier, 2)
            pl = round((cur - avg_entry) * qty * multiplier, 2)
            pct = round((mv / equity) * 100.0, 4) if equity > 0 else 0.0
        pos = {
            "symbol": symbol,
            "kind": kind,
            "qty": qty,
            "avg_entry": avg_entry,
            "current_price": cur,
            "market_value": mv,
            "unrealized_pl": pl,
            "unrealized_pl_pct": (round(pl / (avg_entry * qty * multiplier) * 100.0, 2)
                                  if pl is not None and avg_entry > 0 else None),
            "weight_pct": pct,
            "underlying": occ["underlying"] if occ else symbol,
        }
        if occ:
            pos["strike"] = occ["strike"]
            pos["side"] = occ["side"]
            pos["expiry"] = occ["expiry"]
        out.append(pos)
    return out
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: PASS (all six)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/portfolio_service.py backend/tests/test_portfolio_service.py
git commit -m "feat(backend): portfolio_service _parse_occ + _normalize_positions"
```

---

### Task 5: `_group_strategies` — join positions to local Proposals

**Files:**
- Modify: `backend/app/services/portfolio_service.py`
- Modify: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_portfolio_service.py`:

```python
import json as _json
import uuid
from sqlmodel import SQLModel, create_engine, Session
from app.models import Proposal


@pytest.fixture
def seeded_proposals(monkeypatch):
    """Spin up a fresh in-memory DB and patch get_session to use it."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    spread_id = str(uuid.uuid4())
    long_id = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Proposal(
            id=spread_id, session_id="sess-1", ticker="NVDA",
            legs_json=_json.dumps([
                {"contract_symbol": "NVDA260619C00800000", "qty": 1, "action": "buy", "premium": 12.40, "side": "call", "strike": 800.0},
                {"contract_symbol": "NVDA260619C00850000", "qty": 1, "action": "sell", "premium": 8.20, "side": "call", "strike": 850.0},
            ]),
            max_risk=420.0, max_reward=580.0, breakeven=804.20, expiry="2026-06-19",
            rationale="bull spread", confidence=0.7, risks_json="[]", status="executed",
        ))
        s.add(Proposal(
            id=long_id, session_id="sess-1", ticker="AAPL",
            legs_json=_json.dumps([
                {"contract_symbol": "AAPL250718C00220000", "qty": 1, "action": "buy", "premium": 6.20, "side": "call", "strike": 220.0},
            ]),
            max_risk=620.0, max_reward=None, breakeven=226.20, expiry="2025-07-18",
            rationale="long call", confidence=0.6, risks_json="[]", status="executed",
        ))
        s.commit()
    from contextlib import contextmanager
    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    from app.services import portfolio_service
    monkeypatch.setattr(portfolio_service, "get_session", fake_session)
    return {"spread_id": spread_id, "long_id": long_id}


def test_group_strategies_full_spread_open(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "NVDA260619C00800000", "kind": "option", "qty": 1.0, "avg_entry": 12.40, "current_price": 14.00,
         "market_value": 1400.0, "unrealized_pl": 160.0, "underlying": "NVDA", "side": "call", "strike": 800.0, "expiry": "2026-06-19"},
        {"symbol": "NVDA260619C00850000", "kind": "option", "qty": 1.0, "avg_entry": 8.20, "current_price": 9.00,
         "market_value": 900.0, "unrealized_pl": 80.0, "underlying": "NVDA", "side": "call", "strike": 850.0, "expiry": "2026-06-19"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    g = groups[0]
    assert g["proposal_id"] == seeded_proposals["spread_id"]
    assert g["ticker"] == "NVDA"
    assert g["type"] == "bull-call-spread"
    assert g["legs_open"] == 2 and g["legs_total"] == 2
    # cost_basis: buy 1240 - sell 820 = 420 (debit)
    assert g["cost_basis"] == pytest.approx(420.0)
    # current_value: long leg MV(1400) - short leg MV(900) = 500
    assert g["current_value"] == pytest.approx(500.0)
    assert g["unrealized_pl"] == pytest.approx(80.0)
    assert g["expiry"] == "2026-06-19"


def test_group_strategies_partial_spread(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "NVDA260619C00800000", "kind": "option", "qty": 1.0, "avg_entry": 12.40, "current_price": 14.00,
         "market_value": 1400.0, "unrealized_pl": 160.0, "underlying": "NVDA", "side": "call", "strike": 800.0, "expiry": "2026-06-19"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    g = groups[0]
    assert g["legs_open"] == 1 and g["legs_total"] == 2
    # current value reflects only the open long leg
    assert g["current_value"] == pytest.approx(1400.0)


def test_group_strategies_long_call(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "AAPL250718C00220000", "kind": "option", "qty": 1.0, "avg_entry": 6.20, "current_price": 5.10,
         "market_value": 510.0, "unrealized_pl": -110.0, "underlying": "AAPL", "side": "call", "strike": 220.0, "expiry": "2025-07-18"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    assert groups[0]["type"] == "long-call"
    assert groups[0]["legs_total"] == 1


def test_group_strategies_no_match(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "TSLA250620P00200000", "kind": "option", "qty": 1.0, "avg_entry": 5.0, "current_price": 4.5,
         "market_value": 450.0, "unrealized_pl": -50.0, "underlying": "TSLA", "side": "put", "strike": 200.0, "expiry": "2025-06-20"},
    ]
    assert _group_strategies(positions) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd backend && pytest tests/test_portfolio_service.py -v -k group_strategies`
Expected: FAIL — `ImportError: cannot import name '_group_strategies'`

- [ ] **Step 3: Implement**

Add to `backend/app/services/portfolio_service.py`:

```python
def _classify_strategy(legs: list[dict]) -> str:
    """Best-effort name from leg shape."""
    if len(legs) == 1:
        l = legs[0]
        if l["action"] == "buy":
            return f"long-{l.get('side', 'option')}"
        return f"short-{l.get('side', 'option')}"
    if len(legs) == 2 and legs[0].get("side") == legs[1].get("side"):
        side = legs[0].get("side", "option")
        longs = [l for l in legs if l["action"] == "buy"]
        shorts = [l for l in legs if l["action"] == "sell"]
        if longs and shorts:
            net_debit = sum(l["premium"] * l["qty"] for l in longs) - sum(l["premium"] * l["qty"] for l in shorts)
            direction = "bull" if (side == "call" and net_debit > 0) or (side == "put" and net_debit < 0) else "bear"
            return f"{direction}-{side}-spread"
    return "multi-leg"


def _group_strategies(positions: list[dict]) -> list[dict]:
    """For each executed Proposal, build one strategy row from currently-held legs."""
    pos_by_sym = {p["symbol"]: p for p in positions if p["kind"] == "option"}
    if not pos_by_sym:
        return []
    out: list[dict] = []
    with get_session() as s:
        proposals = s.exec(
            select(Proposal).where(Proposal.status == "executed").order_by(Proposal.created_at.desc())
        ).all()
    for p in proposals:
        legs = json.loads(p.legs_json)
        leg_syms = [l["contract_symbol"] for l in legs]
        held = [sym for sym in leg_syms if sym in pos_by_sym]
        if not held:
            continue
        cost_basis = 0.0
        for l in legs:
            sign = 1 if l["action"] == "buy" else -1
            cost_basis += sign * float(l["premium"]) * int(l["qty"]) * 100
        current_value = 0.0
        unrealized_pl = 0.0
        for l in legs:
            sym = l["contract_symbol"]
            if sym not in pos_by_sym:
                continue
            held_pos = pos_by_sym[sym]
            sign = 1 if l["action"] == "buy" else -1
            mv = held_pos.get("market_value")
            if mv is not None:
                current_value += sign * float(mv)
            pl = held_pos.get("unrealized_pl")
            if pl is not None:
                unrealized_pl += sign * float(pl)
        pl_pct = round((unrealized_pl / abs(cost_basis)) * 100.0, 2) if cost_basis != 0 else None
        out.append({
            "proposal_id": p.id,
            "ticker": p.ticker,
            "type": _classify_strategy(legs),
            "legs": [{"symbol": l["contract_symbol"], "qty": int(l["qty"]), "side": l["action"]} for l in legs],
            "cost_basis": round(cost_basis, 2),
            "current_value": round(current_value, 2) if current_value else 0.0,
            "unrealized_pl": round(unrealized_pl, 2),
            "unrealized_pl_pct": pl_pct,
            "expiry": p.expiry,
            "legs_open": len(held),
            "legs_total": len(legs),
        })
    return out
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/portfolio_service.py backend/tests/test_portfolio_service.py
git commit -m "feat(backend): _group_strategies joins positions to local Proposals"
```

---

### Task 6: `build_snapshot` orchestrator

**Files:**
- Modify: `backend/app/services/portfolio_service.py`
- Modify: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_portfolio_service.py`:

```python
def test_build_snapshot_fixtures_mode(seeded_proposals, monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import portfolio_service; reload(portfolio_service)
    # re-apply DB patch after reload
    from contextlib import contextmanager
    from sqlmodel import Session
    @contextmanager
    def fake_session():
        # reuse seeded engine via the prior fixture's stash; pull from a module-level handle
        from app.services import portfolio_service as ps
        with ps._test_session_factory() as ses:  # set below
            yield ses
    # Provide positions by patching alpaca_service callables to return the seeded spread
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "NVDA260619C00800000", "qty": 1.0, "avg_entry_price": 12.40},
        {"symbol": "NVDA260619C00850000", "qty": 1.0, "avg_entry_price": 8.20},
    ])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {s: 14.00 if s.endswith("00800000") else 9.00 for s in syms})
    snap = portfolio_service.build_snapshot()
    assert snap["account"]["equity"] == 100000.0
    assert len(snap["positions"]) == 2
    assert len(snap["strategies"]) == 1
    assert snap["allocations"]["by_kind"]["cash"] == pytest.approx(50.0, abs=0.01)
    assert snap["errors"] == []
    assert "fetched_at" in snap
    assert isinstance(snap["history"], list)


def test_build_snapshot_partial_failure(monkeypatch):
    from app.services import alpaca_service, portfolio_service
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    def boom(): raise RuntimeError("alpaca down")
    monkeypatch.setattr(alpaca_service, "get_positions", boom)
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {})
    snap = portfolio_service.build_snapshot()
    assert "positions_unavailable" in snap["errors"]
    assert snap["positions"] == []
    assert snap["account"]["equity"] == 100000.0
```

The `_test_session_factory` shim is set in the implementation; if the seeded_proposals fixture isn't applied (different test isolation), the `history` query just returns empty, which the test allows.

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd backend && pytest tests/test_portfolio_service.py::test_build_snapshot_fixtures_mode tests/test_portfolio_service.py::test_build_snapshot_partial_failure -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_snapshot'`

- [ ] **Step 3: Implement**

Add to `backend/app/services/portfolio_service.py`:

```python
def _build_history(limit: int = 20) -> list[dict]:
    with get_session() as s:
        rows = s.exec(select(Proposal).order_by(Proposal.created_at.desc()).limit(limit)).all()
        out = []
        for p in rows:
            ex = s.exec(select(Execution).where(Execution.proposal_id == p.id)).first()
            out.append({
                "proposal_id": p.id,
                "ticker": p.ticker,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
                "executed_at": ex.submitted_at.isoformat() if ex else None,
                "alpaca_order_id": ex.alpaca_order_id if ex else None,
            })
        return out


def build_snapshot() -> dict:
    """Return a PortfolioSnapshot. Partial failures captured in `errors` rather than raised."""
    errors: list[str] = []
    account: dict = {"cash": None, "equity": None, "buying_power": None, "day_pl": None, "day_pl_pct": None}
    try:
        a = alpaca_service.get_portfolio()
        account.update(a)
        # day_pl/day_pl_pct not yet exposed by get_portfolio; set null defaults
        account.setdefault("day_pl", None)
        account.setdefault("day_pl_pct", None)
    except Exception:
        errors.append("account_unavailable")

    raw_positions: list[dict] = []
    try:
        raw_positions = alpaca_service.get_positions()
    except Exception:
        errors.append("positions_unavailable")

    symbols = [r["symbol"] for r in raw_positions]
    try:
        prices = alpaca_service.get_latest_prices(symbols) if symbols else {}
    except Exception:
        prices = {s: None for s in symbols}
        errors.append("prices_unavailable")

    positions = _normalize_positions(raw_positions, prices, account)
    strategies = []
    try:
        strategies = _group_strategies(positions)
    except Exception:
        errors.append("strategies_unavailable")

    allocations = _compute_allocations(positions, account)

    history: list[dict] = []
    try:
        history = _build_history()
    except Exception:
        errors.append("history_unavailable")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "positions": positions,
        "strategies": strategies,
        "allocations": allocations,
        "history": history,
        "errors": errors,
    }
```

Note: the `_test_session_factory` shim referenced in the test isn't actually needed — the `seeded_proposals` fixture already patches `get_session`; remove that block from the test before running. Replace the `fake_session()` shim in `test_build_snapshot_fixtures_mode` with reuse of the original fixture by accepting `seeded_proposals` (already a fixture) and removing the inner re-patch:

```python
def test_build_snapshot_fixtures_mode(seeded_proposals, monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from app.services import alpaca_service, portfolio_service
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "NVDA260619C00800000", "qty": 1.0, "avg_entry_price": 12.40},
        {"symbol": "NVDA260619C00850000", "qty": 1.0, "avg_entry_price": 8.20},
    ])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {s: 14.00 if s.endswith("00800000") else 9.00 for s in syms})
    snap = portfolio_service.build_snapshot()
    assert snap["account"]["equity"] == 100000.0
    assert len(snap["positions"]) == 2
    assert len(snap["strategies"]) == 1
    assert snap["allocations"]["by_kind"]["cash"] == pytest.approx(50.0, abs=0.01)
    assert snap["errors"] == []
    assert "fetched_at" in snap
    assert isinstance(snap["history"], list)
```

(Apply that replacement in `tests/test_portfolio_service.py`.)

- [ ] **Step 4: Run all portfolio_service tests**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/portfolio_service.py backend/tests/test_portfolio_service.py
git commit -m "feat(backend): build_snapshot orchestrator with partial-failure errors"
```

---

### Task 7: `get_equity_curve` thin wrapper

**Files:**
- Modify: `backend/app/services/portfolio_service.py`
- Modify: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_portfolio_service.py`:

```python
def test_get_equity_curve_passthrough(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import portfolio_service; reload(portfolio_service)
    res = portfolio_service.get_equity_curve("1M")
    assert res["period"] == "1M"
    assert isinstance(res["points"], list)


def test_get_equity_curve_invalid_period():
    from app.services import portfolio_service
    with pytest.raises(ValueError):
        portfolio_service.get_equity_curve("INVALID")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd backend && pytest tests/test_portfolio_service.py::test_get_equity_curve_passthrough tests/test_portfolio_service.py::test_get_equity_curve_invalid_period -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_equity_curve'`

- [ ] **Step 3: Implement**

Add to `backend/app/services/portfolio_service.py`:

```python
VALID_PERIODS = {"1D", "1W", "1M", "3M", "ALL"}


def get_equity_curve(period: str) -> dict:
    if period not in VALID_PERIODS:
        raise ValueError(f"invalid period: {period}")
    return alpaca_service.get_portfolio_history(period)
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd backend && pytest tests/test_portfolio_service.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/portfolio_service.py backend/tests/test_portfolio_service.py
git commit -m "feat(backend): get_equity_curve passthrough with period validation"
```

---

### Task 8: HTTP routes `/portfolio/snapshot` and `/portfolio/equity-curve`

**Files:**
- Modify: `backend/app/api/http.py`
- Create: `backend/tests/test_portfolio_api.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_portfolio_api.py`:

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
    from app.services import portfolio_service; reload(portfolio_service)
    from app.api import http as http_module; reload(http_module)
    from app import main; reload(main)
    return TestClient(main.app)


def test_portfolio_snapshot_endpoint(client, monkeypatch):
    from app.services import alpaca_service
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {})
    r = client.get("/portfolio/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert {"fetched_at", "account", "positions", "strategies", "allocations", "history", "errors"}.issubset(body.keys())


def test_portfolio_equity_curve_endpoint(client):
    r = client.get("/portfolio/equity-curve", params={"period": "1M"})
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "1M"
    assert isinstance(body["points"], list)


def test_portfolio_equity_curve_bad_period(client):
    r = client.get("/portfolio/equity-curve", params={"period": "BOGUS"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd backend && pytest tests/test_portfolio_api.py -v`
Expected: FAIL — `assert 404 == 200` (routes not registered yet)

- [ ] **Step 3: Implement**

Add to `backend/app/api/http.py` (after existing imports):

```python
from app.services import portfolio_service
```

Append at the bottom of the file:

```python
@router.get("/portfolio/snapshot")
def portfolio_snapshot():
    return portfolio_service.build_snapshot()


@router.get("/portfolio/equity-curve")
def portfolio_equity_curve(period: str = "1M"):
    try:
        return portfolio_service.get_equity_curve(period)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd backend && pytest tests/test_portfolio_api.py -v`
Expected: PASS (all three)

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: PASS (all existing + new)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/http.py backend/tests/test_portfolio_api.py
git commit -m "feat(backend): /portfolio/snapshot and /portfolio/equity-curve endpoints"
```

---

## Phase 2 — Frontend foundation

### Task 9: Shared TypeScript types

**Files:**
- Create: `frontend/src/types/portfolio.ts`

- [ ] **Step 1: Create the types file**

Create `frontend/src/types/portfolio.ts`:

```typescript
export type Period = "1D" | "1W" | "1M" | "3M" | "ALL";

export type PositionKind = "stock" | "option";

export type Position = {
  symbol: string;
  kind: PositionKind;
  qty: number;
  avg_entry: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null;
  underlying: string;
  strike?: number;
  side?: "call" | "put";
  expiry?: string;
};

export type StrategyLeg = { symbol: string; qty: number; side: "buy" | "sell" };

export type StrategyGroup = {
  proposal_id: string;
  ticker: string;
  type: string;
  legs: StrategyLeg[];
  cost_basis: number;
  current_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  expiry: string;
  legs_open: number;
  legs_total: number;
};

export type Allocations = {
  by_kind: { stock: number; option: number; cash: number };
  by_underlying: { ticker: string; weight_pct: number; market_value: number }[];
};

export type HistoryRow = {
  proposal_id: string;
  ticker: string;
  status: "pending" | "approved" | "rejected" | "executed" | "failed";
  created_at: string;
  executed_at: string | null;
  alpaca_order_id: string | null;
};

export type AccountSummary = {
  cash: number | null;
  equity: number | null;
  buying_power: number | null;
  day_pl: number | null;
  day_pl_pct: number | null;
};

export type PortfolioSnapshot = {
  fetched_at: string;
  account: AccountSummary;
  positions: Position[];
  strategies: StrategyGroup[];
  allocations: Allocations;
  history: HistoryRow[];
  errors: string[];
};

export type EquityCurve = {
  period: Period;
  points: { t: string; equity: number }[];
  base_value: number;
  profit_loss: number;
  profit_loss_pct: number;
};
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS (no errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/portfolio.ts
git commit -m "feat(frontend): portfolio TypeScript types"
```

---

### Task 10: API client methods

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add the methods**

Replace the entire contents of `frontend/src/lib/api.ts`:

```typescript
import type { PortfolioSnapshot, EquityCurve, Period } from "@/types/portfolio";

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

export async function getPortfolioSnapshot(): Promise<PortfolioSnapshot> {
  const r = await fetch(`${BASE}/portfolio/snapshot`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getEquityCurve(period: Period): Promise<EquityCurve> {
  const r = await fetch(`${BASE}/portfolio/equity-curve?period=${period}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): getPortfolioSnapshot + getEquityCurve API client"
```

---

### Task 11: Invalidation event emitter

**Files:**
- Create: `frontend/src/lib/portfolio-events.ts`

- [ ] **Step 1: Create the file**

Create `frontend/src/lib/portfolio-events.ts`:

```typescript
"use client";
import { useEffect } from "react";

const EVENT_NAME = "portfolio:invalidate";

export function emitPortfolioInvalidate() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  }
}

export function usePortfolioInvalidate(cb: () => void) {
  useEffect(() => {
    const h = () => cb();
    window.addEventListener(EVENT_NAME, h);
    return () => window.removeEventListener(EVENT_NAME, h);
  }, [cb]);
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/portfolio-events.ts
git commit -m "feat(frontend): portfolio invalidation event emitter"
```

---

### Task 12: Wire approve/reject to fire invalidation

**Files:**
- Modify: `frontend/src/components/proposal-card.tsx`

- [ ] **Step 1: Import the emitter and call it after success**

In `frontend/src/components/proposal-card.tsx`, add the import after the existing imports (line 3):

```typescript
import { emitPortfolioInvalidate } from "@/lib/portfolio-events";
```

In the Approve button's `onClick` handler, after `setResult(\`Order ${r.alpaca_order_id} · ${r.status}\`);`:

```typescript
emitPortfolioInvalidate();
```

In the Reject button's `onClick` handler, after `setResult("Rejected");`:

```typescript
emitPortfolioInvalidate();
```

The Approve handler block becomes:

```typescript
onClick={async () => {
  setBusy(true);
  try {
    const r = await approveProposal(proposal.proposal_id);
    setResult(`Order ${r.alpaca_order_id} · ${r.status}`);
    emitPortfolioInvalidate();
  } catch (e) {
    setResult(`Error: ${(e as Error).message}`);
  } finally {
    setBusy(false);
  }
}}
```

The Reject handler block becomes:

```typescript
onClick={async () => {
  setBusy(true);
  try {
    await rejectProposal(proposal.proposal_id);
    setResult("Rejected");
    emitPortfolioInvalidate();
  } catch (e) {
    setResult(`Error: ${(e as Error).message}`);
  } finally {
    setBusy(false);
  }
}}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/proposal-card.tsx
git commit -m "feat(frontend): emit portfolio:invalidate on approve/reject"
```

---

### Task 13: Format helper

**Files:**
- Modify: `frontend/src/lib/utils.ts`

- [ ] **Step 1: Append formatter helpers**

Append to `frontend/src/lib/utils.ts`:

```typescript
export function fmtUsd(n: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  const decimals = opts.decimals ?? 2;
  const formatted = n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  if (opts.sign && n > 0) return `+${formatted}`;
  return formatted;
}

export function fmtPct(n: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  const decimals = opts.decimals ?? 2;
  const formatted = `${n.toFixed(decimals)}%`;
  if (opts.sign && n > 0) return `+${formatted}`;
  return formatted;
}

export function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/utils.ts
git commit -m "feat(frontend): fmtUsd / fmtPct / fmtTime helpers"
```

---

## Phase 3 — Frontend components

### Task 14: `PortfolioHeader`

**Files:**
- Create: `frontend/src/components/portfolio/portfolio-header.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/portfolio-header.tsx`:

```typescript
"use client";
import Link from "next/link";
import { fmtTime } from "@/lib/utils";

type Props = {
  fetchedAt: string | null;
  refreshing: boolean;
  onRefresh: () => void;
};

export function PortfolioHeader({ fetchedAt, refreshing, onRefresh }: Props) {
  return (
    <header className="flex items-center justify-between px-5 py-4 border-b border-[color:var(--hairline)]">
      <h1 className="font-mono text-[18px] tracking-[.18em]">PORTFOLIO</h1>
      <div className="flex items-center gap-4 text-[12px] text-[color:var(--fg-dim)]">
        <span className="num">
          {fetchedAt ? `last updated ${fmtTime(fetchedAt)}` : "—"}
        </span>
        <button
          disabled={refreshing}
          onClick={onRefresh}
          className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] disabled:opacity-40 transition-colors"
        >
          {refreshing ? "Refreshing…" : "⟳ Refresh"}
        </button>
        <Link
          href="/"
          className="px-3 py-1.5 text-[11px] tracking-[.18em] uppercase border border-[color:var(--hairline-2)] hover:border-[color:var(--signal)] hover:text-[color:var(--signal)] transition-colors"
        >
          ← Trade
        </Link>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/portfolio/portfolio-header.tsx
git commit -m "feat(frontend): PortfolioHeader component"
```

---

### Task 15: `AccountSummary`

**Files:**
- Create: `frontend/src/components/portfolio/account-summary.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/account-summary.tsx`:

```typescript
"use client";
import type { AccountSummary as A } from "@/types/portfolio";
import { fmtUsd, fmtPct } from "@/lib/utils";

type Props = { account: A | null; loading: boolean; error: string | null };

export function AccountSummary({ account, loading, error }: Props) {
  if (error) {
    return (
      <section className="px-5 py-5 border-b border-[color:var(--hairline)] text-[12px] text-[color:var(--down)]">
        Account unavailable — {error}
      </section>
    );
  }
  if (loading || !account) {
    return (
      <section className="px-5 py-5 border-b border-[color:var(--hairline)] grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i}>
            <div className="smallcaps mb-1">—</div>
            <div className="num text-[20px] text-[color:var(--fg-mute)]">—</div>
          </div>
        ))}
      </section>
    );
  }
  const dayPlColor = (account.day_pl ?? 0) >= 0 ? "var(--up)" : "var(--down)";
  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)] grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3">
      <div>
        <div className="smallcaps mb-1">Equity</div>
        <div className="num text-[24px]">{fmtUsd(account.equity)}</div>
      </div>
      <div>
        <div className="smallcaps mb-1">Day P/L</div>
        <div className="num text-[24px]" style={{ color: dayPlColor }}>
          {fmtUsd(account.day_pl, { sign: true })}
          <span className="text-[12px] text-[color:var(--fg-mute)] ml-2">
            {fmtPct(account.day_pl_pct, { sign: true })}
          </span>
        </div>
      </div>
      <div>
        <div className="smallcaps mb-1">Cash</div>
        <div className="num text-[24px]">{fmtUsd(account.cash)}</div>
      </div>
      <div>
        <div className="smallcaps mb-1">Buying Power</div>
        <div className="num text-[24px]">{fmtUsd(account.buying_power)}</div>
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
git add frontend/src/components/portfolio/account-summary.tsx
git commit -m "feat(frontend): AccountSummary component"
```

---

### Task 16: `PositionsTable`

**Files:**
- Create: `frontend/src/components/portfolio/positions-table.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/positions-table.tsx`:

```typescript
"use client";
import { useState } from "react";
import type { Position } from "@/types/portfolio";
import { fmtUsd, fmtPct } from "@/lib/utils";

type Props = { positions: Position[]; loading: boolean; error: string | null };

type SortKey = "symbol" | "weight_pct" | "unrealized_pl";

export function PositionsTable({ positions, loading, error }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("weight_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = [...positions].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (av === bv) return 0;
    const cmp = av > bv ? 1 : -1;
    return sortDir === "asc" ? cmp : -cmp;
  });

  function toggle(k: SortKey) {
    if (sortKey === k) setSortDir(d => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("desc"); }
  }

  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)]">
      <h2 className="smallcaps panel-rule mb-4">Positions</h2>
      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn’t load positions — {error}</div>
      ) : loading ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : positions.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No open positions.</div>
      ) : (
        <table className="w-full text-[12.5px] font-mono">
          <thead>
            <tr className="text-[color:var(--fg-mute)] text-left">
              <th className="py-1 cursor-pointer" onClick={() => toggle("symbol")}>Symbol</th>
              <th>Kind</th>
              <th className="num text-right">Qty</th>
              <th className="num text-right">Avg</th>
              <th className="num text-right">Current</th>
              <th className="num text-right">Mkt Val</th>
              <th className="num text-right cursor-pointer" onClick={() => toggle("unrealized_pl")}>P/L</th>
              <th className="num text-right cursor-pointer" onClick={() => toggle("weight_pct")}>Weight</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(p => {
              const plColor = (p.unrealized_pl ?? 0) > 0 ? "var(--up)" : (p.unrealized_pl ?? 0) < 0 ? "var(--down)" : "var(--fg)";
              return (
                <tr key={p.symbol} className="border-t border-[color:var(--hairline)]">
                  <td className="py-1.5 truncate max-w-[180px]">{p.symbol}</td>
                  <td className="text-[color:var(--fg-dim)]">{p.kind}</td>
                  <td className="num text-right">{p.qty}</td>
                  <td className="num text-right">{fmtUsd(p.avg_entry)}</td>
                  <td className="num text-right">{fmtUsd(p.current_price)}</td>
                  <td className="num text-right">{fmtUsd(p.market_value)}</td>
                  <td className="num text-right" style={{ color: plColor }}>{fmtUsd(p.unrealized_pl, { sign: true })}</td>
                  <td className="num text-right">{fmtPct(p.weight_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/portfolio/positions-table.tsx
git commit -m "feat(frontend): PositionsTable with sortable columns"
```

---

### Task 17: `StrategiesList`

**Files:**
- Create: `frontend/src/components/portfolio/strategies-list.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/strategies-list.tsx`:

```typescript
"use client";
import { useState } from "react";
import type { StrategyGroup } from "@/types/portfolio";
import { fmtUsd, fmtPct } from "@/lib/utils";

type Props = { strategies: StrategyGroup[]; loading: boolean; error: string | null };

export function StrategiesList({ strategies, loading, error }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  return (
    <section className="px-5 py-5 border-b border-[color:var(--hairline)]">
      <h2 className="smallcaps panel-rule mb-4">Strategies</h2>
      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn’t load strategies — {error}</div>
      ) : loading ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : strategies.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No active strategies.</div>
      ) : (
        <ul className="divide-y divide-[color:var(--hairline)]">
          {strategies.map(g => {
            const plColor = (g.unrealized_pl ?? 0) > 0 ? "var(--up)" : (g.unrealized_pl ?? 0) < 0 ? "var(--down)" : "var(--fg)";
            const isOpen = open[g.proposal_id];
            return (
              <li key={g.proposal_id} className="py-3">
                <button
                  onClick={() => setOpen(o => ({ ...o, [g.proposal_id]: !isOpen }))}
                  className="w-full flex items-center justify-between gap-4 text-left"
                >
                  <span className="font-mono text-[13px]">
                    <span className="text-[color:var(--fg)] mr-2">{isOpen ? "▾" : "▸"}</span>
                    <b>{g.ticker}</b>{" "}
                    <span className="text-[color:var(--fg-dim)]">{g.type}</span>{" "}
                    <span className="text-[color:var(--fg-mute)]">exp {g.expiry}</span>
                  </span>
                  <span className="num text-[12.5px]" style={{ color: plColor }}>
                    {fmtUsd(g.unrealized_pl, { sign: true })}
                    <span className="ml-2 text-[color:var(--fg-mute)]">{fmtPct(g.unrealized_pl_pct, { sign: true })}</span>
                  </span>
                </button>
                {isOpen && (
                  <div className="mt-2 ml-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12px] font-mono">
                    <span className="smallcaps">Cost</span>
                    <span className="num">{fmtUsd(g.cost_basis)}</span>
                    <span className="smallcaps">Now</span>
                    <span className="num">{fmtUsd(g.current_value)}</span>
                    <span className="smallcaps">Legs</span>
                    <span>{g.legs_open} of {g.legs_total} open</span>
                    <span className="smallcaps">Contracts</span>
                    <ul className="space-y-0.5">
                      {g.legs.map((l, i) => (
                        <li key={i} className="text-[color:var(--fg-dim)]">
                          <span className="text-[color:var(--fg)] mr-2">{l.side.toUpperCase()}</span>×{l.qty} {l.symbol}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/portfolio/strategies-list.tsx
git commit -m "feat(frontend): StrategiesList collapsible"
```

---

### Task 18: `AllocationCard` — donut + by-underlying bars

**Files:**
- Create: `frontend/src/components/portfolio/allocation-card.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/allocation-card.tsx`:

```typescript
"use client";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import type { Allocations } from "@/types/portfolio";
import { fmtPct, fmtUsd } from "@/lib/utils";

type Props = { allocations: Allocations | null; loading: boolean; error: string | null };

const COLORS = {
  stock: "var(--up)",
  option: "var(--signal)",
  cash: "var(--fg-dim)",
};

export function AllocationCard({ allocations, loading, error }: Props) {
  if (error) {
    return (
      <section className="p-5 border border-[color:var(--hairline)]">
        <h2 className="smallcaps panel-rule mb-4">Allocation</h2>
        <div className="text-[12px] text-[color:var(--down)]">{error}</div>
      </section>
    );
  }
  if (loading || !allocations) {
    return (
      <section className="p-5 border border-[color:var(--hairline)]">
        <h2 className="smallcaps panel-rule mb-4">Allocation</h2>
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      </section>
    );
  }

  const pieData = [
    { name: "stock", value: allocations.by_kind.stock, color: COLORS.stock },
    { name: "option", value: allocations.by_kind.option, color: COLORS.option },
    { name: "cash", value: allocations.by_kind.cash, color: COLORS.cash },
  ].filter(d => d.value > 0);

  const topUnder = allocations.by_underlying.slice(0, 6);
  const maxWeight = Math.max(1, ...topUnder.map(u => u.weight_pct));

  return (
    <section className="p-5 border border-[color:var(--hairline)] h-full">
      <h2 className="smallcaps panel-rule mb-4">Allocation</h2>
      <div className="h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={70} paddingAngle={2}>
              {pieData.map((d, i) => <Cell key={i} fill={d.color} stroke="var(--ink)" />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: "var(--ink-2)", border: "1px solid var(--hairline-2)" }}
              formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px] font-mono mt-2 mb-5">
        {pieData.map(d => (
          <div key={d.name} className="flex items-center gap-1.5">
            <span style={{ background: d.color, width: 8, height: 8, display: "inline-block" }} />
            <span className="text-[color:var(--fg-dim)]">{d.name}</span>
            <span className="num ml-auto">{d.value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
      <div>
        <div className="smallcaps mb-2">By Underlying</div>
        {topUnder.length === 0 ? (
          <div className="text-[11.5px] font-mono text-[color:var(--fg-mute)]">—</div>
        ) : (
          <ul className="space-y-1.5">
            {topUnder.map(u => (
              <li key={u.ticker} className="grid grid-cols-[80px_1fr_auto] items-center gap-2 text-[12px] font-mono">
                <span>{u.ticker}</span>
                <span className="h-1.5 bg-[color:var(--ink-3)] relative">
                  <span
                    className="absolute inset-y-0 left-0 bg-[color:var(--signal)]"
                    style={{ width: `${(u.weight_pct / maxWeight) * 100}%` }}
                  />
                </span>
                <span className="num text-[color:var(--fg-dim)]">{fmtPct(u.weight_pct)} · {fmtUsd(u.market_value, { decimals: 0 })}</span>
              </li>
            ))}
          </ul>
        )}
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
git add frontend/src/components/portfolio/allocation-card.tsx
git commit -m "feat(frontend): AllocationCard donut + by-underlying bars"
```

---

### Task 19: `EquityCurve`

**Files:**
- Create: `frontend/src/components/portfolio/equity-curve.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/equity-curve.tsx`:

```typescript
"use client";
import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import type { EquityCurve as EC, Period } from "@/types/portfolio";
import { getEquityCurve } from "@/lib/api";
import { fmtUsd, fmtPct } from "@/lib/utils";

const PERIODS: Period[] = ["1D", "1W", "1M", "3M", "ALL"];

export function EquityCurve() {
  const [period, setPeriod] = useState<Period>("1M");
  const [data, setData] = useState<EC | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEquityCurve(period)
      .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e: Error) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [period]);

  const plColor = (data?.profit_loss ?? 0) >= 0 ? "var(--up)" : "var(--down)";

  return (
    <section className="p-5 border border-[color:var(--hairline)] h-full flex flex-col">
      <header className="flex items-center justify-between mb-3">
        <div>
          <h2 className="smallcaps">Equity Curve</h2>
          {data && (
            <div className="num text-[18px] mt-1" style={{ color: plColor }}>
              {fmtUsd(data.profit_loss, { sign: true })}{" "}
              <span className="text-[12px] text-[color:var(--fg-mute)] ml-1">{fmtPct((data.profit_loss_pct ?? 0) * 100, { sign: true })}</span>
            </div>
          )}
        </div>
        <div className="flex gap-1">
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2.5 py-1 text-[11px] font-mono tracking-[.14em] border ${period === p ? "border-[color:var(--signal)] text-[color:var(--signal)]" : "border-[color:var(--hairline-2)] text-[color:var(--fg-dim)]"}`}
            >
              {p}
            </button>
          ))}
        </div>
      </header>
      <div className="flex-1 min-h-[220px]">
        {error ? (
          <div className="text-[12px] text-[color:var(--down)]">Couldn’t load curve — {error}</div>
        ) : loading || !data ? (
          <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
        ) : data.points.length === 0 ? (
          <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">Not enough history yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.points}>
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: "var(--fg-mute)" }} hide />
              <YAxis dataKey="equity" tick={{ fontSize: 10, fill: "var(--fg-mute)" }} domain={["auto", "auto"]} width={60} />
              <Tooltip
                contentStyle={{ background: "var(--ink-2)", border: "1px solid var(--hairline-2)" }}
                formatter={(v: number) => [fmtUsd(v), "equity"]}
                labelFormatter={(l: string) => new Date(l).toLocaleString()}
              />
              <Line type="monotone" dataKey="equity" stroke="var(--signal)" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
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
git add frontend/src/components/portfolio/equity-curve.tsx
git commit -m "feat(frontend): EquityCurve with period toggle"
```

---

### Task 20: `HistoryTable`

**Files:**
- Create: `frontend/src/components/portfolio/history-table.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/portfolio/history-table.tsx`:

```typescript
"use client";
import type { HistoryRow } from "@/types/portfolio";

type Props = { rows: HistoryRow[]; loading: boolean; error: string | null };

const STATUS_COLOR: Record<HistoryRow["status"], string> = {
  pending: "var(--fg-dim)",
  approved: "var(--signal)",
  rejected: "var(--down)",
  executed: "var(--up)",
  failed: "var(--down)",
};

export function HistoryTable({ rows, loading, error }: Props) {
  return (
    <section className="px-5 py-5">
      <h2 className="smallcaps panel-rule mb-4">History</h2>
      {error ? (
        <div className="text-[12px] text-[color:var(--down)]">Couldn’t load history — {error}</div>
      ) : loading ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">loading…</div>
      ) : rows.length === 0 ? (
        <div className="text-[12px] text-[color:var(--fg-mute)] font-mono">No proposals yet.</div>
      ) : (
        <table className="w-full text-[12.5px] font-mono">
          <thead>
            <tr className="text-[color:var(--fg-mute)] text-left">
              <th className="py-1">Ticker</th>
              <th>Status</th>
              <th>Created</th>
              <th>Executed</th>
              <th>Order</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.proposal_id} className="border-t border-[color:var(--hairline)]">
                <td className="py-1.5">{r.ticker}</td>
                <td style={{ color: STATUS_COLOR[r.status] }}>{r.status}</td>
                <td className="text-[color:var(--fg-dim)]">{new Date(r.created_at).toLocaleString()}</td>
                <td className="text-[color:var(--fg-dim)]">{r.executed_at ? new Date(r.executed_at).toLocaleString() : "—"}</td>
                <td className="text-[color:var(--fg-dim)] truncate max-w-[180px]">{r.alpaca_order_id ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/portfolio/history-table.tsx
git commit -m "feat(frontend): HistoryTable component"
```

---

### Task 21: `PortfolioView` container

**Files:**
- Create: `frontend/src/components/portfolio/portfolio-view.tsx`

- [ ] **Step 1: Create the container**

Create `frontend/src/components/portfolio/portfolio-view.tsx`:

```typescript
"use client";
import { useCallback, useEffect, useState } from "react";
import type { PortfolioSnapshot } from "@/types/portfolio";
import { getPortfolioSnapshot } from "@/lib/api";
import { usePortfolioInvalidate } from "@/lib/portfolio-events";
import { PortfolioHeader } from "./portfolio-header";
import { AccountSummary } from "./account-summary";
import { EquityCurve } from "./equity-curve";
import { AllocationCard } from "./allocation-card";
import { StrategiesList } from "./strategies-list";
import { PositionsTable } from "./positions-table";
import { HistoryTable } from "./history-table";

function hasError(snap: PortfolioSnapshot | null, key: string): string | null {
  return snap?.errors.includes(key) ? key : null;
}

export function PortfolioView() {
  const [snap, setSnap] = useState<PortfolioSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    getPortfolioSnapshot()
      .then(d => { setSnap(d); setLoading(false); })
      .catch((e: Error) => { setError(e.message); setLoading(false); });
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  usePortfolioInvalidate(refresh);

  return (
    <div className="flex flex-col">
      <PortfolioHeader fetchedAt={snap?.fetched_at ?? null} refreshing={loading} onRefresh={refresh} />

      {error && !snap && (
        <div className="px-5 py-4 text-[12px] text-[color:var(--down)]">
          Couldn’t load snapshot — {error} <button onClick={refresh} className="ml-2 underline">retry</button>
        </div>
      )}

      <AccountSummary
        account={snap?.account ?? null}
        loading={loading && !snap}
        error={hasError(snap, "account_unavailable")}
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 px-5 py-5 border-b border-[color:var(--hairline)]">
        <div className="lg:col-span-8">
          <EquityCurve />
        </div>
        <div className="lg:col-span-4">
          <AllocationCard
            allocations={snap?.allocations ?? null}
            loading={loading && !snap}
            error={null}
          />
        </div>
      </div>

      <StrategiesList
        strategies={snap?.strategies ?? []}
        loading={loading && !snap}
        error={hasError(snap, "strategies_unavailable")}
      />

      <PositionsTable
        positions={snap?.positions ?? []}
        loading={loading && !snap}
        error={hasError(snap, "positions_unavailable")}
      />

      <HistoryTable
        rows={snap?.history ?? []}
        loading={loading && !snap}
        error={hasError(snap, "history_unavailable")}
      />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/portfolio/portfolio-view.tsx
git commit -m "feat(frontend): PortfolioView container with refresh + invalidation"
```

---

### Task 22: Route shell `/portfolio`

**Files:**
- Create: `frontend/src/app/portfolio/page.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/app/portfolio/page.tsx`:

```typescript
import { PortfolioView } from "@/components/portfolio/portfolio-view";

export default function PortfolioPage() {
  return (
    <div style={{ minHeight: "calc(100vh - 36px)" }} className="reveal reveal-1">
      <PortfolioView />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/portfolio/page.tsx
git commit -m "feat(frontend): /portfolio route shell"
```

---

### Task 23: Top-bar nav link in `StatusRail`

The existing global header is `StatusRail` rendered from `app/layout.tsx`. Add a Trade/Portfolio toggle.

**Files:**
- Modify: `frontend/src/components/status-rail.tsx`

- [ ] **Step 1: Inspect the current StatusRail**

Run: `cat frontend/src/components/status-rail.tsx | head -80` to see current structure (the agent should read this file fully before editing).

- [ ] **Step 2: Add nav links**

Add this snippet inside `StatusRail`'s rendered JSX, in the right-side cluster of the bar (look for the existing right-aligned region — typically inside an element with `ml-auto` or `justify-end`). Add as a sibling of existing right-side controls:

```typescript
<nav className="flex items-center gap-1 ml-2">
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
</nav>
```

Also add at the top of the file:

```typescript
import Link from "next/link";
import { usePathname } from "next/navigation";
```

And inside the component body, before the return:

```typescript
const pathname = usePathname();
```

If `StatusRail` is not currently a client component, add `"use client";` to the very top of the file. (It almost certainly already is — verify before adding.)

- [ ] **Step 3: Typecheck and build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/status-rail.tsx
git commit -m "feat(frontend): Trade/Portfolio nav links in StatusRail"
```

---

## Phase 4 — End-to-end verification

### Task 24: Backend offline smoke

**Files:** none (verification only)

- [ ] **Step 1: Boot backend in fixtures mode**

Run (in one terminal): `cd backend && source .venv/bin/activate && FIXTURES_MODE=1 ALPACA_BASE_URL=https://paper-api.alpaca.markets uvicorn app.main:app --port 8000`

- [ ] **Step 2: Hit each endpoint**

In another terminal:

```bash
curl -s http://localhost:8000/portfolio/snapshot | head -c 600
echo
curl -s "http://localhost:8000/portfolio/equity-curve?period=1M" | head -c 600
echo
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/portfolio/equity-curve?period=BOGUS"
```

Expected:
- `snapshot` returns JSON with `account`, `positions`, `strategies`, `allocations`, `history`, `errors`, `fetched_at` keys
- `equity-curve?period=1M` returns JSON with `period`, `points`, `base_value`, `profit_loss`, `profit_loss_pct`
- `period=BOGUS` returns `400`

- [ ] **Step 3: Stop the backend**

Ctrl-C the backend terminal.

(No commit — verification only.)

---

### Task 25: Frontend dev smoke

**Files:** none (verification only)

- [ ] **Step 1: Boot both servers**

Terminal 1: `cd backend && source .venv/bin/activate && FIXTURES_MODE=1 make dev`
Terminal 2: `cd frontend && pnpm dev`

- [ ] **Step 2: Manual smoke checklist**

Open `http://localhost:3000/portfolio` in a browser and verify:

1. Page renders all sections: header, account summary, equity curve, allocation, strategies, positions, history.
2. Equity curve loads at 1M; toggling 1D / 1W / 3M / ALL refetches *only* the curve (other cards do not re-skeleton).
3. Click **Refresh** — `last updated` timestamp advances; cards re-render.
4. Navigate to `/` (via Trade link) — the trading dashboard still works.
5. Submit and approve a proposal on `/`. Navigate back to `/portfolio`. Confirm the snapshot refetched (timestamp advanced) — if the page was kept open, the invalidation event should trigger automatic refresh.
6. The `← Trade` link in the portfolio header returns to `/`.
7. Resize to mobile width — sections stack single-column; allocation card moves below curve.

- [ ] **Step 3: Production build sanity**

Run: `cd frontend && pnpm build`
Expected: PASS

(No commit — verification only.)

---

### Task 26: Final test suite + commit a changelog note

**Files:** none new (verification + summary commit)

- [ ] **Step 1: Run full backend tests**

Run: `cd backend && pytest -v`
Expected: PASS (all tests, original + new)

- [ ] **Step 2: Final typecheck and build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: PASS

- [ ] **Step 3: Update README API reference**

Modify `README.md` — find the "API reference" table and add two rows after `/bars/{symbol}`:

```markdown
| `/portfolio/snapshot` | GET | Account + positions + strategies + allocations + history |
| `/portfolio/equity-curve?period=1D|1W|1M|3M|ALL` | GET | Equity over time |
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: portfolio endpoints in API reference"
```

---

## Self-review

**Spec coverage:**
- New `/portfolio` route → Task 22 ✅
- Account summary card → Task 15 ✅
- Positions table with weights/P&L → Task 16 ✅
- Strategies grouped via local Proposals → Tasks 5, 17 ✅
- Allocation breakdown (kind + by-underlying) → Tasks 3, 18 ✅
- Equity curve with period toggle → Tasks 2, 7, 19 ✅
- History table from Proposal+Execution → Task 20 ✅
- Refresh on load + post-approve + manual button → Tasks 11, 12, 14, 21 ✅
- Hybrid backend (snapshot + equity-curve) → Tasks 6, 7, 8 ✅
- Conservative strategy grouping (local Proposals only) → Task 5 ✅
- Per-card error state + partial-failure backend → Tasks 6, 15-21 ✅
- Empty-state handling (no positions, no history) → Tasks 16, 17, 20 ✅
- Filter qty=0 positions → Task 4 ✅
- Partially-closed strategy ("N of M legs open") → Task 5 ✅
- Fixtures for offline mode → Tasks 1, 2 (FIXTURES_MODE branches inline) ✅
- Nav between Trade and Portfolio → Task 23 ✅
- README API ref updated → Task 26 ✅

**Placeholder scan:** none.

**Type consistency:** `PortfolioSnapshot`, `EquityCurve`, `Position`, `StrategyGroup`, `Allocations`, `HistoryRow`, `AccountSummary`, `Period` defined once in `frontend/src/types/portfolio.ts` (Task 9) and consumed by every subsequent task. Backend field names (`fetched_at`, `errors`, `legs_open`, `legs_total`, `unrealized_pl_pct`, `weight_pct`, `by_kind`, `by_underlying`) match the TS types exactly.

**Out-of-scope confirmation:** no agent tool, no WebSocket portfolio push, no aggressive grouping by Alpaca order_id, no CSV export — matches spec.
