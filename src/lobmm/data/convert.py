"""Convert raw Tardis CSV.gz files to Parquet, one file per data type, contract and day.

Output: data/parquet/<data_type>/<SYMBOL>/<YYYY-MM-DD>.parquet

Every output gets a `seq` column: the row's position in the original file (0, 1, 2, ...).
Tardis files are in capture order, and rows that share a timestamp must be applied in that
order, so `seq` is the tie-breaker the book rebuild relies on.

Files are streamed in blocks with pyarrow, so memory stays small even for BTCUSDT.
"""

from __future__ import annotations

import gzip
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

RAW_NAME = re.compile(
    r"^(?P<exchange>[a-z0-9-]+)_(?P<data_type>.+)_(?P<day>\d{4}-\d{2}-\d{2})_(?P<symbol>[A-Z0-9]+)\.csv\.gz$"
)

_TS = {"timestamp": pa.int64(), "local_timestamp": pa.int64()}
_STR = {"exchange": pa.string(), "symbol": pa.string()}

# Explicit column types. Columns not listed are type-inferred by pyarrow.
COLUMN_TYPES: dict[str, dict[str, pa.DataType]] = {
    "incremental_book_L2": {
        **_STR,
        **_TS,
        "is_snapshot": pa.bool_(),
        "side": pa.string(),
        "price": pa.float64(),
        "amount": pa.float64(),
    },
    "trades": {
        **_STR,
        **_TS,
        "id": pa.string(),
        "side": pa.string(),
        "price": pa.float64(),
        "amount": pa.float64(),
    },
    "book_snapshot_25": {
        **_STR,
        **_TS,
        **{
            f"{side}[{i}].{field}": pa.float64()
            for side in ("asks", "bids")
            for i in range(25)
            for field in ("price", "amount")
        },
    },
    "derivative_ticker": {
        **_STR,
        **_TS,
        "funding_timestamp": pa.int64(),
        "funding_rate": pa.float64(),
        "predicted_funding_rate": pa.float64(),
        "open_interest": pa.float64(),
        "last_price": pa.float64(),
        "index_price": pa.float64(),
        "mark_price": pa.float64(),
    },
}

_LEVEL_COL = re.compile(r"^(asks|bids)\[(\d+)\]\.(price|amount)$")


def _rename(name: str) -> str:
    """asks[0].price -> ask_px_0, bids[3].amount -> bid_sz_3; other names unchanged."""
    m = _LEVEL_COL.match(name)
    if not m:
        return name
    side = "ask" if m.group(1) == "asks" else "bid"
    field = "px" if m.group(3) == "price" else "sz"
    return f"{side}_{field}_{m.group(2)}"


@dataclass(frozen=True)
class RawFile:
    path: Path
    exchange: str
    data_type: str
    day: str
    symbol: str


@dataclass(frozen=True)
class ConvertResult:
    raw: RawFile
    out: Path
    rows: int
    raw_mb: float
    parquet_mb: float
    seconds: float
    skipped: bool = False


def parse_raw_name(path: Path) -> RawFile | None:
    m = RAW_NAME.match(path.name)
    if not m:
        return None
    return RawFile(path=path, **m.groupdict())


def find_raw_files(
    raw_dir: Path,
    days: list[str] | None = None,
    symbols: list[str] | None = None,
    data_types: list[str] | None = None,
) -> list[RawFile]:
    found = []
    for p in sorted(Path(raw_dir).rglob("*.csv.gz")):
        rf = parse_raw_name(p)
        if rf is None:
            continue
        if days and rf.day not in days:
            continue
        if symbols and rf.symbol not in symbols:
            continue
        if data_types and rf.data_type not in data_types:
            continue
        found.append(rf)
    return found


def parquet_path(parquet_dir: Path, rf: RawFile) -> Path:
    return Path(parquet_dir) / rf.data_type / rf.symbol / f"{rf.day}.parquet"


def count_csv_rows(path: Path) -> int:
    """Data rows in a CSV.gz (lines minus the header). Slow on big files; used to verify."""
    lines, last = 0, b""
    with gzip.open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            lines += chunk.count(b"\n")
            last = chunk[-1:]
    if last and last != b"\n":  # last line has no trailing newline
        lines += 1
    return max(lines - 1, 0)  # minus the header


def convert_file(
    rf: RawFile,
    parquet_dir: Path,
    overwrite: bool = False,
    verify: bool = False,
    block_mb: float = 64,
) -> ConvertResult:
    """Stream one CSV.gz into Parquet with explicit types and a `seq` row-order column."""
    out = parquet_path(parquet_dir, rf)
    raw_mb = rf.path.stat().st_size / 2**20
    if out.exists() and not overwrite:
        rows = pq.ParquetFile(out).metadata.num_rows
        return ConvertResult(rf, out, rows, raw_mb, out.stat().st_size / 2**20, 0.0, skipped=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    start = time.perf_counter()

    reader = pacsv.open_csv(
        str(rf.path),  # .gz is decompressed automatically
        read_options=pacsv.ReadOptions(block_size=int(block_mb * 2**20)),
        convert_options=pacsv.ConvertOptions(
            column_types=COLUMN_TYPES.get(rf.data_type, _TS),
            strings_can_be_null=True,
        ),
    )

    writer = None
    rows = 0
    try:
        for batch in reader:
            n = batch.num_rows
            if n == 0:
                continue
            table = pa.Table.from_batches([batch])
            table = table.rename_columns([_rename(c) for c in table.column_names])
            seq = pa.array(np.arange(rows, rows + n, dtype=np.int64))
            table = table.add_column(0, "seq", seq)
            if writer is None:
                writer = pq.ParquetWriter(tmp, table.schema, compression="zstd")
            writer.write_table(table)
            rows += n
        if writer is None:  # header-only file: write an empty table with the right schema
            schema = pa.schema(
                [pa.field("seq", pa.int64())]
                + [pa.field(_rename(f.name), f.type) for f in reader.schema]
            )
            pq.write_table(schema.empty_table(), tmp, compression="zstd")
    finally:
        if writer is not None:
            writer.close()

    written = pq.ParquetFile(tmp).metadata.num_rows
    if written != rows:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{rf.path.name}: wrote {written} rows but read {rows}")
    if verify:
        expected = count_csv_rows(rf.path)
        if expected != rows:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"{rf.path.name}: CSV has {expected} rows, Parquet has {rows}")

    tmp.replace(out)  # only a complete file ever gets the final name
    return ConvertResult(
        rf, out, rows, raw_mb, out.stat().st_size / 2**20, time.perf_counter() - start
    )
