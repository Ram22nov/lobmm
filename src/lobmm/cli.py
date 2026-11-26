"""Command line entry point: one command per pipeline stage.

uv run lobmm show-config
uv run lobmm download --day 2026-07-01 --symbols SOLUSDT XRPUSDT BTCUSDT
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

import yaml

from lobmm.config import DEFAULT_CONFIG, load_config


def _cmd_show_config(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(yaml.safe_dump(cfg, sort_keys=False))
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    from lobmm.data.download import download_day

    cfg = load_config(args.config)
    day = (
        dt.date.fromisoformat(args.day)
        if args.day
        else dt.date.fromisoformat(cfg["days"]["dev_day"])
    )
    symbols = args.symbols or cfg["market"]["candidates"]
    out = download_day(cfg, day, symbols)
    print(f"downloaded {day} for {', '.join(symbols)} into {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lobmm", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to a YAML config")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("show-config", help="validate and print the config")
    p.set_defaults(func=_cmd_show_config)

    p = sub.add_parser("download", help="download one free Tardis day")
    p.add_argument("--day", help="YYYY-MM-01 (default: days.dev_day in the config)")
    p.add_argument("--symbols", nargs="+", help="default: market.candidates in the config")
    p.set_defaults(func=_cmd_download)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
