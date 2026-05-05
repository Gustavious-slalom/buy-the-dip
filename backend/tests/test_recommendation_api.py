import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import news_service; reload(news_service)
    from app.services import recommendation_service; reload(recommendation_service)
    from app.api import http as http_module; reload(http_module)
    from app.api import ws as ws_module; reload(ws_module)
    from app import main; reload(main)
    return TestClient(main.app)


def test_recommendations_latest_empty(client, monkeypatch):
    from app.services import recommendation_service
    monkeypatch.setattr(recommendation_service, "get_latest_run", lambda: None)
    r = client.get("/recommendations/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] is None
    assert body["generated_at"] is None
    assert body["cards"] == []
    assert body["sources"] == {"watchlist": [], "positions": [], "discover": []}


def test_recommendations_latest_returns_persisted(client, monkeypatch):
    from app.services import recommendation_service
    canned = {
        "run_id": "abc",
        "generated_at": "2026-05-05T14:02:31+00:00",
        "cards": [{"symbol": "NVDA", "source": "watchlist", "bias": "bullish", "confidence": 0.7, "rationale": "x", "top_headlines": []}],
        "sources": {"watchlist": ["NVDA"], "positions": [], "discover": []},
    }
    monkeypatch.setattr(recommendation_service, "get_latest_run", lambda: canned)
    r = client.get("/recommendations/latest")
    assert r.status_code == 200
    assert r.json() == canned


def test_ws_recommendation_start_flow(client, monkeypatch):
    """WS receives discovery → 2 cards (in finish order) → complete after recommendation.start."""
    from app.services import recommendation_service

    async def fake_generate_all(emit):
        await emit({"type": "recommendation.discovery", "ts": "t", "data": {"sources": {"watchlist": ["AAPL", "NVDA"], "positions": [], "discover": []}}})
        await emit({"type": "recommendation.card", "ts": "t", "data": {"symbol": "AAPL", "source": "watchlist", "bias": "bullish", "confidence": 0.6, "rationale": "r", "top_headlines": []}})
        await emit({"type": "recommendation.card", "ts": "t", "data": {"symbol": "NVDA", "source": "watchlist", "bias": "bullish", "confidence": 0.7, "rationale": "r", "top_headlines": []}})
        await emit({"type": "recommendation.complete", "ts": "t", "data": {"run_id": "rid", "generated_at": "2026-05-05T14:02:31Z", "count": 2}})
        return {"run_id": "rid", "generated_at": "2026-05-05T14:02:31Z", "cards": [], "sources": {"watchlist": [], "positions": [], "discover": []}}

    monkeypatch.setattr(recommendation_service, "generate_all", fake_generate_all)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "recommendation.start"})
        msgs = [ws.receive_json() for _ in range(4)]
    types = [m["type"] for m in msgs]
    assert types == [
        "recommendation.discovery",
        "recommendation.card",
        "recommendation.card",
        "recommendation.complete",
    ]
