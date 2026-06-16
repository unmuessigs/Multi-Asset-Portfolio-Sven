"""
Shared Streamlit session state.

Streamlit re-runs each page top-to-bottom on every interaction, so we keep the
single source of truth (market-data provider + portfolio) in ``st.session_state``
and hand every page the same objects. A demo portfolio is seeded on first load
so the dashboards are immediately populated.
"""
from __future__ import annotations

import streamlit as st

from .data.market_data import MarketData
from .portfolio.portfolio import Portfolio
from .analytics.risk import RiskAnalytics
from .instruments import Equity, ETF, Option, Future, Bond, Cash, Position
from . import config


# --------------------------------------------------------------------------- #
#  Singletons
# --------------------------------------------------------------------------- #
def get_market() -> MarketData:
    if "market" not in st.session_state:
        st.session_state.market = MarketData(
            use_live=st.session_state.get("use_live", True))
    return st.session_state.market


def get_portfolio() -> Portfolio:
    if "portfolio" not in st.session_state:
        pf = Portfolio(get_market())
        seed_sample(pf)
        st.session_state.portfolio = pf
    return st.session_state.portfolio


def get_risk() -> RiskAnalytics:
    pf = get_portfolio()
    try:
        bench = pf.market.returns(config.DEFAULT_BENCHMARK, "1y")
    except Exception:
        bench = None
    return RiskAnalytics(pf, benchmark_returns=bench)


# --------------------------------------------------------------------------- #
#  Demo portfolio
# --------------------------------------------------------------------------- #
def seed_sample(pf: Portfolio) -> None:
    """Populate a diversified multi-asset demo book."""
    m = pf.market

    def spot(sym):
        try:
            return m.spot(sym)
        except Exception:
            return 100.0

    aapl, msft = spot("AAPL"), spot("MSFT")

    specs = [
        # (instrument, quantity, direction, entry_factor)
        (Equity("AAPL"),                 200, 1, 0.88),
        (Equity("MSFT"),                 120, 1, 0.93),
        (Equity("NVDA"),                  80, 1, 0.70),
        (ETF("SPY"),                     150, 1, 0.95),
        (ETF("QQQ"),                     100, 1, 0.90),
        (Future("CL=F", 1000),             3, 1, 1.04),   # crude oil future
        (Option("AAPL", round(aapl * 1.05), 0.25, 0.28, "call"), 15, 1, 0.65),
        (Option("MSFT", round(msft * 0.95), 0.50, 0.26, "put"),  10, 1, 0.80),
        (Bond("UST 10Y", 1000, 0.0400, 10, 0.0425, 2),    25, 1, 0.99),
        (Bond("Corp 5Y A", 1000, 0.0550, 5, 0.0600, 2),   20, 1, 1.00),
        (Cash("USD"),                  75000, 1, 1.00),
    ]

    for inst, qty, direction, factor in specs:
        ctx = pf.context()
        unit = inst.price(ctx)
        pos = Position(instrument=inst, quantity=qty, direction=direction,
                       entry_price=unit * factor)
        pf.add(pos)


def reset_portfolio():
    pf = Portfolio(get_market())
    st.session_state.portfolio = pf


def load_demo_portfolio():
    pf = Portfolio(get_market())
    seed_sample(pf)
    st.session_state.portfolio = pf


# --------------------------------------------------------------------------- #
#  Shared sidebar
# --------------------------------------------------------------------------- #
def render_sidebar():
    """Global controls shown on every page."""
    pf = get_portfolio()
    with st.sidebar:
        st.markdown("### ⬢ ATLAS")
        st.caption("Multi-Asset Risk Terminal")

        st.divider()
        live = st.toggle("Live-Marktdaten (yfinance)",
                         value=st.session_state.get("use_live", True),
                         help="Aus = deterministische Simulationsdaten (offline).")
        if live != st.session_state.get("use_live", True):
            st.session_state.use_live = live
            # Rebuild market + portfolio with new data mode.
            st.session_state.pop("market", None)
            load_demo_portfolio()
            st.rerun()

        rate = st.number_input("Risk-Free Rate", value=float(pf.rate),
                               min_value=0.0, max_value=0.20, step=0.0025,
                               format="%.4f")
        pf.rate = rate

        st.divider()
        c1, c2 = st.columns(2)
        if c1.button("Demo laden", use_container_width=True):
            load_demo_portfolio()
            st.rerun()
        if c2.button("Leeren", use_container_width=True):
            reset_portfolio()
            st.rerun()

        if pf.has_synthetic_data():
            st.warning("⚠ Teilweise Simulationsdaten (kein Live-Feed).",
                       icon="⚠")
        st.caption(f"Positionen: **{len(pf)}**")
