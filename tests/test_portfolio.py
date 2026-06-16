"""Integration tests for portfolio aggregation, risk and scenarios.

Uses synthetic (offline) market data so the tests are deterministic and need
no network access.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.market_data import MarketData
from src.portfolio.portfolio import Portfolio
from src.analytics.risk import RiskAnalytics
from src.analytics.scenario import ScenarioEngine
from src.instruments import Equity, ETF, Option, Future, Bond, Cash, Position


def build_portfolio() -> Portfolio:
    market = MarketData(use_live=False)        # force synthetic data
    pf = Portfolio(market)
    s = market.spot("AAPL")
    pf.add(Position(Equity("AAPL"), 100, 1, s * 0.9))
    pf.add(Position(ETF("SPY"), 50, 1, market.spot("SPY")))
    pf.add(Position(Option("AAPL", round(s), 0.5, 0.25, "call"), 10, 1, 2.0))
    pf.add(Position(Future("ES=F", 50), 1, -1, market.spot("ES=F")))
    pf.add(Position(Bond("UST", 1000, 0.04, 10, 0.0425, 2), 10, 1, 990))
    pf.add(Position(Cash("USD"), 10000, 1, 1.0))
    return pf


def test_value_and_counts():
    pf = build_portfolio()
    assert len(pf) == 6
    assert pf.total_value() != 0
    assert pf.gross_exposure() > 0


def test_greeks_aggregate_has_delta():
    pf = build_portfolio()
    g = pf.portfolio_greeks()
    assert set(g) == {"delta", "gamma", "vega", "theta", "rho"}
    # Equity + ETF + option contribute positive delta; short future subtracts.
    assert g["gamma"] != 0        # option provides gamma
    assert g["vega"] != 0


def test_allocation_sums_to_100():
    pf = build_portfolio()
    alloc = pf.allocation()
    assert abs(alloc["Weight"].sum() - 100) < 1e-6


def test_value_series_length():
    pf = build_portfolio()
    vs = pf.value_series("1y")
    assert len(vs) > 100


def test_risk_metrics_runtime():
    pf = build_portfolio()
    risk = RiskAnalytics(pf, benchmark_returns=pf.market.returns("SPY"))
    m = risk.metrics()
    assert m.value != 0
    assert m.var_parametric >= 0
    assert m.cvar >= 0
    rc = risk.risk_contributions()
    assert not rc.empty


def test_scenario_engine():
    pf = build_portfolio()
    eng = ScenarioEngine(pf)
    up = eng.run(spot_shock=0.10)
    down = eng.run(spot_shock=-0.10)
    # A net-long book gains when the market rises.
    assert up.new_value > down.new_value
    pct, vals, pnls = eng.spot_sweep()
    assert len(pnls) == len(pct) > 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
