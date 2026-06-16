"""Equity and ETF instruments (linear cash instruments)."""
from __future__ import annotations

from .base import Instrument, MarketContext, zero_greeks


class Equity(Instrument):
    """A single stock. Delta = 1 per share, no second-order Greeks."""

    asset_class = "Equity"

    def price(self, market: MarketContext) -> float:
        return market.spot(self.symbol)

    def greeks(self, market: MarketContext) -> dict:
        g = zero_greeks()
        g["delta"] = 1.0          # share-equivalent delta
        return g


class ETF(Equity):
    """Exchange-traded fund. Behaves like equity for valuation/risk."""

    asset_class = "ETF"
