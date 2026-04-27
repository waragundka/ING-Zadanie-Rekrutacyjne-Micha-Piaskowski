"""Smoke tests for Plotly chart builders.

The dashboard renders these figures live, so the priority here is structural
correctness — every builder returns a Figure with the expected trace shape and
axis configuration. We do not assert pixel-level rendering.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from portfolio_sim.allocation import Allocation
from portfolio_sim.visualizer import (
    allocation_pie_chart,
    daily_change_chart,
    drawdown_chart,
    return_attribution_chart,
    returns_distribution_chart,
    total_value_chart,
)


@pytest.fixture
def sample_valuations() -> pd.DataFrame:
    index = pd.date_range("2026-03-02", periods=5, freq="D")
    frame = pd.DataFrame(
        {
            "value_USD": [300.0, 305.0, 302.0, 308.0, 310.0],
            "value_EUR": [400.0, 402.0, 405.0, 408.0, 410.0],
            "value_HUF": [300.0, 298.0, 305.0, 302.0, 305.0],
        },
        index=index,
    )
    frame["total_value"] = frame.filter(like="value_").sum(axis=1)
    frame["cumulative_pnl"] = frame["total_value"] - 1000.0
    frame["daily_change"] = frame["total_value"].diff()
    rolling_peak = frame["total_value"].cummax()
    frame["drawdown_pct"] = (frame["total_value"] / rolling_peak - 1.0) * 100.0
    return frame


@pytest.fixture
def sample_allocation() -> Allocation:
    return Allocation.from_percentages({"USD": 30.0, "EUR": 40.0, "HUF": 30.0})


def test_total_value_chart_builds(sample_valuations: pd.DataFrame) -> None:
    fig = total_value_chart(sample_valuations, initial_amount=1000.0)

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].type == "scatter"
    assert fig.layout.xaxis.rangeslider.visible is True


def test_total_value_chart_annotates_extremes_by_default(sample_valuations: pd.DataFrame) -> None:
    fig = total_value_chart(sample_valuations, initial_amount=1000.0)

    # 1 hline annotation + best + worst = 3
    assert len(fig.layout.annotations) == 3


def test_total_value_chart_skips_extremes_when_disabled(sample_valuations: pd.DataFrame) -> None:
    fig = total_value_chart(sample_valuations, initial_amount=1000.0, annotate_extremes=False)

    # only the hline label remains
    assert len(fig.layout.annotations) == 1


def test_total_value_chart_handles_single_day_series() -> None:
    index = pd.date_range("2026-03-02", periods=1, freq="D")
    valuations = pd.DataFrame(
        {
            "total_value": [1000.0],
            "cumulative_pnl": [0.0],
            "daily_change": [float("nan")],
            "drawdown_pct": [0.0],
        },
        index=index,
    )

    fig = total_value_chart(valuations, initial_amount=1000.0)

    assert isinstance(fig, go.Figure)
    # No best/worst arrows when daily_change is empty after dropna.
    assert len(fig.layout.annotations) == 1


def test_daily_change_chart_builds(sample_valuations: pd.DataFrame) -> None:
    fig = daily_change_chart(sample_valuations)

    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "bar"
    assert fig.layout.yaxis.title.text == "Δ value (PLN)"


def test_drawdown_chart_uses_percent_suffix(sample_valuations: pd.DataFrame) -> None:
    fig = drawdown_chart(sample_valuations)

    assert isinstance(fig, go.Figure)
    assert fig.layout.yaxis.ticksuffix == "%"


def test_allocation_pie_chart_builds() -> None:
    fig = allocation_pie_chart(["USD", "EUR", "HUF"], [300.0, 400.0, 300.0], "Day 1")

    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "pie"
    assert fig.layout.title.text == "Day 1"


def test_return_attribution_waterfall_includes_net_total(
    sample_valuations: pd.DataFrame, sample_allocation: Allocation
) -> None:
    fig = return_attribution_chart(sample_valuations, sample_allocation)

    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "waterfall"
    # n currencies + 1 net total bar
    assert len(fig.data[0].x) == len(sample_allocation.codes) + 1
    assert list(fig.data[0].x)[-1] == "Net P&L"
    assert fig.data[0].measure[-1] == "total"


def test_returns_distribution_chart_renders_var_and_cvar_overlays(
    sample_valuations: pd.DataFrame,
) -> None:
    fig = returns_distribution_chart(sample_valuations, var_pln=3.0, cvar_pln=5.0)

    assert isinstance(fig, go.Figure)
    assert fig.data[0].type == "histogram"
    # 3 vlines: VaR, CVaR, zero. Each lives in layout.shapes.
    assert len(fig.layout.shapes) == 3
    assert fig.layout.xaxis.title.text == "Daily P&L (PLN)"
    assert fig.layout.yaxis.title.text == "Frequency (days)"


def test_returns_distribution_chart_omits_overlays_when_no_loss(
    sample_valuations: pd.DataFrame,
) -> None:
    # No tail losses observed → only the zero reference line is drawn.
    fig = returns_distribution_chart(sample_valuations, var_pln=0.0, cvar_pln=0.0)

    assert len(fig.layout.shapes) == 1
