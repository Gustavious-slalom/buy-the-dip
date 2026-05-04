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
