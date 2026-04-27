"""Convenience launcher: opens the Streamlit dashboard in the default browser.

For non-interactive use, prefer the CLI:
    python -m portfolio_sim --start 2026-03-01 --output report.png
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    dashboard = Path(__file__).resolve().parent / "dashboard.py"
    if not dashboard.exists():
        print(f"Dashboard not found: {dashboard}", file=sys.stderr)
        return 1

    print("Starting Streamlit dashboard...")
    completed = subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(dashboard)],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
