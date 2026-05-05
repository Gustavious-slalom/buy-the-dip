from datetime import datetime, timezone
from sqlmodel import SQLModel, Field

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Proposal(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str
    created_at: datetime = Field(default_factory=_now)
    ticker: str
    legs_json: str
    max_risk: float
    max_reward: float | None = None
    breakeven: float | None = None
    expiry: str
    rationale: str
    confidence: float
    risks_json: str
    status: str = "pending"  # pending | approved | rejected | executed | failed

class Execution(SQLModel, table=True):
    id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="proposal.id")
    alpaca_order_id: str | None = None
    submitted_at: datetime = Field(default_factory=_now)
    status: str  # submitted | filled | rejected | failed
    raw_response_json: str

class Trace(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    ts: datetime = Field(default_factory=_now)
    event_type: str
    payload_json: str

class Watchlist(SQLModel, table=True):
    ticker: str = Field(primary_key=True)
    added_at: datetime = Field(default_factory=_now)

class SellRule(SQLModel, table=True):
    symbol: str = Field(primary_key=True)
    take_profit: float           # e.g. 0.01 → sell when gain >= 1%
    stop_loss: float             # e.g. -0.003 → sell when loss <= -0.3%
    qty: float | None = None     # None = close full position
    active: bool = True
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

class SellOrder(SQLModel, table=True):
    id: str = Field(primary_key=True)
    symbol: str
    qty: float
    trigger: str                   # "manual" | "take_profit" | "stop_loss"
    avg_entry: float
    trigger_price: float | None = None
    alpaca_order_id: str | None = None
    status: str                    # "submitted" | "filled" | "failed"
    submitted_at: datetime = Field(default_factory=_now)
    raw_response_json: str = ""
