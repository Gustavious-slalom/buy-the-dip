import pytest

from app.services.portfolio_service import _compute_allocations


def test_compute_allocations_kind_split():
    positions = [
        {"symbol": "SPY", "kind": "stock", "underlying": "SPY", "market_value": 48000.0},
        {"symbol": "AAPL250117C00150000", "kind": "option", "underlying": "AAPL", "market_value": 1500.0},
        {"symbol": "AAPL250117C00160000", "kind": "option", "underlying": "AAPL", "market_value": 500.0},
    ]
    account = {"cash": 50000.0, "equity": 100000.0}
    alloc = _compute_allocations(positions, account)

    # by_kind sums to ~100
    assert abs(alloc["by_kind"]["stock"] + alloc["by_kind"]["option"] + alloc["by_kind"]["cash"] - 100.0) < 0.01
    assert alloc["by_kind"]["stock"] == pytest.approx(48.0, abs=0.01)
    assert alloc["by_kind"]["option"] == pytest.approx(2.0, abs=0.01)
    assert alloc["by_kind"]["cash"] == pytest.approx(50.0, abs=0.01)

    # by_underlying aggregates options under underlying ticker
    by_under = {row["ticker"]: row for row in alloc["by_underlying"]}
    assert by_under["SPY"]["market_value"] == pytest.approx(48000.0)
    assert by_under["AAPL"]["market_value"] == pytest.approx(2000.0)


def test_compute_allocations_handles_none_market_value():
    positions = [
        {"symbol": "SPY", "kind": "stock", "underlying": "SPY", "market_value": None},
        {"symbol": "AAPL", "kind": "stock", "underlying": "AAPL", "market_value": 1000.0},
    ]
    account = {"cash": 9000.0, "equity": 10000.0}
    alloc = _compute_allocations(positions, account)
    # None values are excluded from totals; remaining alloc still computed against equity
    assert alloc["by_kind"]["stock"] == pytest.approx(10.0, abs=0.01)
    assert all(row["ticker"] != "SPY" or row["market_value"] == 0.0 for row in alloc["by_underlying"]) or \
           "SPY" not in {r["ticker"] for r in alloc["by_underlying"]}


from app.services.portfolio_service import _parse_occ, _normalize_positions


def test_parse_occ_call():
    parsed = _parse_occ("AAPL250117C00150000")
    assert parsed == {"underlying": "AAPL", "expiry": "2025-01-17", "side": "call", "strike": 150.0}


def test_parse_occ_put_with_decimals():
    parsed = _parse_occ("NVDA260619P00875500")
    assert parsed["side"] == "put"
    assert parsed["strike"] == 875.5
    assert parsed["expiry"] == "2026-06-19"
    assert parsed["underlying"] == "NVDA"


def test_normalize_positions_stock_and_option():
    raw = [
        {"symbol": "SPY", "qty": 100.0, "avg_entry_price": 480.0},
        {"symbol": "AAPL250117C00150000", "qty": 2.0, "avg_entry_price": 6.20},
    ]
    prices = {"SPY": 482.55, "AAPL250117C00150000": 7.90}
    account = {"equity": 100000.0}
    out = _normalize_positions(raw, prices, account)

    spy = next(p for p in out if p["symbol"] == "SPY")
    assert spy["kind"] == "stock"
    assert spy["market_value"] == pytest.approx(482.55 * 100)
    assert spy["unrealized_pl"] == pytest.approx((482.55 - 480.0) * 100)
    assert spy["weight_pct"] == pytest.approx(spy["market_value"] / 100000.0 * 100, abs=0.01)

    opt = next(p for p in out if p["symbol"].startswith("AAPL"))
    assert opt["kind"] == "option"
    # Options multiplier = 100
    assert opt["market_value"] == pytest.approx(7.90 * 2 * 100)
    assert opt["unrealized_pl"] == pytest.approx((7.90 - 6.20) * 2 * 100)
    assert opt["underlying"] == "AAPL"
    assert opt["side"] == "call"
    assert opt["strike"] == 150.0


def test_normalize_positions_filters_zero_qty():
    raw = [{"symbol": "SPY", "qty": 0.0, "avg_entry_price": 480.0}]
    out = _normalize_positions(raw, {"SPY": 482.55}, {"equity": 100000.0})
    assert out == []


def test_normalize_positions_missing_price_yields_nulls():
    raw = [{"symbol": "SPY", "qty": 100.0, "avg_entry_price": 480.0}]
    out = _normalize_positions(raw, {"SPY": None}, {"equity": 100000.0})
    assert out[0]["current_price"] is None
    assert out[0]["market_value"] is None
    assert out[0]["unrealized_pl"] is None
    assert out[0]["weight_pct"] is None


import json as _json
import uuid
from sqlmodel import SQLModel, create_engine, Session
from app.models import Proposal


@pytest.fixture
def seeded_proposals(monkeypatch):
    """Spin up a fresh in-memory DB and patch get_session to use it."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    spread_id = str(uuid.uuid4())
    long_id = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Proposal(
            id=spread_id, session_id="sess-1", ticker="NVDA",
            legs_json=_json.dumps([
                {"contract_symbol": "NVDA260619C00800000", "qty": 1, "action": "buy", "premium": 12.40, "side": "call", "strike": 800.0},
                {"contract_symbol": "NVDA260619C00850000", "qty": 1, "action": "sell", "premium": 8.20, "side": "call", "strike": 850.0},
            ]),
            max_risk=420.0, max_reward=580.0, breakeven=804.20, expiry="2026-06-19",
            rationale="bull spread", confidence=0.7, risks_json="[]", status="executed",
        ))
        s.add(Proposal(
            id=long_id, session_id="sess-1", ticker="AAPL",
            legs_json=_json.dumps([
                {"contract_symbol": "AAPL250718C00220000", "qty": 1, "action": "buy", "premium": 6.20, "side": "call", "strike": 220.0},
            ]),
            max_risk=620.0, max_reward=None, breakeven=226.20, expiry="2025-07-18",
            rationale="long call", confidence=0.6, risks_json="[]", status="executed",
        ))
        s.commit()
    from contextlib import contextmanager
    @contextmanager
    def fake_session():
        with Session(engine) as ses:
            yield ses
    from app.services import portfolio_service
    monkeypatch.setattr(portfolio_service, "get_session", fake_session)
    return {"spread_id": spread_id, "long_id": long_id}


def test_group_strategies_full_spread_open(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "NVDA260619C00800000", "kind": "option", "qty": 1.0, "avg_entry": 12.40, "current_price": 14.00,
         "market_value": 1400.0, "unrealized_pl": 160.0, "underlying": "NVDA", "side": "call", "strike": 800.0, "expiry": "2026-06-19"},
        {"symbol": "NVDA260619C00850000", "kind": "option", "qty": 1.0, "avg_entry": 8.20, "current_price": 9.00,
         "market_value": 900.0, "unrealized_pl": 80.0, "underlying": "NVDA", "side": "call", "strike": 850.0, "expiry": "2026-06-19"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    g = groups[0]
    assert g["proposal_id"] == seeded_proposals["spread_id"]
    assert g["ticker"] == "NVDA"
    assert g["type"] == "bull-call-spread"
    assert g["legs_open"] == 2 and g["legs_total"] == 2
    # cost_basis: buy 1240 - sell 820 = 420 (debit)
    assert g["cost_basis"] == pytest.approx(420.0)
    # current_value: long leg MV(1400) - short leg MV(900) = 500
    assert g["current_value"] == pytest.approx(500.0)
    assert g["unrealized_pl"] == pytest.approx(80.0)
    assert g["expiry"] == "2026-06-19"


def test_group_strategies_partial_spread(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "NVDA260619C00800000", "kind": "option", "qty": 1.0, "avg_entry": 12.40, "current_price": 14.00,
         "market_value": 1400.0, "unrealized_pl": 160.0, "underlying": "NVDA", "side": "call", "strike": 800.0, "expiry": "2026-06-19"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    g = groups[0]
    assert g["legs_open"] == 1 and g["legs_total"] == 2
    # current value reflects only the open long leg
    assert g["current_value"] == pytest.approx(1400.0)


def test_group_strategies_long_call(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "AAPL250718C00220000", "kind": "option", "qty": 1.0, "avg_entry": 6.20, "current_price": 5.10,
         "market_value": 510.0, "unrealized_pl": -110.0, "underlying": "AAPL", "side": "call", "strike": 220.0, "expiry": "2025-07-18"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    assert groups[0]["type"] == "long-call"
    assert groups[0]["legs_total"] == 1


def test_group_strategies_no_match(seeded_proposals):
    from app.services.portfolio_service import _group_strategies
    positions = [
        {"symbol": "TSLA250620P00200000", "kind": "option", "qty": 1.0, "avg_entry": 5.0, "current_price": 4.5,
         "market_value": 450.0, "unrealized_pl": -50.0, "underlying": "TSLA", "side": "put", "strike": 200.0, "expiry": "2025-06-20"},
    ]
    assert _group_strategies(positions) == []


def test_group_strategies_profitable_short_leg(seeded_proposals):
    """A short leg where the price has fallen (profitable for the seller) must contribute
    positively to the strategy P/L. Position-level unrealized_pl is direction-naive
    (price_change * qty * multiplier, assuming long), so _group_strategies must apply
    sign * unrealized_pl: sign(-1) * negative = positive contribution."""
    from app.services.portfolio_service import _group_strategies
    positions = [
        # Long call: bought at 12.40, now at 13.00 — unrealized_pl = +60 (price up = gain for long)
        {"symbol": "NVDA260619C00800000", "kind": "option", "qty": 1.0, "avg_entry": 12.40, "current_price": 13.00,
         "market_value": 1300.0, "unrealized_pl": 60.0, "underlying": "NVDA", "side": "call", "strike": 800.0, "expiry": "2026-06-19"},
        # Short call: sold at 8.20, now at 6.00 — unrealized_pl = -220 (price fell; direction-naive shows as loss)
        # Correct strategy contribution: sign(-1) * (-220) = +220 (price drop is a gain for the short seller)
        {"symbol": "NVDA260619C00850000", "kind": "option", "qty": 1.0, "avg_entry": 8.20, "current_price": 6.00,
         "market_value": 600.0, "unrealized_pl": -220.0, "underlying": "NVDA", "side": "call", "strike": 850.0, "expiry": "2026-06-19"},
    ]
    groups = _group_strategies(positions)
    assert len(groups) == 1
    g = groups[0]
    # cost_basis: buy 1240 - sell 820 = 420 debit
    assert g["cost_basis"] == pytest.approx(420.0)
    # current_value: long MV(1300) - short MV(600) = 700
    assert g["current_value"] == pytest.approx(700.0)
    # unrealized_pl: (+1)*60 + (-1)*(-220) = 60 + 220 = 280
    assert g["unrealized_pl"] == pytest.approx(280.0)


def test_build_snapshot_fixtures_mode(seeded_proposals, monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from app.services import alpaca_service, portfolio_service
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    monkeypatch.setattr(alpaca_service, "get_positions", lambda: [
        {"symbol": "NVDA260619C00800000", "qty": 1.0, "avg_entry_price": 12.40},
        {"symbol": "NVDA260619C00850000", "qty": 1.0, "avg_entry_price": 8.20},
    ])
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {s: 14.00 if s.endswith("00800000") else 9.00 for s in syms})
    snap = portfolio_service.build_snapshot()
    assert snap["account"]["equity"] == 100000.0
    assert len(snap["positions"]) == 2
    assert len(snap["strategies"]) == 1
    assert snap["allocations"]["by_kind"]["cash"] == pytest.approx(50.0, abs=0.01)
    assert snap["errors"] == []
    assert "fetched_at" in snap
    assert isinstance(snap["history"], list)


def test_build_snapshot_partial_failure(monkeypatch):
    from app.services import alpaca_service, portfolio_service
    monkeypatch.setattr(alpaca_service, "get_portfolio", lambda: {"cash": 50000.0, "equity": 100000.0, "buying_power": 100000.0})
    def boom(): raise RuntimeError("alpaca down")
    monkeypatch.setattr(alpaca_service, "get_positions", boom)
    monkeypatch.setattr(alpaca_service, "get_latest_prices", lambda syms: {})
    snap = portfolio_service.build_snapshot()
    assert "positions_unavailable" in snap["errors"]
    assert snap["positions"] == []
    assert snap["account"]["equity"] == 100000.0


def test_get_equity_curve_passthrough(monkeypatch):
    monkeypatch.setenv("FIXTURES_MODE", "1")
    from importlib import reload
    from app import config; reload(config)
    from app.services import alpaca_service; reload(alpaca_service)
    from app.services import portfolio_service; reload(portfolio_service)
    res = portfolio_service.get_equity_curve("1M")
    assert res["period"] == "1M"
    assert isinstance(res["points"], list)


def test_get_equity_curve_invalid_period():
    from app.services import portfolio_service
    with pytest.raises(ValueError):
        portfolio_service.get_equity_curve("INVALID")
