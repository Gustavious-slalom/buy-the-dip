# backend/app/agent/tools.py
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

async def dispatch(name: str, input: dict, session_id: str) -> dict:
    if name == "get_quote": return alpaca_service.get_quote(input["symbol"])
    if name == "get_options_chain": return alpaca_service.get_options_chain(input["symbol"], input.get("expiry"))
    if name == "get_greeks": return alpaca_service.get_greeks(input["contract_symbol"])
    if name == "get_news": return news_service.get_news(input["symbol"], input.get("since_days", 7))
    if name == "get_portfolio": return alpaca_service.get_portfolio()
    if name == "get_positions": return {"positions": alpaca_service.get_positions()}
    if name == "propose_trade":
        return proposal_service.create_proposal(
            session_id=session_id, ticker=input["ticker"], legs=input["legs"],
            rationale=input["rationale"], confidence=input.get("confidence", 0.5),
            risks=input.get("risks", []), expiry=input["expiry"],
        )
    raise ValueError(f"unknown tool {name}")
