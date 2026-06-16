"""
Plotly charts specific to the Hedging Analytics page.

Kept separate from charts.py for modularity. Reuses the shared dark-theme
layout (config.PLOTLY_LAYOUT) so the visuals match the rest of ATLAS.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from .. import config

C = config.COLORS
L = config.PLOTLY_LAYOUT


def _fig(height: int = 320) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**L, height=height)
    return fig


def before_after_greeks(before: dict, after: dict,
                        keys=("delta", "gamma", "vega", "theta")) -> go.Figure:
    """Grouped bar of portfolio Greeks before vs after the hedge."""
    fig = _fig(320)
    labels = [k.capitalize() for k in keys]
    fig.add_trace(go.Bar(
        x=labels, y=[before.get(k, 0.0) for k in keys], name="Vor Hedge",
        marker=dict(color=C["neutral"]),
        text=[f"{before.get(k, 0.0):,.1f}" for k in keys], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=labels, y=[after.get(k, 0.0) for k in keys], name="Nach Hedge",
        marker=dict(color=C["accent"]),
        text=[f"{after.get(k, 0.0):,.1f}" for k in keys], textposition="outside",
    ))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    fig.update_layout(barmode="group")
    fig.update_yaxes(gridcolor=C["border"])
    return fig


def exposure_curve(spot, before, after, base_spot, y_title: str) -> go.Figure:
    """Delta or Gamma across underlying price, before vs after the hedge."""
    fig = _fig(300)
    fig.add_trace(go.Scatter(x=spot, y=before, mode="lines", name="Vor Hedge",
                  line=dict(color=C["accent_2"], width=2.5)))
    if after:
        fig.add_trace(go.Scatter(x=spot, y=after, mode="lines", name="Nach Hedge",
                      line=dict(color=C["positive"], width=2.5)))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1, dash="dot"))
    fig.add_vline(x=base_spot, line=dict(color=C["text_muted"], width=1, dash="dash"),
                  annotation_text="Spot")
    fig.update_xaxes(gridcolor=C["border"], title="Underlying Price")
    fig.update_yaxes(gridcolor=C["border"], title=y_title)
    return fig


def pnl_profile(spot, pnl_before, pnl_after, base_spot) -> go.Figure:
    """Local Greek-based P&L profile, before vs after the hedge."""
    fig = _fig(320)
    fig.add_trace(go.Scatter(x=spot, y=pnl_before, mode="lines", name="Vor Hedge",
                  line=dict(color=C["negative"], width=2.5)))
    fig.add_trace(go.Scatter(x=spot, y=pnl_after, mode="lines", name="Nach Hedge",
                  line=dict(color=C["positive"], width=2.5)))
    fig.add_hline(y=0, line=dict(color=C["text_muted"], width=1))
    fig.add_vline(x=base_spot, line=dict(color=C["text_muted"], width=1, dash="dash"))
    fig.update_xaxes(gridcolor=C["border"], title="Underlying Price")
    fig.update_yaxes(gridcolor=C["border"], title="Approx. P&L", tickprefix="$")
    return fig
