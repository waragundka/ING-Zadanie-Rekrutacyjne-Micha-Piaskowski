"""Plotly figure builders — dark theme tuned for the simulator dashboard."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from portfolio_sim.allocation import Allocation

# --- Dark theme palette -----------------------------------------------------
BG = "#0E0E0E"
PANEL_BG = "#161616"
GRID = "#2A2A2A"
TEXT = "#E5E5E5"
MUTED_TEXT = "#8A8A8A"
NEUTRAL_LINE = "#3F3F3F"

ING_ORANGE = "#FF6200"
GAIN = "#2ECC71"
LOSS = "#E74C3C"

# Palette deliberately excludes pure black/white — every slice stays visible
# against either the panel or paper background.
_PALETTE = [
    "#FF6200",  # ING orange
    "#3498DB",  # azure blue
    "#2ECC71",  # emerald
    "#9B59B6",  # amethyst
    "#F1C40F",  # sun yellow
]

PLN_HOVER = "<b>%{x|%Y-%m-%d}</b><br>%{y:,.2f} PLN<extra></extra>"
PCT_HOVER = "<b>%{x|%Y-%m-%d}</b><br>%{y:.2f}%<extra></extra>"

_FONT_FAMILY = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, '
    '"Helvetica Neue", Arial, sans-serif'
)
_FONT = dict(family=_FONT_FAMILY, size=12, color=TEXT)

_TITLE_STYLE = dict(
    font=dict(size=14, color=TEXT),
    x=0.0,
    xanchor="left",
    y=0.97,
    yanchor="top",
)

_TIME_AXIS = dict(
    type="date",
    showgrid=True,
    gridcolor=GRID,
    zeroline=False,
    color=TEXT,
    tickfont=dict(color=MUTED_TEXT, size=11),
    showspikes=True,
    spikemode="across",
    spikethickness=1,
    spikecolor=NEUTRAL_LINE,
    spikedash="dot",
)

# Slim dark rangeslider — drag the handles to zoom into a sub-window of the
# series. Kept thin (6% of plot height) so it never crowds the chart.
_RANGESLIDER = dict(
    visible=True,
    thickness=0.06,
    bgcolor=PANEL_BG,
    bordercolor=NEUTRAL_LINE,
    borderwidth=1,
)


def _time_axis_with_slider() -> dict[str, Any]:
    return {**_TIME_AXIS, "rangeslider": _RANGESLIDER}

_VALUE_AXIS = dict(
    showgrid=True,
    gridcolor=GRID,
    zeroline=False,
    color=TEXT,
    tickfont=dict(color=MUTED_TEXT, size=11),
    showspikes=True,
    spikemode="across",
    spikethickness=1,
    spikecolor=NEUTRAL_LINE,
    spikedash="dot",
)

_BASE_LAYOUT = dict(
    plot_bgcolor=PANEL_BG,
    paper_bgcolor=BG,
    font=_FONT,
    hovermode="x unified",
    margin=dict(l=70, r=20, t=50, b=55),
    hoverlabel=dict(bgcolor="#1F1F1F", bordercolor=NEUTRAL_LINE, font=dict(color=TEXT)),
    modebar=dict(color=MUTED_TEXT, activecolor=ING_ORANGE, bgcolor="rgba(0,0,0,0)"),
)


def _axis_title(text: str) -> dict[str, Any]:
    """Explicit titles disable Plotly's editable-mode placeholder ('Click to enter…')."""
    return dict(text=text, font=dict(color=MUTED_TEXT, size=12), standoff=14)


def total_value_chart(
    valuations: pd.DataFrame,
    initial_amount: float,
    *,
    annotate_extremes: bool = True,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=valuations.index,
            y=valuations["total_value"],
            mode="lines+markers",
            name="Portfolio value",
            line=dict(color=ING_ORANGE, width=2.5),
            marker=dict(size=5, color=ING_ORANGE),
            hovertemplate=PLN_HOVER,
            showlegend=False,
        )
    )
    fig.add_hline(
        y=initial_amount,
        line_dash="dash",
        line_color=MUTED_TEXT,
        line_width=1,
        annotation_text=f"Initial: {initial_amount:,.0f} PLN",
        annotation_position="bottom right",
        annotation_font=dict(size=10, color=MUTED_TEXT),
    )

    if annotate_extremes:
        daily = valuations["daily_change"].dropna()
        if not daily.empty:
            best_idx = daily.idxmax()
            worst_idx = daily.idxmin()
            fig.add_annotation(
                x=best_idx,
                y=valuations.loc[best_idx, "total_value"],
                text=f"Best · {daily[best_idx]:+,.2f}",
                showarrow=True,
                arrowhead=2,
                arrowsize=0.8,
                arrowcolor=GAIN,
                bgcolor=GAIN,
                bordercolor=GAIN,
                font=dict(color="white", size=10),
                ay=-32,
                borderpad=3,
            )
            fig.add_annotation(
                x=worst_idx,
                y=valuations.loc[worst_idx, "total_value"],
                text=f"Worst · {daily[worst_idx]:+,.2f}",
                showarrow=True,
                arrowhead=2,
                arrowsize=0.8,
                arrowcolor=LOSS,
                bgcolor=LOSS,
                bordercolor=LOSS,
                font=dict(color="white", size=10),
                ay=32,
                borderpad=3,
            )

    fig.update_layout(
        title=dict(text="Portfolio value (PLN)", **_TITLE_STYLE),
        xaxis={**_time_axis_with_slider(), "title": _axis_title("Date")},
        yaxis={**_VALUE_AXIS, "title": _axis_title("Value (PLN)")},
        height=440,
        **_BASE_LAYOUT,
    )
    return fig


def daily_change_chart(valuations: pd.DataFrame) -> go.Figure:
    series = valuations["daily_change"].dropna()
    colors = [GAIN if value >= 0 else LOSS for value in series]
    fig = go.Figure(
        data=[
            go.Bar(
                x=series.index,
                y=series.values,
                marker_color=colors,
                marker_line_width=0,
                name="Daily change",
                hovertemplate=PLN_HOVER,
                showlegend=False,
            )
        ]
    )
    fig.update_layout(
        title=dict(text="Day-on-day change (PLN)", **_TITLE_STYLE),
        xaxis={**_TIME_AXIS, "title": _axis_title("Date")},
        yaxis={**_VALUE_AXIS, "title": _axis_title("Δ value (PLN)")},
        height=340,
        **_BASE_LAYOUT,
    )
    return fig


def drawdown_chart(valuations: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=valuations.index,
            y=valuations["drawdown_pct"],
            mode="lines",
            name="Drawdown",
            line=dict(color=LOSS, width=1.5),
            fill="tozeroy",
            fillcolor="rgba(231, 76, 60, 0.25)",
            hovertemplate=PCT_HOVER,
            showlegend=False,
        )
    )
    fig.update_layout(
        title=dict(text="Drawdown from peak (%)", **_TITLE_STYLE),
        xaxis={**_TIME_AXIS, "title": _axis_title("Date")},
        yaxis={**_VALUE_AXIS, "ticksuffix": "%", "title": _axis_title("Drawdown (%)")},
        height=340,
        **_BASE_LAYOUT,
    )
    return fig


def allocation_pie_chart(labels: list[str], values: list[float], title: str) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=_PALETTE, line=dict(color=BG, width=2)),
                texttemplate="%{label}<br>%{percent}",
                textposition="outside",
                textfont=dict(size=12, color=TEXT),
                hovertemplate="<b>%{label}</b><br>%{value:,.2f} PLN<br>%{percent}<extra></extra>",
                sort=False,
                automargin=True,
            )
        ]
    )
    fig.update_layout(
        title=dict(text=title, **_TITLE_STYLE),
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=BG,
        font=_FONT,
        margin=dict(l=10, r=10, t=50, b=10),
        height=320,
        showlegend=False,
        hoverlabel=dict(bgcolor="#1F1F1F", bordercolor=NEUTRAL_LINE, font=dict(color=TEXT)),
        modebar=dict(color=MUTED_TEXT, activecolor=ING_ORANGE, bgcolor="rgba(0,0,0,0)"),
        uniformtext=dict(mode="show", minsize=10),
    )
    return fig


def returns_distribution_chart(
    valuations: pd.DataFrame,
    var_pln: float,
    cvar_pln: float,
    *,
    confidence: float = 0.95,
) -> go.Figure:
    """Histogram of daily P&L with VaR / CVaR overlays.

    Standard market-risk visual on FX desks: shows the empirical loss
    distribution and where the regulatory tail thresholds sit. VaR and CVaR
    enter the figure as positive PLN losses and are plotted as negative
    P&L lines (loss side of the distribution).
    """
    daily = valuations["daily_change"].dropna()
    bin_count = max(8, min(20, len(daily)))
    fig = go.Figure(
        data=[
            go.Histogram(
                x=daily.values,
                nbinsx=bin_count,
                marker=dict(color=ING_ORANGE, line=dict(color=BG, width=1)),
                opacity=0.85,
                hovertemplate="P&L %{x:+,.2f} PLN<br>%{y} day(s)<extra></extra>",
                name="Daily P&L",
                showlegend=False,
            )
        ]
    )
    pct = int(round(confidence * 100))
    cvar_color = "#C0392B"
    if var_pln > 0:
        fig.add_vline(x=-var_pln, line_dash="dash", line_color=LOSS, line_width=2)
    if cvar_pln > 0:
        fig.add_vline(x=-cvar_pln, line_dash="dot", line_color=cvar_color, line_width=2)
    fig.add_vline(x=0, line_color=NEUTRAL_LINE, line_width=1)

    # Single combined legend pinned to the top-right corner so the two threshold
    # labels never overlap each other or the histogram bars.
    if var_pln > 0 or cvar_pln > 0:
        legend_lines = []
        if var_pln > 0:
            legend_lines.append(
                f"<span style='color:{LOSS}'>┄┄ VaR {pct}% · {var_pln:,.2f} PLN</span>"
            )
        if cvar_pln > 0:
            legend_lines.append(
                f"<span style='color:{cvar_color}'>···· CVaR {pct}% · {cvar_pln:,.2f} PLN</span>"
            )
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.99,
            y=0.97,
            xanchor="right",
            yanchor="top",
            text="<br>".join(legend_lines),
            showarrow=False,
            align="left",
            font=dict(size=10, color=TEXT),
            bgcolor="rgba(22, 22, 22, 0.85)",
            bordercolor=NEUTRAL_LINE,
            borderwidth=1,
            borderpad=6,
        )

    fig.update_layout(
        title=dict(text="Daily P&L distribution with VaR / CVaR (PLN)", **_TITLE_STYLE),
        xaxis=dict(
            showgrid=True,
            gridcolor=GRID,
            zeroline=False,
            color=TEXT,
            tickfont=dict(color=MUTED_TEXT, size=11),
            title=_axis_title("Daily P&L (PLN)"),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=GRID,
            zeroline=False,
            color=TEXT,
            tickfont=dict(color=MUTED_TEXT, size=11),
            title=_axis_title("Frequency (days)"),
        ),
        bargap=0.05,
        height=400,
        showlegend=False,
        **_BASE_LAYOUT,
    )
    return fig


def return_attribution_chart(valuations: pd.DataFrame, allocation: Allocation) -> go.Figure:
    """Waterfall: PLN P&L per currency, terminating in net portfolio result."""
    contributions = {
        code: float(valuations[f"value_{code}"].iloc[-1] - valuations[f"value_{code}"].iloc[0])
        for code in allocation.codes
    }
    total = sum(contributions.values())

    labels = list(contributions.keys()) + ["Net P&L"]
    values = list(contributions.values()) + [total]
    measures = ["relative"] * len(contributions) + ["total"]

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"{value:+,.2f}" for value in values],
            textposition="outside",
            textfont=dict(size=11, color=TEXT),
            connector={"line": {"color": NEUTRAL_LINE, "dash": "dot", "width": 1}},
            increasing={"marker": {"color": GAIN}},
            decreasing={"marker": {"color": LOSS}},
            totals={"marker": {"color": ING_ORANGE}},
            hovertemplate="<b>%{x}</b><br>%{y:+,.2f} PLN<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text="Return attribution by currency (PLN)", **_TITLE_STYLE),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            color=TEXT,
            tickfont=dict(color=TEXT, size=11),
            title=_axis_title("Currency"),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=GRID,
            zeroline=True,
            zerolinecolor=NEUTRAL_LINE,
            color=TEXT,
            tickfont=dict(color=MUTED_TEXT, size=11),
            title=_axis_title("Contribution (PLN)"),
        ),
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=BG,
        font=_FONT,
        margin=dict(l=70, r=20, t=50, b=55),
        height=400,
        showlegend=False,
        hoverlabel=dict(bgcolor="#1F1F1F", bordercolor=NEUTRAL_LINE, font=dict(color=TEXT)),
        modebar=dict(color=MUTED_TEXT, activecolor=ING_ORANGE, bgcolor="rgba(0,0,0,0)"),
    )
    return fig
