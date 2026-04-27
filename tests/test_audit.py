"""Audit-trail JSON manifest."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from portfolio_sim.allocation import Allocation
from portfolio_sim.audit import _input_fingerprint, record_run
from portfolio_sim.metrics import PortfolioMetrics
from portfolio_sim.portfolio import SimulationResult


def _make_result(allocation: Allocation) -> SimulationResult:
    index = pd.date_range("2026-03-02", periods=3, freq="D")
    valuations = pd.DataFrame(
        {
            "value_USD": [300.0, 310.0, 305.0],
            "value_EUR": [400.0, 405.0, 410.0],
            "value_HUF": [300.0, 295.0, 300.0],
            "total_value": [1000.0, 1010.0, 1015.0],
            "cumulative_pnl": [0.0, 10.0, 15.0],
            "daily_change": [float("nan"), 10.0, 5.0],
            "drawdown_pct": [0.0, 0.0, 0.0],
        },
        index=index,
    )
    return SimulationResult(
        valuations=valuations,
        initial_amount=1000.0,
        allocation=allocation,
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 4),
    )


def _make_metrics() -> PortfolioMetrics:
    return PortfolioMetrics(
        initial_value=1000.0,
        final_value=1015.0,
        total_return_pln=15.0,
        total_return_pct=1.5,
        best_day=pd.Timestamp("2026-03-03"),
        best_day_value=10.0,
        worst_day=pd.Timestamp("2026-03-04"),
        worst_day_value=5.0,
        max_drawdown_pct=0.0,
        realized_volatility_pct=0.5,
        holding_days=2,
    )


def test_record_run_writes_well_formed_manifest(
    tmp_path: Path, basic_allocation: Allocation
) -> None:
    output = record_run(_make_result(basic_allocation), _make_metrics(), runs_dir=tmp_path)

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["inputs"]["initial_amount_pln"] == 1000.0
    assert payload["inputs"]["allocation"] == {"USD": 0.30, "EUR": 0.40, "HUF": 0.30}
    assert payload["inputs"]["holding_days"] == 2
    assert payload["metrics"]["best_day"] == "2026-03-03"
    assert payload["metrics"]["worst_day"] == "2026-03-04"


def test_record_run_filename_carries_input_hash(
    tmp_path: Path, basic_allocation: Allocation
) -> None:
    output = record_run(_make_result(basic_allocation), _make_metrics(), runs_dir=tmp_path)
    expected_hash = _input_fingerprint(_make_result(basic_allocation))

    assert expected_hash in output.name
    assert output.name.endswith(".json")


def test_input_fingerprint_is_deterministic(basic_allocation: Allocation) -> None:
    assert _input_fingerprint(_make_result(basic_allocation)) == _input_fingerprint(
        _make_result(basic_allocation)
    )


def test_input_fingerprint_changes_with_allocation(basic_allocation: Allocation) -> None:
    other_allocation = Allocation.from_percentages({"USD": 50, "EUR": 30, "HUF": 20})
    base = _make_result(basic_allocation)
    other = SimulationResult(
        valuations=base.valuations,
        initial_amount=base.initial_amount,
        allocation=other_allocation,
        start_date=base.start_date,
        end_date=base.end_date,
    )

    assert _input_fingerprint(base) != _input_fingerprint(other)


def test_record_run_creates_nested_directory(
    tmp_path: Path, basic_allocation: Allocation
) -> None:
    runs_dir = tmp_path / "nested" / "audit"

    record_run(_make_result(basic_allocation), _make_metrics(), runs_dir=runs_dir)

    assert runs_dir.is_dir()
    assert any(runs_dir.iterdir())
