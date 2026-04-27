"""Shared pytest fixtures."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from portfolio_sim.allocation import Allocation


@pytest.fixture
def basic_allocation() -> Allocation:
    return Allocation.from_percentages({"USD": 30.0, "EUR": 40.0, "HUF": 30.0})


@pytest.fixture
def usd_rates_frame() -> pd.DataFrame:
    """A 5-business-day USD rate frame (Mon-Fri)."""
    dates = pd.to_datetime(
        ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]
    )
    return pd.DataFrame({"date": dates, "rate": [4.00, 4.05, 4.02, 4.10, 4.08]})


@pytest.fixture
def fake_nbp_response() -> dict:
    return {
        "table": "A",
        "currency": "dolar amerykański",
        "code": "USD",
        "rates": [
            {"no": "041/A/NBP/2026", "effectiveDate": "2026-03-02", "mid": 4.0000},
            {"no": "042/A/NBP/2026", "effectiveDate": "2026-03-03", "mid": 4.0500},
            {"no": "043/A/NBP/2026", "effectiveDate": "2026-03-04", "mid": 4.0200},
        ],
    }


@pytest.fixture
def simulation_window() -> tuple[date, date]:
    start = date(2026, 3, 2)
    return start, start + timedelta(days=4)
