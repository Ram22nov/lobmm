# lobmm: signal-aware market making on crypto order books

![CI](https://github.com/YOUR_GITHUB_USERNAME/lobmm/actions/workflows/ci.yml/badge.svg)

A small, honest version of a crypto market-making desk. It rebuilds the Binance USD-M futures
order book from tick data, measures how well order-book features predict the next 1–30 seconds
of price, and backtests three quoting strategies under realistic fills, fees and latency.

**Questions**

1. How much does the order book tell you about the next 1–30 seconds of price, and how fast does
   that information fade?
2. Does quoting around that signal, with an inventory limit, lose less to adverse selection than
   quoting blindly?
3. At what fees and delays does the strategy stop working?

**Status:** in progress, week 1 (repo, data pipeline, order-book rebuild).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 for you.

```bash
uv sync                      # create .venv and install pinned dependencies
uv run pre-commit install    # lint on every commit
uv run pytest                # run the tests
uv run lobmm show-config     # validate and print configs/base.yaml
uv run lobmm download        # download the dev day for the candidate contracts
```

## Data

Free first-of-month [Tardis.dev](https://tardis.dev) files for Binance USD-M perpetual futures:
`incremental_book_L2`, `book_snapshot_25`, `trades`, `derivative_ticker`.

- 12 research days (Aug 2025 – Jul 2026): feature work and tuning, walk-forward splits.
- 4 locked test days (Aug – Nov 2026): run once, at the end, with frozen settings.

Data lives in `data/` and is never committed.

## Layout

```
configs/            YAML: market, days, fees, latency, strategy settings
src/lobmm/
  data/             download, convert to Parquet
  book/             order-book rebuild and validation
  features/         imbalance, microprice, order-flow imbalance, trade flow
  research/         targets, models, walk-forward, metrics
  strategy/         symmetric, inventory-lean, signal-lean quoting
  backtest/         event loop, fill model, latency, fees
  analysis/         PnL split, markouts, sensitivity grids, plots
  cli.py            one command per stage
notebooks/          exploration only; pipeline logic lives in src/
tests/              pytest suite, run by GitHub Actions
reports/            figures and the write-up
```

## Working rules

- Every run reads a YAML config and saves its results next to a copy of that config.
- Random seeds are fixed.
- Notebooks may call `src/` code but never hold logic the pipeline depends on.
- The locked test days are touched once, on 17 Jan 2027.
