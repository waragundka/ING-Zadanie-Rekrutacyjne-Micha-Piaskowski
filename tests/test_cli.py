"""End-to-end tests for the CLI entry point."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from portfolio_sim.__main__ import _parse_allocation, _parse_date, main
from portfolio_sim.nbp_client import NBPAPIError


def _stub_client_for(rates: pd.DataFrame) -> MagicMock:
    stub = MagicMock()
    stub.fetch_rates.return_value = rates
    return stub


@pytest.fixture
def fake_rate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04"]),
            "rate": [4.00, 4.05, 4.02],
        }
    )


def test_cli_runs_full_pipeline_to_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_rate_frame: pd.DataFrame
) -> None:
    output = tmp_path / "report.html"
    runs_dir = tmp_path / "runs"

    monkeypatch.setattr(
        "portfolio_sim.__main__.NBPClient", lambda: _stub_client_for(fake_rate_frame)
    )

    rc = main(
        [
            "--amount", "1000",
            "--start", "2026-03-03",
            "--allocation", "USD:30,EUR:40,HUF:30",
            "--days", "1",
            "--output", str(output),
            "--runs-dir", str(runs_dir),
        ]
    )

    assert rc == 0
    assert output.exists()
    audit_files = list(runs_dir.glob("*.json"))
    assert len(audit_files) == 1
    payload = json.loads(audit_files[0].read_text(encoding="utf-8"))
    assert payload["inputs"]["initial_amount_pln"] == 1000.0


def test_cli_skips_audit_when_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_rate_frame: pd.DataFrame
) -> None:
    output = tmp_path / "report.html"
    runs_dir = tmp_path / "runs"

    monkeypatch.setattr(
        "portfolio_sim.__main__.NBPClient", lambda: _stub_client_for(fake_rate_frame)
    )

    rc = main(
        [
            "--start", "2026-03-03",
            "--days", "1",
            "--output", str(output),
            "--runs-dir", str(runs_dir),
            "--no-audit",
        ]
    )

    assert rc == 0
    assert output.exists()
    assert not runs_dir.exists() or not list(runs_dir.glob("*.json"))


def test_cli_returns_2_on_nbp_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_client = MagicMock()
    failing_client.fetch_rates.side_effect = NBPAPIError("upstream is down")
    monkeypatch.setattr("portfolio_sim.__main__.NBPClient", lambda: failing_client)

    rc = main(
        [
            "--start", "2026-03-03",
            "--days", "1",
            "--output", str(tmp_path / "report.html"),
            "--runs-dir", str(tmp_path / "runs"),
            "--no-audit",
        ]
    )

    assert rc == 2


def test_parse_allocation_rejects_malformed_token() -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="CODE:PERCENT"):
        _parse_allocation("USD30,EUR40")


def test_parse_allocation_rejects_non_numeric_percent() -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="Invalid percent"):
        _parse_allocation("USD:abc,EUR:40,HUF:30")


def test_parse_date_rejects_bad_format() -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="YYYY-MM-DD"):
        _parse_date("03/03/2026")
