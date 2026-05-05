from app.services.proposal_service import compute_risk_reward
import pytest
from unittest.mock import patch


def test_long_call_risk():
    legs = [{"action":"buy","side":"call","qty":1,"strike":200,"premium":3.0,"contract_symbol":"X"}]
    r = compute_risk_reward(legs)
    assert r["max_risk"] == 300.0
    assert r["max_reward"] is None  # unlimited
    assert r["breakeven"] == 203.0


def test_vertical_call_spread():
    legs = [
        {"action":"buy","side":"call","qty":1,"strike":200,"premium":3.0,"contract_symbol":"A"},
        {"action":"sell","side":"call","qty":1,"strike":210,"premium":1.0,"contract_symbol":"B"},
    ]
    r = compute_risk_reward(legs)
    assert r["max_risk"] == 200.0   # net debit 2.00 * 100
    assert r["max_reward"] == 800.0 # (10 width - 2 debit) * 100
    assert r["breakeven"] == 202.0


def test_credit_call_spread():
    legs = [
        {"action":"sell","side":"call","qty":1,"strike":200,"premium":3.0,"contract_symbol":"A"},
        {"action":"buy","side":"call","qty":1,"strike":210,"premium":1.0,"contract_symbol":"B"},
    ]
    r = compute_risk_reward(legs)
    assert r["max_reward"] == 200.0  # net credit 2.00 * 100
    assert r["max_risk"] == 800.0    # (10 width * 1 - 2 credit) * 100
    assert r["breakeven"] == 198.0   # short_strike 200 - net_credit 2


def test_ratio_spread_returns_safe_fallback():
    """Ratio spreads (unequal leg quantities) must NOT return a max_reward.
    Treating them as verticals produces a wrong max_reward figure."""
    legs = [
        {"action": "buy",  "side": "call", "qty": 2, "strike": 200, "premium": 3.0, "contract_symbol": "A"},
        {"action": "sell", "side": "call", "qty": 1, "strike": 210, "premium": 1.0, "contract_symbol": "B"},
    ]
    r = compute_risk_reward(legs)
    # net_debit = 2*3 - 1*1 = 5.0 → max_risk = 500
    assert r["max_risk"] == 500.0
    assert r["max_reward"] is None   # unknown — ratio spread has complex risk
    assert r["breakeven"] is None


def test_create_proposal_raises_if_over_max_risk():
    """create_proposal must reject proposals that exceed MAX_RISK_USD before DB write."""
    # A single long call with premium=60 and qty=1 → max_risk = 6000
    legs = [{"action": "buy", "side": "call", "qty": 1, "strike": 500, "premium": 60.0, "contract_symbol": "X"}]
    with patch("app.services.proposal_service.settings") as mock_settings:
        mock_settings.max_risk_usd = 5000.0
        with pytest.raises(ValueError, match="exceeds MAX_RISK_USD"):
            from app.services.proposal_service import create_proposal
            create_proposal(
                session_id="s1", ticker="AAPL", legs=legs,
                rationale="test", confidence=0.8, risks=[], expiry="2026-06-20"
            )
