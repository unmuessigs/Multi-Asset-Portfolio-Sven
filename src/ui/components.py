"""
Reusable UI components: KPI cards and styled tables.

These render raw HTML/CSS (defined in theme.py) so the dashboards stay almost
text-free and look like an institutional terminal.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from .. import config

C = config.COLORS


# --------------------------------------------------------------------------- #
#  Number formatting helpers
# --------------------------------------------------------------------------- #
def fmt_money(x: float, decimals: int = 0) -> str:
    if x is None or pd.isna(x):
        return "-"
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.{decimals}f}"


def fmt_num(x: float, decimals: int = 2) -> str:
    if x is None or pd.isna(x):
        return "-"
    return f"{x:,.{decimals}f}"


def fmt_pct(x: float, decimals: int = 2, plus: bool = True) -> str:
    if x is None or pd.isna(x):
        return "-"
    s = f"{x:+.{decimals}f}%" if plus else f"{x:.{decimals}f}%"
    return s


# --------------------------------------------------------------------------- #
#  KPI cards
# --------------------------------------------------------------------------- #
def kpi_card(label: str, value: str, delta: Optional[str] = None,
             delta_dir: int = 0, accent: str = "") -> str:
    """Return the HTML for a single KPI card.

    delta_dir: +1 green, -1 red, 0 muted.
    accent: "", "blue", "green", "red", "purple", "teal" (left bar colour).
    """
    cls = {1: "pos", -1: "neg", 0: "muted"}[delta_dir]
    delta_html = f'<div class="kpi-delta {cls}">{delta}</div>' if delta else ""
    return (
        f'<div class="kpi-card {accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{delta_html}</div>'
    )


def kpi_row(cards: list, columns: Optional[int] = None):
    """Render a responsive grid of KPI card HTML strings."""
    n = columns or len(cards)
    grid = (
        f'<div class="kpi-grid" style="grid-template-columns:repeat({n},1fr);">'
        + "".join(cards) + "</div>"
    )
    st.markdown(grid, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Styled dataframe
# --------------------------------------------------------------------------- #
def styled_table(df: pd.DataFrame, money_cols=(), pct_cols=(), num_cols=(),
                 pnl_cols=(), height: Optional[int] = None):
    """Display a dataframe with monospace formatting and red/green P&L."""
    if df.empty:
        st.info("Keine Daten.")
        return

    disp = df.copy()

    def colour_pnl(val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""
        if v > 0:
            return f"color: {C['positive']};"
        if v < 0:
            return f"color: {C['negative']};"
        return f"color: {C['text_muted']};"

    fmt = {}
    for c in money_cols:
        if c in disp:
            fmt[c] = lambda v: fmt_money(v, 0)
    for c in num_cols:
        if c in disp:
            fmt[c] = lambda v: fmt_num(v, 3)
    for c in pct_cols:
        if c in disp:
            fmt[c] = lambda v: fmt_pct(v, 2)
    for c in pnl_cols:
        if c in disp:
            fmt[c] = lambda v: fmt_money(v, 0)

    sty = disp.style.format(fmt)
    for c in pnl_cols:
        if c in disp:
            sty = sty.map(colour_pnl, subset=[c])
    sty = sty.set_properties(**{
        "background-color": C["bg_card"],
        "color": C["text"],
        "font-family": "ui-monospace, monospace",
        "font-size": "12.5px",
        "border-color": C["border"],
    })
    # Newer Streamlit versions reject height=None, so only pass it when set.
    kwargs = dict(use_container_width=True, hide_index=True)
    if height is not None:
        kwargs["height"] = height
    st.dataframe(sty, **kwargs)


def empty_state(message: str):
    st.markdown(
        f"""
        <div style="text-align:center; padding:60px 20px; color:{C['text_muted']};
             border:1px dashed {C['border']}; border-radius:14px;">
            <div style="font-size:42px; margin-bottom:10px;">&#11042;</div>
            <div style="font-size:15px;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
