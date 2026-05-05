import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import portfolio_service; reload(portfolio_service)
    from app.api import http as http_module; reload(http_module)
    from app import main; reload(main)
    return TestClient(main.app)


def test_portfolio_snapshot_endpoint(client, monkeypatch):
    from app.services import alpaca_service
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {})
    r = client.get("/portfolio/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert {"fetched_at", "account", "positions", "strategies", "allocations", "history", "errors"}.issubset(body.keys())


def test_portfolio_equity_curve_endpoint(client):
    r = client.get("/portfolio/equity-curve", params={"period": "1M"})
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "1M"
    assert isinstance(body["points"], list)


def test_portfolio_equity_curve_bad_period(client):
    r = client.get("/portfolio/equity-curve", params={"period": "BOGUS"})
    assert r.status_code == 400


def test_fixture_mode_snapshot_end_to_end(client):
    """Exercises the fixture-mode code paths without patching any alpaca_service methods.
    If a fixture file is missing, misnamed, or contains malformed JSON this test will fail,
    providing early warning that fixture mode is broken before a demo or CI run.
    """
    r = client.get("/portfolio/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert {"fetched_at", "account", "positions", "strategies", "allocations", "history", "errors"}.issubset(body.keys())
    # In fixture mode get_portfolio() returns hardcoded data; get_positions() returns []
    assert body["account"]["equity"] == 100000.0
    assert body["errors"] == []


def test_fixture_mode_snapshot_history_limit(client):
    """Verify the history_limit query param is accepted and respected."""
    r = client.get("/portfolio/snapshot", params={"history_limit": 5})
    assert r.status_code == 200
    assert len(r.json()["history"]) <= 5
