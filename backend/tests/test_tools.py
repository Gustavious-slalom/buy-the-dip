# backend/tests/test_tools.py
from app.agent.tools import TOOLS

def test_execute_trade_not_in_tools():
    names = {t["name"] for t in TOOLS}
    assert "execute_trade" not in names
    assert {"get_quote","get_options_chain","get_greeks","get_news","get_portfolio","get_positions","propose_trade"}.issubset(names)
