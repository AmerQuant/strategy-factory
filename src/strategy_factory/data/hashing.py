"""Content hashing of bar tables and raw files (F-0.1.8).

``content_hash`` identifies a snapshot by its *content*, not by its file. The table is first
normalized (canonical column order and dtypes, rows sorted by ``ts`` then by every other
column), then serialized with our own, library-independent format and hashed with sha256.

**Serialization, hash_version 2** (``HASH_VERSION``)::

    header   = UTF-8 JSON of {"columns": [[name, dtype], ...], "hash_version": 2, "rows": n}
               with sorted keys and separators (",", ":"); dtype is one of
               "datetime_us_utc", "float64", "int64"
    payload  = header + b"\\x00"
               + for each canonical column, in canonical order:
                   validity  n bytes, 1 = value present, 0 = null
                   values    n little-endian 8-byte values:
                               ts       int64 microseconds since 1970-01-01T00:00:00 UTC
                               Float64  IEEE-754 binary64; every NaN written as 0x7FF8000000000000
                               Int64    two's-complement int64
                             the value slot of a null is 0 (all zero bytes)
    hash     = sha256(payload), lower-case hex

The result is independent of input row order, column order, chunking, Parquet settings and
the Polars/Arrow version. Version 1 (Arrow IPC stream bytes) is no longer produced.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

from strategy_factory.data.schema import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, canonical_columns

HASH_VERSION = 2
CANONICAL_NAN_BITS = 0x7FF8000000000000
_CHUNK = 1 << 20


def normalize(df: pl.DataFrame) -> pl.DataFrame:
    """Canonical form of a bar table: canonical columns/dtypes, sorted rows, one chunk."""
    cols = canonical_columns(df)
    dtypes = {**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}
    out = df.select([pl.col(c).cast(dtypes[c]) for c in cols])
    return out.sort(cols, maintain_order=True, nulls_last=False).rechunk()


def _dtype_name(dtype: pl.DataType) -> str:
    if isinstance(dtype, pl.Datetime):
        if dtype.time_unit != "us" or dtype.time_zone != "UTC":
            raise ValueError(f"ts must be Datetime(us, UTC), got {dtype}")
        return "datetime_us_utc"
    if dtype == pl.Float64():
        return "float64"
    if dtype == pl.Int64():
        return "int64"
    raise ValueError(f"unsupported dtype for hashing: {dtype}")


def _column_bytes(s: pl.Series) -> tuple[bytes, bytes]:
    """(validity bitmap, little-endian values) of one normalized column."""
    valid = s.is_not_null().to_numpy().astype(np.uint8)
    name = _dtype_name(s.dtype)
    if name == "datetime_us_utc":
        values = s.dt.epoch("us").fill_null(0).to_numpy().astype("<i8")
    elif name == "int64":
        values = s.fill_null(0).to_numpy().astype("<i8")
    else:
        floats = s.fill_null(0.0).to_numpy().astype("<f8")
        bits = floats.view("<u8").copy()
        bits[np.isnan(floats)] = CANONICAL_NAN_BITS
        values = bits
    return valid.tobytes(), values.tobytes()


def serialize(df: pl.DataFrame) -> bytes:
    """The hash_version-2 byte payload of the normalized table (see module docstring)."""
    table = normalize(df)
    header = {
        "columns": [[c, _dtype_name(table.schema[c])] for c in table.columns],
        "hash_version": HASH_VERSION,
        "rows": table.height,
    }
    parts = [json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8"), b"\x00"]
    for c in table.columns:
        valid, values = _column_bytes(table[c])
        parts += [valid, values]
    return b"".join(parts)


def content_hash(df: pl.DataFrame) -> str:
    """sha256 (hex) of :func:`serialize` -- hash_version 2."""
    return hashlib.sha256(serialize(df)).hexdigest()


def file_sha256(path: Path) -> str:
    """sha256 (hex) of a raw file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
