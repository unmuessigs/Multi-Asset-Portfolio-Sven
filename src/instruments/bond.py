"""Coupon bond instrument (priced from yield, with rate sensitivity)."""
from __future__ import annotations

from .base import Instrument, MarketContext, zero_greeks
from ..pricing.bond_math import BondMath


class Bond(Instrument):
    """A plain-vanilla fixed-coupon bond.

    Parameters
    ----------
    symbol       : identifier (e.g. "UST 10Y")
    face         : par/redemption value (price quoted per this face)
    coupon_rate  : annual coupon rate (decimal)
    years        : years to maturity
    ytm          : annual yield to maturity (decimal)
    freq         : coupon frequency per year
    """

    asset_class = "Bond"

    def __init__(self, symbol: str, face: float, coupon_rate: float,
                 years: float, ytm: float, freq: int = 2):
        super().__init__(symbol)
        self.face = face
        self.coupon_rate = coupon_rate
        self.years = years
        self.ytm = ytm
        self.freq = freq

    def _effective_ytm(self, market: MarketContext) -> float:
        # Scenario engine shifts yields via rate_shock (parallel shift).
        return self.ytm + market.rate_shock

    def price(self, market: MarketContext) -> float:
        return BondMath.price(self.face, self.coupon_rate, self.years,
                              self._effective_ytm(market), self.freq)

    def analytics(self, market: MarketContext):
        """Return the full BondResult (duration, convexity, yields...)."""
        return BondMath.analyse(self.face, self.coupon_rate, self.years,
                                self.freq, ytm=self._effective_ytm(market))

    def greeks(self, market: MarketContext) -> dict:
        """Bonds carry no option Greeks; rate risk is reported via duration.

        We expose ``rho`` as the price change for a +1 percentage-point rise in
        yield (i.e. -ModDur * Price * 0.01), so it slots into the portfolio
        rate-sensitivity aggregate alongside option rho.
        """
        g = zero_greeks()
        res = self.analytics(market)
        g["rho"] = -res.modified_duration * res.price * 0.01
        return g
