import uuid
import json
from app.db import get_session
from app.models import Proposal


def compute_risk_reward(legs: list[dict]) -> dict:
    """
    Compute risk/reward metrics for a multi-leg option strategy.
    
    Supports:
    - Single long call/put: max_risk = premium * 100 * qty, max_reward = None (unlimited)
    - Vertical debit/credit spread: max_risk and max_reward based on width and net debit
    """
    longs = [l for l in legs if l["action"] == "buy"]
    shorts = [l for l in legs if l["action"] == "sell"]
    net_debit = sum(l["premium"] * l["qty"] for l in longs) - sum(l["premium"] * l["qty"] for l in shorts)
    
    # Single long call/put
    if len(legs) == 1 and legs[0]["action"] == "buy":
        l = legs[0]
        be = l["strike"] + l["premium"] if l["side"] == "call" else l["strike"] - l["premium"]
        return {"max_risk": l["premium"] * 100 * l["qty"], "max_reward": None, "breakeven": be}
    
    # Vertical spread (same side, different strikes)
    if len(legs) == 2 and legs[0]["side"] == legs[1]["side"]:
        width = abs(legs[0]["strike"] - legs[1]["strike"])
        if net_debit > 0:  # debit spread
            long_strike = next(l["strike"] for l in longs)
            be = long_strike + net_debit if longs[0]["side"] == "call" else long_strike - net_debit
            return {"max_risk": net_debit * 100, "max_reward": (width - net_debit) * 100, "breakeven": be}
    
    # Fallback
    return {"max_risk": abs(net_debit) * 100, "max_reward": None, "breakeven": None}


def create_proposal(session_id: str, ticker: str, legs: list[dict], rationale: str,
                    confidence: float, risks: list[str], expiry: str) -> dict:
    """
    Create a proposal and persist to database.
    
    Returns a dict with proposal_id and computed risk/reward metrics.
    """
    rr = compute_risk_reward(legs)
    pid = str(uuid.uuid4())
    p = Proposal(
        id=pid,
        session_id=session_id,
        ticker=ticker,
        legs_json=json.dumps(legs),
        max_risk=rr["max_risk"],
        max_reward=rr["max_reward"],
        breakeven=rr["breakeven"],
        expiry=expiry,
        rationale=rationale,
        confidence=confidence,
        risks_json=json.dumps(risks),
        status="pending",
    )
    with get_session() as s:
        s.add(p)
        s.commit()
        s.refresh(p)
    
    return {
        "proposal_id": pid,
        **rr,
        "legs": legs,
        "rationale": rationale,
        "confidence": confidence,
        "risks": risks,
        "expiry": expiry,
        "ticker": ticker,
    }
