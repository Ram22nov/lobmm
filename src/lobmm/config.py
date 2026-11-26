"""Load, validate and snapshot run configurations.

Working rule: every run reads a YAML config and saves its results next to a copy of it.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "base.yaml"


class ConfigError(ValueError):
    """Raised when a config breaks one of the project's rules."""


def _to_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Read a YAML config, validate it, and return it as a dict."""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    validate_config(cfg)
    return cfg


def get_research_days(cfg: dict[str, Any]) -> list[dt.date]:
    return [_to_date(d) for d in cfg["days"]["research"]]


def get_test_days(cfg: dict[str, Any]) -> list[dt.date]:
    return [_to_date(d) for d in cfg["days"]["test"]]


def validate_config(cfg: dict[str, Any]) -> None:
    """Enforce the rules that keep the research honest."""
    for key in ("seed", "market", "data", "days", "fees", "latency", "strategy"):
        if key not in cfg:
            raise ConfigError(f"missing top-level key: {key!r}")

    research = get_research_days(cfg)
    test = get_test_days(cfg)

    for d in research + test:
        if d.day != 1:
            raise ConfigError(f"{d} is not a first-of-month day (Tardis free data only)")

    overlap = set(research) & set(test)
    if overlap:
        raise ConfigError(f"research and test days overlap: {sorted(overlap)}")

    if research and test and max(research) >= min(test):
        raise ConfigError("every test day must come after every research day")

    dev_day = _to_date(cfg["days"]["dev_day"])
    if dev_day in test:
        raise ConfigError(f"dev_day {dev_day} is a locked test day; pick a research day")


def save_run_config(cfg: dict[str, Any], out_dir: str | Path) -> Path:
    """Write a copy of the config used for a run into its results folder."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "config.yaml"
    with open(target, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return target
