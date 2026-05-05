import pytest


def test_build_user_message_lists_headlines_and_quote():
    from app.agent.recommendation_prompt import build_user_message
    msg = build_user_message(
        symbol="NVDA",
        quote_price=920.50,
        news_items=[
            {"headline": "NVDA beats Q3", "summary": "Record numbers."},
            {"headline": "Wall St raises target", "summary": "$1,250."},
        ],
    )
    assert "NVDA" in msg
    assert "920.50" in msg
    assert "NVDA beats Q3" in msg
    assert "Wall St raises target" in msg
    assert "JSON" in msg


def test_strict_retry_message_explicit():
    from app.agent.recommendation_prompt import build_strict_retry_message
    msg = build_strict_retry_message()
    assert "JSON" in msg
    assert "no markdown" in msg.lower() or "no fences" in msg.lower() or "no code block" in msg.lower()


def test_discover_candidates_dedup_and_priority(monkeypatch):
    """watchlist > positions > discover; held options collapse to underlying; discover capped at 5."""
    from app.services import recommendation_service, news_service, alpaca_service
    from app.models import Watchlist
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Watchlist(ticker="AAPL"))
        s.add(Watchlist(ticker="NVDA"))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses

    monkeypatch.setattr(recommendation_service, "get_session", fake_session)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "TSLA", "qty": 10.0, "avg_entry_price": 220.0},
        {"symbol": "NVDA260619C00800000", "qty": 1.0, "avg_entry_price": 12.40},
    ])
    monkeypatch.setattr(news_service, "get_general_news", lambda: [
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "AMD"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "META"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "GOOG"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "COIN"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "AVGO"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "QQQ"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "AAPL"},
        {"headline": "h", "summary": "s", "url": "u", "datetime": 1, "related": "TSLA"},
    ])
    cs = recommendation_service.discover_candidates()
    assert sorted(cs.watchlist) == ["AAPL", "NVDA"]
    assert cs.positions == ["TSLA"]
    assert len(cs.discover) == 5
    overlap = (set(cs.discover) & set(cs.watchlist)) | (set(cs.discover) & set(cs.positions))
    assert overlap == set()


def test_discover_candidates_handles_general_news_failure(monkeypatch):
    """Discovery falls back gracefully if general_news raises."""
    from app.services import recommendation_service, news_service, alpaca_service
    from app.models import Watchlist
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Watchlist(ticker="AAPL"))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])

    def boom():
        raise RuntimeError("finnhub down")
    monkeypatch.setattr(news_service, "get_general_news", boom)

    cs = recommendation_service.discover_candidates()
    assert cs.watchlist == ["AAPL"]
    assert cs.positions == []
    assert cs.discover == []
    assert cs.discovery_error == "general_news_unavailable"
