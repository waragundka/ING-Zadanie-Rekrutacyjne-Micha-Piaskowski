.PHONY: install install-dev test lint typecheck dashboard report clean

PY ?= python3

install:
	$(PY) -m pip install -r requirements.txt

install-dev:
	$(PY) -m pip install -e ".[dev,report]"

test:
	$(PY) -m pytest tests/ --cov=portfolio_sim --cov-report=term-missing

lint:
	$(PY) -m ruff check portfolio_sim tests

typecheck:
	$(PY) -m mypy portfolio_sim

dashboard:
	$(PY) -m streamlit run dashboard.py

report:
	$(PY) -m portfolio_sim --start 2026-03-03 --output portfolio_report.png

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
