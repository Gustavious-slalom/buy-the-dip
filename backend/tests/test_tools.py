# backend/tests/test_tools.py
from app.agent.tools import TOOLS

def test_execute_trade_not_in_tools():
    names = {t["name"] for t in TOOLS}
    assert "execute_trade" not in names
    assert {"get_quote","get_options_chain","get_greeks","get_news","get_portfolio","get_positions","propose_trade"}.issubset(names)

import pytest
from unittest.mock import patch
from app.agent.tools import dispatch


@pytest.mark.asyncio
async def test_dispatch_get_quote(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    result = await dispatch("get_quote", {"symbol": "AAPL"}, session_id="s1")
    assert {"symbol", "price", "bid", "ask", "ts"}.issubset(result.keys())


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_raises():
    with pytest.raises(ValueError, match="unknown tool"):
        await dispatch("execute_trade", {}, session_id="s1")
