"""
Hedge optimizer — pick a tradable hedge (underlying + one option) that
minimises a weighted objective:

    J = w_delta * delta_res^2 + w_gamma * gamma_res^2
        + w_cost * |total_outlay| + w_trades * n_legs

A transparent *discrete search* is used: for each candidate option we evaluate a
small window of integer contract counts around the gamma-neutral solution, and
for each we pick the integer share count that best neutralises the residual
delta. This is robust, dependency-light (no solver required) and easy to audit.

All inputs are share-equivalent Greeks for a single underlying — Greeks of
different underlyings are never combined here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import math

from .hedging import (HedgeOption, TransactionCosts, UnderlyingGreeks,
                      build_delta_gamma_hedge, finalize_hedge)


# Priority presets -> (w_delta, w_gamma, w_cost, w_trades)
PRIORITY_WEIGHTS = {
    "Ausgewogener Hedge": (1.0, 1.0, 1e-6, 0.0),
    "Möglichst neutrales Delta": (10.0, 1.0, 1e-6, 0.0),
    "Möglichst neutrales Gamma": (1.0, 10.0, 1e-6, 0.0),
    "Minimale Hedge-Kosten": (1.0, 1.0, 1e-3, 0.0),
    "Möglichst wenige Transaktionen": (1.0, 1.0, 1e-6, 5.0),
}


@dataclass
class OptimizedHedge:
    option: HedgeOption
    contracts: int
    shares: int
    residual: dict
    cost: dict
    objective: float
    n_legs: int


def _evaluate(ug: UnderlyingGreeks, option: HedgeOption, n_contracts: int,
              weights, tc: TransactionCosts) -> OptimizedHedge:
    """Score one (option, integer contracts) combination."""
    w_d, w_g, w_c, w_t = weights

    delta_temp = ug.delta + n_contracts * option.delta_per_contract
    shares = int(round(-delta_temp))            # best integer delta neutraliser

    delta_res = ug.delta + shares + n_contracts * option.delta_per_contract
    gamma_res = ug.gamma + n_contracts * option.gamma_per_contract
    vega_res = ug.vega + n_contracts * option.vega_unit * option.multiplier
    theta_res = ug.theta + n_contracts * option.theta_unit * option.multiplier

    # cost
    shares_cf = -shares * ug.spot
    option_cf = -n_contracts * option.price_per_contract
    traded = abs(shares * ug.spot) + abs(n_contracts * option.price_per_contract)
    n_legs = (1 if shares != 0 else 0) + (1 if n_contracts != 0 else 0)
    txn = (tc.fixed_per_order * n_legs + tc.per_contract * abs(n_contracts)
           + tc.slippage_pct * traded)
    total_outlay = -(shares_cf + option_cf) + txn

    objective = (w_d * delta_res ** 2 + w_g * gamma_res ** 2
                 + w_c * abs(total_outlay) + w_t * n_legs)

    return OptimizedHedge(
        option=option, contracts=n_contracts, shares=shares,
        residual={"delta": delta_res, "gamma": gamma_res,
                  "vega": vega_res, "theta": theta_res},
        cost={"shares_cashflow": shares_cf, "option_cashflow": option_cf,
              "net_cashflow": shares_cf + option_cf,
              "transaction_costs": txn, "total_outlay": total_outlay,
              "traded_notional": traded, "n_orders": n_legs},
        objective=objective, n_legs=n_legs,
    )


def optimize_hedge(ug: UnderlyingGreeks, candidates: List[HedgeOption],
                   priority: str = "Ausgewogener Hedge",
                   tc: Optional[TransactionCosts] = None,
                   window: int = 3) -> Optional[OptimizedHedge]:
    """Return the best hedge across all candidate options.

    For each candidate, the gamma-neutral contract count is computed and a small
    integer window around it is searched. Returns ``None`` if no candidate has
    usable gamma.
    """
    tc = tc or TransactionCosts()
    weights = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["Ausgewogener Hedge"])

    best: Optional[OptimizedHedge] = None
    for option in candidates:
        gpc = option.gamma_per_contract
        if abs(gpc) < 1e-9:
            continue                            # unusable hedge instrument
        n_theory = -ug.gamma / gpc
        lo = int(math.floor(n_theory)) - window
        hi = int(math.ceil(n_theory)) + window
        for n in range(lo, hi + 1):
            cand = _evaluate(ug, option, n, weights, tc)
            if best is None or cand.objective < best.objective:
                best = cand
    return best


def rank_candidates(ug: UnderlyingGreeks, candidates: List[HedgeOption],
                    priority: str = "Ausgewogener Hedge",
                    tc: Optional[TransactionCosts] = None) -> List[OptimizedHedge]:
    """Return the best integer solution per candidate option, ranked."""
    tc = tc or TransactionCosts()
    weights = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["Ausgewogener Hedge"])
    results = []
    for option in candidates:
        gpc = option.gamma_per_contract
        if abs(gpc) < 1e-9:
            continue
        n_theory = -ug.gamma / gpc
        local_best = None
        for n in range(int(math.floor(n_theory)) - 3,
                       int(math.ceil(n_theory)) + 4):
            cand = _evaluate(ug, option, n, weights, tc)
            if local_best is None or cand.objective < local_best.objective:
                local_best = cand
        if local_best:
            results.append(local_best)
    results.sort(key=lambda r: r.objective)
    return results
