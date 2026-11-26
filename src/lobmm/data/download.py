"""Download free first-of-month Tardis.dev files for Binance USD-M futures.

Tardis serves the first day of each month without an API key.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from lobmm.config import REPO_ROOT


def download_day(
    cfg: dict[str, Any],
    day: dt.date,
    symbols: list[str],
    data_types: list[str] | None = None,
) -> Path:
    """Download one day of raw CSV.gz files into data/raw. Returns the download folder."""
    if day.day != 1:
        raise ValueError(f"{day} is not the first of a month; free Tardis data needs an API key")

    # Imported here so tests and other commands do not need the client installed.
    # Newer tardis-dev exposes download_datasets; older versions use datasets.download.
    try:
        from tardis_dev import download_datasets as _download
    except ImportError:
        from tardis_dev.datasets import download as _download

    raw_dir = REPO_ROOT / cfg["data"]["raw_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    _download(
        exchange=cfg["market"]["exchange"],
        data_types=data_types or cfg["data"]["data_types"],
        symbols=symbols,
        from_date=day.isoformat(),
        to_date=(day + dt.timedelta(days=1)).isoformat(),
        download_dir=str(raw_dir),
    )
    return raw_dir
