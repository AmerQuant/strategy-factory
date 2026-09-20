"""Immutable snapshot store for canonical bar series (F-0.1.8).

Layout under ``SFAC_DATA_ROOT``::

    <source>/<symbol>/<timeframe>/<snapshot_hash>.parquet
    <source>/<symbol>/<timeframe>/<snapshot_hash>.meta.json   (full SeriesMetadata)

* The snapshot hash is :func:`~strategy_factory.data.hashing.content_hash` of the normalized
  table, so identical content always maps to the same file.
* Writes are atomic (temporary file + rename) and both files are set read-only afterwards.
  An existing snapshot is never overwritten or modified; writing the same content again
  returns the stored metadata.
* The hash covers **content only**, so the same bars written with different metadata would
  silently keep the first metadata. :data:`MATERIAL_FIELDS` -- the fields that say *what series
  this is* -- are therefore compared on every repeat write and any difference raises
  (**D-384**, **D-392**); there is no in-place metadata correction, because snapshots are
  immutable. ``notes``, ``raw_refs``, ``downloaded_at``, ``created_at`` and ``derived_from``
  describe the run, not the series, and never raise.
* Symbols are made filesystem-safe for the path only (see :func:`safe_component`); the
  metadata keeps the real symbol.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import stat
from pathlib import Path

import polars as pl

from strategy_factory.core.env import resolve_env
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.data.hashing import content_hash, normalize
from strategy_factory.data.schema import SeriesMetadata, critical_issues, validate_bars

DATA_ROOT_ENV = "SFAC_DATA_ROOT"
#: Metadata that identifies the series itself; a repeat write may not change any of it (D-384).
MATERIAL_FIELDS = (
    "source",
    "source_symbol",
    "asset_class",
    "price_type",
    "adjustment",
    "session",
    "feed",
    "volume_quality",
    "original_tz",
    "bar_label",
    "hash_version",
)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def data_root() -> Path:
    """``SFAC_DATA_ROOT`` from the environment or ``.env``; raises ``ConfigError`` if unset."""
    value, _origin = resolve_env((DATA_ROOT_ENV,))[DATA_ROOT_ENV]
    if not value:
        raise ConfigError(
            f"{DATA_ROOT_ENV} is not set: define it in the environment or in .env "
            "(see .env.example); it must point to the snapshot store outside the repo"
        )
    return Path(value)


def safe_component(name: str) -> str:
    """Filesystem-safe path component (Windows and POSIX) for a symbol/source name."""
    cleaned = _UNSAFE.sub("_", name).strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise DataError(f"cannot build a path component from {name!r}")
    if cleaned.upper().split(".")[0] in _RESERVED:
        cleaned += "_"
    return cleaned


def _set_read_only(path: Path) -> None:
    path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".partial")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class SnapshotStore:
    """Snapshot store rooted at ``root`` (default: ``SFAC_DATA_ROOT``)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else data_root()

    def snapshot_dir(self, source: str, symbol: str, timeframe: str) -> Path:
        return self.root / safe_component(source) / safe_component(symbol) / timeframe

    def paths(
        self, source: str, symbol: str, timeframe: str, snapshot_hash: str
    ) -> tuple[Path, Path]:
        d = self.snapshot_dir(source, symbol, timeframe)
        return d / f"{snapshot_hash}.parquet", d / f"{snapshot_hash}.meta.json"

    def write_snapshot(self, df: pl.DataFrame, meta: SeriesMetadata) -> SeriesMetadata:
        """Validate, hash and store ``df``; returns ``meta`` with the store fields filled.

        Rows are sorted by ``ts`` before validation (the canonical order). Any critical
        validation issue raises :class:`DataError`. If the same content is already stored,
        nothing is written and the stored metadata is returned.
        """
        if "ts" in df.columns and isinstance(df.schema["ts"], pl.Datetime):
            df = df.sort("ts", maintain_order=True)
        critical = critical_issues(validate_bars(df, meta))
        if critical:
            detail = "; ".join(f"{i.code} ({i.count}): {i.message}" for i in critical)
            raise DataError(f"bar validation failed: {detail}", stage="store", symbol=meta.symbol)
        table = normalize(df)
        digest = content_hash(table)
        pq_path, meta_path = self.paths(meta.source, meta.symbol, meta.timeframe, digest)
        if pq_path.exists():
            if not meta_path.exists():
                raise DataError(
                    f"incomplete snapshot (parquet without metadata): {pq_path}",
                    stage="store",
                    symbol=meta.symbol,
                )
            stored_meta = self.read_metadata(meta.source, meta.symbol, meta.timeframe, digest)
            _check_material(stored_meta, meta, pq_path)
            return stored_meta

        stored = meta.model_copy(
            update={
                "snapshot_hash": digest,
                "row_count": table.height,
                "first_ts": table["ts"].min() if table.height else None,
                "last_ts": table["ts"].max() if table.height else None,
                "created_at": dt.datetime.now(dt.UTC),
            }
        )
        stored = SeriesMetadata.model_validate(stored.model_dump())
        pq_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = pq_path.with_name(pq_path.name + ".partial")
        table.write_parquet(tmp, compression="zstd", statistics=True)
        if content_hash(pl.read_parquet(tmp)) != digest:
            tmp.unlink()
            raise DataError(
                "written parquet does not reproduce the content hash",
                stage="store",
                symbol=meta.symbol,
            )
        os.replace(tmp, pq_path)
        _set_read_only(pq_path)
        _atomic_write_bytes(meta_path, stored.model_dump_json(indent=2).encode("utf-8"))
        _set_read_only(meta_path)
        return stored

    def read_metadata(
        self, source: str, symbol: str, timeframe: str, snapshot_hash: str
    ) -> SeriesMetadata:
        _, meta_path = self.paths(source, symbol, timeframe, snapshot_hash)
        if not meta_path.is_file():
            raise DataError(f"snapshot metadata not found: {meta_path}", symbol=symbol)
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data.setdefault("hash_version", 1)  # sidecars written before hash_version existed
        return SeriesMetadata.model_validate(data)

    def scan_snapshot(
        self,
        source: str,
        symbol: str,
        timeframe: str,
        snapshot_hash: str,
        columns: list[str] | None = None,
        start: dt.datetime | None = None,
        end: dt.datetime | None = None,
    ) -> pl.LazyFrame:
        """Lazy scan with filter pushdown; ``start <= ts < end``."""
        pq_path, _ = self.paths(source, symbol, timeframe, snapshot_hash)
        if not pq_path.is_file():
            raise DataError(f"snapshot not found: {pq_path}", symbol=symbol)
        lf = pl.scan_parquet(pq_path)
        if start is not None:
            lf = lf.filter(pl.col("ts") >= start)
        if end is not None:
            lf = lf.filter(pl.col("ts") < end)
        if columns is not None:
            lf = lf.select(columns)
        return lf

    def read_snapshot(
        self,
        source: str,
        symbol: str,
        timeframe: str,
        snapshot_hash: str,
        columns: list[str] | None = None,
        start: dt.datetime | None = None,
        end: dt.datetime | None = None,
    ) -> pl.DataFrame:
        return self.scan_snapshot(
            source, symbol, timeframe, snapshot_hash, columns, start, end
        ).collect()


def _check_material(stored: SeriesMetadata, incoming: SeriesMetadata, path: Path) -> None:
    """Raise when a repeat write changes what the series *is* (D-384, D-392)."""
    changed = [
        (f, getattr(stored, f), getattr(incoming, f))
        for f in MATERIAL_FIELDS
        if getattr(stored, f) != getattr(incoming, f)
    ]
    if not changed:
        return
    detail = "; ".join(f"{f}: stored {old!r}, incoming {new!r}" for f, old, new in changed)
    raise DataError(
        f"snapshot {path.stem[:12]} at {path} already exists with different metadata "
        f"({detail}). "
        "Snapshots are immutable and the hash covers content only, so metadata cannot be "
        "corrected in place; fix the config before the first ingest (D-384).",
        stage="store",
        symbol=incoming.symbol,
    )


def write_snapshot(df: pl.DataFrame, meta: SeriesMetadata) -> SeriesMetadata:
    """Write to the store at ``SFAC_DATA_ROOT`` (see :meth:`SnapshotStore.write_snapshot`)."""
    return SnapshotStore().write_snapshot(df, meta)


def read_snapshot(
    source: str,
    symbol: str,
    timeframe: str,
    snapshot_hash: str,
    columns: list[str] | None = None,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> pl.DataFrame:
    """Read from the store at ``SFAC_DATA_ROOT`` (see :meth:`SnapshotStore.read_snapshot`)."""
    return SnapshotStore().read_snapshot(
        source, symbol, timeframe, snapshot_hash, columns, start, end
    )
