"""Audit-trail logging — persist every simulation run for reproducibility."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from portfolio_sim.metrics import PortfolioMetrics
from portfolio_sim.portfolio import SimulationResult

log = logging.getLogger(__name__)

DEFAULT_RUNS_DIR = Path("runs")
SCHEMA_VERSION = 1


def _serialize_metrics(metrics: PortfolioMetrics) -> dict[str, Any]:
    payload = asdict(metrics)
    for key in ("best_day", "worst_day"):
        value = payload.get(key)
        if value is not None:
            payload[key] = value.strftime("%Y-%m-%d")
    return payload


def _input_fingerprint(result: SimulationResult) -> str:
    """SHA-256 digest of the inputs that fully determine a simulation outcome."""
    canonical = json.dumps(
        {
            "amount": float(result.initial_amount),
            "allocation": dict(sorted(result.allocation.as_dict().items())),
            "start": result.start_date.isoformat(),
            "end": result.end_date.isoformat(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def record_run(
    result: SimulationResult,
    metrics: PortfolioMetrics,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> Path:
    """Persist a JSON manifest of run inputs and KPIs to disk.

    File name: `{ISO timestamp}_{12-char input hash}.json`. Identical inputs
    produce identical hashes, which makes deduplicating reruns trivial and
    gives auditors a stable reference for each simulation.
    """
    runs_path = Path(runs_dir)
    runs_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    fingerprint = _input_fingerprint(result)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "recorded_at_utc": now.isoformat(),
        "input_hash": fingerprint,
        "inputs": {
            "initial_amount_pln": float(result.initial_amount),
            "allocation": result.allocation.as_dict(),
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "holding_days": (result.end_date - result.start_date).days,
        },
        "metrics": _serialize_metrics(metrics),
    }

    output = runs_path / f"{timestamp}_{fingerprint}.json"
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("Recorded simulation run: %s", output)
    return output
