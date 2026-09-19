"""Content hashing of bar tables and raw files (F-0.1.8).

``content_hash`` identifies a snapshot by its *content*, not by its file: the table is
normalized (canonical column order, canonical dtypes, rows sorted by ``ts`` then by every
other column, a single chunk) and serialized as an uncompressed Arrow IPC stream, whose
bytes are hashed with sha256. The result is independent of the input row order, of
chunking and of any Parquet write settings.

The IPC bytes depend on the Polars version pinned in ``uv.lock``; upgrading Polars requires
re-checking the hash of a reference fixture (tests pin one).
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import polars as pl

from strategy_factory.data.schema import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, canonical_columns

_CHUNK = 1 << 20


def normalize(df: pl.DataFrame) -> pl.DataFrame:
    """Canonical form of a bar table: canonical columns/dtypes, sorted rows, one chunk."""
    cols = canonical_columns(df)
    dtypes = {**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}
    out = df.select([pl.col(c).cast(dtypes[c]) for c in cols])
    return out.sort(cols, maintain_order=True).rechunk()


def content_hash(df: pl.DataFrame) -> str:
    """sha256 (hex) of the canonical Arrow IPC serialization of ``df``."""
    buf = io.BytesIO()
    normalize(df).write_ipc_stream(buf, compression="uncompressed")
    return hashlib.sha256(buf.getvalue()).hexdigest()


def file_sha256(path: Path) -> str:
    """sha256 (hex) of a raw file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
