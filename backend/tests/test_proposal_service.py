from app.services.proposal_service import compute_risk_reward


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
