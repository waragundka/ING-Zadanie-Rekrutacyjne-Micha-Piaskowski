"""KPI extraction."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_sim.metrics import compute_metrics


def _build_valuations(values: list[float], start: str = "2026-03-02") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(values), freq="D")
    frame = pd.DataFrame({"total_value": values}, index=index)
    frame["cumulative_pnl"] = frame["total_value"] - values[0]
    frame["daily_change"] = frame["total_value"].diff()
    rolling_peak = frame["total_value"].cummax()
    frame["drawdown_pct"] = (frame["total_value"] / rolling_peak - 1.0) * 100.0
    return frame


def test_metrics_track_total_return() -> None:
    valuations = _build_valuations([1000.0, 1010.0, 1020.0, 1030.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.initial_value == pytest.approx(1000.0)
    assert metrics.final_value == pytest.approx(1030.0)
    assert metrics.total_return_pln == pytest.approx(30.0)
    assert metrics.total_return_pct == pytest.approx(3.0)


def test_best_and_worst_day_exclude_day_one() -> None:
    # Day 1 has no prior observation: NaN diff. With monotonic decline,
    # an old buggy implementation that filled day 1 with 0 would return day 1
    # as "best day" — the correct answer is the smallest absolute drop.
    valuations = _build_valuations([1000.0, 990.0, 985.0, 980.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.best_day == pd.Timestamp("2026-03-04")  # -5 PLN — smallest loss
    assert metrics.best_day_value == pytest.approx(-5.0)
    assert metrics.worst_day == pd.Timestamp("2026-03-03")  # -10 PLN
    assert metrics.worst_day_value == pytest.approx(-10.0)


def test_max_drawdown_picks_deepest_trough() -> None:
    valuations = _build_valuations([1000.0, 1100.0, 990.0, 1050.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    # Trough at 990 after peak of 1100: -10%.
    assert metrics.max_drawdown_pct == pytest.approx(-10.0)


def test_realized_volatility_is_not_annualized() -> None:
    # Two-day return series of [+1%, -1%] -> stdev ~ 0.01414 -> 1.414% (raw, not * sqrt(252)).
    valuations = _build_valuations([1000.0, 1010.0, 999.9])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    expected = np.std([0.01, -10.1 / 1010.0], ddof=1) * 100.0
    assert metrics.realized_volatility_pct == pytest.approx(expected, rel=1e-3)


def test_holding_days_count_excludes_day_one() -> None:
    valuations = _build_valuations([1000.0, 1010.0, 1020.0])  # 3 entries, 2 holding days

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.holding_days == 2


def test_sharpe_and_sortino_on_mixed_returns() -> None:
    # Series with both gains and losses → both ratios well-defined.
    valuations = _build_valuations([1000.0, 1010.0, 1005.0, 1020.0, 1012.0, 1030.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    returns = valuations["total_value"].pct_change().dropna()
    expected_sharpe = float(returns.mean() / returns.std())
    downside = returns[returns < 0]
    expected_sortino = float(returns.mean() / np.sqrt((downside ** 2).mean()))

    assert metrics.sharpe_ratio == pytest.approx(expected_sharpe, rel=1e-6)
    assert metrics.sortino_ratio == pytest.approx(expected_sortino, rel=1e-6)


def test_sharpe_returns_none_on_constant_series() -> None:
    # Flat returns → stdev == 0 → ratio undefined.
    valuations = _build_valuations([1000.0, 1000.0, 1000.0, 1000.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None  # No negative returns either.


def test_sortino_returns_none_when_no_losses() -> None:
    # Monotonically rising returns → no downside → Sortino undefined.
    valuations = _build_valuations([1000.0, 1010.0, 1025.0, 1040.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.sortino_ratio is None
    assert metrics.sharpe_ratio is not None  # Sharpe still works on positive vol.


def test_var_and_cvar_are_positive_loss_magnitudes() -> None:
    # Daily P&L: NaN, -10, -20, +5, -50, +8 (5 valid observations).
    # 95th-percentile loss should land near -50; CVaR averages the tail.
    valuations = _build_valuations([1000.0, 990.0, 970.0, 975.0, 925.0, 933.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.var_95_pln >= 0.0
    assert metrics.cvar_95_pln >= metrics.var_95_pln  # CVaR ≥ VaR by construction.
    assert metrics.var_95_pln <= 50.0  # Bounded by largest observed loss.
    assert metrics.cvar_95_pln <= 50.0


def test_var_is_zero_when_no_losses() -> None:
    # All daily moves are positive → no tail loss → VaR/CVaR = 0.
    valuations = _build_valuations([1000.0, 1010.0, 1020.0, 1030.0, 1040.0])

    metrics = compute_metrics(valuations, initial_amount=1000.0)

    assert metrics.var_95_pln == pytest.approx(0.0)
    assert metrics.cvar_95_pln == pytest.approx(0.0)
