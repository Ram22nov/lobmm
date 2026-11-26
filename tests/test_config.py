import copy
import datetime as dt

import pytest
import yaml

from lobmm.config import (
    ConfigError,
    get_research_days,
    get_test_days,
    load_config,
    save_run_config,
    validate_config,
)


@pytest.fixture
def cfg():
    return load_config()


def test_base_config_loads(cfg):
    assert cfg["market"]["exchange"] == "binance-futures"


def test_split_is_12_research_and_4_test_days(cfg):
    assert len(get_research_days(cfg)) == 12
    assert len(get_test_days(cfg)) == 4


def test_test_days_come_after_research_days(cfg):
    assert max(get_research_days(cfg)) < min(get_test_days(cfg))


def test_dev_day_is_not_a_locked_test_day(cfg):
    assert dt.date.fromisoformat(cfg["days"]["dev_day"]) not in get_test_days(cfg)


def test_weekend_list_matches_the_calendar(cfg):
    all_days = get_research_days(cfg) + get_test_days(cfg)
    weekend = {dt.date.fromisoformat(d) for d in cfg["days"]["weekend"]}
    assert weekend == {d for d in all_days if d.weekday() >= 5}


def test_overlapping_split_is_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["days"]["test"].append(bad["days"]["research"][-1])
    with pytest.raises(ConfigError):
        validate_config(bad)


def test_dev_day_on_test_day_is_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["days"]["dev_day"] = bad["days"]["test"][0]
    with pytest.raises(ConfigError):
        validate_config(bad)


def test_non_first_of_month_day_is_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["days"]["research"][0] = "2025-08-15"
    with pytest.raises(ConfigError):
        validate_config(bad)


def test_run_config_is_saved_next_to_results(cfg, tmp_path):
    path = save_run_config(cfg, tmp_path / "run_001")
    with open(path, encoding="utf-8") as f:
        assert yaml.safe_load(f) == cfg
