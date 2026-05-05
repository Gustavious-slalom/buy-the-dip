import os

def test_fixtures_mode_returns_canned(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service
    reload(alpaca_service)
    chain = alpaca_service.get_options_chain("AAPL", expiry="2025-06-20")
    assert chain["contracts"][0]["symbol"].startswith("AAPL")

def test_get_quote_shape(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    q = alpaca_service.get_quote("AAPL")
    assert {"symbol","price","bid","ask","ts"}.issubset(q.keys())

def test_get_latest_prices_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    prices = alpaca_service.get_latest_prices(["AAPL", "NVDA"])
    assert set(prices.keys()) == {"AAPL", "NVDA"}
    assert all(isinstance(v, float) for v in prices.values())
