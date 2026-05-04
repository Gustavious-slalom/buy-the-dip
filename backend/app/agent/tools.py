# backend/app/agent/tools.py
import asyncio
import functools
from app.services import alpaca_service, news_service, proposal_service

TOOLS = [
    {"name": "get_quote", "description": "Latest quote for a stock symbol.",
     "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "get_options_chain", "description": "Options chain for a symbol; optionally filter by expiry YYYY-MM-DD.",
     "input_schema": {"type": "object", "properties": {"symbol": {"type":"string"},"expiry":{"type":"string"}}, "required":["symbol"]}},
    {"name": "get_greeks", "description": "Greeks for a specific option contract symbol.",
     "input_schema": {"type":"object","properties":{"contract_symbol":{"type":"string"}},"required":["contract_symbol"]}},
    {"name": "get_news", "description": "Recent news + summary for a ticker.",
     "input_schema": {"type":"object","properties":{"symbol":{"type":"string"},"since_days":{"type":"integer"}},"required":["symbol"]}},
    {"name": "get_portfolio", "description": "Account cash, equity, buying power.",
     "input_schema": {"type":"object","properties":{}}},
    {"name": "get_positions", "description": "Currently held positions.",
     "input_schema": {"type":"object","properties":{}}},
    {"name": "propose_trade", "description": "Create a pending options trade proposal. Does NOT execute. Legs format: [{action: 'buy'|'sell', side: 'call'|'put', qty, strike, premium, contract_symbol}].",
     "input_schema": {"type":"object","properties":{
        "ticker":{"type":"string"},
        "legs":{"type":"array","items":{"type":"object"}},
        "rationale":{"type":"string"},
        "confidence":{"type":"number"},
        "risks":{"type":"array","items":{"type":"string"}},
        "expiry":{"type":"string"},
     },"required":["ticker","legs","rationale","expiry"]}},
]


async def _run(fn, *args, **kwargs):
    """Run a blocking function in a thread pool to avoid freezing the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


async def dispatch(name: str, input: dict, session_id: str) -> dict:
    """Route a Claude tool call to the appropriate service.

    All service calls are wrapped in run_in_executor so synchronous I/O
    (Alpaca/Finnhub HTTP requests) does not block the asyncio event loop.
    WS event emission (agent.tool_call / agent.tool_result) is handled
    by loop.py — dispatch only returns the result dict.
    """
    if name == "get_quote":
        return await _run(alpaca_service.get_quote, input["symbol"])
    if name == "get_options_chain":
        return await _run(alpaca_service.get_options_chain, input["symbol"], input.get("expiry"))
    if name == "get_greeks":
        return await _run(alpaca_service.get_greeks, input["contract_symbol"])
    if name == "get_news":
        return await _run(news_service.get_news, input["symbol"], input.get("since_days", 7))
    if name == "get_portfolio":
        return await _run(alpaca_service.get_portfolio)
    if name == "get_positions":
        positions = await _run(alpaca_service.get_positions)
        return {"positions": positions}
    if name == "propose_trade":
        return await _run(
            proposal_service.create_proposal,
            session_id, input["ticker"], input["legs"],
            input["rationale"], input.get("confidence", 0.5),
            input.get("risks", []), input["expiry"],
        )
    raise ValueError(f"unknown tool {name}")

