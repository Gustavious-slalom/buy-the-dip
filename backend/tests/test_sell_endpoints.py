import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import sell_service; reload(sell_service)
    from app.services import monitor_service; reload(monitor_service)
    from app.api import http as http_module; reload(http_module)
    from app import main; reload(main)
    return TestClient(main.app, raise_server_exceptions=True)


# ── sell_position endpoint ────────────────────────────────────────────────────

def test_sell_position_endpoint(client):
    r = client.post("/positions/sell", json={"symbol": "AAPL", "qty": 5, "avg_entry": 180.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "sell_order_id" in body
    assert body["alpaca_order_id"] == "fixture-sell-AAPL"
    assert body["status"] == "accepted"


def test_sell_position_endpoint_missing_fields(client):
    r = client.post("/positions/sell", json={"symbol": "AAPL"})
    assert r.status_code == 422


# ── sell rules endpoints ──────────────────────────────────────────────────────

def test_set_sell_rule_endpoint(client):
    r = client.post("/positions/rules", json={
        "symbol": "TSLA", "take_profit": 0.01, "stop_loss": -0.003
    })
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TSLA"
    assert body["take_profit"] == pytest.approx(0.01)
    assert body["stop_loss"] == pytest.approx(-0.003)
    assert body["active"] is True


def test_list_sell_rules_endpoint(client):
    client.post("/positions/rules", json={"symbol": "TSLA", "take_profit": 0.01, "stop_loss": -0.003})
    r = client.get("/positions/rules")
    assert r.status_code == 200
    rules = r.json()
    assert any(rule["symbol"] == "TSLA" for rule in rules)


def test_delete_sell_rule_endpoint(client):
    client.post("/positions/rules", json={"symbol": "MSFT", "take_profit": 0.02, "stop_loss": -0.005})
    r = client.delete("/positions/rules/MSFT")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Rule should no longer appear in list
    rules = client.get("/positions/rules").json()
    assert not any(rule["symbol"] == "MSFT" for rule in rules)


def test_delete_nonexistent_rule_is_noop(client):
    r = client.delete("/positions/rules/NONEXISTENT")
    assert r.status_code == 200


def test_set_rule_upsert(client):
    client.post("/positions/rules", json={"symbol": "AAPL", "take_profit": 0.01, "stop_loss": -0.003})
    # Update the same symbol
    r = client.post("/positions/rules", json={"symbol": "AAPL", "take_profit": 0.02, "stop_loss": -0.005})
    assert r.status_code == 200
    assert r.json()["take_profit"] == pytest.approx(0.02)
    # Only one rule for AAPL
    rules = client.get("/positions/rules").json()
    aapl_rules = [rule for rule in rules if rule["symbol"] == "AAPL"]
    assert len(aapl_rules) == 1
