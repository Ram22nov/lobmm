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


def _cmd_convert(args: argparse.Namespace) -> int:
    from lobmm.config import REPO_ROOT
    from lobmm.data.convert import convert_file, find_raw_files

    cfg = load_config(args.config)
    raw_dir = REPO_ROOT / cfg["data"]["raw_dir"]
    parquet_dir = REPO_ROOT / cfg["data"]["parquet_dir"]
    days = None if args.all_days else [args.day or cfg["days"]["dev_day"]]

    files = find_raw_files(raw_dir, days=days, symbols=args.symbols, data_types=args.types)
    if not files:
        print(f"no raw files found in {raw_dir} for days={days} symbols={args.symbols}")
        return 1

    total_raw = total_pq = 0.0
    for rf in files:
        res = convert_file(rf, parquet_dir, overwrite=args.overwrite, verify=args.verify)
        total_raw += res.raw_mb
        total_pq += res.parquet_mb
        status = "skip" if res.skipped else f"{res.seconds:6.1f}s"
        print(
            f"{rf.day} {rf.symbol:8s} {rf.data_type:20s} {res.rows:>12,} rows  "
            f"{res.raw_mb:8.1f} MB -> {res.parquet_mb:8.1f} MB  {status}"
        )
    ratio = total_pq / total_raw if total_raw else 0.0
    print(
        f"\n{len(files)} files: {total_raw:,.0f} MB csv.gz -> {total_pq:,.0f} MB parquet "
        f"({ratio:.0%} of the raw size)"
    )
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

    p = sub.add_parser("convert", help="convert raw CSV.gz files to Parquet")
    p.add_argument("--day", help="YYYY-MM-DD (default: days.dev_day in the config)")
    p.add_argument("--all-days", action="store_true", help="convert every downloaded day")
    p.add_argument("--symbols", nargs="+", help="default: every symbol found")
    p.add_argument("--types", nargs="+", help="data types (default: all found)")
    p.add_argument("--overwrite", action="store_true", help="redo files that already exist")
    p.add_argument("--verify", action="store_true", help="recount CSV rows (slow, thorough)")
    p.set_defaults(func=_cmd_convert)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
