import json
from datetime import datetime, timezone
from math import gcd
from functools import reduce
from pathlib import Path
from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, OptionChainRequest
from alpaca.trading.requests import MarketOrderRequest, OptionLegRequest
from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce, PositionIntent
from app.config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

def _trading():
    return TradingClient(settings.alpaca_api_key, settings.alpaca_api_secret, paper=True)

def _stock_data():
    return StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret)

def _option_data():
    return OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret)

def get_quote(symbol: str) -> dict:
    if settings.fixtures_mode:
        return {"symbol": symbol, "price": 200.0, "bid": 199.95, "ask": 200.05, "ts": datetime.now(timezone.utc).isoformat()}
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    res = _stock_data().get_stock_latest_quote(req)[symbol]
    mid = (res.bid_price + res.ask_price) / 2
    return {"symbol": symbol, "price": mid, "bid": res.bid_price, "ask": res.ask_price, "ts": res.timestamp.isoformat()}

def get_latest_prices(symbols: list[str]) -> dict[str, float | None]:
    """Batched mid-price fetch. Stocks → StockLatestQuoteRequest; option contracts (OCC, len>=15) → OptionLatestQuoteRequest."""
    if not symbols:
        return {}
    if settings.fixtures_mode:
        return {s: 200.0 if len(s) < 15 else 6.50 for s in symbols}
    stocks = [s for s in symbols if len(s) < 15]
    opts = [s for s in symbols if len(s) >= 15]
    out: dict[str, float | None] = {s: None for s in symbols}
    if stocks:
        from alpaca.data.requests import StockLatestQuoteRequest
        try:
            res = _stock_data().get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=stocks))
            for sym, q in res.items():
                if q.bid_price and q.ask_price:
                    out[sym] = float((q.bid_price + q.ask_price) / 2)
        except Exception:
            pass  # leave as None
    if opts:
        from alpaca.data.requests import OptionLatestQuoteRequest
        try:
            res = _option_data().get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=opts))
            for sym, q in res.items():
                if q.bid_price and q.ask_price:
                    out[sym] = float((q.bid_price + q.ask_price) / 2)
        except Exception:
            pass
    return out

def get_options_chain(symbol: str, expiry: str | None = None) -> dict:
    if settings.fixtures_mode:
        # Fixture is always AAPL data; symbol arg is intentionally ignored in offline mode
        return json.loads((FIXTURES / "aapl_chain.json").read_text())
    req = OptionChainRequest(underlying_symbol=symbol)
    snap = _option_data().get_option_chain(req)
    contracts = []
    for sym, s in snap.items():
        if expiry and expiry not in sym:
            continue
        g = s.greeks
        q = s.latest_quote
        contracts.append({
            "symbol": sym,
            # OCC format: 8 trailing digits encode strike (last 3 are cents)
            "strike": int(sym[-8:]) / 1000,
            "side": "call" if "C" in sym[-9:] else "put",
            "bid": q.bid_price if q else None,
            "ask": q.ask_price if q else None,
            "delta": getattr(g, "delta", None) if g else None,
            "gamma": getattr(g, "gamma", None) if g else None,
            "theta": getattr(g, "theta", None) if g else None,
            "vega": getattr(g, "vega", None) if g else None,
            "iv": s.implied_volatility,
        })
    return {"underlying": symbol, "expiry": expiry, "contracts": contracts[:40]}

def get_greeks(contract_symbol: str) -> dict:
    if settings.fixtures_mode:
        return {"symbol": contract_symbol, "delta": 0.45, "gamma": 0.03, "theta": -0.05, "vega": 0.12, "iv": 0.28}
    # alpaca-py exposes greeks only via chain snapshots; call get_options_chain for per-contract greeks
    return {"symbol": contract_symbol, "delta": None, "gamma": None, "theta": None, "vega": None, "iv": None}

def get_portfolio() -> dict:
    if settings.fixtures_mode:
        return {"cash": 100000.0, "equity": 100000.0, "buying_power": 200000.0}
    a = _trading().get_account()
    return {"cash": float(a.cash), "equity": float(a.equity), "buying_power": float(a.buying_power)}

def get_positions() -> list[dict]:
    if settings.fixtures_mode:
        return []
    return [
        {"symbol": p.symbol, "qty": float(p.qty), "avg_entry_price": float(p.avg_entry_price)}
        for p in _trading().get_all_positions()
    ]

def submit_multileg_order(legs: list[dict]) -> dict:
    """Caller MUST verify proposal status='approved' before invoking."""
    settings.assert_paper()
    if settings.fixtures_mode:
        return {"id": "fixture-order-00000000", "status": "accepted", "raw": "{}"}
    qtys = [int(l.get("qty", 1)) for l in legs]
    common = reduce(gcd, qtys) or 1
    order_legs = [
        OptionLegRequest(
            symbol=l["contract_symbol"],
            ratio_qty=q // common,
            side=OrderSide.BUY if l["action"] == "buy" else OrderSide.SELL,
            position_intent=PositionIntent.BUY_TO_OPEN if l["action"] == "buy" else PositionIntent.SELL_TO_OPEN,
        )
        for l, q in zip(legs, qtys)
    ]
    req = MarketOrderRequest(
        qty=common, order_class=OrderClass.MLEG, time_in_force=TimeInForce.DAY,
        legs=order_legs,
    )
    order = _trading().submit_order(req)
    return {"id": str(order.id), "status": str(order.status), "raw": order.model_dump_json()}
