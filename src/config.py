"""
Global configuration: colour palette, financial constants and app settings.

Keeping these in one place makes the look-and-feel consistent across every
dashboard and lets us re-theme the whole platform from a single file.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
#  Branding / app meta
# --------------------------------------------------------------------------- #
APP_NAME = "ATLAS Terminal"
APP_SUBTITLE = "Multi-Asset Portfolio & Derivatives Analytics"

# --------------------------------------------------------------------------- #
#  Colour palette (institutional dark theme)
# --------------------------------------------------------------------------- #
COLORS = {
    "bg": "#0B0E11",
    "bg_card": "#151A21",
    "bg_card_alt": "#1B222B",
    "border": "#252D38",
    "text": "#E6E9EF",
    "text_muted": "#8A93A2",
    "accent": "#FF8A00",     # amber
    "accent_2": "#2D9CDB",   # blue
    "positive": "#16C784",   # green  (gains)
    "negative": "#EA3943",   # red    (losses)
    "neutral": "#8A93A2",
    "purple": "#9B6DFF",
    "teal": "#13C4C4",
    "yellow": "#F3BA2F",
}

# Categorical palette used for allocation / multi-series charts
CATEGORICAL = [
    "#FF8A00", "#2D9CDB", "#16C784", "#9B6DFF",
    "#F3BA2F", "#13C4C4", "#EA3943", "#6C7A89",
]

# Diverging scale for heatmaps (red -> dark -> green)
DIVERGING = [
    [0.0, "#EA3943"],
    [0.5, "#151A21"],
    [1.0, "#16C784"],
]

# Asset-class -> colour mapping (stable across the app)
ASSET_COLORS = {
    "Equity": "#2D9CDB",
    "ETF": "#16C784",
    "Future": "#F3BA2F",
    "Option": "#FF8A00",
    "Bond": "#9B6DFF",
    "Cash": "#6C7A89",
}

# --------------------------------------------------------------------------- #
#  Financial constants / defaults
# --------------------------------------------------------------------------- #
RISK_FREE_RATE = 0.0425       # default annualised risk-free rate (4.25 %)
TRADING_DAYS = 252            # trading days per year
DEFAULT_VAR_CONFIDENCE = 0.95
DEFAULT_BENCHMARK = "SPY"     # market proxy for Beta
DAYS_PER_YEAR = 365.0

# Plotly base layout shared by every chart
PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="ui-monospace, SFMono-Regular, Menlo, monospace",
              color=COLORS["text"], size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h",
                yanchor="bottom", y=1.02, xanchor="right", x=1),
    colorway=CATEGORICAL,
)
