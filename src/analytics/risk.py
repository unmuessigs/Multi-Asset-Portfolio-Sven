"""
Portfolio risk analytics: VaR, Expected Shortfall, Beta, Sharpe, volatility
and per-position risk contributions.

Methods
-------
Parametric (variance-covariance) VaR assumes normally distributed returns:

    VaR(alpha, h) = z_alpha * sigma_daily * sqrt(h) * PortfolioValue

Historical VaR uses the empirical alpha-quantile of the reconstructed daily
P&L distribution (no distributional assumption).

Expected Shortfall / CVaR is the mean loss conditional on breaching the VaR
threshold — a coherent, tail-aware risk measure.

Beta is the slope of portfolio returns regressed on benchmark returns
(cov / var). Sharpe is the annualised excess-return-to-volatility ratio.

Risk contributions decompose total portfolio variance into per-position
components: contribution_i = (Sigma w)_i / (w' Sigma w), computed from the
covariance matrix of position-level P&L.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from .. import config


@dataclass
class RiskMetrics:
    value: float
    volatility: float          # annualised, %
    var_parametric: float      # currency, positive = potential loss
    var_historical: float
    cvar: float
    beta: float
    sharpe: float
    confidence: float
    horizon_days: int


class RiskAnalytics:
    def __init__(self, portfolio, benchmark_returns: pd.Series | None = None):
        self.pf = portfolio
        self.benchmark_returns = benchmark_returns

    # ------------------------------------------------------------------ #
    #  Core metrics
    # ------------------------------------------------------------------ #
    def metrics(self, confidence: float = config.DEFAULT_VAR_CONFIDENCE,
                horizon_days: int = 1, period: str = "1y") -> RiskMetrics:
        value = self.pf.total_value()
        rets = self.pf.return_series(period)

        if len(rets) < 5:
            return RiskMetrics(value, 0, 0, 0, 0, 0, 0, confidence, horizon_days)

        sigma_daily = float(rets.std())
        vol_annual = sigma_daily * np.sqrt(config.TRADING_DAYS) * 100

        z = norm.ppf(confidence)
        gross = self.pf.gross_exposure()

        # Parametric VaR scaled by gross exposure and holding horizon.
        var_param = z * sigma_daily * np.sqrt(horizon_days) * gross

        # Historical VaR / CVaR from the empirical P&L distribution.
        pnl = rets * gross * np.sqrt(horizon_days)
        var_hist = -np.percentile(pnl, (1 - confidence) * 100)
        tail = pnl[pnl <= -var_hist]
        cvar = -tail.mean() if len(tail) else var_hist

        beta = self._beta(rets)
        sharpe = self._sharpe(rets)

        return RiskMetrics(value, vol_annual, max(var_param, 0), max(var_hist, 0),
                           max(cvar, 0), beta, sharpe, confidence, horizon_days)

    def _beta(self, rets: pd.Series) -> float:
        if self.benchmark_returns is None:
            return float("nan")
        df = pd.concat([rets, self.benchmark_returns], axis=1).dropna()
        if len(df) < 5:
            return float("nan")
        cov = np.cov(df.iloc[:, 0], df.iloc[:, 1])
        var_m = cov[1, 1]
        return float(cov[0, 1] / var_m) if var_m else float("nan")

    def _sharpe(self, rets: pd.Series) -> float:
        rf_daily = config.RISK_FREE_RATE / config.TRADING_DAYS
        excess = rets - rf_daily
        if rets.std() == 0:
            return 0.0
        return float(excess.mean() / rets.std() * np.sqrt(config.TRADING_DAYS))

    # ------------------------------------------------------------------ #
    #  VaR distribution data (for the histogram chart)
    # ------------------------------------------------------------------ #
    def var_distribution(self, confidence: float = config.DEFAULT_VAR_CONFIDENCE,
                         period: str = "1y") -> tuple[np.ndarray, float, float]:
        rets = self.pf.return_series(period)
        gross = self.pf.gross_exposure()
        pnl = (rets * gross).values
        if len(pnl) == 0:
            return np.array([]), 0.0, 0.0
        var = -np.percentile(pnl, (1 - confidence) * 100)
        tail = pnl[pnl <= -var]
        cvar = -tail.mean() if len(tail) else var
        return pnl, var, cvar

    # ------------------------------------------------------------------ #
    #  Per-position risk contributions
    # ------------------------------------------------------------------ #
    def risk_contributions(self, period: str = "1y") -> pd.DataFrame:
        vf = self.pf.position_value_frame(period)
        pnl = vf.diff().dropna()
        if pnl.empty or pnl.shape[1] == 0:
            return pd.DataFrame(columns=["Position", "Contribution", "Pct"])

        cov = pnl.cov().values
        # Equal-unit weights: positions already in currency P&L terms, so the
        # marginal contribution to variance is simply the row-sum of cov.
        ones = np.ones(cov.shape[0])
        total_var = ones @ cov @ ones
        contrib = cov @ ones                      # marginal contributions
        pct = contrib / total_var * 100 if total_var else contrib * 0

        names = [c.split(":", 1)[1] for c in vf.columns]
        df = pd.DataFrame({"Position": names,
                           "Contribution": contrib,
                           "Pct": pct})
        return df.sort_values("Pct", ascending=False).reset_index(drop=True)
