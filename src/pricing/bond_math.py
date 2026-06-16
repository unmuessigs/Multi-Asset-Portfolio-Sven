"""
Fixed-income analytics for plain-vanilla coupon bonds.

Conventions
-----------
* ``face``         : redemption / par value (e.g. 1000)
* ``coupon_rate``  : annual coupon rate as a decimal (e.g. 0.05 = 5 %)
* ``years``        : years to maturity
* ``freq``         : coupon payments per year (1 = annual, 2 = semi-annual)
* ``ytm``          : annual yield to maturity (decimal), compounded ``freq`` times

All cash flows are discounted on a per-period basis using the periodic yield
y = ytm / freq.

Definitions
-----------
Price            = sum_t  CF_t / (1 + y)^t              (t in periods)
Macaulay Dur.    = sum_t  t/freq * PV(CF_t) / Price     (in years)
Modified Dur.    = Macaulay / (1 + y)
Convexity        = [ sum_t t(t+1) CF_t / (1+y)^{t+2} ] / Price / freq^2
Current Yield    = annual coupon / clean price
YTM              = root of (price(ytm) - market_price)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq


@dataclass
class BondResult:
    """Full analytics snapshot for a bond."""
    price: float
    ytm: float
    current_yield: float
    macaulay_duration: float
    modified_duration: float
    convexity: float


class BondMath:
    """Stateless coupon-bond calculator."""

    # ------------------------------------------------------------------ #
    #  Cash-flow schedule
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cashflows(face, coupon_rate, years, freq):
        """Return (periods, cashflow) arrays. Last flow includes redemption."""
        n = int(round(years * freq))
        n = max(n, 1)
        coupon = face * coupon_rate / freq
        periods = np.arange(1, n + 1)
        cfs = np.full(n, coupon, dtype=float)
        cfs[-1] += face        # principal repaid at maturity
        return periods, cfs

    # ------------------------------------------------------------------ #
    #  Price given a yield
    # ------------------------------------------------------------------ #
    @staticmethod
    def price(face, coupon_rate, years, ytm, freq=2) -> float:
        periods, cfs = BondMath._cashflows(face, coupon_rate, years, freq)
        y = ytm / freq
        discount = (1 + y) ** periods
        return float(np.sum(cfs / discount))

    # ------------------------------------------------------------------ #
    #  Yield to maturity from a market price
    # ------------------------------------------------------------------ #
    @staticmethod
    def yield_to_maturity(market_price, face, coupon_rate, years, freq=2) -> float:
        def objective(ytm):
            return BondMath.price(face, coupon_rate, years, ytm, freq) - market_price
        try:
            return brentq(objective, -0.99, 5.0, maxiter=200, xtol=1e-10)
        except (ValueError, RuntimeError):
            return float("nan")

    # ------------------------------------------------------------------ #
    #  Duration & convexity
    # ------------------------------------------------------------------ #
    @staticmethod
    def durations(face, coupon_rate, years, ytm, freq=2):
        """Return (macaulay, modified, convexity)."""
        periods, cfs = BondMath._cashflows(face, coupon_rate, years, freq)
        y = ytm / freq
        discount = (1 + y) ** periods
        pv = cfs / discount
        price = pv.sum()
        if price <= 0:
            return float("nan"), float("nan"), float("nan")

        # Macaulay duration: PV-weighted average time (converted to years).
        macaulay = float(np.sum((periods / freq) * pv) / price)
        modified = macaulay / (1 + y)

        # Convexity: second derivative of price w.r.t. yield, per-period then
        # rescaled to annual units by dividing by freq**2.
        convexity = float(
            np.sum(periods * (periods + 1) * cfs / (1 + y) ** (periods + 2))
            / price / (freq ** 2)
        )
        return macaulay, modified, convexity

    # ------------------------------------------------------------------ #
    #  One-shot full analytics
    # ------------------------------------------------------------------ #
    @staticmethod
    def analyse(face, coupon_rate, years, freq=2,
                ytm=None, market_price=None) -> BondResult:
        """Compute every metric. Provide *either* ``ytm`` or ``market_price``."""
        if ytm is None and market_price is None:
            raise ValueError("Provide either ytm or market_price")
        if ytm is None:
            ytm = BondMath.yield_to_maturity(market_price, face, coupon_rate,
                                             years, freq)
        price = BondMath.price(face, coupon_rate, years, ytm, freq)
        mac, mod, conv = BondMath.durations(face, coupon_rate, years, ytm, freq)
        current_yield = (face * coupon_rate) / price if price else float("nan")
        return BondResult(price, ytm, current_yield, mac, mod, conv)

    # ------------------------------------------------------------------ #
    #  Price change estimate for a yield shock (duration + convexity)
    # ------------------------------------------------------------------ #
    @staticmethod
    def price_change(price, modified_duration, convexity, dy) -> float:
        """Second-order Taylor estimate of the price change for a yield move ``dy``.

            dP/P  ~=  -ModDur * dy + 0.5 * Convexity * dy**2
        """
        return price * (-modified_duration * dy + 0.5 * convexity * dy ** 2)
