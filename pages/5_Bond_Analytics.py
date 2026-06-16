"""Dashboard 5 — Bond Analytics: duration, convexity, YTM, rate sensitivity."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import streamlit as st

from src.ui import theme, charts
from src.ui.components import (kpi_card, kpi_row, styled_table, empty_state,
                               fmt_money, fmt_num, fmt_pct)
from src import state
from src.instruments import Bond
from src.pricing.bond_math import BondMath


theme.apply_theme("ATLAS · Bonds")
theme.header("FIXED INCOME")
state.render_sidebar()

pf = state.get_portfolio()

bond_positions = [p for p in pf.positions if isinstance(p.instrument, Bond)]
if not bond_positions:
    empty_state("Keine Anleihen im Portfolio. Füge Bonds im Portfolio Builder hinzu.")
    st.stop()

ctx = pf.context()

# --------------------------------------------------------------------------- #
#  Per-bond analytics
# --------------------------------------------------------------------------- #
rows = []
for p in bond_positions:
    b: Bond = p.instrument
    res = b.analytics(ctx)
    mv = p.market_value(ctx)
    rows.append({
        "Bond": b.symbol, "Qty": p.quantity, "Coupon": b.coupon_rate * 100,
        "Maturity": b.years, "Price": res.price, "Mkt Value": mv,
        "YTM": res.ytm * 100, "Current Yield": res.current_yield * 100,
        "Macaulay": res.macaulay_duration, "ModDur": res.modified_duration,
        "Convexity": res.convexity,
        "_ytm": res.ytm, "_moddur": res.modified_duration,
        "_conv": res.convexity, "_price": res.price,
    })
bdf = pd.DataFrame(rows)

# Portfolio-level value-weighted figures
total_mv = bdf["Mkt Value"].sum()
w = bdf["Mkt Value"] / total_mv if total_mv else bdf["Mkt Value"] * 0
port_moddur = float((w * bdf["ModDur"]).sum())
port_convex = float((w * bdf["Convexity"]).sum())
port_ytm = float((w * bdf["YTM"]).sum())

# --------------------------------------------------------------------------- #
#  KPI strip
# --------------------------------------------------------------------------- #
theme.section("Fixed-Income Summary")
kpi_row([
    kpi_card("Bond Mkt Value", fmt_money(total_mv), f"{len(bdf)} bonds", 0, "purple"),
    kpi_card("Avg YTM", fmt_pct(port_ytm, plus=False), "value-weighted", 0, "blue"),
    kpi_card("Port. Mod. Duration", fmt_num(port_moddur, 2), "years", 0, "teal"),
    kpi_card("Port. Convexity", fmt_num(port_convex, 2), "", 0, ""),
    kpi_card("DV01 (≈)", fmt_money(port_moddur * total_mv * 0.0001),
             "per 1bp", -1, "red"),
], columns=5)

# --------------------------------------------------------------------------- #
#  Charts
# --------------------------------------------------------------------------- #
left, right = st.columns([1.2, 1])
with left:
    theme.section("Yield Curve & Holdings")
    # Representative curve anchored on the risk-free rate (upward sloping).
    mats = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    base = pf.rate
    curve = [base + 0.004 * np.log1p(t) for t in mats]
    holdings = list(zip(bdf["Maturity"], bdf["_ytm"]))
    st.plotly_chart(charts.yield_curve(mats, curve, holdings),
                    use_container_width=True, config={"displayModeBar": False})
with right:
    theme.section("Duration Contribution")
    dc = pd.DataFrame({
        "Bond": bdf["Bond"],
        "DurationContribution": (w * bdf["ModDur"]).values,
    }).sort_values("DurationContribution", ascending=False)
    st.plotly_chart(charts.duration_contribution(dc),
                    use_container_width=True, config={"displayModeBar": False})

theme.section("Interest-Rate Sensitivity (Portfolio Bonds)")
# Second-order Taylor estimate across parallel yield shifts.
dy_bps = list(range(-150, 151, 25))
price_changes = []
for bps in dy_bps:
    dy = bps / 10000.0
    total = 0.0
    for _, rr in bdf.iterrows():
        # scale per-bond price change by quantity held
        qty = rr["Qty"]
        total += qty * BondMath.price_change(rr["_price"], rr["_moddur"],
                                             rr["_conv"], dy)
    price_changes.append(total)
st.plotly_chart(charts.rate_sensitivity(dy_bps, price_changes),
                use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
#  Detail table
# --------------------------------------------------------------------------- #
theme.section("Bond Detail")
display = bdf.drop(columns=[c for c in bdf.columns if c.startswith("_")])
styled_table(
    display,
    money_cols=["Price", "Mkt Value"],
    pct_cols=["Coupon", "YTM", "Current Yield"],
    num_cols=["Qty", "Maturity", "Macaulay", "ModDur", "Convexity"],
)
