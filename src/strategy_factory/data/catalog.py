"""Snapshot catalog and reference selection (F-0.1.8).

Files under ``SFAC_DATA_ROOT``:

* ``catalog.parquet``: one row per registered snapshot -- every :class:`SeriesMetadata`
  field (``raw_refs`` and ``derived_from`` as JSON text) plus the catalog-only columns
  ``is_reference`` and ``quality_status`` (``ok | warning | critical | unchecked``, F-0.1.6);
* ``catalog_events.parquet``: append-only log ``(ts, event, symbol, timeframe,
  snapshot_hash, previous_reference, note)``.

Exactly one snapshot per ``(symbol, timeframe)`` is the reference; every change of the
reference is logged. Writes are atomic (temporary file + rename).

**Single-writer assumption:** only one process modifies the catalog at a time (the CLI or
the orchestrator). There is no file locking; concurrent writers could lose updates.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.schema import RawRef, SeriesMetadata, SnapshotKey
from strategy_factory.data.store import data_root

CATALOG_FILE = "catalog.parquet"
EVENTS_FILE = "catalog_events.parquet"
KEY = ("source", "symbol", "timeframe", "snapshot_hash")
QUALITY_STATUSES = ("ok", "warning", "critical", "unchecked")
CATALOG_ONLY = ("is_reference", "quality_status")

_TS = pl.Datetime("us", "UTC")
CATALOG_SCHEMA: dict[str, pl.DataType] = {
    "source": pl.Utf8(),
    "source_symbol": pl.Utf8(),
    "symbol": pl.Utf8(),
    "asset_class": pl.Utf8(),
    "timeframe": pl.Utf8(),
    "price_type": pl.Utf8(),
    "adjustment": pl.Utf8(),
    "session": pl.Utf8(),
    "feed": pl.Utf8(),
    "volume_quality": pl.Utf8(),
    "original_tz": pl.Utf8(),
    "bar_label": pl.Utf8(),
    "raw_refs": pl.Utf8(),
    "downloaded_at": _TS,
    "notes": pl.Utf8(),
    "snapshot_hash": pl.Utf8(),
    "row_count": pl.Int64(),
    "first_ts": _TS,
    "last_ts": _TS,
    "created_at": _TS,
    "value_final_time_local": pl.Utf8(),
    "value_final_tz": pl.Utf8(),
    "value_final_status": pl.Utf8(),
    "hash_version": pl.Int64(),
    "derived_from": pl.Utf8(),
    "is_reference": pl.Boolean(),
    "quality_status": pl.Utf8(),
}
# defaults for columns added after a catalog file was written (older rows are hash_version 1)
_MIGRATION_DEFAULTS: dict[str, object] = {
    "value_final_time_local": None,
    "value_final_tz": None,
    "value_final_status": None,
    "hash_version": 1,
    "derived_from": None,
    "quality_status": "unchecked",
}
EVENTS_SCHEMA: dict[str, pl.DataType] = {
    "ts": _TS,
    "event": pl.Utf8(),
    "symbol": pl.Utf8(),
    "timeframe": pl.Utf8(),
    "snapshot_hash": pl.Utf8(),
    "previous_reference": pl.Utf8(),
    "note": pl.Utf8(),
}


def _atomic_write_parquet(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    df.write_parquet(tmp)
    os.replace(tmp, path)


def _meta_to_row(meta: SeriesMetadata, is_reference: bool) -> dict[str, Any]:
    row = meta.model_dump()
    row["raw_refs"] = json.dumps([r.model_dump() for r in meta.raw_refs])
    row["derived_from"] = (
        meta.derived_from.model_dump_json() if meta.derived_from is not None else None
    )
    row["is_reference"] = is_reference
    row["quality_status"] = "unchecked"
    return row


def _row_to_meta(row: dict[str, Any]) -> SeriesMetadata:
    data = {k: v for k, v in row.items() if k not in CATALOG_ONLY}
    data["raw_refs"] = tuple(RawRef.model_validate(r) for r in json.loads(row["raw_refs"]))
    if row.get("derived_from"):
        data["derived_from"] = SnapshotKey.model_validate_json(row["derived_from"])
    return SeriesMetadata.model_validate(data)


def _key_filter(key: SnapshotKey) -> pl.Expr:
    return pl.all_horizontal([pl.col(k) == getattr(key, k) for k in KEY])


class Catalog:
    """Catalog stored under ``root`` (default: ``SFAC_DATA_ROOT``)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else data_root()
        self.path = self.root / CATALOG_FILE
        self.events_path = self.root / EVENTS_FILE

    # -- raw tables ----------------------------------------------------------------------
    def table(self) -> pl.DataFrame:
        if not self.path.is_file():
            return pl.DataFrame(schema=CATALOG_SCHEMA)
        cat = pl.read_parquet(self.path)
        missing = [c for c in CATALOG_SCHEMA if c not in cat.columns]
        if missing:
            cat = cat.with_columns(
                pl.lit(_MIGRATION_DEFAULTS.get(c), dtype=CATALOG_SCHEMA[c]).alias(c)
                for c in missing
            )
        return cat.select([pl.col(c).cast(t) for c, t in CATALOG_SCHEMA.items()])

    def events(self) -> pl.DataFrame:
        if not self.events_path.is_file():
            return pl.DataFrame(schema=EVENTS_SCHEMA)
        return pl.read_parquet(self.events_path)

    def _log(
        self,
        event: str,
        symbol: str,
        timeframe: str,
        snapshot_hash: str,
        previous_reference: str | None,
        note: str,
    ) -> None:
        row = pl.DataFrame(
            [
                {
                    "ts": dt.datetime.now(dt.UTC),
                    "event": event,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "snapshot_hash": snapshot_hash,
                    "previous_reference": previous_reference,
                    "note": note,
                }
            ],
            schema=EVENTS_SCHEMA,
        )
        _atomic_write_parquet(pl.concat([self.events(), row]), self.events_path)

    # -- API -----------------------------------------------------------------------------
    def register(self, meta: SeriesMetadata, note: str = "") -> SeriesMetadata:
        """Add a stored snapshot to the catalog (idempotent for an already listed key)."""
        if not meta.is_stored:
            raise DataError(
                "only stored snapshots (snapshot_hash filled by the store) can be registered",
                stage="catalog",
                symbol=meta.symbol,
            )
        cat = self.table()
        key = {k: getattr(meta, k) for k in KEY}
        exists = cat.filter(pl.all_horizontal([pl.col(k) == v for k, v in key.items()]))
        if exists.height:
            return meta
        row = pl.DataFrame([_meta_to_row(meta, is_reference=False)], schema=CATALOG_SCHEMA)
        _atomic_write_parquet(pl.concat([cat, row]), self.path)
        assert meta.snapshot_hash is not None
        self._log(
            "register", meta.symbol, meta.timeframe, meta.snapshot_hash, None, note or meta.source
        )
        return meta

    def list_snapshots(
        self, symbol: str | None = None, timeframe: str | None = None, source: str | None = None
    ) -> pl.DataFrame:
        cat = self.table()
        for col, val in (("symbol", symbol), ("timeframe", timeframe), ("source", source)):
            if val is not None:
                cat = cat.filter(pl.col(col) == val)
        return cat.sort(["symbol", "timeframe", "source", "created_at"])

    def set_reference(
        self, symbol: str, timeframe: str, snapshot_hash: str, note: str = ""
    ) -> None:
        """Make ``snapshot_hash`` the only reference for ``(symbol, timeframe)``; logged."""
        cat = self.table()
        sel = (pl.col("symbol") == symbol) & (pl.col("timeframe") == timeframe)
        target = cat.filter(sel & (pl.col("snapshot_hash") == snapshot_hash))
        if target.height != 1:
            raise DataError(
                f"snapshot {snapshot_hash[:12]} for ({symbol}, {timeframe}) must be registered "
                f"exactly once to become the reference (found {target.height})",
                stage="catalog",
                symbol=symbol,
            )
        current = cat.filter(sel & pl.col("is_reference"))
        previous = current["snapshot_hash"][0] if current.height else None
        if previous == snapshot_hash and current.height == 1:
            return
        cat = cat.with_columns(
            pl.when(sel)
            .then(pl.col("snapshot_hash") == snapshot_hash)
            .otherwise(pl.col("is_reference"))
            .alias("is_reference")
        )
        _atomic_write_parquet(cat, self.path)
        self._log("set_reference", symbol, timeframe, snapshot_hash, previous, note)

    def get_reference(self, symbol: str, timeframe: str) -> SeriesMetadata:
        cat = self.table().filter(
            (pl.col("symbol") == symbol)
            & (pl.col("timeframe") == timeframe)
            & pl.col("is_reference")
        )
        if cat.height == 0:
            raise DataError(
                f"no reference snapshot for ({symbol}, {timeframe})", stage="catalog", symbol=symbol
            )
        if cat.height > 1:
            raise DataError(
                f"catalog corrupt: {cat.height} references for ({symbol}, {timeframe})",
                stage="catalog",
                symbol=symbol,
            )
        return _row_to_meta(cat.row(0, named=True))

    def get(self, key: SnapshotKey) -> SeriesMetadata:
        """Metadata of the registered snapshot ``key``."""
        rows = self.table().filter(_key_filter(key))
        if rows.height != 1:
            raise DataError(
                f"snapshot {key.short()} is not registered in the catalog",
                stage="catalog",
                symbol=key.symbol,
            )
        return _row_to_meta(rows.row(0, named=True))

    def quality_status(self, key: SnapshotKey) -> str:
        """``ok | warning | critical | unchecked`` of a registered snapshot (F-0.1.6)."""
        rows = self.table().filter(_key_filter(key))
        if rows.height != 1:
            raise DataError(
                f"snapshot {key.short()} is not registered in the catalog",
                stage="catalog",
                symbol=key.symbol,
            )
        return str(rows["quality_status"][0])

    def set_quality_status(self, key: SnapshotKey, status: str, note: str = "") -> None:
        """Record the quality status of a registered snapshot; logged as a ``quality`` event."""
        if status not in QUALITY_STATUSES:
            raise DataError(f"invalid quality status {status!r}; expected {QUALITY_STATUSES}")
        cat = self.table()
        sel = _key_filter(key)
        if cat.filter(sel).height != 1:
            raise DataError(
                f"snapshot {key.short()} is not registered in the catalog",
                stage="catalog",
                symbol=key.symbol,
            )
        cat = cat.with_columns(
            pl.when(sel)
            .then(pl.lit(status))
            .otherwise(pl.col("quality_status"))
            .alias("quality_status")
        )
        _atomic_write_parquet(cat, self.path)
        self._log("quality", key.symbol, key.timeframe, key.snapshot_hash, None, note or status)

    def retire(self, hashes: list[str], note: str) -> pl.DataFrame:
        """Remove **derived, never-referenced** snapshots from the catalog; return their rows.

        The one exception to D-392 that D-702 allows: a clean-layer snapshot written by an earlier
        pass of T04k, whose stored metadata is stale. Refused -- nothing changes -- if any hash is
        a raw snapshot (``derived_from`` empty), is a reference now, or **was ever** a reference
        (a ``set_reference`` event names it). One ``retire`` event per snapshot, one atomic
        rewrite. The snapshot files themselves are the store's business
        (:meth:`SnapshotStore.quarantine`).
        """
        wanted = set(hashes)
        cat = self.table()
        rows = cat.filter(pl.col("snapshot_hash").is_in(sorted(wanted)))
        problems: list[str] = []
        if rows.height != len(wanted):
            problems.append(f"{len(wanted) - rows.height} hash(es) not in the catalog")
        if rows.filter(pl.col("derived_from").is_null()).height:
            problems.append("raw snapshots (derived_from empty) are never retired")
        if rows.filter(pl.col("is_reference")).height:
            problems.append("a current reference cannot be retired")
        ever = self.events().filter(
            (pl.col("event") == "set_reference") & pl.col("snapshot_hash").is_in(sorted(wanted))
        )
        if ever.height:
            problems.append(f"{ever['snapshot_hash'].n_unique()} hash(es) were once a reference")
        if problems:
            raise DataError("retire refused: " + "; ".join(problems), stage="catalog")
        _atomic_write_parquet(cat.filter(~pl.col("snapshot_hash").is_in(sorted(wanted))), self.path)
        now = dt.datetime.now(dt.UTC)
        events = pl.DataFrame(
            [
                {
                    "ts": now,
                    "event": "retire",
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "snapshot_hash": r["snapshot_hash"],
                    "previous_reference": None,
                    "note": note,
                }
                for r in rows.iter_rows(named=True)
            ],
            schema=EVENTS_SCHEMA,
        )
        _atomic_write_parquet(pl.concat([self.events(), events]), self.events_path)
        return rows

    def has_reference(self, symbol: str, timeframe: str) -> bool:
        try:
            self.get_reference(symbol, timeframe)
        except DataError:
            return False
        return True
