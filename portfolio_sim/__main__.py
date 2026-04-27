"""Command-line entry point: `python -m portfolio_sim ...`"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from portfolio_sim.allocation import Allocation
from portfolio_sim.audit import DEFAULT_RUNS_DIR, record_run
from portfolio_sim.metrics import compute_metrics
from portfolio_sim.nbp_client import NBPAPIError, NBPClient
from portfolio_sim.portfolio import DEFAULT_HOLDING_DAYS, PortfolioSimulator
from portfolio_sim.report import export_one_pager

log = logging.getLogger("portfolio_sim")


def _parse_allocation(raw: str) -> Allocation:
    """Parse a CLI allocation string like 'USD:30,EUR:40,HUF:30' into an Allocation."""
    percentages: dict[str, float] = {}
    for raw_token in raw.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if ":" not in token:
            raise argparse.ArgumentTypeError(
                f"Allocation entry {token!r} must be CODE:PERCENT (e.g. USD:30)."
            )
        code, value = token.split(":", maxsplit=1)
        try:
            percentages[code.strip().upper()] = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid percent in {token!r}: {exc}") from exc
    try:
        return Allocation.from_percentages(percentages)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_date(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Date must be YYYY-MM-DD, got {raw!r}.") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-sim",
        description=(
            "Simulate a buy-and-hold currency basket using NBP mid-rates. "
            "Produces a single-page report and an auditable JSON run record."
        ),
    )
    parser.add_argument(
        "--amount", type=float, default=1000.0, help="Initial PLN amount (default: 1000)."
    )
    parser.add_argument(
        "--start",
        type=_parse_date,
        required=True,
        help="Investment start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--allocation",
        type=_parse_allocation,
        default=_parse_allocation("USD:30,EUR:40,HUF:30"),
        help="Currency split, e.g. 'USD:30,EUR:40,HUF:30' (must sum to 100).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_HOLDING_DAYS,
        help=f"Holding period in calendar days (default: {DEFAULT_HOLDING_DAYS}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("portfolio_report.png"),
        help="Report output path; extension drives format (default: portfolio_report.png).",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_RUNS_DIR,
        help=f"Directory for JSON audit records (default: {DEFAULT_RUNS_DIR}).",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="Skip writing the JSON audit record.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        simulator = PortfolioSimulator(NBPClient())
        result = simulator.run(
            amount=args.amount,
            allocation=args.allocation,
            start=args.start,
            holding_days=args.days,
        )
    except NBPAPIError as exc:
        log.error("NBP API failure: %s", exc)
        return 2
    except ValueError as exc:
        log.error("Invalid input: %s", exc)
        return 1

    metrics = compute_metrics(result.valuations, result.initial_amount)
    log.info(
        "Final value: %.2f PLN (%+.2f PLN, %+.2f%%) · max drawdown %.2f%% · vol %.2f%%",
        metrics.final_value,
        metrics.total_return_pln,
        metrics.total_return_pct,
        metrics.max_drawdown_pct,
        metrics.realized_volatility_pct,
    )

    output_path = export_one_pager(result, metrics, args.output)
    log.info("Report saved to %s", output_path)

    if not args.no_audit:
        audit_path = record_run(result, metrics, runs_dir=args.runs_dir)
        log.info("Audit record: %s", audit_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
