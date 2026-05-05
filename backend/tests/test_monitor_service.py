import pytest
import asyncio


@pytest.fixture(autouse=True)
def use_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import sell_service; reload(sell_service)
    from app.services import monitor_service; reload(monitor_service)
    from app.db import init_db; init_db()


def test_check_thresholds_no_rules():
    from app.services.monitor_service import check_thresholds_once
    result = asyncio.run(check_thresholds_once())
    assert result == []


def test_check_thresholds_no_positions(monkeypatch):
    from app.services import sell_service, alpaca_service
    from app.services.monitor_service import check_thresholds_once
    sell_service.set_rule("AAPL", take_profit=0.01, stop_loss=-0.003)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])
    result = asyncio.run(check_thresholds_once())
    assert result == []


def test_check_thresholds_fires_take_profit(monkeypatch):
    from app.services import sell_service, alpaca_service
    from app.services.monitor_service import check_thresholds_once
    sell_service.set_rule("AAPL", take_profit=0.01, stop_loss=-0.003)
    # avg_entry=100, price=102 → pct=+2% → triggers take_profit
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "AAPL", "qty": 10.0, "avg_entry_price": 100.0}
    ])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"AAPL": 102.0})
    result = asyncio.run(check_thresholds_once())
    assert len(result) == 1
    assert result[0]["ok"] is True
    # Rule should be deactivated after firing
    rules = sell_service.list_rules()
    assert not any(r.symbol == "AAPL" for r in rules)


def test_check_thresholds_fires_stop_loss(monkeypatch):
    from app.services import sell_service, alpaca_service
    from app.services.monitor_service import check_thresholds_once
    sell_service.set_rule("TSLA", take_profit=0.01, stop_loss=-0.003)
    # avg_entry=200, price=199 → pct=-0.5% → triggers stop_loss
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "TSLA", "qty": 5.0, "avg_entry_price": 200.0}
    ])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"TSLA": 199.0})
    result = asyncio.run(check_thresholds_once())
    assert len(result) == 1
    assert result[0]["ok"] is True


def test_check_thresholds_no_trigger_in_range(monkeypatch):
    from app.services import sell_service, alpaca_service
    from app.services.monitor_service import check_thresholds_once
    sell_service.set_rule("MSFT", take_profit=0.01, stop_loss=-0.003)
    # avg_entry=100, price=100.5 → pct=+0.5% → no trigger
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "MSFT", "qty": 3.0, "avg_entry_price": 100.0}
    ])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"MSFT": 100.5})
    result = asyncio.run(check_thresholds_once())
    assert result == []


def test_check_thresholds_skips_options(monkeypatch):
    from app.services import sell_service, alpaca_service
    from app.services.monitor_service import check_thresholds_once
    # OCC symbol (len >= 15): AAPL240119C00150000
    occ_symbol = "AAPL240119C00150000"
    assert len(occ_symbol) >= 15
    sell_service.set_rule(occ_symbol, take_profit=0.01, stop_loss=-0.003)
    # Should skip entirely (stock_rules will be empty)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": occ_symbol, "qty": 1.0, "avg_entry_price": 5.0}
    ])
    result = asyncio.run(check_thresholds_once())
    assert result == []
