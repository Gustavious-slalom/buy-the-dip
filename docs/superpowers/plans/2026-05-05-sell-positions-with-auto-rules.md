# Sell Positions with Automated Take-Profit & Stop-Loss

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users sell any open stock position from the Portfolio UI — immediately (market order), or via automated rules that fire without manual confirmation:
- **Take-profit:** auto-sell when a position's gain reaches +1 % above avg entry.
- **Stop-loss:** auto-sell when a position's loss reaches −0.3 % below avg entry.

**Architecture:** A new `SellOrder` SQLModel tracks every sell request and its outcome. A lightweight price-monitor background task (FastAPI lifespan) polls open positions' live prices and fires sell orders when thresholds are crossed. The frontend adds a "Sell" button per row in `PositionsTable` plus a per-position rule-configuration panel. Sell events invalidate the portfolio via the existing `portfolio:invalidate` event.

**Safety invariant (matching existing pattern):** Immediate sells require explicit user confirmation in the UI. Auto-rule sells execute without confirmation but are rate-limited, logged, and only apply to stock positions (not options) to avoid complex contract mechanics.

**Tech Stack:** Python 3.11 / FastAPI (lifespan background task) / SQLModel / SQLite / alpaca-py (MarketOrderRequest). Next.js App Router / TypeScript / Tailwind.

---

## File Structure

### New backend files
- `backend/app/models.py` — add `SellOrder`, `SellRule` models
- `backend/app/services/sell_service.py` — `sell_position`, `set_rule`, `list_rules`, `delete_rule`
- `backend/app/services/monitor_service.py` — background price polling + auto-rule executor
- `backend/tests/test_sell_service.py` — unit tests for sell_service
- `backend/tests/test_monitor_service.py` — unit tests for monitor thresholds
- `backend/tests/fixtures/sell_order_fixture.json` — canned sell order response

### Modified backend files
- `backend/app/models.py` — append `SellOrder` and `SellRule` tables
- `backend/app/api/http.py` — add `/positions/sell`, `/positions/rules` (CRUD) endpoints
- `backend/app/services/alpaca_service.py` — add `sell_stock_position(symbol, qty)` using `MarketOrderRequest`
- `backend/app/main.py` — register monitor_service background task in FastAPI lifespan

### New frontend files
- `frontend/src/components/portfolio/sell-button.tsx` — confirm-then-sell dialog per position row
- `frontend/src/components/portfolio/sell-rule-panel.tsx` — per-position take-profit / stop-loss toggle + threshold display
- `frontend/src/lib/sell-api.ts` — `sellPosition`, `setSellRule`, `deleteSellRule`, `listSellRules`
- `frontend/src/types/sell.ts` — `SellOrder`, `SellRule` TypeScript types

### Modified frontend files
- `frontend/src/components/portfolio/positions-table.tsx` — add Sell button + rule indicator column
- `frontend/src/lib/portfolio-events.ts` — add `emitSellExecuted` (same channel as invalidate)

---

## Data Models

### `SellRule` (SQLite table)
```
symbol        TEXT PK        — position symbol (stock only)
take_profit   REAL           — % gain threshold to auto-sell (e.g. 0.01 = 1%)
stop_loss     REAL           — % loss threshold to auto-sell (e.g. -0.003 = -0.3%)
qty           REAL           — shares to sell when triggered (default: full qty)
active        BOOL           — rule enabled flag
created_at    DATETIME
updated_at    DATETIME
```

### `SellOrder` (SQLite table)
```
id                TEXT PK    — uuid
symbol            TEXT
qty               REAL
trigger           TEXT       — "manual" | "take_profit" | "stop_loss"
avg_entry         REAL       — recorded at submission time
trigger_price     REAL       — price at which rule fired (null for manual)
alpaca_order_id   TEXT
status            TEXT       — "submitted" | "filled" | "failed"
submitted_at      DATETIME
raw_response_json TEXT
```

---

## Phase 1 — Backend: sell_position + alpaca_service

### Task 1: `sell_stock_position` in `alpaca_service`

**Files:**
- Modify: `backend/app/services/alpaca_service.py`
- Test: `backend/tests/test_sell_service.py`

- [ ] **Step 1: Write failing test**
```python
def test_sell_stock_position_fixtures(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    result = alpaca_service.sell_stock_position("AAPL", qty=10)
    assert result["status"] in ("accepted", "filled", "new")
    assert "id" in result
```

- [ ] **Step 2: Run test → confirm FAIL**
```bash
cd backend && pytest tests/test_sell_service.py::test_sell_stock_position_fixtures -v
```

- [ ] **Step 3: Implement**

Add to `backend/app/services/alpaca_service.py` (after `submit_multileg_order`):
```python
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

def sell_stock_position(symbol: str, qty: float) -> dict:
    """Submit a market sell order for `qty` shares of `symbol` (paper only)."""
    settings.assert_paper()
    if settings.fixtures_mode:
        return {"id": f"fixture-sell-{symbol}", "status": "accepted", "raw": "{}"}
    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    order = _trading().submit_order(req)
    return {"id": str(order.id), "status": str(order.status), "raw": order.model_dump_json()}
```

- [ ] **Step 4: Run test → confirm PASS**

---

### Task 2: `SellOrder` + `SellRule` models

**Files:** `backend/app/models.py`

- [ ] **Step 1: Write failing test**
```python
def test_sell_rule_model_fields():
    from app.models import SellRule
    r = SellRule(symbol="AAPL", take_profit=0.01, stop_loss=-0.003, qty=10.0)
    assert r.active is True
```

- [ ] **Step 2: Implement**

Append to `backend/app/models.py`:
```python
class SellRule(SQLModel, table=True):
    symbol: str = Field(primary_key=True)
    take_profit: float          # e.g. 0.01 → sell when gain >= 1%
    stop_loss: float            # e.g. -0.003 → sell when loss <= -0.3%
    qty: float | None = None    # None = close full position
    active: bool = True
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

class SellOrder(SQLModel, table=True):
    id: str = Field(primary_key=True)
    symbol: str
    qty: float
    trigger: str                  # "manual" | "take_profit" | "stop_loss"
    avg_entry: float
    trigger_price: float | None = None
    alpaca_order_id: str | None = None
    status: str                   # "submitted" | "filled" | "failed"
    submitted_at: datetime = Field(default_factory=_now)
    raw_response_json: str = ""
```

- [ ] **Step 3: Run test → confirm PASS**

---

### Task 3: `sell_service.py`

**Files:**
- Create: `backend/app/services/sell_service.py`
- Test: `backend/tests/test_sell_service.py`

- [ ] **Step 1: Write failing tests**
```python
def test_sell_position_creates_sell_order(...)
def test_set_rule_upserts_correctly(...)
def test_delete_rule_deactivates(...)
def test_list_rules_returns_active_only(...)
```

- [ ] **Step 2: Implement `sell_service.py`**
```python
import uuid
from datetime import datetime, timezone
from sqlmodel import select
from app.db import get_session
from app.models import SellOrder, SellRule
from app.services import alpaca_service

def sell_position(symbol: str, qty: float, avg_entry: float,
                  trigger: str = "manual", trigger_price: float | None = None) -> dict:
    """Execute a market sell and persist a SellOrder record."""
    order = alpaca_service.sell_stock_position(symbol, qty)
    record = SellOrder(
        id=str(uuid.uuid4()), symbol=symbol, qty=qty,
        trigger=trigger, avg_entry=avg_entry,
        trigger_price=trigger_price,
        alpaca_order_id=order["id"],
        status=order["status"],
        raw_response_json=order["raw"],
    )
    with get_session() as s:
        s.add(record); s.commit()
    return {"ok": True, "sell_order_id": record.id, "alpaca_order_id": order["id"], "status": order["status"]}

def set_rule(symbol: str, take_profit: float, stop_loss: float, qty: float | None = None) -> SellRule:
    with get_session() as s:
        rule = s.get(SellRule, symbol)
        if rule:
            rule.take_profit = take_profit
            rule.stop_loss = stop_loss
            rule.qty = qty
            rule.active = True
            rule.updated_at = datetime.now(timezone.utc)
        else:
            rule = SellRule(symbol=symbol, take_profit=take_profit, stop_loss=stop_loss, qty=qty)
        s.add(rule); s.commit(); s.refresh(rule)
    return rule

def delete_rule(symbol: str) -> None:
    with get_session() as s:
        rule = s.get(SellRule, symbol)
        if rule:
            rule.active = False
            s.add(rule); s.commit()

def list_rules() -> list[SellRule]:
    with get_session() as s:
        return s.exec(select(SellRule).where(SellRule.active == True)).all()  # noqa: E712
```

- [ ] **Step 3: Run tests → confirm PASS**

---

## Phase 2 — Backend: price monitor background task

### Task 4: `monitor_service.py`

**Files:**
- Create: `backend/app/services/monitor_service.py`
- Test: `backend/tests/test_monitor_service.py`

- [ ] **Step 1: Write failing tests**
```python
def test_check_thresholds_fires_take_profit(...)
    # position with +1.5% gain → sell triggered
def test_check_thresholds_fires_stop_loss(...)
    # position with -0.5% loss → sell triggered
def test_check_thresholds_no_trigger(...)
    # position at +0.5% → no sell
def test_check_thresholds_skips_options(...)
    # OCC symbol → skipped (len >= 15)
```

- [ ] **Step 2: Implement `monitor_service.py`**
```python
import asyncio
import logging
from app.services import alpaca_service, sell_service
from app.services.portfolio_service import OCC_MIN_LEN

log = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 15

async def check_thresholds_once() -> list[dict]:
    """Single evaluation pass. Returns list of triggered sells (for testing)."""
    triggered = []
    rules = sell_service.list_rules()
    if not rules:
        return triggered
    # Only stock positions (skip OCC option symbols)
    stock_rules = [r for r in rules if len(r.symbol) < OCC_MIN_LEN]
    if not stock_rules:
        return triggered
    positions = alpaca_service.get_positions()
    pos_by_sym = {p["symbol"]: p for p in positions}
    symbols = [r.symbol for r in stock_rules if r.symbol in pos_by_sym]
    if not symbols:
        return triggered
    prices = alpaca_service.get_latest_prices(symbols)
    for rule in stock_rules:
        pos = pos_by_sym.get(rule.symbol)
        price = prices.get(rule.symbol)
        if not pos or price is None:
            continue
        avg_entry = float(pos["avg_entry_price"])
        if avg_entry == 0:
            continue
        pct_change = (price - avg_entry) / avg_entry
        qty = rule.qty or float(pos["qty"])
        if pct_change >= rule.take_profit:
            log.info("take_profit triggered %s pct=%.4f", rule.symbol, pct_change)
            result = sell_service.sell_position(
                rule.symbol, qty, avg_entry,
                trigger="take_profit", trigger_price=price,
            )
            triggered.append(result)
        elif pct_change <= rule.stop_loss:
            log.info("stop_loss triggered %s pct=%.4f", rule.symbol, pct_change)
            result = sell_service.sell_position(
                rule.symbol, qty, avg_entry,
                trigger="stop_loss", trigger_price=price,
            )
            triggered.append(result)
    return triggered

async def run_monitor():
    """Infinite polling loop. Called from FastAPI lifespan."""
    while True:
        try:
            await check_thresholds_once()
        except Exception as e:
            log.warning("monitor error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

- [ ] **Step 3: Register in `main.py` lifespan**
```python
from contextlib import asynccontextmanager
from app.services import monitor_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(monitor_service.run_monitor())
    yield
    task.cancel()
```

- [ ] **Step 4: Run tests → confirm PASS**

---

## Phase 3 — Backend: HTTP endpoints

### Task 5: `/positions/sell` + `/positions/rules` endpoints

**Files:** `backend/app/api/http.py`

- [ ] **Step 1: Write failing endpoint tests**
```python
def test_sell_position_endpoint(client)
def test_set_sell_rule_endpoint(client)
def test_delete_sell_rule_endpoint(client)
def test_list_sell_rules_endpoint(client)
```

- [ ] **Step 2: Implement**

Add to `backend/app/api/http.py`:
```python
from app.services import sell_service

class SellBody(BaseModel):
    symbol: str
    qty: float
    avg_entry: float

class SellRuleBody(BaseModel):
    symbol: str
    take_profit: float = 0.01    # default +1%
    stop_loss: float = -0.003    # default -0.3%
    qty: float | None = None

@router.post("/positions/sell")
def sell_position(body: SellBody):
    try:
        return sell_service.sell_position(body.symbol, body.qty, body.avg_entry)
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/positions/rules")
def set_sell_rule(body: SellRuleBody):
    rule = sell_service.set_rule(body.symbol, body.take_profit, body.stop_loss, body.qty)
    return rule.model_dump()

@router.delete("/positions/rules/{symbol}")
def delete_sell_rule(symbol: str):
    sell_service.delete_rule(symbol)
    return {"ok": True}

@router.get("/positions/rules")
def list_sell_rules():
    return [r.model_dump() for r in sell_service.list_rules()]
```

- [ ] **Step 3: Run tests → confirm PASS**

---

## Phase 4 — Frontend: sell UI

### Task 6: Types + API client

**Files:**
- Create: `frontend/src/types/sell.ts`
- Create: `frontend/src/lib/sell-api.ts`

- [ ] **Implement `sell.ts`**
```typescript
export type SellOrder = {
  sell_order_id: string;
  alpaca_order_id: string;
  status: string;
};

export type SellRule = {
  symbol: string;
  take_profit: number;   // e.g. 0.01
  stop_loss: number;     // e.g. -0.003
  qty: number | null;
  active: boolean;
};
```

- [ ] **Implement `sell-api.ts`**
```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function sellPosition(symbol: string, qty: number, avg_entry: number) { ... }
export async function setSellRule(symbol: string, take_profit: number, stop_loss: number, qty?: number) { ... }
export async function deleteSellRule(symbol: string) { ... }
export async function listSellRules(): Promise<SellRule[]> { ... }
```

---

### Task 7: `SellButton` component

**File:** `frontend/src/components/portfolio/sell-button.tsx`

Behaviour:
- Renders a small "Sell" button in each stock row.
- On click: shows inline confirm prompt showing symbol, qty, current P/L colour.
- On confirm: calls `sellPosition()`, toasts result, emits `portfolio:invalidate`.
- Disabled for option positions (kind === "option").

- [ ] **Implement `SellButton`**
- [ ] **Wire into `PositionsTable` — add "Sell" column (stock rows only)**

---

### Task 8: `SellRulePanel` component

**File:** `frontend/src/components/portfolio/sell-rule-panel.tsx`

Behaviour:
- Collapsible panel beneath each stock position row.
- Shows current rule status: "Take-profit: +1.0% | Stop-loss: −0.3% | Active ✓".
- Toggle switches to enable/disable.
- Edit fields for custom thresholds (validates: take_profit > 0, stop_loss < 0).
- Calls `setSellRule` / `deleteSellRule` on save/remove.
- Default values pre-filled: take_profit = 0.01, stop_loss = -0.003.

- [ ] **Implement `SellRulePanel`**
- [ ] **Wire into `PositionsTable` — expandable row beneath each stock position**

---

## Phase 5 — Validation

### Task 9: Run full test suite + build

- [ ] **Backend**
```bash
cd backend && source .venv/bin/activate && pytest -v
```
Expected: all tests pass (no regressions)

- [ ] **Frontend**
```bash
cd frontend && pnpm build
```
Expected: builds cleanly, no TypeScript errors

- [ ] **Manual smoke test (FIXTURES_MODE=1)**
  1. Open `/portfolio` — verify Sell buttons appear on stock rows, disabled on option rows.
  2. Click Sell on any row → confirm dialog appears with correct symbol/qty.
  3. Confirm → toast shows order ID → portfolio refreshes.
  4. Open rule panel → toggle take-profit + stop-loss → save → rule badge appears on row.
  5. Disable rule → badge disappears.

---

## Edge Cases & Safety Constraints

| Concern | Mitigation |
|---|---|
| Auto-sell options | Skipped — OCC symbols (`len >= OCC_MIN_LEN`) are excluded from monitor |
| Double-trigger (rule fires twice) | After sell executes, deactivate the rule (`active = False`) |
| Partial fill leaves residual | SellOrder records actual submitted qty; UI reflects alpaca status |
| Monitor crashes | `run_monitor` wraps each iteration in try/except; lifespan task is restarted on next server restart |
| Sell more than held | Backend validates `qty <= position.qty` before submitting to Alpaca |
| Thresholds too tight | Frontend validates: take_profit ∈ (0, 1], stop_loss ∈ [-1, 0) |

---

## Commit Strategy

```
feat(backend): add SellRule + SellOrder models
feat(backend): sell_stock_position in alpaca_service
feat(backend): sell_service — sell_position + rule CRUD
feat(backend): monitor_service — auto take-profit / stop-loss polling
feat(backend): /positions/sell + /positions/rules endpoints
feat(frontend): sell types + sell-api client
feat(frontend): SellButton with confirm dialog in PositionsTable
feat(frontend): SellRulePanel with take-profit / stop-loss controls
```
