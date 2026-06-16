"""
Global styling: injects the institutional dark-theme CSS and renders the
terminal-style header. Import ``apply_theme`` at the top of every page.
"""
from __future__ import annotations

import streamlit as st

from .. import config

C = config.COLORS

_CSS = f"""
<style>
    /* ---- base ------------------------------------------------------- */
    .stApp {{ background: {C['bg']}; }}
    section[data-testid="stSidebar"] {{
        background: {C['bg_card']};
        border-right: 1px solid {C['border']};
    }}
    #MainMenu, footer, header {{ visibility: hidden; }}
    .block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1500px; }}

    /* ---- terminal header ------------------------------------------- */
    .atlas-header {{
        display: flex; align-items: baseline; gap: 14px;
        border-bottom: 2px solid {C['accent']};
        padding: 6px 2px 10px 2px; margin-bottom: 18px;
    }}
    .atlas-logo {{
        font-family: ui-monospace, monospace; font-weight: 800;
        font-size: 26px; letter-spacing: 2px; color: {C['accent']};
    }}
    .atlas-sub {{ color: {C['text_muted']}; font-size: 13px; letter-spacing: 1px; }}
    .atlas-tag {{
        margin-left: auto; font-size: 11px; color: {C['text_muted']};
        border: 1px solid {C['border']}; border-radius: 4px; padding: 3px 9px;
    }}

    /* ---- KPI cards -------------------------------------------------- */
    .kpi-grid {{ display: grid; gap: 12px; margin-bottom: 6px; }}
    .kpi-card {{
        background: linear-gradient(160deg, {C['bg_card']}, {C['bg_card_alt']});
        border: 1px solid {C['border']}; border-radius: 12px;
        padding: 16px 18px; position: relative; overflow: hidden;
    }}
    .kpi-card::before {{
        content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
        background: {C['accent']};
    }}
    .kpi-label {{
        color: {C['text_muted']}; font-size: 11px; text-transform: uppercase;
        letter-spacing: 1.4px; margin-bottom: 8px;
    }}
    .kpi-value {{
        font-family: ui-monospace, monospace; font-size: 26px; font-weight: 700;
        color: {C['text']}; line-height: 1.1;
    }}
    .kpi-delta {{ font-size: 13px; margin-top: 6px; font-weight: 600; }}
    .pos {{ color: {C['positive']}; }}
    .neg {{ color: {C['negative']}; }}
    .muted {{ color: {C['text_muted']}; }}

    /* accent variants for the left bar */
    .kpi-card.blue::before   {{ background: {C['accent_2']}; }}
    .kpi-card.green::before  {{ background: {C['positive']}; }}
    .kpi-card.red::before    {{ background: {C['negative']}; }}
    .kpi-card.purple::before {{ background: {C['purple']}; }}
    .kpi-card.teal::before   {{ background: {C['teal']}; }}

    /* ---- section titles -------------------------------------------- */
    .section-title {{
        font-size: 13px; text-transform: uppercase; letter-spacing: 1.6px;
        color: {C['text_muted']}; margin: 22px 0 8px 0;
        border-left: 3px solid {C['accent']}; padding-left: 9px;
    }}

    /* ---- dataframe polish ------------------------------------------ */
    .stDataFrame {{ border: 1px solid {C['border']}; border-radius: 10px; }}

    /* ---- metric pill ----------------------------------------------- */
    .pill {{
        display:inline-block; padding:3px 10px; border-radius:20px;
        font-size:12px; font-weight:600; border:1px solid {C['border']};
    }}
</style>
"""


def apply_theme(page_title: str = config.APP_NAME):
    st.set_page_config(page_title=page_title, page_icon="📊",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(_CSS, unsafe_allow_html=True)


def header(tag: str = "LIVE"):
    st.markdown(
        f"""
        <div class="atlas-header">
            <span class="atlas-logo">⬢ {config.APP_NAME}</span>
            <span class="atlas-sub">{config.APP_SUBTITLE}</span>
            <span class="atlas-tag">● {tag}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
