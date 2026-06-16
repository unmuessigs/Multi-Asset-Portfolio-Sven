"""Dashboard 2 — Risk Analytics: portfolio Greeks, VaR/CVaR, Beta, Sharpe."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from src.ui import theme, charts
from src.ui.components import (kpi_card, kpi_row, styled_table, fmt_money,
                               fmt_num, fmt_pct)
from src import state
from src.instruments.base import GREEK_KEYS


theme.apply_theme("ATLAS · Risk")
theme.header("RISK")
state.render_sidebar()

pf = state.get_portfolio()
risk = state.get_risk()

if pf.is_empty:
    from src.ui.components import empty_state
    empty_state("Keine Positionen für die Risikoanalyse.")
    st.stop()

# --------------------------------------------------------------------------- #
#  Controls
# --------------------------------------------------------------------------- #
c1, c2, _ = st.columns([1, 1, 3])
conf = c1.selectbox("VaR Confidence", [0.90, 0.95, 0.99], index=1,
                    format_func=lambda x: f"{x:.0%}")
horizon = c2.selectbox("Horizon (days)", [1, 5, 10, 21], index=0)

m = risk.metrics(confidence=conf, horizon_days=horizon)
greeks = pf.portfolio_greeks()

# --------------------------------------------------------------------------- #
#  Greeks KPI strip
# --------------------------------------------------------------------------- #
theme.section("Portfolio Greeks")
gcards = [
    kpi_card("Delta", fmt_num(greeks["delta"], 1), "Δ spot exposure", 0, "blue"),
    kpi_card("Gamma", fmt_num(greeks["gamma"], 2), "Δ of delta", 0, "purple"),
    kpi_card("Vega", fmt_num(greeks["vega"], 1), "per 1 vol pt", 0, "teal"),
    kpi_card("Theta", fmt_num(greeks["theta"], 1), "per day",
             1 if greeks["theta"] >= 0 else -1,
             "green" if greeks["theta"] >= 0 else "red"),
    kpi_card("Rho", fmt_num(greeks["rho"], 1), "per 1 rate pt", 0, ""),
]
kpi_row(gcards, columns=5)

# --------------------------------------------------------------------------- #
#  Risk KPI strip
# --------------------------------------------------------------------------- #
theme.section(f"Risk Metrics · {conf:.0%} · {horizon}d")
rcards = [
    kpi_card(f"VaR (param)", fmt_money(m.var_parametric), "potential loss", -1, "red"),
    kpi_card(f"VaR (hist)", fmt_money(m.var_historical), "empirical", -1, "red"),
    kpi_card("Expected Shortfall", fmt_money(m.cvar), "CVaR tail", -1, "red"),
    kpi_card("Beta", fmt_num(m.beta, 2), "vs S&P 500", 0, "blue"),
    kpi_card("Sharpe", fmt_num(m.sharpe, 2), "risk-adjusted",
             1 if m.sharpe >= 0 else -1,
             "green" if m.sharpe >= 0 else "red"),
]
kpi_row(rcards, columns=5)

# --------------------------------------------------------------------------- #
#  Charts
# --------------------------------------------------------------------------- #
left, right = st.columns([1.3, 1])
with left:
    theme.section("Greeks Heatmap by Position")
    gt = pf.greeks_table()
    derivs = gt[gt[list(GREEK_KEYS)].abs().sum(axis=1) > 1e-9]
    if derivs.empty:
        st.info("Keine Positionen mit Greeks (Optionen/Bonds) im Portfolio.")
    else:
        st.plotly_chart(charts.greeks_heatmap(derivs, GREEK_KEYS),
                        use_container_width=True, config={"displayModeBar": False})
with right:
    theme.section("Aggregate Greeks")
    st.plotly_chart(charts.greeks_bar(greeks),
                    use_container_width=True, config={"displayModeBar": False})

left2, right2 = st.columns([1, 1])
with left2:
    theme.section("Risk Contribution by Position")
    rc = risk.risk_contributions()
    if rc.empty:
        st.info("Nicht genügend Historie für Risikobeiträge.")
    else:
        st.plotly_chart(charts.risk_contribution_bar(rc.head(12)),
                        use_container_width=True, config={"displayModeBar": False})
with right2:
    theme.section("VaR Distribution · 1Y Daily P&L")
    pnl, var, cvar = risk.var_distribution(confidence=conf)
    if len(pnl) == 0:
        st.info("Keine Verteilungsdaten verfügbar.")
    else:
        st.plotly_chart(charts.var_distribution(pnl, var, cvar),
                        use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
#  Detailed Greeks table
# --------------------------------------------------------------------------- #
theme.section("Position Greeks Detail")
styled_table(pf.greeks_table(), num_cols=list(GREEK_KEYS))
