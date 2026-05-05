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
