# backend/tests/test_news_service.py
def test_news_fixtures(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE","1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import news_service; reload(news_service)
    out = news_service.get_news("AAPL", since_days=7)
    assert out["items"][0]["headline"] == "Apple beats earnings"
    assert out["summary"] == ""  # Haiku is skipped in fixtures mode


def test_get_general_news_fixtures_mode(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import news_service; reload(news_service)
    items = news_service.get_general_news()
    assert isinstance(items, list) and len(items) >= 3
    assert {"headline", "summary", "url", "datetime", "related"}.issubset(items[0].keys())
