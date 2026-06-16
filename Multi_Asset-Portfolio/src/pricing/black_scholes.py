"""
Black-Scholes-Merton option pricing engine (European options).

Model
-----
The Black-Scholes-Merton model prices a European option on an asset whose
price follows geometric Brownian motion with constant volatility ``sigma`` and
continuous dividend yield ``q``:

    d1 = [ln(S/K) + (r - q + sigma**2 / 2) * T] / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)

    Call = S e^{-qT} N(d1) - K e^{-rT} N(d2)
    Put  = K e^{-rT} N(-d2) - S e^{-qT} N(-d1)

where N(.) is the standard-normal CDF.

Greeks are the partial derivatives of the option value with respect to the
model inputs. We return them in *practitioner* conventions:

    * Delta  : per +1.00 move in spot               (dimensionless)
    * Gamma  : per +1.00 move in spot, of delta
    * Vega   : per +1 percentage-point (0.01) of vol
    * Theta  : per +1 calendar day of time decay
    * Rho    : per +1 percentage-point (0.01) of rate

These scalings match what risk systems (Bloomberg OVML, IB) display, so the
numbers are directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt, exp

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


@dataclass
class BSResult:
    """Container for a full Black-Scholes valuation + Greeks."""
    price: float
    delta: float
    gamma: float
    vega: float      # per 1 vol point (0.01)
    theta: float     # per 1 day
    rho: float       # per 1 rate point (0.01)


class BlackScholes:
    """Stateless Black-Scholes-Merton calculator.

    All methods accept:
        S     : spot price of the underlying
        K     : strike
        T     : time to expiry in years
        r     : continuously-compounded risk-free rate
        sigma : annualised volatility (e.g. 0.20 = 20 %)
        q     : continuous dividend yield (default 0)
        kind  : "call" or "put"
    """

    # ------------------------------------------------------------------ #
    #  Core helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _d1_d2(S, K, T, r, sigma, q):
        # Guard against degenerate inputs that would divide by zero.
        T = max(T, 1e-9)
        sigma = max(sigma, 1e-9)
        d1 = (log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)
        return d1, d2

    # ------------------------------------------------------------------ #
    #  Price
    # ------------------------------------------------------------------ #
    @staticmethod
    def price(S, K, T, r, sigma, q=0.0, kind="call") -> float:
        if T <= 0:  # option has expired -> intrinsic value
            return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
        d1, d2 = BlackScholes._d1_d2(S, K, T, r, sigma, q)
        if kind == "call":
            return S * exp(-q * T) * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
        return K * exp(-r * T) * norm.cdf(-d2) - S * exp(-q * T) * norm.cdf(-d1)

    # ------------------------------------------------------------------ #
    #  Greeks (returned all at once for efficiency)
    # ------------------------------------------------------------------ #
    @staticmethod
    def greeks(S, K, T, r, sigma, q=0.0, kind="call") -> BSResult:
        if T <= 0:
            intrinsic = (max(S - K, 0.0) if kind == "call" else max(K - S, 0.0))
            # At expiry delta is a step function; report 1/0/-1 sensibly.
            if kind == "call":
                delta = 1.0 if S > K else 0.0
            else:
                delta = -1.0 if S < K else 0.0
            return BSResult(intrinsic, delta, 0.0, 0.0, 0.0, 0.0)

        d1, d2 = BlackScholes._d1_d2(S, K, T, r, sigma, q)
        pdf = norm.pdf(d1)
        disc_q = exp(-q * T)
        disc_r = exp(-r * T)
        sqrtT = sqrt(T)

        price = BlackScholes.price(S, K, T, r, sigma, q, kind)

        # Gamma & Vega are identical for calls and puts.
        gamma = disc_q * pdf / (S * sigma * sqrtT)
        vega = S * disc_q * pdf * sqrtT * 0.01          # per 1 vol point

        if kind == "call":
            delta = disc_q * norm.cdf(d1)
            theta = (-(S * disc_q * pdf * sigma) / (2 * sqrtT)
                     - r * K * disc_r * norm.cdf(d2)
                     + q * S * disc_q * norm.cdf(d1))
            rho = K * T * disc_r * norm.cdf(d2) * 0.01   # per 1 rate point
        else:
            delta = -disc_q * norm.cdf(-d1)
            theta = (-(S * disc_q * pdf * sigma) / (2 * sqrtT)
                     + r * K * disc_r * norm.cdf(-d2)
                     - q * S * disc_q * norm.cdf(-d1))
            rho = -K * T * disc_r * norm.cdf(-d2) * 0.01

        theta = theta / 365.0                            # per calendar day
        return BSResult(price, delta, gamma, vega, theta, rho)

    # ------------------------------------------------------------------ #
    #  Implied volatility (root find on the price)
    # ------------------------------------------------------------------ #
    @staticmethod
    def implied_vol(target_price, S, K, T, r, q=0.0, kind="call") -> float:
        """Back out the volatility that reproduces ``target_price``.

        Uses Brent's method on the monotone price-vs-vol relationship. Returns
        NaN if the target price is outside the no-arbitrage bounds.
        """
        if T <= 0 or target_price <= 0:
            return float("nan")

        intrinsic = (max(S - K, 0.0) if kind == "call" else max(K - S, 0.0))
        if target_price < intrinsic - 1e-8:
            return float("nan")

        def objective(sig):
            return BlackScholes.price(S, K, T, r, sig, q, kind) - target_price

        try:
            return brentq(objective, 1e-4, 5.0, maxiter=200, xtol=1e-8)
        except (ValueError, RuntimeError):
            return float("nan")

    # ------------------------------------------------------------------ #
    #  Vectorised price (handy for payoff / surface charts)
    # ------------------------------------------------------------------ #
    @staticmethod
    def price_vector(S_arr, K, T, r, sigma, q=0.0, kind="call") -> np.ndarray:
        """Vectorised price over an array of spot values."""
        S_arr = np.asarray(S_arr, dtype=float)
        if T <= 0:
            return (np.maximum(S_arr - K, 0.0) if kind == "call"
                    else np.maximum(K - S_arr, 0.0))
        sigma = max(sigma, 1e-9)
        d1 = (np.log(S_arr / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)
        if kind == "call":
            return (S_arr * exp(-q * T) * norm.cdf(d1)
                    - K * exp(-r * T) * norm.cdf(d2))
        return (K * exp(-r * T) * norm.cdf(-d2)
                - S_arr * exp(-q * T) * norm.cdf(-d1))
