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

def test_get_portfolio_history_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    res = alpaca_service.get_portfolio_history("1M")
    assert res["period"] == "1M"
    assert isinstance(res["points"], list) and len(res["points"]) > 0
    assert {"t", "equity"}.issubset(res["points"][0].keys())
    assert "base_value" in res and "profit_loss" in res and "profit_loss_pct" in res

def test_get_portfolio_history_invalid_period(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    import pytest
    with pytest.raises(ValueError):
        alpaca_service.get_portfolio_history("XYZ")
