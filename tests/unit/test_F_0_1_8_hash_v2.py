"""F-0.1.8: library-independent content hash (hash_version 2), tested against its specification."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import struct

import polars as pl
import pytest
from fixtures.bars import make_bars

from strategy_factory.data.hashing import HASH_VERSION, content_hash, serialize

NAN_BITS = 0x7FF8000000000000
T0 = dt.datetime(2024, 1, 2, tzinfo=dt.UTC)


def golden_frame() -> pl.DataFrame:
    """3 rows, one NaN in a price, one null in an optional column (already canonical order)."""
    return pl.DataFrame(
        {
            "ts": [T0, T0 + dt.timedelta(days=1), T0 + dt.timedelta(days=2)],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, float("nan"), 102.5],
            "volume": [1000.0, 1001.0, 1002.0],
            "trades": [12, None, 14],
        },
        schema={
            "ts": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "trades": pl.Int64,
        },
    )


def spec_payload() -> bytes:
    """The golden frame serialized by hand from the specification (struct only)."""
    cols = [
        ["ts", "datetime_us_utc"],
        ["open", "float64"],
        ["high", "float64"],
        ["low", "float64"],
        ["close", "float64"],
        ["volume", "float64"],
        ["trades", "int64"],
    ]
    header = json.dumps(
        {"hash_version": 2, "columns": cols, "rows": 3}, sort_keys=True, separators=(",", ":")
    )
    out = header.encode("utf-8") + b"\x00"
    us = [int((T0 + dt.timedelta(days=d)).timestamp()) * 1_000_000 for d in range(3)]
    out += bytes([1, 1, 1]) + struct.pack("<3q", *us)
    for vals in ([100.0, 101.0, 102.0], [101.0, 102.0, 103.0], [99.0, 100.0, 101.0]):
        out += bytes([1, 1, 1]) + struct.pack("<3d", *vals)
    out += (
        bytes([1, 1, 1])
        + struct.pack("<d", 100.5)
        + struct.pack("<Q", NAN_BITS)
        + struct.pack("<d", 102.5)
    )
    out += bytes([1, 1, 1]) + struct.pack("<3d", 1000.0, 1001.0, 1002.0)
    out += bytes([1, 0, 1]) + struct.pack("<3q", 12, 0, 14)  # null slot is 0
    return out


GOLDEN_HASH = "a6a55ab3a76bf86af1336300e41c7aa12ae458a923d7d175fde48888cbdce165"


def test_F_0_1_8_hash_version_is_2() -> None:
    assert HASH_VERSION == 2


def test_F_0_1_8_serialization_matches_the_specification() -> None:
    assert serialize(golden_frame()) == spec_payload()


def test_F_0_1_8_golden_hash_pinned() -> None:
    expected = hashlib.sha256(spec_payload()).hexdigest()
    assert content_hash(golden_frame()) == expected == GOLDEN_HASH


def test_F_0_1_8_all_nan_bit_patterns_hash_alike() -> None:
    quiet = struct.unpack("<d", struct.pack("<Q", 0x7FF8000000000000))[0]
    other = struct.unpack("<d", struct.pack("<Q", 0x7FF8000000000123))[0]  # NaN with payload
    a = golden_frame().with_columns(pl.Series("close", [100.5, quiet, 102.5]))
    b = golden_frame().with_columns(pl.Series("close", [100.5, other, 102.5]))
    assert content_hash(a) == content_hash(b) == GOLDEN_HASH


def test_F_0_1_8_null_differs_from_zero_and_nan() -> None:
    base = golden_frame()
    zero = base.with_columns(pl.Series("trades", [12, 0, 14], dtype=pl.Int64))
    assert content_hash(zero) != content_hash(base)  # validity bitmap distinguishes them
    null_close = base.with_columns(pl.Series("close", [100.5, None, 102.5], dtype=pl.Float64))
    assert content_hash(null_close) != content_hash(base)  # null != NaN


@pytest.mark.parametrize("col", ["ts", "open", "high", "low", "close", "volume", "trades"])
def test_F_0_1_8_any_single_value_change_changes_hash(col: str) -> None:
    base = golden_frame()
    delta = dt.timedelta(microseconds=1) if col == "ts" else (1 if col == "trades" else 1e-9)
    changed = base.with_columns(
        pl.when(pl.int_range(pl.len()) == 2)
        .then(pl.col(col) + delta)
        .otherwise(pl.col(col))
        .alias(col)
    )
    assert content_hash(changed) != content_hash(base)


def test_F_0_1_8_header_depends_on_present_columns() -> None:
    df = make_bars(3)
    assert content_hash(df) != content_hash(
        df.with_columns(pl.lit(None, dtype=pl.Float64).alias("vwap"))
    )
