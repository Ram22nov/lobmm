# On Windows, run these through Git Bash, or type the uv commands directly in PowerShell.

.PHONY: setup test lint format download-dev all

setup:
	uv sync
	uv run pre-commit install

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

download-dev:
	uv run lobmm download

# Grows stage by stage: download -> convert -> book -> features -> research -> backtest -> analysis
all: test
