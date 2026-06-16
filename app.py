"""
ATLAS Terminal — main entry point (Dashboard 1: Portfolio Overview).

Run with:  streamlit run app.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from src.ui import theme, charts
from src.ui.components import kpi_card, kpi_row, styled_table, fmt_money, fmt_pct
from src import state


theme.apply_theme("ATLAS · Overview")
theme.header("LIVE" if st.session_state.get("use_live", True) else "SIM")
state.render_sidebar()

pf = state.get_portfolio()
risk = state.get_risk()

if pf.is_empty:
    from src.ui.components import empty_state
    empty_state("Noch keine Positionen. Lade das Demo-Portfolio oder "
                "nutze den Portfolio Builder.")
    st.stop()

# --------------------------------------------------------------------------- #
#  KPI strip
# --------------------------------------------------------------------------- #
ctx = pf.context()
value = pf.total_value(ctx)
daily = pf.daily_pnl()
total_ret = pf.total_return_pct(ctx)
metrics = risk.metrics()

daily_pct = (daily / value * 100) if value else 0.0
cards = [
    kpi_card("Portfolio Value", fmt_money(value), accent="blue"),
    kpi_card("Daily P&L", fmt_money(daily),
             fmt_pct(daily_pct), 1 if daily >= 0 else -1,
             accent="green" if daily >= 0 else "red"),
    kpi_card("Total Return", fmt_pct(total_ret),
             "vs cost basis", 1 if total_ret >= 0 else -1,
             accent="green" if total_ret >= 0 else "red"),
    kpi_card("Positions", str(len(pf)), accent="purple"),
    kpi_card("Volatility (ann.)", fmt_pct(metrics.volatility, plus=False),
             "realised", 0, accent="teal"),
    kpi_card("Gross Exposure", fmt_money(pf.gross_exposure(ctx)), accent=""),
]
kpi_row(cards, columns=6)

# --------------------------------------------------------------------------- #
#  Charts
# --------------------------------------------------------------------------- #
left, right = st.columns([1, 1.4])
with left:
    theme.section("Asset Allocation")
    st.plotly_chart(charts.allocation_donut(pf.allocation(ctx)),
                    use_container_width=True, config={"displayModeBar": False})
with right:
    theme.section("Portfolio Value · 1Y")
    st.plotly_chart(charts.value_over_time(pf.value_series("1y")),
                    use_container_width=True, config={"displayModeBar": False})

theme.section("Cumulative Performance")
st.plotly_chart(charts.performance_chart(pf.value_series("1y")),
                use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
#  Positions table
# --------------------------------------------------------------------------- #
theme.section("Positions")
tbl = pf.positions_table(ctx).drop(columns=["#"])
styled_table(
    tbl,
    money_cols=["Entry", "Price", "Mkt Value"],
    pnl_cols=["P&L"],
    pct_cols=["P&L %"],
    num_cols=["Qty"],
)
