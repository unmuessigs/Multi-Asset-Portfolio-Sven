"""
Instrument & Position abstractions.

Design
------
``Instrument`` is the abstract base every asset class inherits from. An
instrument knows how to value *one unit/contract* of itself and to report its
per-unit Greeks. It is deliberately stateless with respect to *how much* the
investor holds — that lives on ``Position``.

``Position`` wraps an instrument with a quantity, a direction (long/short) and
an entry price, and exposes signed market value, P&L and signed Greeks. This
separation keeps the maths reusable (one Option object can be priced
independently of position size) and mirrors how real risk systems model books.

Greeks convention
-----------------
Per-unit Greeks are "share-equivalent": linear instruments (equity, ETF,
future) have delta = 1 and all other Greeks = 0, so a long position's delta
equals its quantity. Options return Black-Scholes Greeks per share. Position
Greeks are then ``signed_qty * multiplier * per_unit_greek`` which makes them
additive across the whole portfolio.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# Greeks that every instrument reports (zeros for non-derivatives).
GREEK_KEYS = ("delta", "gamma", "vega", "theta", "rho")


def zero_greeks() -> dict:
    return {k: 0.0 for k in GREEK_KEYS}


@dataclass
class MarketContext:
    """Snapshot of market inputs needed for valuation.

    ``spots`` maps an underlying symbol -> current price. ``rate`` is the
    risk-free rate. Optional ``spot_shock`` / ``vol_shock`` / ``rate_shock`` /
    ``time_decay`` are used by the scenario engine to stress the book without
    mutating the underlying positions.
    """
    spots: dict = field(default_factory=dict)
    rate: float = 0.0425
    spot_shock: float = 0.0      # relative shock, e.g. +0.10 = +10 %
    vol_shock: float = 0.0       # absolute vol points, e.g. +0.05 = +5 pts
    rate_shock: float = 0.0      # absolute rate change, e.g. +0.01 = +100 bps
    time_decay: float = 0.0      # years of time decay to apply (e.g. 1/365)

    def spot(self, symbol: str, default: float = 0.0) -> float:
        base = self.spots.get(symbol, default)
        return base * (1.0 + self.spot_shock)


class Instrument(ABC):
    """Abstract base class for every tradable instrument."""

    asset_class: str = "Generic"
    multiplier: float = 1.0      # contract multiplier (options=100, etc.)

    def __init__(self, symbol: str):
        self.symbol = symbol

    @abstractmethod
    def price(self, market: MarketContext) -> float:
        """Fair value of a single unit/contract under ``market``."""

    def greeks(self, market: MarketContext) -> dict:
        """Per-unit Greeks. Default: no sensitivities (linear cash flow)."""
        return zero_greeks()

    # Symbol used to look up a spot price; defaults to the instrument symbol.
    @property
    def underlying(self) -> str:
        return self.symbol

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.symbol})"


@dataclass
class Position:
    """A holding of an instrument."""

    instrument: Instrument
    quantity: float
    direction: int = 1            # +1 long, -1 short
    entry_price: float = 0.0      # price paid per unit/contract
    label: Optional[str] = None   # optional display name

    @property
    def signed_qty(self) -> float:
        return self.direction * self.quantity

    @property
    def asset_class(self) -> str:
        return self.instrument.asset_class

    @property
    def name(self) -> str:
        return self.label or self.instrument.symbol

    def unit_price(self, market: MarketContext) -> float:
        return self.instrument.price(market)

    def market_value(self, market: MarketContext) -> float:
        """Signed market value: negative for shorts (a liability)."""
        return self.signed_qty * self.instrument.multiplier * self.unit_price(market)

    def cost_basis(self) -> float:
        return self.signed_qty * self.instrument.multiplier * self.entry_price

    def pnl(self, market: MarketContext) -> float:
        """Unrealised P&L vs entry price."""
        return self.signed_qty * self.instrument.multiplier * (
            self.unit_price(market) - self.entry_price
        )

    def greeks(self, market: MarketContext) -> dict:
        """Position-level Greeks (signed, scaled by size and multiplier)."""
        g = self.instrument.greeks(market)
        scale = self.signed_qty * self.instrument.multiplier
        return {k: g[k] * scale for k in GREEK_KEYS}
