"""End-to-end pricing pipeline."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from portfolio_sim.allocation import Allocation
from portfolio_sim.portfolio import PortfolioSimulator, SimulationResult


class _StubClient:
    """Returns a fixed rate frame per currency — bypasses HTTP entirely."""

    def __init__(self, rates: dict[str, pd.DataFrame]) -> None:
        self._rates = rates
        self.calls: list[tuple[str, date, date]] = []

    def fetch_rates(self, code: str, start: date, end: date) -> pd.DataFrame:
        self.calls.append((code, start, end))
        return self._rates[code].copy()


def _make_rate_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {"date": pd.to_datetime([r[0] for r in rows]), "rate": [r[1] for r in rows]}
    )


def test_run_returns_simulation_result(basic_allocation: Allocation) -> None:
    rates = {
        "USD": _make_rate_frame([("2026-03-02", 4.00), ("2026-03-03", 4.10)]),
        "EUR": _make_rate_frame([("2026-03-02", 4.30), ("2026-03-03", 4.32)]),
        "HUF": _make_rate_frame([("2026-03-02", 0.011), ("2026-03-03", 0.012)]),
    }
    simulator = PortfolioSimulator(_StubClient(rates))

    result = simulator.run(
        amount=1000.0, allocation=basic_allocation, start=date(2026, 3, 2), holding_days=1
    )

    assert isinstance(result, SimulationResult)
    assert result.initial_amount == 1000.0
    assert {"value_USD", "value_EUR", "value_HUF", "total_value"}.issubset(result.valuations.columns)


def test_alignment_forward_fills_weekend_gaps(basic_allocation: Allocation) -> None:
    # Friday 2026-03-06 quote → must roll forward over Sat/Sun → Mon 03-09.
    rates = {
        code: _make_rate_frame([("2026-03-06", 4.00), ("2026-03-09", 4.10)])
        for code in basic_allocation.codes
    }
    simulator = PortfolioSimulator(_StubClient(rates))

    result = simulator.run(
        amount=1000.0,
        allocation=basic_allocation,
        start=date(2026, 3, 6),
        holding_days=3,
    )

    saturday = pd.Timestamp("2026-03-07")
    sunday = pd.Timestamp("2026-03-08")
    assert result.valuations.loc[saturday, "value_USD"] == pytest.approx(
        result.valuations.loc[pd.Timestamp("2026-03-06"), "value_USD"]
    )
    assert result.valuations.loc[sunday, "value_USD"] == pytest.approx(
        result.valuations.loc[pd.Timestamp("2026-03-06"), "value_USD"]
    )


def test_initial_total_value_matches_amount(basic_allocation: Allocation) -> None:
    rates = {
        code: _make_rate_frame([("2026-03-02", 4.0), ("2026-03-03", 4.0)])
        for code in basic_allocation.codes
    }
    simulator = PortfolioSimulator(_StubClient(rates))

    result = simulator.run(
        amount=1000.0, allocation=basic_allocation, start=date(2026, 3, 2), holding_days=1
    )

    assert result.valuations["total_value"].iloc[0] == pytest.approx(1000.0)
    assert result.valuations["cumulative_pnl"].iloc[0] == pytest.approx(0.0)


def test_drawdown_is_zero_when_value_only_grows(basic_allocation: Allocation) -> None:
    rising = [("2026-03-02", 4.0), ("2026-03-03", 4.1), ("2026-03-04", 4.2), ("2026-03-05", 4.3)]
    rates = {code: _make_rate_frame(rising) for code in basic_allocation.codes}
    simulator = PortfolioSimulator(_StubClient(rates))

    result = simulator.run(
        amount=1000.0, allocation=basic_allocation, start=date(2026, 3, 2), holding_days=3
    )

    assert (result.valuations["drawdown_pct"] <= 0).all()
    assert result.valuations["drawdown_pct"].min() == pytest.approx(0.0)


def test_day_one_daily_change_is_nan(basic_allocation: Allocation) -> None:
    rates = {code: _make_rate_frame([("2026-03-02", 4.0), ("2026-03-03", 4.1)]) for code in basic_allocation.codes}
    simulator = PortfolioSimulator(_StubClient(rates))

    result = simulator.run(
        amount=1000.0, allocation=basic_allocation, start=date(2026, 3, 2), holding_days=1
    )

    assert pd.isna(result.valuations["daily_change"].iloc[0])
    assert not pd.isna(result.valuations["daily_change"].iloc[1])


def test_run_rejects_non_positive_amount(basic_allocation: Allocation) -> None:
    simulator = PortfolioSimulator(_StubClient({}))

    with pytest.raises(ValueError, match="must be positive"):
        simulator.run(amount=0.0, allocation=basic_allocation, start=date(2026, 3, 2))


def test_alignment_raises_when_no_quote_before_start(basic_allocation: Allocation) -> None:
    # First quote is AFTER the requested start — leaves day 1 NaN even after ffill.
    rates = {code: _make_rate_frame([("2026-03-05", 4.0)]) for code in basic_allocation.codes}
    simulator = PortfolioSimulator(_StubClient(rates))

    with pytest.raises(ValueError, match="extend the lookback"):
        simulator.run(
            amount=1000.0, allocation=basic_allocation, start=date(2026, 3, 2), holding_days=5
        )


def test_long_weekend_keeps_value_flat_and_daily_change_zero(
    basic_allocation: Allocation,
) -> None:
    # Friday 2026-05-01 quote, then nothing until Tuesday 2026-05-05 — Polish
    # public holidays (May 1, May 3) chained with a weekend produce a 3-day gap.
    # Forward-fill must keep portfolio value frozen across Sat/Sun/Mon, with
    # daily_change == 0 on each non-business day.
    rates = {
        code: _make_rate_frame([("2026-05-01", 4.00), ("2026-05-05", 4.20)])
        for code in basic_allocation.codes
    }
    simulator = PortfolioSimulator(_StubClient(rates))

    result = simulator.run(
        amount=1000.0,
        allocation=basic_allocation,
        start=date(2026, 5, 1),
        holding_days=4,
    )

    friday = pd.Timestamp("2026-05-01")
    saturday = pd.Timestamp("2026-05-02")
    sunday = pd.Timestamp("2026-05-03")
    monday = pd.Timestamp("2026-05-04")
    tuesday = pd.Timestamp("2026-05-05")

    friday_total = result.valuations.loc[friday, "total_value"]
    for day in (saturday, sunday, monday):
        assert result.valuations.loc[day, "total_value"] == pytest.approx(friday_total)
        # daily_change is computed via diff(); on a flat day it MUST be 0
        # (not NaN — only day 1 is NaN by design).
        assert result.valuations.loc[day, "daily_change"] == pytest.approx(0.0)
        assert result.valuations.loc[day, "cumulative_pnl"] == pytest.approx(
            result.valuations.loc[friday, "cumulative_pnl"]
        )

    # First real publication after the gap moves the value again.
    assert result.valuations.loc[tuesday, "total_value"] != pytest.approx(friday_total)
    assert result.valuations.loc[tuesday, "daily_change"] != pytest.approx(0.0)
