"""
Dashboard 7 - Hedging Analytics.

Suggests concrete Delta / Gamma / Delta-Gamma hedge trades for the existing
portfolio, per underlying. Presentation + interaction only; all financial logic
lives in src/hedging.py and src/hedge_optimizer.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import streamlit as st

from src.ui import theme, hedge_charts
from src.ui.components import (kpi_card, kpi_row, styled_table, empty_state,
                               fmt_money, fmt_num, fmt_pct)
from src import state, config
from src.instruments import Option
from src import hedging
from src.hedging import (HedgeOption, TransactionCosts, hedge_option_from_position,
                         build_delta_hedge, build_gamma_hedge,
                         build_delta_gamma_hedge, finalize_hedge,
                         rounding_alternatives, hedge_error,
                         exposure_profile, pnl_profile_greek, UnderlyingGreeks)
from src.hedge_optimizer import (optimize_hedge, rank_candidates,
                                 PRIORITY_WEIGHTS)


theme.apply_theme("ATLAS - Hedging")
theme.header("HEDGING")
state.render_sidebar()

pf = state.get_portfolio()

if pf.is_empty:
    empty_state("Kein Portfolio vorhanden. Lade das Demo oder baue ein Portfolio "
                "im Portfolio Builder.")
    st.stop()

ctx = pf.context()
ug_map = hedging.compute_underlying_greeks(pf, ctx)

if not ug_map:
    empty_state("Das Portfolio enthaelt keine Positionen mit Delta/Gamma-Exposure "
                "(nur Bonds/Cash). Fuege Aktien, ETFs, Futures oder Optionen hinzu.")
    st.stop()

# --------------------------------------------------------------------------- #
#  Top: portfolio exposure KPIs + unit legend
# --------------------------------------------------------------------------- #
agg = pf.portfolio_greeks(ctx)
kpi_row([
    kpi_card("Portfolio Delta", fmt_num(agg["delta"], 1), "aktienaequiv.", 0, "blue"),
    kpi_card("Portfolio Gamma", fmt_num(agg["gamma"], 2), "pro 1.0 Move", 0, "purple"),
    kpi_card("Portfolio Vega", fmt_num(agg["vega"], 1), "pro 1 Vol-Pkt", 0, "teal"),
    kpi_card("Portfolio Theta", fmt_num(agg["theta"], 1), "pro Tag",
             1 if agg["theta"] >= 0 else -1, "green" if agg["theta"] >= 0 else "red"),
    kpi_card("Underlyings", str(len(ug_map)), "mit Exposure", 0, ""),
    kpi_card("Net Asset Value", fmt_money(pf.total_value(ctx)), "NAV", 0, "blue"),
], columns=6)

st.caption("Einheiten: **Delta** = aktienaequivalent (Anzahl Underlying-Einheiten) - "
           "**Gamma** = Aenderung des Delta pro +1.0 Kursbewegung - "
           "**Vega** = Wertaenderung pro +1 Volatilitaetspunkt (0.01) - "
           "**Theta** = Wertaenderung pro +1 Kalendertag.")

# Per-underlying table (Greeks are NOT mixed across underlyings)
theme.section("Exposure je Underlying")
ug_rows = [{
    "Underlying": u.underlying, "Spot": u.spot, "Delta": u.delta,
    "Gamma": u.gamma, "Vega": u.vega, "Theta": u.theta,
    "Mkt Value": u.market_value, "Optionen": "Ja" if u.has_options else "Nein",
    "Positionen": u.n_positions,
} for u in ug_map.values()]
styled_table(pd.DataFrame(ug_rows), money_cols=["Spot", "Mkt Value"],
             num_cols=["Delta", "Gamma", "Vega", "Theta"])

# --------------------------------------------------------------------------- #
#  Hedge configuration
# --------------------------------------------------------------------------- #
theme.section("Hedge-Konfiguration")
cfg1, cfg2, cfg3 = st.columns(3)
underlying = cfg1.selectbox("Underlying", list(ug_map.keys()))
mode = cfg2.selectbox("Hedge-Modus",
                      ["Delta Hedge", "Gamma Hedge", "Delta-Gamma Hedge"])
rounding = cfg3.selectbox("Rundung",
                          ["nearest", "floor", "ceil", "theoretical"],
                          format_func={"nearest": "Naechste ganze Zahl",
                                       "floor": "Abrunden", "ceil": "Aufrunden",
                                       "theoretical": "Theoretisch (Dezimal)"}.get)

ug = ug_map[underlying]
needs_option = mode in ("Gamma Hedge", "Delta-Gamma Hedge")

# Transaction costs
with st.expander("Transaktionskosten (optional)"):
    t1, t2, t3 = st.columns(3)
    fixed = t1.number_input("Fix pro Order ($)", value=0.0, min_value=0.0, step=1.0)
    per_ct = t2.number_input("Pro Optionskontrakt ($)", value=0.0,
                             min_value=0.0, step=0.1)
    slip = t3.number_input("Slippage / Bid-Ask (%)", value=0.0, min_value=0.0,
                           step=0.01, format="%.3f") / 100.0
tc = TransactionCosts(fixed_per_order=fixed, per_contract=per_ct, slippage_pct=slip)

# --------------------------------------------------------------------------- #
#  Hedge-instrument selection (for Gamma / Delta-Gamma)
# --------------------------------------------------------------------------- #
hedge_option = None
use_optimizer = False
priority = "Ausgewogener Hedge"
candidates = []

if needs_option:
    existing_opts = [p.instrument for p in hedging.positions_for_underlying(pf, underlying)
                     if isinstance(p.instrument, Option)]
    source_choices = ["Manuell"]
    if existing_opts:
        source_choices.append("Bestehende Option als Vorlage")
    source_choices.append("Auto-Optimierung")
    src_sel = st.radio("Hedge-Instrument", source_choices, horizontal=True)

    spot_default = float(round(ug.spot, 2))
    if src_sel == "Bestehende Option als Vorlage":
        names = [o.symbol for o in existing_opts]
        pick = st.selectbox("Vorlage", names)
        tmpl = existing_opts[names.index(pick)]
        hedge_option = hedge_option_from_position(tmpl, ug.spot, pf.rate)
    else:
        o1, o2, o3, o4 = st.columns(4)
        kind = o1.selectbox("Typ", ["call", "put"])
        strike = o2.number_input("Strike", value=spot_default, min_value=0.01, step=1.0)
        days = o3.number_input("Laufzeit (Tage)", value=30, min_value=1, step=1)
        iv = o4.number_input("Implizite Vol", value=0.25, min_value=0.001,
                             step=0.01, format="%.3f")
        o5, o6, o7 = st.columns(3)
        rate = o5.number_input("Zinssatz", value=float(pf.rate), min_value=0.0,
                               step=0.0025, format="%.4f")
        divy = o6.number_input("Dividendenrendite", value=0.0, min_value=0.0,
                               step=0.005, format="%.4f")
        mult = o7.number_input("Multiplikator", value=100.0, min_value=1.0, step=1.0)
        hedge_option = HedgeOption(kind=kind, strike=strike,
                                   expiry_years=days / 365.0, sigma=iv,
                                   spot=ug.spot, rate=rate, dividend_yield=divy,
                                   multiplier=mult)

        if src_sel == "Auto-Optimierung":
            use_optimizer = True
            priority = st.selectbox("Priorisierung", list(PRIORITY_WEIGHTS.keys()))
            st.caption("Hinweis: Keine Live-Optionskette verfuegbar. Die Kandidaten "
                       "werden modellbasiert aus deiner IV/Laufzeit um den Spot "
                       "erzeugt (keine Marktdaten).")
            # Build a theoretical strike grid around spot (model-based candidates).
            for m in (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15):
                candidates.append(HedgeOption(
                    kind=kind, strike=round(ug.spot * m, 2),
                    expiry_years=days / 365.0, sigma=iv, spot=ug.spot,
                    rate=rate, dividend_yield=divy, multiplier=mult))

# --------------------------------------------------------------------------- #
#  Build the hedge
# --------------------------------------------------------------------------- #
theme.section(f"Hedge-Empfehlung - {underlying}")

before = {"delta": ug.delta, "gamma": ug.gamma, "vega": ug.vega, "theta": ug.theta}
res = None
opt_ranking = None
error_msg = None

try:
    if mode == "Delta Hedge":
        res = build_delta_hedge(ug)
    else:
        if hedge_option is None:
            raise ValueError("Bitte ein Hedge-Instrument konfigurieren.")
        if use_optimizer and candidates:
            best = optimize_hedge(ug, candidates, priority, tc)
            opt_ranking = rank_candidates(ug, candidates, priority, tc)
            if best is None:
                raise ValueError("Keine Kandidaten-Option mit nutzbarem Gamma.")
            hedge_option = best.option
        if mode == "Gamma Hedge":
            res = build_gamma_hedge(ug, hedge_option)
        else:
            res = build_delta_gamma_hedge(ug, hedge_option)
    res = finalize_hedge(res, rounding, tc)
except ValueError as e:
    error_msg = str(e)

if error_msg:
    st.error(f"Hedge nicht berechenbar: {error_msg}")
    st.stop()


# --------------------------------------------------------------------------- #
#  Recommendation text
# --------------------------------------------------------------------------- #
def share_sentence(n, sym):
    if abs(n) < 1e-9:
        return None
    if n > 0:
        return f"**Kaufe {abs(n):,.0f} Einheiten** von **{sym}**."
    return f"**Verkaufe {abs(n):,.0f} Einheiten** von **{sym}** leer (Short)."


def option_sentence(n, opt: HedgeOption):
    if abs(n) < 1e-9:
        return None
    verb = "Kaufe" if n > 0 else "Verkaufe (Short)"
    return (f"**{verb} {abs(n):,.0f} {opt.kind.upper()}-Kontrakte** "
            f"(Strike {opt.strike:g}, Laufzeit {opt.expiry_years*365:.0f} Tage, "
            f"IV {opt.sigma:.0%}, Multiplikator {opt.multiplier:g}).")


steps = []
if res.option is not None:
    s = option_sentence(res.contracts, res.option)
    if s:
        steps.append(s)
s = share_sentence(res.shares, underlying)
if s:
    steps.append(s)

if steps:
    st.markdown("\n".join(f"{i+1}. {t}" for i, t in enumerate(steps)))
else:
    st.info("Keine Trades notwendig - das Portfolio ist bereits neutral.")

for w in res.warnings:
    st.warning(w)

# --------------------------------------------------------------------------- #
#  Residual KPIs + before/after
# --------------------------------------------------------------------------- #
after = res.residual
kpi_row([
    kpi_card("Delta nachher", fmt_num(after["delta"], 2),
             f"vorher {before['delta']:,.1f}", 0, "blue"),
    kpi_card("Gamma nachher", fmt_num(after["gamma"], 3),
             f"vorher {before['gamma']:,.2f}", 0, "purple"),
    kpi_card("Hedge-Kosten", fmt_money(res.cost["total_outlay"]),
             fmt_pct(res.cost["total_outlay"] / pf.total_value(ctx) * 100
                     if pf.total_value(ctx) else 0),
             -1 if res.cost["total_outlay"] > 0 else 1, "red"),
    kpi_card("Trades", str(res.cost["n_orders"]), "Orders", 0, "teal"),
], columns=4)

# Greeks staging table (before / after option / after full)
theme.section("Greeks-Verlauf")
stage_rows = [{"Greek": "Delta", "Vor Hedge": before["delta"],
               "Nach Options-Hedge": res.delta_after_option,
               "Nach vollst. Hedge": after["delta"]},
              {"Greek": "Gamma", "Vor Hedge": before["gamma"],
               "Nach Options-Hedge": res.gamma_after_option,
               "Nach vollst. Hedge": after["gamma"]}]
if res.option is None:
    # Delta-only hedge: no option stage
    stage_df = pd.DataFrame([
        {"Greek": "Delta", "Vor Hedge": before["delta"],
         "Nach vollst. Hedge": after["delta"]},
        {"Greek": "Gamma", "Vor Hedge": before["gamma"],
         "Nach vollst. Hedge": after["gamma"]},
    ])
    styled_table(stage_df, num_cols=["Vor Hedge", "Nach vollst. Hedge"])
else:
    styled_table(pd.DataFrame(stage_rows),
                 num_cols=["Vor Hedge", "Nach Options-Hedge", "Nach vollst. Hedge"])

# --------------------------------------------------------------------------- #
#  Charts: before/after bar, exposure curves, P&L
# --------------------------------------------------------------------------- #
c1, c2 = st.columns(2)
with c1:
    theme.section("Greeks: Vor vs. Nach")
    st.plotly_chart(hedge_charts.before_after_greeks(before, after),
                    use_container_width=True, config={"displayModeBar": False})
with c2:
    theme.section("Trades")
    trade_rows = []
    if res.option is not None and abs(res.contracts) > 1e-9:
        trade_rows.append({"Instrument": f"{res.option.kind.upper()} "
                           f"{res.option.strike:g}",
                           "Aktion": "Kauf" if res.contracts > 0 else "Verkauf/Short",
                           "Menge": abs(res.contracts), "Typ": "Option",
                           "Preis": res.option.price_per_contract})
    if abs(res.shares) > 1e-9:
        trade_rows.append({"Instrument": underlying,
                           "Aktion": "Kauf" if res.shares > 0 else "Verkauf/Short",
                           "Menge": abs(res.shares), "Typ": "Underlying",
                           "Preis": res.spot})
    if trade_rows:
        styled_table(pd.DataFrame(trade_rows), money_cols=["Preis"], num_cols=["Menge"])
    else:
        st.info("Keine Trades.")

# Scenario range for exposure / P&L profiles
theme.section("Szenario nach Hedge")
rng = st.slider("Underlying-Preisbereich", -40, 40, (-20, 20), 1, format="%d%%")
lo, hi = rng
spot_grid = ug.spot * (1 + np.linspace(lo / 100.0, hi / 100.0, 81))

positions_u = hedging.positions_for_underlying(pf, underlying)
prof = exposure_profile(positions_u, pf, underlying, spot_grid, hedge=res)

g1, g2 = st.columns(2)
with g1:
    theme.section("Delta-Verlauf")
    st.plotly_chart(
        hedge_charts.exposure_curve(prof["spot"], prof["delta_before"],
                                    prof["delta_after"], ug.spot, "Delta"),
        use_container_width=True, config={"displayModeBar": False})
with g2:
    theme.section("Gamma-Verlauf")
    st.plotly_chart(
        hedge_charts.exposure_curve(prof["spot"], prof["gamma_before"],
                                    prof["gamma_after"], ug.spot, "Gamma"),
        use_container_width=True, config={"displayModeBar": False})

theme.section("P&L-Profil (Greek-Approximation)")
pnl_before = pnl_profile_greek(before["delta"], before["gamma"], ug.spot, spot_grid)
pnl_after = pnl_profile_greek(after["delta"], after["gamma"], ug.spot, spot_grid)
st.plotly_chart(hedge_charts.pnl_profile(spot_grid, pnl_before, pnl_after, ug.spot),
                use_container_width=True, config={"displayModeBar": False})
st.caption("P&L lokal approximiert: dV = Delta*dS + 0.5*Gamma*dS^2 (konstante "
           "Greeks). Die Delta-/Gamma-Verlaeufe oben sind dagegen exakt neu bewertet.")

# --------------------------------------------------------------------------- #
#  Rounding comparison
# --------------------------------------------------------------------------- #
theme.section("Rundungs-Varianten")
alt_rows = rounding_alternatives(res, tc)
alt_df = pd.DataFrame(alt_rows)
best_idx = alt_df["_error"].idxmin()
alt_df_display = alt_df.drop(columns=["_error"]).copy()
alt_df_display.insert(0, "Beste", ["<<" if i == best_idx else "" for i in alt_df.index])
styled_table(alt_df_display, money_cols=["Hedge-Kosten"],
             num_cols=["Optionskontrakte", "Aktien", "Rest-Delta", "Rest-Gamma"])
st.caption("Markiert (<<): geringster Hedge-Fehler |Rest-Delta| + |Rest-Gamma|.")

# --------------------------------------------------------------------------- #
#  Optimizer ranking (if used)
# --------------------------------------------------------------------------- #
if opt_ranking:
    theme.section("Optimierung - Kandidaten-Ranking")
    rank_rows = [{
        "Option": o.option.auto_label(), "Kontrakte": o.contracts,
        "Aktien": o.shares, "Rest-Delta": o.residual["delta"],
        "Rest-Gamma": o.residual["gamma"], "Kosten": o.cost["total_outlay"],
        "Score": o.objective,
    } for o in opt_ranking]
    styled_table(pd.DataFrame(rank_rows), money_cols=["Kosten"],
                 num_cols=["Kontrakte", "Aktien", "Rest-Delta", "Rest-Gamma", "Score"])

# --------------------------------------------------------------------------- #
#  Hedge cost detail
# --------------------------------------------------------------------------- #
theme.section("Hedge-Kosten Detail")
cost = res.cost
cost_df = pd.DataFrame([
    {"Posten": "Cashflow Aktien", "Betrag": cost["shares_cashflow"]},
    {"Posten": "Cashflow Optionen (Praemie)", "Betrag": cost["option_cashflow"]},
    {"Posten": "Netto-Cashflow", "Betrag": cost["net_cashflow"]},
    {"Posten": "Transaktionskosten", "Betrag": -cost["transaction_costs"]},
    {"Posten": "Gesamt-Auslage (zu zahlen)", "Betrag": -cost["total_outlay"]},
])
styled_table(cost_df, pnl_cols=["Betrag"])

# --------------------------------------------------------------------------- #
#  Disclaimer
# --------------------------------------------------------------------------- #
st.divider()
st.caption(
    "**Hinweis / Disclaimer:** Diese Berechnung ist eine Modellrechnung und keine "
    "Anlageberatung. Greeks veraendern sich bei Marktbewegungen; ein Delta-Gamma-"
    "Hedge ist nur lokal neutral und muss ggf. regelmaessig angepasst werden "
    "(Re-Hedging). Short-Optionen besitzen potenziell erhebliche Verlustrisiken und "
    "Margin-Anforderungen. Liquiditaet, Bid-Ask-Spreads, Margin und Transaktions"
    "kosten werden hier nur vereinfacht beruecksichtigt.")
