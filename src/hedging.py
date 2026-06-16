"""
Hedging analytics — Delta / Gamma / Delta-Gamma hedge construction.

This module contains *pure* financial logic (no Streamlit). It reuses the
existing engine:

    * ``Position.greeks(ctx)`` already returns signed, multiplier-scaled Greeks
      (equities are share-equivalent with delta = 1; options are scaled by the
      contract multiplier of 100). Summing them per underlying therefore yields
      portfolio Greeks in consistent *share-equivalent* units.
    * ``BlackScholes`` provides per-share option Greeks for any hedge option.
    * ``MarketContext`` / ``Portfolio`` provide spots and repricing.

Unit conventions (made explicit in the UI):
    * Delta  : share-equivalent (number of underlying shares the book behaves like)
    * Gamma  : change in share-equivalent delta per +1.0 move in the underlying
    * Vega   : portfolio value change per +1 volatility point (0.01)
    * Theta  : portfolio value change per +1 calendar day

Sign logic (verified by unit tests):
    * Positive portfolio delta  -> SELL/SHORT the underlying to neutralise.
    * Negative portfolio delta  -> BUY the underlying.
    * Positive portfolio gamma  -> SHORT options (negative position gamma).
    * Negative portfolio gamma  -> BUY options (positive position gamma).

IMPORTANT: Greeks of *different underlyings are never mixed* into a single hedge
trade. All hedge calculations operate on one underlying at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List

import math

from .pricing.black_scholes import BlackScholes, BSResult
from .instruments import Option
from .instruments.base import GREEK_KEYS


# --------------------------------------------------------------------------- #
#  Per-underlying portfolio Greeks
# --------------------------------------------------------------------------- #
@dataclass
class UnderlyingGreeks:
    """Aggregate Greeks of all positions sharing one underlying."""
    underlying: str
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    market_value: float = 0.0
    spot: float = 0.0
    n_positions: int = 0
    has_options: bool = False


def compute_underlying_greeks(portfolio, ctx=None) -> Dict[str, UnderlyingGreeks]:
    """Group the book's Greeks by underlying.

    Only instruments with directional exposure (Equity, ETF, Future, Option)
    are included; Bonds and Cash carry no delta/gamma and are skipped.
    """
    ctx = ctx or portfolio.context()
    out: Dict[str, UnderlyingGreeks] = {}
    for p in portfolio.positions:
        if p.asset_class in ("Bond", "Cash"):
            continue
        u = p.instrument.underlying
        g = p.greeks(ctx)                       # signed, multiplier-scaled
        rec = out.get(u)
        if rec is None:
            rec = UnderlyingGreeks(underlying=u, spot=ctx.spot(u))
            out[u] = rec
        rec.delta += g["delta"]
        rec.gamma += g["gamma"]
        rec.vega += g["vega"]
        rec.theta += g["theta"]
        rec.rho += g["rho"]
        rec.market_value += p.market_value(ctx)
        rec.n_positions += 1
        if isinstance(p.instrument, Option):
            rec.has_options = True
    return out


def positions_for_underlying(portfolio, underlying: str) -> list:
    """Return the subset of positions belonging to one underlying."""
    return [p for p in portfolio.positions
            if p.asset_class not in ("Bond", "Cash")
            and p.instrument.underlying == underlying]


# --------------------------------------------------------------------------- #
#  Hedge option (the instrument used to neutralise gamma)
# --------------------------------------------------------------------------- #
@dataclass
class HedgeOption:
    """A candidate option used as a hedge instrument.

    Greeks are computed per share via Black-Scholes; ``*_per_contract`` apply
    the contract multiplier so they are directly comparable to the portfolio's
    share-equivalent Greeks.
    """
    kind: str
    strike: float
    expiry_years: float
    sigma: float
    spot: float
    rate: float
    dividend_yield: float = 0.0
    multiplier: float = 100.0
    label: str = ""

    def __post_init__(self):
        self._g: BSResult = BlackScholes.greeks(
            self.spot, self.strike, self.expiry_years, self.rate,
            self.sigma, self.dividend_yield, self.kind)

    # per-share Greeks
    @property
    def price_unit(self) -> float:
        return self._g.price

    @property
    def delta_unit(self) -> float:
        return self._g.delta

    @property
    def gamma_unit(self) -> float:
        return self._g.gamma

    @property
    def vega_unit(self) -> float:
        return self._g.vega

    @property
    def theta_unit(self) -> float:
        return self._g.theta

    # per-contract Greeks (share-equivalent, comparable to portfolio Greeks)
    @property
    def delta_per_contract(self) -> float:
        return self.delta_unit * self.multiplier

    @property
    def gamma_per_contract(self) -> float:
        return self.gamma_unit * self.multiplier

    @property
    def price_per_contract(self) -> float:
        return self.price_unit * self.multiplier

    def auto_label(self) -> str:
        if self.label:
            return self.label
        return (f"{self.kind.upper()} K={self.strike:g} "
                f"T={self.expiry_years*365:.0f}d IV={self.sigma:.0%}")


def hedge_option_from_position(opt: Option, spot: float, rate: float) -> HedgeOption:
    """Build a HedgeOption template from an existing Option position."""
    return HedgeOption(kind=opt.kind, strike=opt.strike,
                       expiry_years=opt.expiry_years, sigma=opt.sigma,
                       spot=spot, rate=rate, dividend_yield=opt.dividend_yield,
                       multiplier=opt.multiplier)


# --------------------------------------------------------------------------- #
#  Core hedge maths
# --------------------------------------------------------------------------- #
def delta_hedge_shares(delta_p: float, delta_per_unit: float = 1.0) -> float:
    """Shares of the underlying needed to neutralise ``delta_p``.

    N_S = -delta_P / delta_S, with delta_S = 1 for a share. Positive result =>
    buy; negative => sell/short.
    """
    if abs(delta_per_unit) < 1e-12:
        raise ValueError("Underlying delta per unit must be non-zero.")
    return -delta_p / delta_per_unit


def gamma_hedge_contracts(gamma_p: float, option: HedgeOption) -> float:
    """Option contracts needed to neutralise ``gamma_p``.

    N_H = -gamma_P / (gamma_H_unit * M_H).
    """
    gpc = option.gamma_per_contract
    if abs(gpc) < 1e-9:
        raise ValueError(
            "Hedge option gamma is ~0 (deep ITM/OTM or expired); "
            "choose an option closer to at-the-money.")
    return -gamma_p / gpc


def residual_after_option(delta_p: float, gamma_p: float, vega_p: float,
                          theta_p: float, n_contracts: float,
                          option: HedgeOption) -> dict:
    """Portfolio Greeks after adding ``n_contracts`` of the hedge option."""
    return {
        "delta": delta_p + n_contracts * option.delta_per_contract,
        "gamma": gamma_p + n_contracts * option.gamma_per_contract,
        "vega": vega_p + n_contracts * option.vega_unit * option.multiplier,
        "theta": theta_p + n_contracts * option.theta_unit * option.multiplier,
    }


# --------------------------------------------------------------------------- #
#  Rounding
# --------------------------------------------------------------------------- #
def round_quantity(x: float, method: str) -> float:
    """Round a trade quantity. ``method`` in {'theoretical','nearest',
    'floor','ceil'}. 'theoretical' keeps decimals."""
    if method == "theoretical":
        return x
    if method == "nearest":
        return float(round(x))
    if method == "floor":
        # round toward zero-aware floor: floor keeps the sign-consistent lower int
        return float(math.floor(x))
    if method == "ceil":
        return float(math.ceil(x))
    raise ValueError(f"Unknown rounding method: {method}")


# --------------------------------------------------------------------------- #
#  Hedge result containers
# --------------------------------------------------------------------------- #
@dataclass
class HedgeResult:
    mode: str
    underlying: str
    spot: float
    # exposures before
    delta_before: float
    gamma_before: float
    vega_before: float
    theta_before: float
    # the trades (decimal / theoretical)
    shares: float = 0.0
    contracts: float = 0.0
    option: Optional[HedgeOption] = None
    # intermediate (after option leg, for delta-gamma)
    delta_after_option: Optional[float] = None
    gamma_after_option: Optional[float] = None
    # residual after the full (rounded) hedge
    residual: dict = field(default_factory=dict)
    # cost breakdown
    cost: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def build_delta_hedge(ug: UnderlyingGreeks) -> HedgeResult:
    """Mode A — neutralise delta with the underlying only."""
    shares = delta_hedge_shares(ug.delta)
    res = HedgeResult(
        mode="Delta Hedge", underlying=ug.underlying, spot=ug.spot,
        delta_before=ug.delta, gamma_before=ug.gamma,
        vega_before=ug.vega, theta_before=ug.theta,
        shares=shares, contracts=0.0, option=None,
    )
    return res


def build_gamma_hedge(ug: UnderlyingGreeks, option: HedgeOption) -> HedgeResult:
    """Mode B — neutralise gamma with an option (delta will move)."""
    contracts = gamma_hedge_contracts(ug.gamma, option)
    after = residual_after_option(ug.delta, ug.gamma, ug.vega, ug.theta,
                                  contracts, option)
    res = HedgeResult(
        mode="Gamma Hedge", underlying=ug.underlying, spot=ug.spot,
        delta_before=ug.delta, gamma_before=ug.gamma,
        vega_before=ug.vega, theta_before=ug.theta,
        shares=0.0, contracts=contracts, option=option,
        delta_after_option=after["delta"], gamma_after_option=after["gamma"],
    )
    res.warnings.append(
        "Ein reiner Gamma-Hedge verändert das Delta: "
        f"{ug.delta:,.1f} -> {after['delta']:,.1f} (aktienäquivalent).")
    return res


def build_delta_gamma_hedge(ug: UnderlyingGreeks, option: HedgeOption) -> HedgeResult:
    """Mode C — two-step: neutralise gamma with options, then delta with shares."""
    contracts = gamma_hedge_contracts(ug.gamma, option)
    after = residual_after_option(ug.delta, ug.gamma, ug.vega, ug.theta,
                                  contracts, option)
    shares = delta_hedge_shares(after["delta"])     # neutralise leftover delta
    res = HedgeResult(
        mode="Delta-Gamma Hedge", underlying=ug.underlying, spot=ug.spot,
        delta_before=ug.delta, gamma_before=ug.gamma,
        vega_before=ug.vega, theta_before=ug.theta,
        shares=shares, contracts=contracts, option=option,
        delta_after_option=after["delta"], gamma_after_option=after["gamma"],
    )
    return res


# --------------------------------------------------------------------------- #
#  Apply rounding + compute residual Greeks and costs
# --------------------------------------------------------------------------- #
@dataclass
class TransactionCosts:
    fixed_per_order: float = 0.0
    per_contract: float = 0.0
    slippage_pct: float = 0.0      # as fraction, e.g. 0.0005 = 5 bps


def finalize_hedge(res: HedgeResult, rounding: str,
                   tc: TransactionCosts | None = None) -> HedgeResult:
    """Apply rounding to the trades and compute residual Greeks + costs."""
    tc = tc or TransactionCosts()
    shares = round_quantity(res.shares, rounding)
    contracts = round_quantity(res.contracts, rounding)
    res.shares = shares
    res.contracts = contracts

    # Residual Greeks after the *rounded* hedge.
    delta = res.delta_before + shares * 1.0
    gamma = res.gamma_before
    vega = res.vega_before
    theta = res.theta_before
    if res.option is not None:
        delta += contracts * res.option.delta_per_contract
        gamma += contracts * res.option.gamma_per_contract
        vega += contracts * res.option.vega_unit * res.option.multiplier
        theta += contracts * res.option.theta_unit * res.option.multiplier
    res.residual = {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}

    # --- cash flows (positive = inflow to the account) ---------------------
    shares_cf = -shares * res.spot                        # buy shares -> outflow
    option_cf = 0.0
    n_orders = 0
    traded_notional = abs(shares * res.spot)
    if shares != 0:
        n_orders += 1
    if res.option is not None and contracts != 0:
        option_cf = -contracts * res.option.price_per_contract
        traded_notional += abs(contracts * res.option.price_per_contract)
        n_orders += 1

    net_cf = shares_cf + option_cf
    txn = (tc.fixed_per_order * n_orders
           + tc.per_contract * abs(contracts)
           + tc.slippage_pct * traded_notional)

    res.cost = {
        "shares_cashflow": shares_cf,
        "option_cashflow": option_cf,
        "net_cashflow": net_cf,
        "transaction_costs": txn,
        "total_outlay": -net_cf + txn,     # cash needed (positive = you pay)
        "traded_notional": traded_notional,
        "n_orders": n_orders,
    }
    return res


# --------------------------------------------------------------------------- #
#  Rounding comparison table (floor / ceil / nearest)
# --------------------------------------------------------------------------- #
def hedge_error(residual: dict) -> float:
    """Combined hedge error |delta| + |gamma| (lower is better)."""
    return abs(residual.get("delta", 0.0)) + abs(residual.get("gamma", 0.0))


def rounding_alternatives(base: HedgeResult, tc: TransactionCosts | None = None
                          ) -> List[dict]:
    """Build a comparison across rounding methods for one hedge.

    Recomputes the *theoretical* trades first, then evaluates each rounding.
    """
    # Recover theoretical trades (re-run the mode maths on stored 'before').
    ug = UnderlyingGreeks(underlying=base.underlying, delta=base.delta_before,
                          gamma=base.gamma_before, vega=base.vega_before,
                          theta=base.theta_before, spot=base.spot,
                          has_options=base.option is not None)
    rows = []
    for method in ("theoretical", "nearest", "floor", "ceil"):
        if base.mode == "Delta Hedge":
            r = build_delta_hedge(ug)
        elif base.mode == "Gamma Hedge":
            r = build_gamma_hedge(ug, base.option)
        else:
            r = build_delta_gamma_hedge(ug, base.option)
        r = finalize_hedge(r, method, tc)
        rows.append({
            "Strategie": method,
            "Optionskontrakte": r.contracts,
            "Aktien": r.shares,
            "Rest-Delta": r.residual["delta"],
            "Rest-Gamma": r.residual["gamma"],
            "Hedge-Kosten": r.cost["total_outlay"],
            "_error": hedge_error(r.residual),
        })
    return rows


# --------------------------------------------------------------------------- #
#  Exposure & P&L profiles across underlying price (for charts / scenario)
# --------------------------------------------------------------------------- #
def exposure_profile(positions: list, portfolio, underlying: str,
                     spot_range, hedge: Optional[HedgeResult] = None):
    """Exact delta/gamma of this underlying across a range of spot prices.

    Re-prices the underlying's option positions at each spot (full revaluation
    of the Greeks, not an approximation). If ``hedge`` is given, the hedge
    shares (delta 1, gamma 0) and hedge option contracts are added.

    Returns dict with arrays: spot, delta_before, gamma_before,
    delta_after, gamma_after.
    """
    from .instruments.base import MarketContext

    base_spot = portfolio.context().spot(underlying)
    spots = list(spot_range)
    d_before, g_before, d_after, g_after = [], [], [], []

    for s in spots:
        ctx = MarketContext(spots={underlying: s}, rate=portfolio.rate)
        d = g = 0.0
        for p in positions:
            pg = p.greeks(ctx)
            d += pg["delta"]
            g += pg["gamma"]
        d_before.append(d)
        g_before.append(g)

        if hedge is not None:
            da, ga = d, g
            da += hedge.shares * 1.0
            if hedge.option is not None and hedge.contracts != 0:
                hg = BlackScholes.greeks(s, hedge.option.strike,
                                         hedge.option.expiry_years,
                                         hedge.option.rate, hedge.option.sigma,
                                         hedge.option.dividend_yield,
                                         hedge.option.kind)
                da += hedge.contracts * hg.delta * hedge.option.multiplier
                ga += hedge.contracts * hg.gamma * hedge.option.multiplier
            d_after.append(da)
            g_after.append(ga)

    return {
        "spot": spots, "base_spot": base_spot,
        "delta_before": d_before, "gamma_before": g_before,
        "delta_after": d_after, "gamma_after": g_after,
    }


def pnl_profile_greek(delta: float, gamma: float, base_spot: float, spot_range):
    """Local Greek-based P&L approximation: dV ~= delta*dS + 0.5*gamma*dS^2.

    Clearly an *approximation* (constant Greeks). Used to compare the P&L of the
    book before vs after the hedge.
    """
    out = []
    for s in spot_range:
        ds = s - base_spot
        out.append(delta * ds + 0.5 * gamma * ds * ds)
    return out
