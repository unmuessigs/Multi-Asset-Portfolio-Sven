"""Dashboard 3 — Options Analytics: Black-Scholes pricing, Greeks & surfaces."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import streamlit as st

from src.ui import theme, charts
from src.ui.components import kpi_card, kpi_row, fmt_money, fmt_num, fmt_pct
from src import state, config
from src.pricing.black_scholes import BlackScholes
from src.instruments import Option


theme.apply_theme("ATLAS · Options")
theme.header("OPTIONS")
state.render_sidebar()

pf = state.get_portfolio()

# --------------------------------------------------------------------------- #
#  Option selector: existing position or custom
# --------------------------------------------------------------------------- #
option_positions = [(i, p) for i, p in enumerate(pf.positions)
                    if isinstance(p.instrument, Option)]
choices = ["✏ Custom Option"] + [f"{p.name}" for _, p in option_positions]
pick = st.selectbox("Option", choices)

if pick != "✏ Custom Option":
    pos = option_positions[choices.index(pick) - 1][1]
    opt: Option = pos.instrument
    S0 = pf.market.spot(opt.underlying_symbol)
    defaults = dict(S=S0, K=opt.strike, T=opt.expiry_years,
                    sigma=opt.sigma, kind=opt.kind)
else:
    defaults = dict(S=100.0, K=100.0, T=0.25, sigma=0.25, kind="call")

c1, c2, c3, c4, c5 = st.columns(5)
S = c1.number_input("Spot (S)", value=float(round(defaults["S"], 2)), min_value=0.01)
K = c2.number_input("Strike (K)", value=float(round(defaults["K"], 2)), min_value=0.01)
T = c3.number_input("Maturity (yrs)", value=float(round(defaults["T"], 3)),
                    min_value=0.0, step=0.05, format="%.3f")
sigma = c4.number_input("Volatility σ", value=float(round(defaults["sigma"], 3)),
                        min_value=0.001, step=0.01, format="%.3f")
kind = c5.selectbox("Type", ["call", "put"],
                    index=0 if defaults["kind"] == "call" else 1)
r = pf.rate

# --------------------------------------------------------------------------- #
#  Black-Scholes valuation + Greeks
# --------------------------------------------------------------------------- #
res = BlackScholes.greeks(S, K, T, r, sigma, kind=kind)

theme.section("Black-Scholes Valuation")
kpi_row([
    kpi_card("BS Price", fmt_money(res.price, 2), f"{kind.upper()}", 0, "blue"),
    kpi_card("Delta", fmt_num(res.delta, 4), "∂V/∂S", 0, "blue"),
    kpi_card("Gamma", fmt_num(res.gamma, 4), "∂²V/∂S²", 0, "purple"),
    kpi_card("Vega", fmt_num(res.vega, 4), "per 1 vol pt", 0, "teal"),
    kpi_card("Theta", fmt_num(res.theta, 4), "per day",
             1 if res.theta >= 0 else -1, "green" if res.theta >= 0 else "red"),
    kpi_card("Rho", fmt_num(res.rho, 4), "per 1 rate pt", 0, ""),
], columns=6)

# Implied vol from an observed market price
mkt_price = st.number_input("Observed market price (für Implied Vol)",
                            value=float(round(res.price, 2)), min_value=0.0,
                            step=0.05, format="%.2f")
iv = BlackScholes.implied_vol(mkt_price, S, K, T, r, kind=kind)
iv_txt = fmt_pct(iv * 100, plus=False) if iv == iv else "—"
st.markdown(f'<span class="pill">Implied Volatility: <b>{iv_txt}</b></span>',
            unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
#  Payoff & P&L
# --------------------------------------------------------------------------- #
grid = np.linspace(max(0.01, S * 0.5), S * 1.5, 120)
premium = res.price
if kind == "call":
    intrinsic = np.maximum(grid - K, 0.0)
else:
    intrinsic = np.maximum(K - grid, 0.0)
payoff_expiry = intrinsic - premium
value_now = BlackScholes.price_vector(grid, K, T, r, sigma, kind=kind) - premium

left, right = st.columns(2)
with left:
    theme.section("Payoff & Current Value")
    st.plotly_chart(charts.payoff_diagram(grid, payoff_expiry, value_now, spot=S),
                    use_container_width=True, config={"displayModeBar": False})
with right:
    theme.section("Volatility Sensitivity")
    vols = np.linspace(0.05, 0.80, 80)
    prices_vol = [BlackScholes.price(S, K, T, r, v, kind=kind) for v in vols]
    st.plotly_chart(
        charts.sensitivity_curve(vols * 100, prices_vol, "Volatility (%)",
                                 "Option Price", color=config.COLORS["teal"]),
        use_container_width=True, config={"displayModeBar": False})

left2, right2 = st.columns(2)
with left2:
    theme.section("Time Decay (Theta)")
    times = np.linspace(max(T, 0.001), 0.001, 80)
    prices_t = [BlackScholes.price(S, K, t, r, sigma, kind=kind) for t in times]
    st.plotly_chart(
        charts.sensitivity_curve(times * 365, prices_t, "Days to Expiry",
                                 "Option Price", color=config.COLORS["accent"]),
        use_container_width=True, config={"displayModeBar": False})
with right2:
    theme.section("Delta vs Spot")
    deltas = [BlackScholes.greeks(s, K, T, r, sigma, kind=kind).delta for s in grid]
    st.plotly_chart(
        charts.sensitivity_curve(grid, deltas, "Spot", "Delta",
                                 color=config.COLORS["accent_2"]),
        use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
#  Greeks surface
# --------------------------------------------------------------------------- #
theme.section("Greeks Surface · Delta over Spot × Time")
surf_greek = st.selectbox("Surface metric", ["delta", "gamma", "vega", "theta"])
spot_axis = np.linspace(S * 0.6, S * 1.4, 35)
time_axis = np.linspace(0.01, max(T, 0.05) * 1.5, 35)
Z = np.zeros((len(time_axis), len(spot_axis)))
for i, t in enumerate(time_axis):
    for j, s in enumerate(spot_axis):
        g = BlackScholes.greeks(s, K, t, r, sigma, kind=kind)
        Z[i, j] = getattr(g, surf_greek)
st.plotly_chart(
    charts.greeks_surface(spot_axis, time_axis, Z, "Spot", "Time (yrs)",
                          surf_greek.capitalize()),
    use_container_width=True, config={"displayModeBar": False})
