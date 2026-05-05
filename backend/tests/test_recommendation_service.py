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


def test_discover_candidates_falls_back_to_text_scan(monkeypatch):
    """When `related` is empty, scan headlines + summaries against the whitelist."""
    from app.services import recommendation_service, news_service, alpaca_service
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])
    # Empty `related` on every item; tickers only present in headline/summary text.
    monkeypatch.setattr(news_service, "get_general_news", lambda: [
        {"headline": "AAPL beats Q3 expectations", "summary": "Apple shines.", "url": "u", "datetime": 1, "related": ""},
        {"headline": "OPEC cuts production", "summary": "XOM and CVX rally on the news.", "url": "u", "datetime": 2, "related": ""},
        {"headline": "FED holds rates steady", "summary": "The CEO of JPM weighs in on the IPO market.", "url": "u", "datetime": 3, "related": ""},
        {"headline": "Random non-ticker headline", "summary": "Nothing relevant.", "url": "u", "datetime": 4, "related": ""},
    ])

    cs = recommendation_service.discover_candidates()
    # AAPL, XOM, CVX, JPM should be picked up; FED/CEO/IPO are NOT in the whitelist.
    assert "AAPL" in cs.discover
    assert "XOM" in cs.discover
    assert "CVX" in cs.discover
    assert "JPM" in cs.discover
    # False positives must be excluded:
    for noise in ("FED", "CEO", "IPO", "OPEC", "Q3"):
        assert noise not in cs.discover


def test_discover_candidates_text_scan_dedups_against_watchlist(monkeypatch):
    """Text-scan tickers that overlap watchlist/positions are skipped (priority preserved)."""
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
    monkeypatch.setattr(news_service, "get_general_news", lambda: [
        {"headline": "AAPL leads, NVDA close behind", "summary": "Tech bid.", "url": "u", "datetime": 1, "related": ""},
    ])

    cs = recommendation_service.discover_candidates()
    assert cs.watchlist == ["AAPL"]
    assert "AAPL" not in cs.discover  # already in watchlist
    assert "NVDA" in cs.discover


def test_discover_candidates_combines_related_and_text_scan(monkeypatch):
    """When some items have `related` and others don't, both contribute up to the cap."""
    from app.services import recommendation_service, news_service, alpaca_service
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [])
    monkeypatch.setattr(news_service, "get_general_news", lambda: [
        {"headline": "h1", "summary": "s1", "url": "u", "datetime": 1, "related": "AMD"},
        {"headline": "META and GOOG announce partnership", "summary": "Deal details.", "url": "u", "datetime": 2, "related": ""},
    ])

    cs = recommendation_service.discover_candidates()
    # AMD from related; META + GOOG from text scan.
    assert "AMD" in cs.discover
    assert "META" in cs.discover
    assert "GOOG" in cs.discover


import json as _json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.asyncio
async def test_generate_one_happy_path(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    canned = (FIXTURES_DIR / "recommendation_response.json").read_text()
    monkeypatch.setattr(alpaca_service, "get_quote", lambda sym: {"symbol": sym, "price": 920.5, "bid": 920.4, "ask": 920.6, "ts": "2026-05-05T14:00:00Z"})
    monkeypatch.setattr(news_service, "get_news", lambda sym, since_days=7: {
        "symbol": sym,
        "items": [
            {"headline": "NVDA Q3 beats on data-center growth", "summary": "Record numbers.", "url": "https://example.com/a", "datetime": 1},
            {"headline": "Wall St raises NVDA target to $1,250", "summary": "Analysts bullish.", "url": "https://example.com/b", "datetime": 2},
        ],
        "summary": "",
    })

    captured = []
    class FakeMessages:
        async def create(self, **kwargs):
            captured.append(kwargs)
            class Block:
                text = canned
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    card = await recommendation_service.generate_one("NVDA", "watchlist")
    assert card["symbol"] == "NVDA"
    assert card["source"] == "watchlist"
    assert card["bias"] == "bullish"
    assert 0 <= card["confidence"] <= 1
    assert len(card["rationale"]) <= 280
    assert len(card["top_headlines"]) == 2
    assert card["top_headlines"][0]["url"] == "https://example.com/a"
    assert "error" not in card
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_generate_one_retries_on_malformed(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_quote", lambda sym: {"symbol": sym, "price": 100.0, "bid": 100, "ask": 100, "ts": "x"})
    monkeypatch.setattr(news_service, "get_news", lambda sym, since_days=7: {"symbol": sym, "items": [{"headline": "X", "summary": "", "url": "u", "datetime": 1}], "summary": ""})

    canned = (FIXTURES_DIR / "recommendation_response.json").read_text()
    call_count = {"n": 0}
    class FakeMessages:
        async def create(self, **kwargs):
            call_count["n"] += 1
            class Block:
                text = "this is not json" if call_count["n"] == 1 else canned
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    card = await recommendation_service.generate_one("AAPL", "watchlist")
    assert call_count["n"] == 2
    assert card["bias"] == "bullish"


@pytest.mark.asyncio
async def test_generate_one_persistent_failure_raises(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_quote", lambda sym: {"symbol": sym, "price": 100.0, "bid": 100, "ask": 100, "ts": "x"})
    monkeypatch.setattr(news_service, "get_news", lambda sym, since_days=7: {"symbol": sym, "items": [], "summary": ""})

    class FakeMessages:
        async def create(self, **kwargs):
            class Block:
                text = "still not json"
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    with pytest.raises(recommendation_service.MalformedRecommendationError):
        await recommendation_service.generate_one("AAPL", "watchlist")


@pytest.mark.asyncio
async def test_generate_all_streams_and_persists(monkeypatch):
    """Discovery → cards stream in finish order → run is persisted; error cards still flow through."""
    from app.services import recommendation_service
    from app.models import Watchlist, RecommendationRun
    from sqlmodel import SQLModel, create_engine, Session, select as _select
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Watchlist(ticker="AAPL"))
        s.add(Watchlist(ticker="NVDA"))
        s.add(Watchlist(ticker="TSLA"))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    monkeypatch.setattr(recommendation_service, "discover_candidates", lambda: recommendation_service.CandidateSet(
        watchlist=["AAPL", "NVDA", "TSLA"], positions=[], discover=[],
    ))

    async def fake_generate_one(symbol, source):
        if symbol == "TSLA":
            raise recommendation_service.MalformedRecommendationError("unparseable_response")
        return {
            "symbol": symbol, "source": source, "bias": "bullish",
            "confidence": 0.6, "rationale": f"r-{symbol}", "top_headlines": [],
        }
    monkeypatch.setattr(recommendation_service, "generate_one", fake_generate_one)

    emitted: list[dict] = []
    async def emit(evt: dict):
        emitted.append(evt)

    payload = await recommendation_service.generate_all(emit)

    types = [e["type"] for e in emitted]
    assert types[0] == "recommendation.discovery"
    assert types.count("recommendation.card") == 3
    assert types[-1] == "recommendation.complete"

    assert {c["symbol"] for c in payload["cards"]} == {"AAPL", "NVDA", "TSLA"}
    tsla = next(c for c in payload["cards"] if c["symbol"] == "TSLA")
    assert "error" in tsla and tsla["error"] == "unparseable_response"

    with Session(engine) as s:
        rows = s.exec(_select(RecommendationRun)).all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_generate_all_no_candidates_emits_warning(monkeypatch):
    from app.services import recommendation_service
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    monkeypatch.setattr(recommendation_service, "discover_candidates", lambda: recommendation_service.CandidateSet(
        watchlist=[], positions=[], discover=[],
    ))

    emitted: list[dict] = []
    async def emit(evt: dict):
        emitted.append(evt)

    payload = await recommendation_service.generate_all(emit)
    types = [e["type"] for e in emitted]
    assert "recommendation.discovery_warning" in types
    assert types[-1] == "recommendation.complete"
    assert payload["cards"] == []


def test_get_latest_run_returns_most_recent(monkeypatch):
    from app.services import recommendation_service
    from app.models import RecommendationRun
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager
    import time

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(RecommendationRun(id="old", payload_json='{"cards": [], "sources": {"watchlist": [], "positions": [], "discover": []}}'))
        s.commit()
        time.sleep(0.01)
        s.add(RecommendationRun(id="new", payload_json='{"cards": [{"symbol":"NVDA"}], "sources": {"watchlist": [], "positions": [], "discover": []}}'))
        s.commit()

    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    latest = recommendation_service.get_latest_run()
    assert latest is not None
    assert latest["run_id"] == "new"
    assert latest["cards"][0]["symbol"] == "NVDA"


def test_get_latest_run_empty(monkeypatch):
    from app.services import recommendation_service
    from sqlmodel import SQLModel, create_engine, Session
    from contextlib import contextmanager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    monkeypatch.setattr(recommendation_service, "get_session", fake_session)

    assert recommendation_service.get_latest_run() is None


def test_build_market_brief_user_message_includes_quotes_and_news():
    from app.agent.recommendation_prompt import build_market_brief_user_message
    msg = build_market_brief_user_message(
        index_quotes={"SPY": 482.55, "QQQ": 412.10, "IWM": 198.30},
        news_items=[
            {"headline": "CPI cooler than expected", "summary": "Inflation eases."},
            {"headline": "OPEC announces output cut", "summary": "Oil up 3%."},
        ],
    )
    assert "SPY" in msg and "482.55" in msg
    assert "QQQ" in msg and "IWM" in msg
    assert "CPI cooler than expected" in msg
    assert "OPEC announces output cut" in msg
    assert "JSON" in msg


def test_build_market_brief_user_message_handles_missing_inputs():
    from app.agent.recommendation_prompt import build_market_brief_user_message
    msg = build_market_brief_user_message(
        index_quotes={"SPY": None, "QQQ": None, "IWM": None},
        news_items=[],
    )
    assert "no recent news" in msg.lower() or "no news" in msg.lower()
    assert "JSON" in msg


def test_market_brief_system_prompt_specifies_schema():
    from app.agent.recommendation_prompt import MARKET_BRIEF_SYSTEM_PROMPT
    assert "JSON" in MARKET_BRIEF_SYSTEM_PROMPT
    assert "bias" in MARKET_BRIEF_SYSTEM_PROMPT
    assert "headline" in MARKET_BRIEF_SYSTEM_PROMPT
    assert "drivers" in MARKET_BRIEF_SYSTEM_PROMPT
    assert "bullish" in MARKET_BRIEF_SYSTEM_PROMPT
    assert "bearish" in MARKET_BRIEF_SYSTEM_PROMPT
    assert "neutral" in MARKET_BRIEF_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_generate_market_brief_happy_path(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"SPY": 482.55, "QQQ": 412.10, "IWM": 198.30})
    monkeypatch.setattr(news_service, "get_general_news", lambda: [
        {"headline": "CPI cooler than expected", "summary": "Inflation eases.", "url": "u", "datetime": 1, "related": ""},
        {"headline": "OPEC announces output cut", "summary": "Oil up 3%.", "url": "u", "datetime": 2, "related": ""},
    ])

    canned = '{"bias":"bullish","headline":"Risk-on tape; semis lead","drivers":["CPI cooler","OPEC cut","semis bid"]}'
    class FakeMessages:
        async def create(self, **kwargs):
            class Block:
                text = canned
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    brief = await recommendation_service.generate_market_brief()
    assert brief is not None
    assert brief["bias"] == "bullish"
    assert brief["headline"] == "Risk-on tape; semis lead"
    assert brief["drivers"] == ["CPI cooler", "OPEC cut", "semis bid"]
    assert "updated_at" in brief


@pytest.mark.asyncio
async def test_generate_market_brief_malformed_returns_none(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"SPY": 482.55, "QQQ": 412.10, "IWM": 198.30})
    monkeypatch.setattr(news_service, "get_general_news", lambda: [{"headline": "x", "summary": "", "url": "u", "datetime": 1, "related": ""}])

    class FakeMessages:
        async def create(self, **kwargs):
            class Block:
                text = "this is not json"
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    brief = await recommendation_service.generate_market_brief()
    assert brief is None


@pytest.mark.asyncio
async def test_generate_market_brief_no_inputs_returns_none(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"SPY": None, "QQQ": None, "IWM": None})
    monkeypatch.setattr(news_service, "get_general_news", lambda: [])

    called = {"n": 0}
    class FakeMessages:
        async def create(self, **kwargs):
            called["n"] += 1
            class Block:
                text = "x"
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    brief = await recommendation_service.generate_market_brief()
    assert brief is None
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_generate_market_brief_truncates_headline(monkeypatch):
    from app.services import recommendation_service, alpaca_service, news_service
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {"SPY": 482.55, "QQQ": None, "IWM": None})
    monkeypatch.setattr(news_service, "get_general_news", lambda: [])

    long_headline = "x" * 150
    canned = f'{{"bias":"neutral","headline":"{long_headline}","drivers":[]}}'
    class FakeMessages:
        async def create(self, **kwargs):
            class Block:
                text = canned
                type = "text"
            class Msg:
                content = [Block()]
            return Msg()
    class FakeClient:
        messages = FakeMessages()
    monkeypatch.setattr(recommendation_service, "_anthropic", FakeClient())

    brief = await recommendation_service.generate_market_brief()
    assert brief is not None
    assert len(brief["headline"]) == 100


@pytest.mark.asyncio
async def test_generate_all_includes_market_brief_in_payload(monkeypatch):
    from app.services import recommendation_service
    from app.models import Watchlist, RecommendationRun
    from sqlmodel import SQLModel, create_engine, Session, select as _select
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

    monkeypatch.setattr(recommendation_service, "discover_candidates", lambda: recommendation_service.CandidateSet(
        watchlist=["AAPL"], positions=[], discover=[],
    ))

    fixed_brief = {"bias": "bullish", "headline": "Risk-on", "drivers": ["a", "b"], "updated_at": "2026-05-05T14:00:00Z"}

    async def fake_generate_market_brief():
        return fixed_brief
    monkeypatch.setattr(recommendation_service, "generate_market_brief", fake_generate_market_brief)

    async def fake_generate_one(symbol, source):
        return {"symbol": symbol, "source": source, "bias": "neutral", "confidence": 0.5, "rationale": "r", "top_headlines": []}
    monkeypatch.setattr(recommendation_service, "generate_one", fake_generate_one)

    emitted: list[dict] = []
    async def emit(evt: dict):
        emitted.append(evt)

    payload = await recommendation_service.generate_all(emit)

    types = [e["type"] for e in emitted]
    assert "recommendation.market_brief" in types
    discovery_idx = types.index("recommendation.discovery")
    brief_idx = types.index("recommendation.market_brief")
    first_card_idx = types.index("recommendation.card")
    complete_idx = types.index("recommendation.complete")
    assert discovery_idx < brief_idx < first_card_idx < complete_idx

    assert payload["market_brief"] == fixed_brief

    with Session(engine) as s:
        rows = s.exec(_select(RecommendationRun)).all()
        assert len(rows) == 1
        import json as _json
        persisted = _json.loads(rows[0].payload_json)
        assert persisted["market_brief"] == fixed_brief


@pytest.mark.asyncio
async def test_generate_all_market_brief_warning_when_none(monkeypatch):
    from app.services import recommendation_service
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

    monkeypatch.setattr(recommendation_service, "discover_candidates", lambda: recommendation_service.CandidateSet(
        watchlist=["AAPL"], positions=[], discover=[],
    ))

    async def fake_generate_market_brief():
        return None
    monkeypatch.setattr(recommendation_service, "generate_market_brief", fake_generate_market_brief)

    async def fake_generate_one(symbol, source):
        return {"symbol": symbol, "source": source, "bias": "neutral", "confidence": 0.5, "rationale": "r", "top_headlines": []}
    monkeypatch.setattr(recommendation_service, "generate_one", fake_generate_one)

    emitted: list[dict] = []
    async def emit(evt: dict):
        emitted.append(evt)

    payload = await recommendation_service.generate_all(emit)

    types = [e["type"] for e in emitted]
    assert "recommendation.market_brief_warning" in types
    assert "recommendation.market_brief" not in types
    assert payload["market_brief"] is None
