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
