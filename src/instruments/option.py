"""European option instrument (Black-Scholes priced)."""
from __future__ import annotations

from datetime import date

from .base import Instrument, MarketContext, GREEK_KEYS
from ..pricing.black_scholes import BlackScholes


class Option(Instrument):
    """A European call or put on an equity/ETF underlying.

    Parameters
    ----------
    underlying_symbol : ticker of the underlying (used for spot lookup)
    strike            : strike price
    expiry_years      : time to expiry in years (alternatively pass ``expiry``)
    sigma             : (implied) volatility used for valuation
    kind              : "call" or "put"
    dividend_yield    : continuous dividend yield of the underlying
    """

    asset_class = "Option"
    multiplier = 100.0            # standard equity-option contract = 100 shares

    def __init__(self, underlying_symbol: str, strike: float,
                 expiry_years: float, sigma: float, kind: str = "call",
                 dividend_yield: float = 0.0, contract_size: float = 100.0):
        symbol = f"{underlying_symbol} {kind[0].upper()}{strike:g} {expiry_years:.2f}y"
        super().__init__(symbol)
        self.underlying_symbol = underlying_symbol
        self.strike = strike
        self.expiry_years = max(expiry_years, 0.0)
        self.sigma = sigma
        self.kind = kind.lower()
        self.dividend_yield = dividend_yield
        self.multiplier = contract_size

    @property
    def underlying(self) -> str:
        return self.underlying_symbol

    # ------------------------------------------------------------------ #
    #  Effective inputs after applying any scenario shocks
    # ------------------------------------------------------------------ #
    def _inputs(self, market: MarketContext):
        S = market.spot(self.underlying_symbol)
        sigma = max(self.sigma + market.vol_shock, 1e-4)
        r = market.rate + market.rate_shock
        T = max(self.expiry_years - market.time_decay, 0.0)
        return S, sigma, r, T

    def price(self, market: MarketContext) -> float:
        S, sigma, r, T = self._inputs(market)
        return BlackScholes.price(S, self.strike, T, r, sigma,
                                  self.dividend_yield, self.kind)

    def greeks(self, market: MarketContext) -> dict:
        S, sigma, r, T = self._inputs(market)
        res = BlackScholes.greeks(S, self.strike, T, r, sigma,
                                  self.dividend_yield, self.kind)
        return {
            "delta": res.delta,
            "gamma": res.gamma,
            "vega": res.vega,
            "theta": res.theta,
            "rho": res.rho,
        }

    def implied_vol(self, market_price: float, market: MarketContext) -> float:
        S, _, r, T = self._inputs(market)
        return BlackScholes.implied_vol(market_price, S, self.strike, T, r,
                                        self.dividend_yield, self.kind)
