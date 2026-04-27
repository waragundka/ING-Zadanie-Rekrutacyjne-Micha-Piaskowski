"""Pipeline that prices a fixed currency basket day-by-day from NBP quotes."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from portfolio_sim.allocation import Allocation
from portfolio_sim.nbp_client import NBPClient

log = logging.getLogger(__name__)

DEFAULT_HOLDING_DAYS = 30


@dataclass(frozen=True)
class SimulationResult:
    """Output of a single end-to-end simulation run."""

    valuations: pd.DataFrame
    initial_amount: float
    allocation: Allocation
    start_date: date
    end_date: date


class PortfolioSimulator:
    """Price a buy-and-hold currency basket using NBP mid-rates.

    Per the assignment: PLN is converted into the basket once on `start`,
    held for `holding_days` calendar days, and revalued daily. No further
    transactions occur during the holding period.
    """

    def __init__(self, client: NBPClient) -> None:
        self._client = client

    def run(
        self,
        amount: float,
        allocation: Allocation,
        start: date,
        holding_days: int = DEFAULT_HOLDING_DAYS,
    ) -> SimulationResult:
        if amount <= 0:
            raise ValueError(f"Initial amount must be positive (got {amount}).")
        if holding_days <= 0:
            raise ValueError(f"Holding period must be positive (got {holding_days}).")

        end = start + timedelta(days=holding_days)
        log.info(
            "Simulating %.2f PLN over %s..%s across %s.",
            amount,
            start,
            end,
            ", ".join(allocation.codes),
        )

        rates = self._fetch_basket(allocation, start, end)
        aligned = self._align_to_calendar(rates, start, end)
        priced = self._price_holdings(aligned, amount, allocation)
        enriched = self._enrich_with_metrics(priced, amount)

        return SimulationResult(
            valuations=enriched,
            initial_amount=amount,
            allocation=allocation,
            start_date=start,
            end_date=end,
        )

    def _fetch_basket(
        self, allocation: Allocation, start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        return {code: self._client.fetch_rates(code, start, end) for code in allocation.codes}

    @staticmethod
    def _align_to_calendar(
        rates: dict[str, pd.DataFrame], start: date, end: date
    ) -> dict[str, pd.Series]:
        """Reindex each currency on a daily calendar; forward-fill non-business days."""
        calendar = pd.date_range(start=start, end=end, freq="D")
        aligned: dict[str, pd.Series] = {}

        for code, frame in rates.items():
            series = frame.set_index("date")["rate"].astype(float)
            full_index = series.index.union(calendar).sort_values()
            series = series.reindex(full_index).ffill().loc[calendar]

            missing = series.index[series.isna()]
            if len(missing) > 0:
                raise ValueError(
                    f"No published {code} quote on or before {missing[0].date()}; "
                    "extend the lookback window."
                )
            aligned[code] = series

        return aligned

    @staticmethod
    def _price_holdings(
        aligned: dict[str, pd.Series], amount: float, allocation: Allocation
    ) -> pd.DataFrame:
        weights = allocation.as_dict()
        columns: dict[str, pd.Series] = {}
        for code, rate_series in aligned.items():
            buy_rate = rate_series.iloc[0]
            units_held = (amount * weights[code]) / buy_rate
            columns[f"value_{code}"] = units_held * rate_series
        return pd.DataFrame(columns)

    @staticmethod
    def _enrich_with_metrics(valuations: pd.DataFrame, initial_amount: float) -> pd.DataFrame:
        out = valuations.copy()
        out["total_value"] = out.filter(like="value_").sum(axis=1)
        out["cumulative_pnl"] = out["total_value"] - initial_amount
        # Day 1 has no prior observation — leave NaN so downstream metrics ignore it.
        out["daily_change"] = out["total_value"].diff()
        rolling_peak = out["total_value"].cummax()
        out["drawdown_pct"] = (out["total_value"] / rolling_peak - 1.0) * 100.0
        return out
