"""Compose a single-page summary figure for offline distribution."""
from __future__ import annotations

import logging
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from portfolio_sim.metrics import PortfolioMetrics
from portfolio_sim.portfolio import SimulationResult
from portfolio_sim.visualizer import (
    BG,
    GAIN,
    GRID,
    ING_ORANGE,
    LOSS,
    MUTED_TEXT,
    NEUTRAL_LINE,
    PANEL_BG,
    TEXT,
    _PALETTE,
)

log = logging.getLogger(__name__)


def build_one_pager(result: SimulationResult, metrics: PortfolioMetrics) -> go.Figure:
    """Render the key dashboard panels onto a single 2x2 figure."""
    valuations = result.valuations
    allocation = result.allocation

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Portfolio value (PLN)",
            "Day-on-day change (PLN)",
            "Drawdown from peak (%)",
            "Final basket composition",
        ),
        specs=[[{"type": "xy"}, {"type": "xy"}], [{"type": "xy"}, {"type": "domain"}]],
        vertical_spacing=0.18,
        horizontal_spacing=0.12,
    )

    fig.add_trace(
        go.Scatter(
            x=valuations.index,
            y=valuations["total_value"],
            mode="lines",
            line=dict(color=ING_ORANGE, width=2.5),
            name="Total value",
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    fig.add_hline(
        y=result.initial_amount,
        line_dash="dash",
        line_color=MUTED_TEXT,
        row=1,
        col=1,
    )

    daily = valuations["daily_change"].dropna()
    fig.add_trace(
        go.Bar(
            x=daily.index,
            y=daily.values,
            marker_color=[GAIN if value >= 0 else LOSS for value in daily],
            name="Daily change",
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Scatter(
            x=valuations.index,
            y=valuations["drawdown_pct"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=LOSS, width=1.5),
            fillcolor="rgba(200, 16, 46, 0.2)",
            name="Drawdown",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    final_values = [valuations[f"value_{code}"].iloc[-1] for code in allocation.codes]
    fig.add_trace(
        go.Pie(
            labels=list(allocation.codes),
            values=final_values,
            hole=0.4,
            marker=dict(colors=_PALETTE, line=dict(color=BG, width=2)),
            textinfo="label+percent",
            textfont=dict(color=TEXT, size=12),
            showlegend=False,
        ),
        row=2,
        col=2,
    )

    sharpe_str = (
        f"{metrics.sharpe_ratio:.2f}" if metrics.sharpe_ratio is not None else "n/a"
    )
    title = (
        f"NBP currency basket — {result.initial_amount:,.0f} PLN, "
        f"{result.start_date} → {result.end_date}<br>"
        f"<sub>Final {metrics.final_value:,.2f} PLN "
        f"({metrics.total_return_pct:+.2f}%) · "
        f"Max DD {metrics.max_drawdown_pct:.2f}% · "
        f"Vol {metrics.realized_volatility_pct:.2f}% · "
        f"Sharpe {sharpe_str} · "
        f"VaR95 {metrics.var_95_pln:,.2f} PLN · "
        f"CVaR95 {metrics.cvar_95_pln:,.2f} PLN</sub>"
    )
    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center", font=dict(color=TEXT, size=15)),
        plot_bgcolor=PANEL_BG,
        paper_bgcolor=BG,
        font=dict(color=TEXT),
        height=820,
        width=1200,
        margin=dict(l=40, r=40, t=110, b=40),
    )
    fig.update_xaxes(
        gridcolor=GRID, zeroline=False, color=TEXT, tickfont=dict(color=MUTED_TEXT)
    )
    fig.update_yaxes(
        gridcolor=GRID,
        zeroline=True,
        zerolinecolor=NEUTRAL_LINE,
        color=TEXT,
        tickfont=dict(color=MUTED_TEXT),
    )
    for annotation in fig.layout.annotations:
        annotation.font = dict(color=TEXT, size=12)
    return fig


def export_one_pager(
    result: SimulationResult,
    metrics: PortfolioMetrics,
    output_path: Path,
) -> Path:
    """Write the one-pager as PNG/PDF/SVG (extension drives format).

    Raster/PDF/SVG export requires the optional `kaleido` engine. HTML output
    has no extra dependency and is always available.
    """
    fig = build_one_pager(result, metrics)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = output_path.suffix.lower()
    if suffix in {".html", ".htm"}:
        fig.write_html(output_path, include_plotlyjs="cdn")
    else:
        try:
            fig.write_image(output_path)
        except Exception as exc:
            raise RuntimeError(
                f"Could not write {output_path.suffix} report — install the "
                "`kaleido` engine (`pip install portfolio-sim[report]`) or use "
                "an .html output path."
            ) from exc

    log.info("Wrote one-pager to %s", output_path)
    return output_path
