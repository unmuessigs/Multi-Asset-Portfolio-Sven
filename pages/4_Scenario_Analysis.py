"""Dashboard 4 — Scenario Analysis: stress the book across market shocks."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from src.ui import theme, charts
from src.ui.components import kpi_card, kpi_row, styled_table, fmt_money, fmt_num, fmt_pct
from src import state
from src.analytics.scenario import ScenarioEngine
from src.instruments.base import GREEK_KEYS

import pandas as pd


theme.apply_theme("ATLAS · Scenario")
theme.header("SCENARIO")
state.render_sidebar()

pf = state.get_portfolio()
risk = state.get_risk()

if pf.is_empty:
    from src.ui.components import empty_state
    empty_state("Keine Positionen für die Szenarioanalyse.")
    st.stop()

# --------------------------------------------------------------------------- #
#  Shock controls
# --------------------------------------------------------------------------- #
theme.section("Stress Parameters")
c1, c2, c3, c4 = st.columns(4)
spot_shock = c1.slider("Markt-Bewegung", -50, 50, 0, 1,
                       format="%d%%") / 100.0
vol_shock = c2.slider("Volatilität (Punkte)", -30, 30, 0, 1,
                      format="%d pts") / 100.0
rate_shock = c3.slider("Zinsänderung (bps)", -300, 300, 0, 5) / 10000.0
time_decay = c4.slider("Zeitablauf (Tage)", 0, 365, 0, 1) / 365.0

engine = ScenarioEngine(pf)
res = engine.run(spot_shock=spot_shock, vol_shock=vol_shock,
                 rate_shock=rate_shock, time_decay=time_decay)

# Approximate scenario VaR by scaling parametric VaR with gross exposure,
# which moves as options/bonds are repriced under the shock.
base_ctx = pf.context()
shock_ctx = pf.context(spot_shock=spot_shock, vol_shock=vol_shock,
                       rate_shock=rate_shock, time_decay=time_decay)
base_gross = pf.gross_exposure(base_ctx) or 1.0
scen_gross = pf.gross_exposure(shock_ctx)
m = risk.metrics()
scen_var = m.var_parametric * scen_gross / base_gross

# --------------------------------------------------------------------------- #
#  Headline KPIs
# --------------------------------------------------------------------------- #
theme.section("Scenario Outcome")
kpi_row([
    kpi_card("Base Value", fmt_money(res.base_value), "current", 0, "blue"),
    kpi_card("Scenario Value", fmt_money(res.new_value), "stressed",
             1 if res.pnl >= 0 else -1, "green" if res.pnl >= 0 else "red"),
    kpi_card("Scenario P&L", fmt_money(res.pnl), fmt_pct(res.pnl_pct),
             1 if res.pnl >= 0 else -1, "green" if res.pnl >= 0 else "red"),
    kpi_card("Base VaR (95%)", fmt_money(m.var_parametric), "1-day", -1, "red"),
    kpi_card("Scenario VaR", fmt_money(scen_var),
             fmt_pct((scen_var - m.var_parametric) / m.var_parametric * 100
                     if m.var_parametric else 0),
             -1, "red"),
], columns=5)

# --------------------------------------------------------------------------- #
#  Charts
# --------------------------------------------------------------------------- #
left, right = st.columns([1.3, 1])
with left:
    theme.section("Portfolio P&L vs Market Move")
    pct, vals, pnls = engine.spot_sweep(vol_shock=vol_shock, time_decay=time_decay)
    st.plotly_chart(charts.scenario_sweep(pct, pnls),
                    use_container_width=True, config={"displayModeBar": False})
with right:
    theme.section("Greeks: Base vs Scenario")
    st.plotly_chart(charts.greek_change_bar(res.base_greeks, res.new_greeks),
                    use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
#  Greek change table
# --------------------------------------------------------------------------- #
theme.section("Greek Changes")
gdf = pd.DataFrame({
    "Greek": [k.capitalize() for k in GREEK_KEYS],
    "Base": [res.base_greeks[k] for k in GREEK_KEYS],
    "Scenario": [res.new_greeks[k] for k in GREEK_KEYS],
    "Change": [res.greek_changes[k] for k in GREEK_KEYS],
})
styled_table(gdf, num_cols=["Base", "Scenario"], pnl_cols=["Change"])

# --------------------------------------------------------------------------- #
#  Preset scenarios
# --------------------------------------------------------------------------- #
theme.section("Preset Stress Tests")
presets = {
    "Equity -10% / Vol +5pts": dict(spot_shock=-0.10, vol_shock=0.05),
    "Equity +10%": dict(spot_shock=0.10),
    "Vol Spike +10pts": dict(vol_shock=0.10),
    "Rates +100bps": dict(rate_shock=0.01),
    "30 Days Decay": dict(time_decay=30 / 365),
    "Risk-Off (-15%, Vol+8, Rates-50bps)":
        dict(spot_shock=-0.15, vol_shock=0.08, rate_shock=-0.005),
}
rows = []
for name, kw in presets.items():
    r = engine.run(**kw)
    rows.append({"Scenario": name, "Value": r.new_value,
                 "P&L": r.pnl, "P&L %": r.pnl_pct})
styled_table(pd.DataFrame(rows), money_cols=["Value"],
             pnl_cols=["P&L"], pct_cols=["P&L %"])
