"""
Tests for the Hedging Analytics module (12 required cases).

Run offline with synthetic market data. Verifies Greek signs, multiplier
handling, hedge directions, rounding residuals, multi-underlying separation and
robust failure on missing/unusable option data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from src.data.market_data import MarketData
from src.portfolio.portfolio import Portfolio
from src.instruments import Equity, Option, Position
from src.instruments.base import MarketContext
from src import hedging
from src.hedging import (HedgeOption, UnderlyingGreeks, TransactionCosts,
                         build_delta_hedge, build_gamma_hedge,
                         build_delta_gamma_hedge, finalize_hedge,
                         gamma_hedge_contracts, delta_hedge_shares,
                         rounding_alternatives, hedge_error)
from src.hedge_optimizer import optimize_hedge


CTX = MarketContext(spots={"AAPL": 100.0, "MSFT": 200.0}, rate=0.04)


def _atm_call_option(spot=100.0):
    return HedgeOption(kind="call", strike=spot, expiry_years=0.25, sigma=0.25,
                       spot=spot, rate=0.04)


# --------------------------------------------------------------------------- #
#  1-3: option Greek signs
# --------------------------------------------------------------------------- #
def test_long_call_positive_delta_gamma():
    pos = Position(Option("AAPL", 100, 0.25, 0.25, "call"), 1, 1)
    g = pos.greeks(CTX)
    assert g["delta"] > 0 and g["gamma"] > 0


def test_short_call_negative_delta_gamma():
    pos = Position(Option("AAPL", 100, 0.25, 0.25, "call"), 1, -1)
    g = pos.greeks(CTX)
    assert g["delta"] < 0 and g["gamma"] < 0


def test_long_put_negative_delta_positive_gamma():
    pos = Position(Option("AAPL", 100, 0.25, 0.25, "put"), 1, 1)
    g = pos.greeks(CTX)
    assert g["delta"] < 0 and g["gamma"] > 0


# --------------------------------------------------------------------------- #
#  4: pure stock has delta but no gamma
# --------------------------------------------------------------------------- #
def test_stock_delta_no_gamma():
    pos = Position(Equity("AAPL"), 100, 1)
    g = pos.greeks(CTX)
    assert abs(g["delta"] - 100) < 1e-9
    assert g["gamma"] == 0.0


# --------------------------------------------------------------------------- #
#  5: delta hedge of a positive delta -> sell/short shares
# --------------------------------------------------------------------------- #
def test_delta_hedge_positive_delta_sells():
    ug = UnderlyingGreeks("AAPL", delta=150.0, gamma=0.0, spot=100.0)
    res = finalize_hedge(build_delta_hedge(ug), "nearest")
    assert res.shares < 0                       # sell to neutralise long delta
    assert abs(res.residual["delta"]) < 1e-6


def test_delta_hedge_negative_delta_buys():
    ug = UnderlyingGreeks("AAPL", delta=-80.0, gamma=0.0, spot=100.0)
    res = finalize_hedge(build_delta_hedge(ug), "nearest")
    assert res.shares > 0


# --------------------------------------------------------------------------- #
#  6: gamma hedge of a negative gamma -> buy options (positive contracts)
# --------------------------------------------------------------------------- #
def test_gamma_hedge_negative_gamma_buys_options():
    opt = _atm_call_option()
    ug = UnderlyingGreeks("AAPL", delta=0.0, gamma=-5.0, spot=100.0,
                          has_options=True)
    contracts = gamma_hedge_contracts(ug.gamma, opt)
    assert contracts > 0                        # long options add positive gamma


def test_gamma_hedge_positive_gamma_shorts_options():
    opt = _atm_call_option()
    ug = UnderlyingGreeks("AAPL", delta=0.0, gamma=5.0, spot=100.0)
    contracts = gamma_hedge_contracts(ug.gamma, opt)
    assert contracts < 0


# --------------------------------------------------------------------------- #
#  7: combined delta-gamma hedge neutralises both (theoretical)
# --------------------------------------------------------------------------- #
def test_delta_gamma_hedge_neutralises_both():
    opt = _atm_call_option()
    ug = UnderlyingGreeks("AAPL", delta=120.0, gamma=8.0, spot=100.0)
    res = finalize_hedge(build_delta_gamma_hedge(ug, opt), "theoretical")
    assert abs(res.residual["delta"]) < 1e-6
    assert abs(res.residual["gamma"]) < 1e-6


# --------------------------------------------------------------------------- #
#  8: contract multiplier of 100 is applied
# --------------------------------------------------------------------------- #
def test_multiplier_100_applied():
    from src.pricing.black_scholes import BlackScholes
    bs = BlackScholes.greeks(100, 100, 0.25, 0.04, 0.25, kind="call")
    pos = Position(Option("AAPL", 100, 0.25, 0.25, "call"), 2, 1)
    g = pos.greeks(CTX)
    assert abs(g["delta"] - bs.delta * 2 * 100) < 1e-6
    assert abs(g["gamma"] - bs.gamma * 2 * 100) < 1e-6


# --------------------------------------------------------------------------- #
#  9: rounded contract counts give consistent residuals
# --------------------------------------------------------------------------- #
def test_rounding_changes_residual_consistently():
    opt = _atm_call_option()
    ug = UnderlyingGreeks("AAPL", delta=137.0, gamma=6.3, spot=100.0)
    rows = rounding_alternatives(build_delta_gamma_hedge(ug, opt), TransactionCosts())
    # theoretical row should have ~zero error; rounded rows are tradable (ints).
    theo = next(r for r in rows if r["Strategie"] == "theoretical")
    nearest = next(r for r in rows if r["Strategie"] == "nearest")
    assert abs(theo["Rest-Delta"]) < 1e-6 and abs(theo["Rest-Gamma"]) < 1e-6
    assert float(nearest["Optionskontrakte"]).is_integer()
    assert float(nearest["Aktien"]).is_integer()


# --------------------------------------------------------------------------- #
#  10: multiple underlyings are kept separate
# --------------------------------------------------------------------------- #
def test_multiple_underlyings_separated():
    pf = Portfolio(MarketData(use_live=False))
    pf.add(Position(Equity("AAPL"), 100, 1))
    pf.add(Position(Equity("MSFT"), 50, -1))
    pf.add(Position(Option("AAPL", round(pf.market.spot("AAPL")), 0.3, 0.25, "call"),
                    5, 1))
    ug = hedging.compute_underlying_greeks(pf)
    assert set(ug.keys()) == {"AAPL", "MSFT"}
    assert ug["MSFT"].delta < 0                 # short 50 MSFT
    assert ug["AAPL"].has_options and not ug["MSFT"].has_options


# --------------------------------------------------------------------------- #
#  11 & 12: missing/unusable option data raises clearly (no silent failure)
# --------------------------------------------------------------------------- #
def test_expired_option_zero_gamma_raises():
    expired = HedgeOption(kind="call", strike=100, expiry_years=0.0, sigma=0.25,
                          spot=100, rate=0.04)
    with pytest.raises(ValueError):
        gamma_hedge_contracts(5.0, expired)


def test_deep_otm_option_near_zero_gamma_raises():
    deep = HedgeOption(kind="call", strike=10000, expiry_years=0.25, sigma=0.25,
                       spot=100, rate=0.04)
    with pytest.raises(ValueError):
        gamma_hedge_contracts(5.0, deep)


# --------------------------------------------------------------------------- #
#  Bonus: optimizer returns an integer, lower-error solution
# --------------------------------------------------------------------------- #
def test_optimizer_returns_integer_solution():
    ug = UnderlyingGreeks("AAPL", delta=120.0, gamma=8.0, spot=100.0)
    cands = [HedgeOption("call", k, 0.25, 0.25, 100.0, 0.04)
             for k in (90, 95, 100, 105, 110)]
    best = optimize_hedge(ug, cands, "Ausgewogener Hedge")
    assert best is not None
    assert isinstance(best.contracts, int) and isinstance(best.shares, int)
    assert abs(best.residual["delta"]) < 5     # close to neutral after rounding


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
