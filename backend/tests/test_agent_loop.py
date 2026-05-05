# backend/tests/test_agent_loop.py
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.agent.loop import run_session

class FakeEmit:
    def __init__(self): self.events = []
    async def __call__(self, evt): self.events.append(evt)

def _make_stream(deltas: list[str], final_message):
    """Builds an async context manager that mimics client.messages.stream(...)."""
    async def text_stream_gen():
        for d in deltas:
            yield d

    stream_obj = MagicMock()
    stream_obj.text_stream = text_stream_gen()
    stream_obj.get_final_message = AsyncMock(return_value=final_message)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=stream_obj)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm

def test_loop_emits_proposal(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service, news_service, proposal_service
    from app.agent import tools
    reload(alpaca_service); reload(news_service); reload(proposal_service); reload(tools)
    from app.db import init_db; init_db()

    # Turn 1: stream a few thinking deltas, then a propose_trade tool_use block.
    # Note: MagicMock(name=...) sets the mock's internal repr name, NOT mock.name.
    # We must set .name as a regular attribute after construction.
    tool_use_block = MagicMock(type="tool_use", id="t1")
    tool_use_block.name = "propose_trade"
    tool_use_block.input = {
        "ticker":"AAPL",
        "legs":[{"action":"buy","side":"call","qty":1,"strike":200,
                 "premium":3.0,"contract_symbol":"AAPL250620C200"}],
        "rationale":"bullish","confidence":0.7,"risks":["IV"],
        "expiry":"2025-06-20",
    }
    final_1 = MagicMock(
        stop_reason="tool_use",
        content=[
            MagicMock(type="text", text="Analyzing AAPL..."),
            tool_use_block,
        ],
    )
    # Turn 2: end_turn with a small text block.
    final_2 = MagicMock(stop_reason="end_turn",
                        content=[MagicMock(type="text", text="done")])

    with patch("app.agent.loop.AsyncAnthropicBedrock") as A:
        client = A.return_value
        client.messages.stream.side_effect = [
            _make_stream(["Analyzing ", "AAPL..."], final_1),
            _make_stream(["done"], final_2),
        ]
        emit = FakeEmit()
        asyncio.run(run_session(emit, "s1", "analyze AAPL"))

    types = [e["type"] for e in emit.events]
    assert "agent.thinking" in types          # deltas were emitted
    assert "agent.tool_call" in types
    assert "agent.proposal" in types
    assert "agent.complete" in types          # loop exited cleanly on end_turn
    # All thinking events carry a `delta` field, not `text`.
    thinking = [e for e in emit.events if e["type"] == "agent.thinking"]
    assert all("delta" in e["data"] for e in thinking)
