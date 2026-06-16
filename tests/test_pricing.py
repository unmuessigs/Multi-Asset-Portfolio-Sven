"""Unit tests for the pricing engines (run with: python -m pytest -q)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pricing.black_scholes import BlackScholes
from src.pricing.bond_math import BondMath


# --------------------------------------------------------------------------- #
#  Black-Scholes
# --------------------------------------------------------------------------- #
def test_bs_textbook_call():
    # Hull textbook reference: S=K=100, T=1, r=5%, sigma=20% -> ~10.4506
    price = BlackScholes.price(100, 100, 1, 0.05, 0.20, kind="call")
    assert abs(price - 10.4506) < 1e-3


def test_put_call_parity():
    S, K, T, r, sigma, q = 100, 95, 0.75, 0.04, 0.30, 0.01
    c = BlackScholes.price(S, K, T, r, sigma, q, "call")
    p = BlackScholes.price(S, K, T, r, sigma, q, "put")
    lhs = c - p
    rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert abs(lhs - rhs) < 1e-8


def test_delta_bounds_and_gamma_positive():
    g = BlackScholes.greeks(100, 100, 0.5, 0.03, 0.25, kind="call")
    assert 0.0 < g.delta < 1.0
    assert g.gamma > 0
    p = BlackScholes.greeks(100, 100, 0.5, 0.03, 0.25, kind="put")
    assert -1.0 < p.delta < 0.0


def test_implied_vol_roundtrip():
    true_sigma = 0.37
    price = BlackScholes.price(120, 110, 0.5, 0.02, true_sigma, kind="put")
    iv = BlackScholes.implied_vol(price, 120, 110, 0.5, 0.02, kind="put")
    assert abs(iv - true_sigma) < 1e-4


def test_expired_option_intrinsic():
    assert BlackScholes.price(120, 100, 0, 0.05, 0.2, kind="call") == 20
    assert BlackScholes.price(80, 100, 0, 0.05, 0.2, kind="put") == 20


# --------------------------------------------------------------------------- #
#  Bond math
# --------------------------------------------------------------------------- #
def test_bond_prices_at_par():
    # When YTM == coupon, a bond trades at par.
    price = BondMath.price(1000, 0.05, 10, 0.05, freq=2)
    assert abs(price - 1000) < 1e-6


def test_ytm_roundtrip():
    price = BondMath.price(1000, 0.06, 7, 0.045, freq=2)
    ytm = BondMath.yield_to_maturity(price, 1000, 0.06, 7, freq=2)
    assert abs(ytm - 0.045) < 1e-6


def test_duration_below_maturity_and_positive():
    mac, mod, conv = BondMath.durations(1000, 0.05, 10, 0.05, freq=2)
    assert 0 < mod < mac <= 10
    assert conv > 0


def test_zero_coupon_duration_equals_maturity():
    # A zero-coupon bond's Macaulay duration equals its maturity.
    mac, mod, conv = BondMath.durations(1000, 0.0, 5, 0.04, freq=1)
    assert abs(mac - 5) < 1e-6


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
