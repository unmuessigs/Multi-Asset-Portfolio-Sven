"""
Portfolio: a collection of positions with aggregation and valuation.

The portfolio is the central object the dashboards talk to. It builds the
``MarketContext`` from the market-data provider, values every position, and
exposes book-level aggregates (value, P&L, allocation, Greeks) plus a
reconstructed historical value series.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from ..instruments.base import Position, MarketContext, GREEK_KEYS
from ..data.market_data import MarketData
from .. import config


class Portfolio:
    def __init__(self, market: MarketData, rate: float = config.RISK_FREE_RATE):
        self.market = market
        self.rate = rate
        self.positions: List[Position] = []

    # ------------------------------------------------------------------ #
    #  Mutation
    # ------------------------------------------------------------------ #
    def add(self, position: Position) -> None:
        self.positions.append(position)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.positions):
            self.positions.pop(index)

    def clear(self) -> None:
        self.positions.clear()

    def __len__(self) -> int:
        return len(self.positions)

    @property
    def is_empty(self) -> bool:
        return len(self.positions) == 0

    # ------------------------------------------------------------------ #
    #  Market context
    # ------------------------------------------------------------------ #
    def underlyings(self) -> set:
        return {p.instrument.underlying for p in self.positions
                if p.asset_class not in ("Bond", "Cash")}

    def context(self, **shocks) -> MarketContext:
        """Build a MarketContext with current spots, optionally shocked."""
        spots = self.market.spot_map(self.underlyings())
        return MarketContext(spots=spots, rate=self.rate, **shocks)

    # ------------------------------------------------------------------ #
    #  Valuation aggregates
    # ------------------------------------------------------------------ #
    def total_value(self, ctx: Optional[MarketContext] = None) -> float:
        ctx = ctx or self.context()
        return sum(p.market_value(ctx) for p in self.positions)

    def gross_exposure(self, ctx: Optional[MarketContext] = None) -> float:
        ctx = ctx or self.context()
        return sum(abs(p.market_value(ctx)) for p in self.positions)

    def total_pnl(self, ctx: Optional[MarketContext] = None) -> float:
        ctx = ctx or self.context()
        return sum(p.pnl(ctx) for p in self.positions)

    def total_cost(self) -> float:
        return sum(p.cost_basis() for p in self.positions)

    def total_return_pct(self, ctx: Optional[MarketContext] = None) -> float:
        cost = self.total_cost()
        if cost == 0:
            return 0.0
        return self.total_pnl(ctx) / abs(cost) * 100.0

    def daily_pnl(self) -> float:
        """Approximate 1-day P&L using each underlying's previous close.

        Linear instruments use the price change directly; options are repriced
        with Black-Scholes at the previous spot (vol/time held constant), which
        captures the dominant delta/gamma effect for a one-day move.
        """
        ctx_now = self.context()
        prev_spots = {s: self.market.previous_close(s) for s in self.underlyings()}
        ctx_prev = MarketContext(spots=prev_spots, rate=self.rate)
        return sum(p.market_value(ctx_now) - p.market_value(ctx_prev)
                   for p in self.positions)

    # ------------------------------------------------------------------ #
    #  Allocation & positions table
    # ------------------------------------------------------------------ #
    def allocation(self, ctx: Optional[MarketContext] = None) -> pd.DataFrame:
        """Gross-exposure allocation by asset class."""
        ctx = ctx or self.context()
        rows = {}
        for p in self.positions:
            rows.setdefault(p.asset_class, 0.0)
            rows[p.asset_class] += abs(p.market_value(ctx))
        df = pd.DataFrame({"Asset Class": list(rows.keys()),
                           "Exposure": list(rows.values())})
        total = df["Exposure"].sum()
        df["Weight"] = df["Exposure"] / total * 100 if total else 0.0
        return df.sort_values("Exposure", ascending=False).reset_index(drop=True)

    def positions_table(self, ctx: Optional[MarketContext] = None) -> pd.DataFrame:
        ctx = ctx or self.context()
        rows = []
        for i, p in enumerate(self.positions):
            mv = p.market_value(ctx)
            rows.append({
                "#": i,
                "Position": p.name,
                "Class": p.asset_class,
                "Side": "LONG" if p.direction > 0 else "SHORT",
                "Qty": p.quantity,
                "Entry": p.entry_price,
                "Price": p.unit_price(ctx),
                "Mkt Value": mv,
                "P&L": p.pnl(ctx),
                "P&L %": (p.pnl(ctx) / abs(p.cost_basis()) * 100
                          if p.cost_basis() else 0.0),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    #  Greeks aggregation
    # ------------------------------------------------------------------ #
    def portfolio_greeks(self, ctx: Optional[MarketContext] = None) -> dict:
        ctx = ctx or self.context()
        agg = {k: 0.0 for k in GREEK_KEYS}
        for p in self.positions:
            g = p.greeks(ctx)
            for k in GREEK_KEYS:
                agg[k] += g[k]
        return agg

    def greeks_table(self, ctx: Optional[MarketContext] = None) -> pd.DataFrame:
        ctx = ctx or self.context()
        rows = []
        for p in self.positions:
            g = p.greeks(ctx)
            rows.append({"Position": p.name, "Class": p.asset_class, **g})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    #  Historical portfolio value (reconstructed)
    # ------------------------------------------------------------------ #
    def value_series(self, period: str = "1y") -> pd.Series:
        """Reconstruct portfolio value over time.

        Each underlying's historical close is used to reprice positions on every
        date (options via Black-Scholes at the historical spot, with current vol
        and time-to-expiry held constant — an approximation that isolates the
        directional contribution). Bonds and cash are held at current value.
        """
        underlyings = self.underlyings()
        if not underlyings:
            # Only bonds / cash: value is effectively constant.
            today = pd.Timestamp.today().normalize()
            idx = pd.bdate_range(end=today, periods=252)
            return pd.Series(self.total_value(), index=idx)

        # Align all underlying histories on a common date index.
        hist = {}
        for s in underlyings:
            hist[s] = self.market.history(s, period)["Close"]
        prices = pd.DataFrame(hist).dropna()

        static_value = sum(
            p.market_value(self.context())
            for p in self.positions
            if p.asset_class in ("Bond", "Cash")
        )

        values = []
        for ts, row in prices.iterrows():
            ctx = MarketContext(spots=row.to_dict(), rate=self.rate)
            v = static_value
            for p in self.positions:
                if p.asset_class not in ("Bond", "Cash"):
                    v += p.market_value(ctx)
            values.append(v)
        return pd.Series(values, index=prices.index)

    def position_value_frame(self, period: str = "1y") -> pd.DataFrame:
        """Historical market value per position (columns = position names).

        Used by the risk engine to compute a covariance matrix and per-position
        risk contributions. Same repricing approach as ``value_series``.
        """
        underlyings = self.underlyings()
        cols = {}
        if underlyings:
            hist = {s: self.market.history(s, period)["Close"] for s in underlyings}
            prices = pd.DataFrame(hist).dropna()
            index = prices.index
        else:
            index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=252)
            prices = None

        for i, p in enumerate(self.positions):
            name = f"{i}:{p.name}"
            if p.asset_class in ("Bond", "Cash") or prices is None:
                cols[name] = pd.Series(p.market_value(self.context()), index=index)
            else:
                series = []
                for ts, row in prices.iterrows():
                    ctx = MarketContext(spots=row.to_dict(), rate=self.rate)
                    series.append(p.market_value(ctx))
                cols[name] = pd.Series(series, index=index)
        return pd.DataFrame(cols)

    # ------------------------------------------------------------------ #
    #  Portfolio daily returns (for risk metrics)
    # ------------------------------------------------------------------ #
    def return_series(self, period: str = "1y") -> pd.Series:
        vs = self.value_series(period)
        return vs.pct_change().dropna()

    def has_synthetic_data(self) -> bool:
        return any(self.market.is_synthetic(s) for s in self.underlyings())
