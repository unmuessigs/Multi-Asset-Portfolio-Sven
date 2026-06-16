"""Futures contract (linear, leveraged via contract size)."""
from __future__ import annotations

from .base import Instrument, MarketContext, zero_greeks


class Future(Instrument):
    """A futures contract on an underlying.

    Valuation here uses the underlying spot as a proxy for the futures price
    (cost-of-carry is small for short-dated contracts and live futures quotes
    are pulled directly when available). ``contract_size`` is the point value /
    multiplier of the contract.
    """

    asset_class = "Future"

    def __init__(self, symbol: str, contract_size: float = 1.0):
        super().__init__(symbol)
        self.multiplier = contract_size

    def price(self, market: MarketContext) -> float:
        return market.spot(self.symbol)

    def greeks(self, market: MarketContext) -> dict:
        g = zero_greeks()
        g["delta"] = 1.0          # +1 delta per unit of underlying exposure
        return g
