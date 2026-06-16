"""
Scenario / stress-testing engine.

Re-values the entire portfolio under a set of market shocks without mutating
the underlying positions. Shocks are applied through the ``MarketContext``:

    * spot_shock : relative move in every underlying (e.g. +0.10 = +10 %)
    * vol_shock  : absolute change in option volatilities (vol points)
    * rate_shock : parallel shift in the risk-free rate / bond yields
    * time_decay : years of time decay applied to options (theta / roll-down)

The engine reports the new portfolio value, the change in value, and the change
in each aggregate Greek versus the base (unshocked) book.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..instruments.base import GREEK_KEYS


@dataclass
class ScenarioResult:
    base_value: float
    new_value: float
    pnl: float
    pnl_pct: float
    base_greeks: dict
    new_greeks: dict
    greek_changes: dict


class ScenarioEngine:
    def __init__(self, portfolio):
        self.pf = portfolio

    def run(self, spot_shock: float = 0.0, vol_shock: float = 0.0,
            rate_shock: float = 0.0, time_decay: float = 0.0) -> ScenarioResult:
        base_ctx = self.pf.context()
        shock_ctx = self.pf.context(
            spot_shock=spot_shock,
            vol_shock=vol_shock,
            rate_shock=rate_shock,
            time_decay=time_decay,
        )

        base_value = self.pf.total_value(base_ctx)
        new_value = self.pf.total_value(shock_ctx)
        pnl = new_value - base_value
        pnl_pct = (pnl / abs(base_value) * 100) if base_value else 0.0

        base_greeks = self.pf.portfolio_greeks(base_ctx)
        new_greeks = self.pf.portfolio_greeks(shock_ctx)
        changes = {k: new_greeks[k] - base_greeks[k] for k in GREEK_KEYS}

        return ScenarioResult(base_value, new_value, pnl, pnl_pct,
                              base_greeks, new_greeks, changes)

    # ------------------------------------------------------------------ #
    #  Sweep: portfolio value across a range of spot shocks (for charts)
    # ------------------------------------------------------------------ #
    def spot_sweep(self, lo: float = -0.30, hi: float = 0.30, n: int = 61,
                   vol_shock: float = 0.0, time_decay: float = 0.0):
        import numpy as np
        shocks = np.linspace(lo, hi, n)
        base = self.pf.total_value()
        values, pnls = [], []
        for s in shocks:
            ctx = self.pf.context(spot_shock=float(s), vol_shock=vol_shock,
                                   time_decay=time_decay)
            v = self.pf.total_value(ctx)
            values.append(v)
            pnls.append(v - base)
        return shocks * 100, np.array(values), np.array(pnls)
