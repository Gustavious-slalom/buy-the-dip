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
