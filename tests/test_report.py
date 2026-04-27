"""Tests for the single-page report builder and exporter."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from portfolio_sim.allocation import Allocation
from portfolio_sim.metrics import PortfolioMetrics
from portfolio_sim.portfolio import SimulationResult
from portfolio_sim.report import build_one_pager, export_one_pager


@pytest.fixture
def sample_result(basic_allocation: Allocation) -> SimulationResult:
    index = pd.date_range("2026-03-02", periods=4, freq="D")
    valuations = pd.DataFrame(
        {
            "value_USD": [300.0, 305.0, 302.0, 310.0],
            "value_EUR": [400.0, 402.0, 405.0, 410.0],
            "value_HUF": [300.0, 298.0, 305.0, 305.0],
        },
        index=index,
    )
    valuations["total_value"] = valuations.filter(like="value_").sum(axis=1)
    valuations["cumulative_pnl"] = valuations["total_value"] - 1000.0
    valuations["daily_change"] = valuations["total_value"].diff()
    rolling_peak = valuations["total_value"].cummax()
    valuations["drawdown_pct"] = (valuations["total_value"] / rolling_peak - 1.0) * 100.0

    return SimulationResult(
        valuations=valuations,
        initial_amount=1000.0,
        allocation=basic_allocation,
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 5),
    )


@pytest.fixture
def sample_metrics() -> PortfolioMetrics:
    return PortfolioMetrics(
        initial_value=1000.0,
        final_value=1025.0,
        total_return_pln=25.0,
        total_return_pct=2.5,
        best_day=pd.Timestamp("2026-03-05"),
        best_day_value=8.0,
        worst_day=pd.Timestamp("2026-03-04"),
        worst_day_value=-3.0,
        max_drawdown_pct=-0.5,
        realized_volatility_pct=0.4,
        holding_days=3,
    )


def test_build_one_pager_renders_four_panels(
    sample_result: SimulationResult, sample_metrics: PortfolioMetrics
) -> None:
    fig = build_one_pager(sample_result, sample_metrics)

    assert isinstance(fig, go.Figure)
    # 2x2 grid: line + bar + drawdown + pie
    assert len(fig.data) == 4
    trace_types = {trace.type for trace in fig.data}
    assert trace_types == {"scatter", "bar", "pie"}


def test_export_one_pager_writes_html(
    tmp_path: Path, sample_result: SimulationResult, sample_metrics: PortfolioMetrics
) -> None:
    output = tmp_path / "report.html"

    written = export_one_pager(sample_result, sample_metrics, output)

    assert written.exists()
    assert written.suffix == ".html"
    body = written.read_text(encoding="utf-8")
    assert "plotly" in body.lower()


def test_export_one_pager_creates_parent_directories(
    tmp_path: Path, sample_result: SimulationResult, sample_metrics: PortfolioMetrics
) -> None:
    output = tmp_path / "nested" / "deep" / "report.html"

    written = export_one_pager(sample_result, sample_metrics, output)

    assert written.exists()
    assert written.parent.is_dir()
