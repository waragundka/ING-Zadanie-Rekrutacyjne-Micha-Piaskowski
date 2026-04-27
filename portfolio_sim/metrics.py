"""KPI extraction from a simulated valuation series."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

VAR_CONFIDENCE = 0.95


@dataclass(frozen=True)
class PortfolioMetrics:
    initial_value: float
    final_value: float
    total_return_pln: float
    total_return_pct: float
    best_day: pd.Timestamp | None
    best_day_value: float
    worst_day: pd.Timestamp | None
    worst_day_value: float
    max_drawdown_pct: float
    realized_volatility_pct: float
    holding_days: int
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    var_95_pln: float = 0.0
    cvar_95_pln: float = 0.0


def _historical_var_cvar(
    daily_pnl: pd.Series, confidence: float = VAR_CONFIDENCE
) -> tuple[float, float]:
    """Historical 1-day VaR and CVaR/Expected Shortfall, both as positive PLN losses.

    VaR_α: empirical (1−α) percentile of the daily P&L series — the loss
    threshold that the portfolio should breach with probability ≤ (1−α).
    CVaR_α (Expected Shortfall): average of P&L observations at or below the
    VaR threshold — Basel III FRTB replaced VaR with ES for market-risk
    capital because ES is sub-additive and captures tail severity.
    Both returned as positive numbers (loss magnitudes).
    """
    if daily_pnl.empty:
        return 0.0, 0.0
    threshold = float(np.percentile(daily_pnl, (1.0 - confidence) * 100.0))
    var_loss = max(0.0, -threshold)
    tail = daily_pnl[daily_pnl <= threshold]
    if tail.empty:
        return var_loss, var_loss
    cvar_loss = max(var_loss, -float(tail.mean()))
    return var_loss, cvar_loss


def _sharpe_ratio(returns: pd.Series) -> float | None:
    """Realized Sharpe (rf=0): mean / stdev of daily returns. NOT annualized."""
    if returns.empty:
        return None
    stdev = float(returns.std())
    if stdev <= 0:
        return None
    return float(returns.mean()) / stdev


def _sortino_ratio(returns: pd.Series) -> float | None:
    """Realized Sortino: mean / downside-only deviation (target = 0)."""
    if returns.empty:
        return None
    downside = returns[returns < 0]
    if downside.empty:
        return None
    downside_dev = float(np.sqrt((downside ** 2).mean()))
    if downside_dev <= 0:
        return None
    return float(returns.mean()) / downside_dev


def compute_metrics(valuations: pd.DataFrame, initial_amount: float) -> PortfolioMetrics:
    """Aggregate KPIs from an enriched valuation frame.

    Day 1 carries no prior observation, so its `daily_change` is NaN by design
    and is excluded from best/worst-day statistics. Volatility, Sharpe and
    Sortino use raw daily returns and are NOT annualized — a 30-day sample
    makes √252 scaling statistically unreliable. VaR/CVaR are historical
    (empirical) at 95% confidence over a 1-day horizon, returned as positive
    PLN loss magnitudes (banking convention). CVaR is the Basel III FRTB
    Expected Shortfall measure that replaced VaR for market-risk capital.
    """
    daily_change = valuations["daily_change"].dropna()
    daily_returns = valuations["total_value"].pct_change().dropna()

    var_95_pln, cvar_95_pln = _historical_var_cvar(daily_change)

    return PortfolioMetrics(
        initial_value=float(valuations["total_value"].iloc[0]),
        final_value=float(valuations["total_value"].iloc[-1]),
        total_return_pln=float(valuations["cumulative_pnl"].iloc[-1]),
        total_return_pct=float(valuations["cumulative_pnl"].iloc[-1] / initial_amount * 100.0),
        best_day=daily_change.idxmax() if not daily_change.empty else None,
        best_day_value=float(daily_change.max()) if not daily_change.empty else 0.0,
        worst_day=daily_change.idxmin() if not daily_change.empty else None,
        worst_day_value=float(daily_change.min()) if not daily_change.empty else 0.0,
        max_drawdown_pct=float(valuations["drawdown_pct"].min()),
        realized_volatility_pct=(
            float(daily_returns.std() * 100.0) if not daily_returns.empty else 0.0
        ),
        holding_days=int(len(valuations) - 1),
        sharpe_ratio=_sharpe_ratio(daily_returns),
        sortino_ratio=_sortino_ratio(daily_returns),
        var_95_pln=var_95_pln,
        cvar_95_pln=cvar_95_pln,
    )
