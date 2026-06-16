"""Cash position (risk-free, constant value)."""
from __future__ import annotations

from .base import Instrument, MarketContext


class Cash(Instrument):
    """A cash balance in the portfolio's base currency.

    Priced at par (1.0 per unit); quantity represents the nominal amount.
    Carries no market Greeks.
    """

    asset_class = "Cash"

    def __init__(self, symbol: str = "CASH"):
        super().__init__(symbol)

    def price(self, market: MarketContext) -> float:
        return 1.0
