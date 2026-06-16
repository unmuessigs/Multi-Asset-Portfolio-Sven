"""Dashboard 6 — Portfolio Builder: add/remove positions via a GUI form."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from src.ui import theme
from src.ui.components import styled_table, empty_state
from src import state
from src.instruments import Equity, ETF, Option, Future, Bond, Cash, Position


theme.apply_theme("ATLAS · Builder")
theme.header("BUILDER")
state.render_sidebar()

pf = state.get_portfolio()

TYPES = ["Aktie (Equity)", "ETF", "Future", "Option", "Bond", "Cash"]

theme.section("Neue Position hinzufügen")
itype = st.selectbox("Instrumenttyp", TYPES)

# --------------------------------------------------------------------------- #
#  Type-specific input form
# --------------------------------------------------------------------------- #
with st.form("add_position", clear_on_submit=False):
    instrument = None
    quantity = 0.0
    direction = 1
    entry = 0.0

    if itype in ("Aktie (Equity)", "ETF"):
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("Ticker", value="AAPL").upper().strip()
        side = c2.selectbox("Seite", ["Long", "Short"])
        quantity = c3.number_input("Stückzahl", value=100.0, min_value=0.0, step=1.0)
        entry = c4.number_input("Kaufpreis (0 = aktueller Kurs)", value=0.0,
                                min_value=0.0, step=0.5)
        direction = 1 if side == "Long" else -1
        instrument = Equity(ticker) if itype == "Aktie (Equity)" else ETF(ticker)

    elif itype == "Future":
        c1, c2, c3, c4, c5 = st.columns(5)
        ticker = c1.text_input("Ticker", value="ES=F").upper().strip()
        side = c2.selectbox("Seite", ["Long", "Short"])
        quantity = c3.number_input("Kontrakte", value=1.0, min_value=0.0, step=1.0)
        size = c4.number_input("Kontraktgröße", value=50.0, min_value=1.0, step=1.0)
        entry = c5.number_input("Kaufpreis (0 = Kurs)", value=0.0, min_value=0.0)
        direction = 1 if side == "Long" else -1
        instrument = Future(ticker, contract_size=size)

    elif itype == "Option":
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("Underlying", value="AAPL").upper().strip()
        kind = c2.selectbox("Typ", ["call", "put"])
        side = c3.selectbox("Seite", ["Long", "Short"])
        quantity = c4.number_input("Kontrakte", value=1.0, min_value=0.0, step=1.0)
        c5, c6, c7, c8 = st.columns(4)
        strike = c5.number_input("Strike", value=100.0, min_value=0.01, step=1.0)
        maturity = c6.number_input("Laufzeit (Jahre)", value=0.25, min_value=0.0,
                                   step=0.05, format="%.3f")
        vol = c7.number_input("Volatilität σ", value=0.25, min_value=0.001,
                              step=0.01, format="%.3f")
        entry = c8.number_input("Prämie (0 = BS-Preis)", value=0.0, min_value=0.0,
                                step=0.05)
        direction = 1 if side == "Long" else -1
        instrument = Option(ticker, strike, maturity, vol, kind)

    elif itype == "Bond":
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("Bezeichnung", value="UST 10Y")
        side = c2.selectbox("Seite", ["Long", "Short"])
        quantity = c3.number_input("Stückzahl", value=10.0, min_value=0.0, step=1.0)
        face = c4.number_input("Nennwert", value=1000.0, min_value=1.0, step=100.0)
        c5, c6, c7, c8 = st.columns(4)
        coupon = c5.number_input("Kupon %", value=4.0, min_value=0.0, step=0.25) / 100
        years = c6.number_input("Laufzeit (Jahre)", value=10.0, min_value=0.1, step=0.5)
        ytm = c7.number_input("YTM %", value=4.25, min_value=0.0, step=0.05) / 100
        freq = c8.selectbox("Kupon-Frequenz", [1, 2, 4], index=1)
        direction = 1 if side == "Long" else -1
        instrument = Bond(name, face, coupon, years, ytm, freq)

    elif itype == "Cash":
        c1, c2 = st.columns(2)
        ccy = c1.text_input("Währung", value="USD").upper().strip()
        quantity = c2.number_input("Betrag", value=10000.0, min_value=0.0, step=1000.0)
        direction = 1
        entry = 1.0
        instrument = Cash(ccy)

    submitted = st.form_submit_button("➕ Position hinzufügen", type="primary",
                                      use_container_width=True)

if submitted and instrument is not None and quantity > 0:
    ctx = pf.context()
    # Default entry price to the current fair value when left at 0.
    if entry == 0.0 and itype != "Cash":
        try:
            entry = instrument.price(ctx)
        except Exception:
            entry = 0.0
    pf.add(Position(instrument=instrument, quantity=quantity,
                    direction=direction, entry_price=entry))
    st.success(f"Hinzugefügt: {instrument.symbol}")
    st.rerun()

# --------------------------------------------------------------------------- #
#  Current positions + remove
# --------------------------------------------------------------------------- #
theme.section("Aktuelles Portfolio")
if pf.is_empty:
    empty_state("Noch keine Positionen.")
else:
    ctx = pf.context()
    styled_table(
        pf.positions_table(ctx),
        money_cols=["Entry", "Price", "Mkt Value"],
        pnl_cols=["P&L"], pct_cols=["P&L %"], num_cols=["Qty"],
    )

    cc1, cc2 = st.columns([2, 1])
    idx = cc1.selectbox("Position entfernen",
                        options=list(range(len(pf.positions))),
                        format_func=lambda i: f"#{i} · {pf.positions[i].name}")
    if cc2.button("🗑 Entfernen", use_container_width=True):
        pf.remove(idx)
        st.rerun()
