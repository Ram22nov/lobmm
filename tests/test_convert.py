import gzip
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from lobmm.data.convert import (
    convert_file,
    count_csv_rows,
    find_raw_files,
    parquet_path,
    parse_raw_name,
)

BOOK_CSV = """exchange,symbol,timestamp,local_timestamp,is_snapshot,side,price,amount
binance-futures,SOLUSDT,1782864000100000,1782864000105000,false,bid,150.01,3.0
binance-futures,SOLUSDT,1782864000200000,1782864000205000,true,bid,150.00,10.5
binance-futures,SOLUSDT,1782864000200000,1782864000205000,true,ask,150.02,7.25
binance-futures,SOLUSDT,1782864000300000,1782864000301000,false,bid,150.00,0
binance-futures,SOLUSDT,1782864000300000,1782864000301000,false,ask,150.03,1.5
"""

TRADES_CSV = """exchange,symbol,timestamp,local_timestamp,id,side,price,amount
binance-futures,SOLUSDT,1782864000100000,1782864000104000,9001,buy,150.02,0.5
binance-futures,SOLUSDT,1782864000150000,1782864000152000,9002,sell,150.00,1.0
"""

# Two levels instead of 25, enough to test renaming.
_SNAP_HEADER = ",".join(
    ["exchange", "symbol", "timestamp", "local_timestamp"]
    + [
        f"{side}[{i}].{f}"
        for i in range(2)
        for side in ("asks", "bids")
        for f in ("price", "amount")
    ]
)
SNAPSHOT_CSV = (
    _SNAP_HEADER
    + "\nbinance-futures,SOLUSDT,1782864000200000,1782864000205000,"
    + "150.02,7.25,150.00,10.5,150.03,2.0,149.99,4.0\n"
)

_TICKER_HEADER = ",".join(
    ["exchange", "symbol", "timestamp", "local_timestamp", "funding_timestamp", "funding_rate"]
    + ["predicted_funding_rate", "open_interest", "last_price", "index_price", "mark_price"]
)
TICKER_CSV = (
    _TICKER_HEADER
    + "\nbinance-futures,SOLUSDT,1782864000100000,1782864000101000,1782892800000000,"
    + "0.0001,,1234567.0,150.01,150.00,150.005\n"
)


def _write_gz(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


@pytest.fixture
def raw_dir(tmp_path):
    raw = tmp_path / "raw"
    day = "2026-07-01"
    _write_gz(raw / f"binance-futures_incremental_book_L2_{day}_SOLUSDT.csv.gz", BOOK_CSV)
    _write_gz(raw / f"binance-futures_trades_{day}_SOLUSDT.csv.gz", TRADES_CSV)
    _write_gz(raw / f"binance-futures_book_snapshot_25_{day}_SOLUSDT.csv.gz", SNAPSHOT_CSV)
    _write_gz(raw / f"binance-futures_derivative_ticker_{day}_SOLUSDT.csv.gz", TICKER_CSV)
    (raw / "notes.txt").write_text("not a data file")
    return raw


def _convert(raw_dir, data_type, tmp_path, **kw):
    (rf,) = find_raw_files(raw_dir, data_types=[data_type])
    return convert_file(rf, tmp_path / "parquet", **kw)


def test_parse_raw_name_handles_underscores_in_data_type():
    rf = parse_raw_name(Path("binance-futures_incremental_book_L2_2026-07-01_SOLUSDT.csv.gz"))
    assert (rf.exchange, rf.data_type, rf.day, rf.symbol) == (
        "binance-futures",
        "incremental_book_L2",
        "2026-07-01",
        "SOLUSDT",
    )
    assert parse_raw_name(Path("notes.txt")) is None


def test_find_raw_files_filters(raw_dir):
    assert len(find_raw_files(raw_dir)) == 4
    assert len(find_raw_files(raw_dir, data_types=["trades"])) == 1
    assert find_raw_files(raw_dir, symbols=["XRPUSDT"]) == []
    assert find_raw_files(raw_dir, days=["2026-08-01"]) == []


def test_count_csv_rows(raw_dir):
    (rf,) = find_raw_files(raw_dir, data_types=["incremental_book_L2"])
    assert count_csv_rows(rf.path) == 5


def test_book_row_count_types_and_order(raw_dir, tmp_path):
    res = _convert(raw_dir, "incremental_book_L2", tmp_path, verify=True)
    t = pq.read_table(res.out)
    assert res.rows == t.num_rows == 5
    assert res.out == parquet_path(tmp_path / "parquet", res.raw)
    assert t.schema.field("seq").type == pa.int64()
    assert t.schema.field("timestamp").type == pa.int64()
    assert t.schema.field("local_timestamp").type == pa.int64()
    assert t.schema.field("is_snapshot").type == pa.bool_()
    assert t.schema.field("price").type == pa.float64()
    assert t.schema.field("amount").type == pa.float64()
    # seq is the original file order, and the pre-snapshot row is kept (skipped later, not here)
    assert t.column("seq").to_pylist() == [0, 1, 2, 3, 4]
    assert t.column("is_snapshot").to_pylist() == [False, True, True, False, False]
    assert t.column("amount").to_pylist()[3] == 0.0


def test_trades_keep_ids_as_strings(raw_dir, tmp_path):
    t = pq.read_table(_convert(raw_dir, "trades", tmp_path).out)
    assert t.schema.field("id").type == pa.string()
    assert t.column("side").to_pylist() == ["buy", "sell"]


def test_snapshot_columns_are_renamed(raw_dir, tmp_path):
    t = pq.read_table(_convert(raw_dir, "book_snapshot_25", tmp_path).out)
    for col in ("ask_px_0", "ask_sz_0", "bid_px_0", "bid_sz_0", "ask_px_1", "bid_sz_1"):
        assert t.schema.field(col).type == pa.float64()
    assert t.column("bid_px_0").to_pylist() == [150.00]


def test_ticker_empty_value_becomes_null(raw_dir, tmp_path):
    t = pq.read_table(_convert(raw_dir, "derivative_ticker", tmp_path).out)
    assert t.schema.field("funding_timestamp").type == pa.int64()
    assert t.column("predicted_funding_rate").to_pylist() == [None]


def test_existing_output_is_skipped_unless_overwrite(raw_dir, tmp_path):
    first = _convert(raw_dir, "trades", tmp_path)
    assert not first.skipped
    again = _convert(raw_dir, "trades", tmp_path)
    assert again.skipped and again.rows == 2
    forced = _convert(raw_dir, "trades", tmp_path, overwrite=True)
    assert not forced.skipped
    assert not list((tmp_path / "parquet").rglob("*.tmp"))


def test_small_blocks_keep_order(raw_dir, tmp_path):
    """Force many tiny blocks: seq must still run 0..n-1 across block boundaries."""
    (rf,) = find_raw_files(raw_dir, data_types=["incremental_book_L2"])
    # block_mb is in MB; pass a tiny block size via a fractional value
    res = convert_file(rf, tmp_path / "pq_small", block_mb=1 / 2**12)  # ~256 bytes
    t = pq.read_table(res.out)
    assert t.column("seq").to_pylist() == list(range(5))
    assert t.column("price").to_pylist() == [150.01, 150.00, 150.02, 150.00, 150.03]
