"""
Plotly chart factory.

Every function returns a styled ``go.Figure`` using the shared dark-theme
layout from config. Dashboards just call these and hand the result to
``st.plotly_chart`` — keeping presentation logic out of the page files.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .. import config

C = config.COLORS
L = config.PLOTLY_LAYOUT


def _fig(height: int = 320, title: str = "") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**L, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=14,
                          color=C["text_muted"]), x=0.01, y=0.97))
    return fig


# --------------------------------------------------------------------------- #
#  Portfolio overview
# --------------------------------------------------------------------------- #
def allocation_donut(alloc: pd.DataFrame) -> go.Figure:
    colors = [config.ASSET_COLORS.get(a, C["accent"]) for a in alloc["Asset Class"]]
    fig = _fig(330)
    fig.add_trace(go.Pie(
        labels=alloc["Asset Class"], values=alloc["Exposure"],
        hole=0.62, marker=dict(colors=colors, line=dict(color=C["bg"], width=2)),
        textinfo="label+percent", textfont=dict(size=12),
        hovertemplate="%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    total = alloc["Exposure"].sum()
    fig.add_annotation(text=f"<b>${total:,.0f}</b><br><span style='font-size:11px'>"
                            f"Gross Exposure</span>",
                       showarrow=False, font=dict(size=18, color=C["text"]))
    fig.update_layout(showlegend=False)
    return fig


def value_over_time(series: pd.Series) -> go.Figure:
    fig = _fig(330)
    up = series.iloc[-1] >= series.iloc[0]
    line_col = C["positive"] if up else C["negative"]
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values, mode="lines",
        line=dict(color=line_col, width=2),
        fill="tozeroy", fillcolor="rgba(22,199,132,0.08)" if up
        else "rgba(234,57,67,0.08)",
        hovertemplate="%{x|%d %b %Y}<br>$%{y:,.0f}<extra></extra>",
    ))
    fig.update_yaxes(gridcolor=C["border"], tickprefix="$", showgrid=True)
    fig.update_xaxes(gridcolor=C["border"], showgrid=False)
    return fig


def performance_chart(series: pd.Series) -> go.Figure:
    """Cumulative return (%) since the start of the window."""
    fig = _fig(330)
    base = series.iloc[0]
    perf = (series / base - 1.0) * 100
    fig.add_trace(go.Scatter(
        x=perf.index, y=perf.values, mode="lines",
        line=dict(color=C["accent_2"], width=2),
        hovertemplate="%{x|%d %b %Y}<br>%{y:+.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1, dash="dot"))
    fig.update_yaxes(gridcolor=C["border"], ticksuffix="%")
    fig.update_xaxes(gridcolor=C["border"], showgrid=False)
    return fig


# --------------------------------------------------------------------------- #
#  Risk analytics
# --------------------------------------------------------------------------- #
def greeks_heatmap(df: pd.DataFrame, greek_cols) -> go.Figure:
    """Heatmap of per-position Greeks (normalised per column for colouring)."""
    if df.empty:
        return _fig(300)
    mat = df[list(greek_cols)].astype(float)
    # Normalise each Greek column to [-1,1] for comparable colours.
    norm = mat.copy()
    for c in greek_cols:
        m = mat[c].abs().max()
        norm[c] = mat[c] / m if m else 0.0

    fig = _fig(max(260, 40 * len(df)))
    fig.add_trace(go.Heatmap(
        z=norm.values, x=[g.capitalize() for g in greek_cols],
        y=df["Position"], colorscale=config.DIVERGING, zmid=0,
        text=mat.round(2).values, texttemplate="%{text}",
        textfont=dict(size=11), showscale=False,
        hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>",
    ))
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
    return fig


def risk_contribution_bar(df: pd.DataFrame) -> go.Figure:
    fig = _fig(max(260, 38 * len(df)))
    colors = [C["negative"] if v < 0 else C["accent"] for v in df["Pct"]]
    fig.add_trace(go.Bar(
        x=df["Pct"], y=df["Position"], orientation="h",
        marker=dict(color=colors),
        text=[f"{v:+.1f}%" for v in df["Pct"]], textposition="outside",
        hovertemplate="%{y}<br>%{x:.2f}% of risk<extra></extra>",
    ))
    fig.update_xaxes(gridcolor=C["border"], ticksuffix="%")
    fig.update_yaxes(autorange="reversed")
    return fig


def var_distribution(pnl: np.ndarray, var: float, cvar: float) -> go.Figure:
    fig = _fig(330)
    fig.add_trace(go.Histogram(
        x=pnl, nbinsx=50, marker=dict(color=C["accent_2"],
        line=dict(color=C["bg"], width=0.5)),
        opacity=0.85, hovertemplate="P&L $%{x:,.0f}<br>%{y} days<extra></extra>",
    ))
    fig.add_vline(x=-var, line=dict(color=C["negative"], width=2, dash="dash"),
                  annotation_text=f"VaR ${var:,.0f}", annotation_position="top left")
    fig.add_vline(x=-cvar, line=dict(color=C["purple"], width=2, dash="dot"),
                  annotation_text=f"CVaR ${cvar:,.0f}",
                  annotation_position="bottom left")
    fig.update_xaxes(gridcolor=C["border"], tickprefix="$")
    fig.update_yaxes(gridcolor=C["border"])
    return fig


def greeks_bar(greeks: dict) -> go.Figure:
    keys = ["delta", "gamma", "vega", "theta", "rho"]
    vals = [greeks[k] for k in keys]
    colors = [C["positive"] if v >= 0 else C["negative"] for v in vals]
    fig = _fig(280)
    fig.add_trace(go.Bar(
        x=[k.capitalize() for k in keys], y=vals, marker=dict(color=colors),
        text=[f"{v:,.1f}" for v in vals], textposition="outside",
    ))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    fig.update_yaxes(gridcolor=C["border"])
    return fig


# --------------------------------------------------------------------------- #
#  Options analytics
# --------------------------------------------------------------------------- #
def payoff_diagram(spot_grid, payoff_expiry, value_now, breakevens=None,
                   spot=None) -> go.Figure:
    fig = _fig(340)
    fig.add_trace(go.Scatter(
        x=spot_grid, y=payoff_expiry, mode="lines", name="At Expiry",
        line=dict(color=C["accent"], width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=spot_grid, y=value_now, mode="lines", name="Current Value",
        line=dict(color=C["accent_2"], width=2, dash="dot"),
    ))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    if spot is not None:
        fig.add_vline(x=spot, line=dict(color=C["text_muted"], width=1, dash="dash"),
                      annotation_text="Spot")
    fig.update_xaxes(gridcolor=C["border"], title="Underlying Price")
    fig.update_yaxes(gridcolor=C["border"], title="P&L", tickprefix="$")
    return fig


def sensitivity_curve(x, y, x_title, y_title, color=None) -> go.Figure:
    fig = _fig(300)
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines",
                  line=dict(color=color or C["teal"], width=2.5)))
    fig.update_xaxes(gridcolor=C["border"], title=x_title)
    fig.update_yaxes(gridcolor=C["border"], title=y_title)
    return fig


def greeks_surface(x, y, z, x_title, y_title, z_title) -> go.Figure:
    fig = go.Figure(data=[go.Surface(
        x=x, y=y, z=z, colorscale="Viridis", showscale=False,
        contours=dict(z=dict(show=True, usecolormap=True, project_z=True)),
    )])
    fig.update_layout(**L, height=420)
    fig.update_layout(scene=dict(
        xaxis=dict(title=x_title, color=C["text_muted"], gridcolor=C["border"]),
        yaxis=dict(title=y_title, color=C["text_muted"], gridcolor=C["border"]),
        zaxis=dict(title=z_title, color=C["text_muted"], gridcolor=C["border"]),
        bgcolor="rgba(0,0,0,0)",
    ))
    return fig


# --------------------------------------------------------------------------- #
#  Scenario analysis
# --------------------------------------------------------------------------- #
def scenario_sweep(pct_shocks, pnls) -> go.Figure:
    fig = _fig(340)
    colors = np.where(pnls >= 0, C["positive"], C["negative"])
    fig.add_trace(go.Scatter(
        x=pct_shocks, y=pnls, mode="lines",
        line=dict(color=C["accent"], width=2.5),
        hovertemplate="Spot %{x:+.0f}%<br>P&L $%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    fig.add_vline(x=0, line=dict(color=C["text_muted"], width=1, dash="dot"))
    fig.update_xaxes(gridcolor=C["border"], title="Market Move (%)", ticksuffix="%")
    fig.update_yaxes(gridcolor=C["border"], title="Portfolio P&L", tickprefix="$")
    return fig


def greek_change_bar(base: dict, new: dict) -> go.Figure:
    keys = ["delta", "gamma", "vega", "theta", "rho"]
    fig = _fig(300)
    fig.add_trace(go.Bar(x=[k.capitalize() for k in keys],
                         y=[base[k] for k in keys], name="Base",
                         marker=dict(color=C["neutral"])))
    fig.add_trace(go.Bar(x=[k.capitalize() for k in keys],
                         y=[new[k] for k in keys], name="Scenario",
                         marker=dict(color=C["accent"])))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    fig.update_layout(barmode="group")
    fig.update_yaxes(gridcolor=C["border"])
    return fig


# --------------------------------------------------------------------------- #
#  Bond analytics
# --------------------------------------------------------------------------- #
def yield_curve(maturities, yields, portfolio_points=None) -> go.Figure:
    fig = _fig(330)
    fig.add_trace(go.Scatter(
        x=maturities, y=np.array(yields) * 100, mode="lines+markers",
        line=dict(color=C["accent"], width=2.5),
        marker=dict(size=7), name="Yield Curve",
    ))
    if portfolio_points:
        mx, my = zip(*portfolio_points)
        fig.add_trace(go.Scatter(
            x=mx, y=np.array(my) * 100, mode="markers", name="Holdings",
            marker=dict(size=13, color=C["positive"], symbol="diamond",
                        line=dict(color=C["bg"], width=1)),
        ))
    fig.update_xaxes(gridcolor=C["border"], title="Maturity (years)")
    fig.update_yaxes(gridcolor=C["border"], title="Yield", ticksuffix="%")
    return fig


def duration_contribution(df: pd.DataFrame) -> go.Figure:
    fig = _fig(max(240, 44 * len(df)))
    fig.add_trace(go.Bar(
        x=df["DurationContribution"], y=df["Bond"], orientation="h",
        marker=dict(color=C["purple"]),
        text=[f"{v:.2f}" for v in df["DurationContribution"]],
        textposition="outside",
        hovertemplate="%{y}<br>Contribution: %{x:.3f} yrs<extra></extra>",
    ))
    fig.update_xaxes(gridcolor=C["border"], title="Contribution to Duration (yrs)")
    fig.update_yaxes(autorange="reversed")
    return fig


def rate_sensitivity(dy_bps, price_changes) -> go.Figure:
    fig = _fig(330)
    colors = np.where(np.array(price_changes) >= 0, C["positive"], C["negative"])
    fig.add_trace(go.Bar(
        x=dy_bps, y=price_changes, marker=dict(color=colors),
        hovertemplate="%{x:+d} bps<br>$%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    fig.update_xaxes(gridcolor=C["border"], title="Rate Shift (bps)")
    fig.update_yaxes(gridcolor=C["border"], title="Δ Bond Value", tickprefix="$")
    return fig
