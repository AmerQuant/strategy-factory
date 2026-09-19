"""Development / embargo / holdout split and the holdout lock (F-0.6.1).

For the bars ``ts[0..n-1]`` of a snapshot (``configs/data/split.yaml``):

* holdout = the last ``holdout_fraction`` of the time span ``ts[n-1] - ts[0]``, but at least
  ``holdout_min_months`` calendar months: it starts at the first bar on or after
  ``min(last - fraction * span, last - months)``;
* embargo = ``max_lookback_bars + max_holding_bars`` bars directly before the holdout;
* development = every bar before the embargo.

Boundaries are bar timestamps and inclusive: ``dev_start..dev_end`` and
``holdout_start..holdout_end``. The split is registered once per snapshot key in the
registry (``splits``); recomputing it with different boundaries is refused, because a moved
boundary would leak holdout bars into development.

:class:`DataAccess` returns development bars only. :meth:`SplitManager.open_holdout` is the
**only** path to holdout bars: it first records the access in ``holdout_access`` (one-shot
per candidate; a second call raises :class:`HoldoutAccessError`), then reads the bars.
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any, Protocol

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from strategy_factory.core.errors import DataError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import SplitConfig
from strategy_factory.data.quality import ensure_usable
from strategy_factory.data.schema import SeriesMetadata, SnapshotKey
from strategy_factory.data.store import SnapshotStore

log = get_logger(__name__)
_BOUNDARIES = ("dev_start", "dev_end", "embargo_bars", "holdout_start", "holdout_end")


class Split(BaseModel):
    """Split of one snapshot; boundaries are inclusive bar timestamps (UTC)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: SnapshotKey
    dev_start: dt.datetime
    dev_end: dt.datetime
    embargo_bars: int = Field(ge=0)
    holdout_start: dt.datetime
    holdout_end: dt.datetime
    expected_holdout_trades: float | None = None
    warnings: tuple[str, ...] = ()

    def boundaries(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in _BOUNDARIES}


class SplitLedger(Protocol):
    """Where splits and holdout accesses are recorded (the registry in production)."""

    def register_snapshot(self, meta: SeriesMetadata, is_reference: bool) -> None: ...

    def get_split(self, key: SnapshotKey) -> dict[str, Any] | None: ...

    def add_split(self, split: Split) -> None: ...

    def record_holdout_access(self, candidate_id: str, result: dict[str, Any]) -> None: ...


class RegistryLedger:
    """:class:`SplitLedger` on the PostgreSQL registry (T03)."""

    def __init__(self, engine: Engine) -> None:
        from strategy_factory.registry.writer import RegistryWriter

        self.engine = engine
        self.writer = RegistryWriter(engine)

    def register_snapshot(self, meta: SeriesMetadata, is_reference: bool) -> None:
        self.writer.register_snapshot(meta.model_dump(mode="json"), is_reference=is_reference)

    def get_split(self, key: SnapshotKey) -> dict[str, Any] | None:
        from strategy_factory.registry.queries import get_split

        return get_split(self.engine, key.model_dump())

    def add_split(self, split: Split) -> None:
        from strategy_factory.registry.writer import SplitRecord

        self.writer.add_split(
            SplitRecord(
                **split.key.model_dump(),
                **split.boundaries(),
                expected_holdout_trades=split.expected_holdout_trades,
            )
        )

    def record_holdout_access(self, candidate_id: str, result: dict[str, Any]) -> None:
        self.writer.record_holdout_access(candidate_id, result)


def _stored_boundaries(row: dict[str, Any]) -> dict[str, Any]:
    """Boundaries of a registry row, datetimes normalized to ``datetime.UTC``."""
    return {
        k: row[k].astimezone(dt.UTC) if isinstance(row[k], dt.datetime) else row[k]
        for k in _BOUNDARIES
    }


def subtract_months(t: dt.datetime, months: int) -> dt.datetime:
    """``t`` minus calendar months (day clipped to the target month's length)."""
    y, m0 = divmod(t.year * 12 + (t.month - 1) - months, 12)
    return t.replace(year=y, month=m0 + 1, day=min(t.day, calendar.monthrange(y, m0 + 1)[1]))


def compute_split(
    ts: pl.Series,
    key: SnapshotKey,
    cfg: SplitConfig,
    trades_per_year: float | None = None,
) -> Split:
    """Split boundaries for the sorted bar starts ``ts`` (pure function)."""
    n = ts.len()
    if n == 0:
        raise DataError("cannot split an empty snapshot", stage="split", symbol=key.symbol)
    first, last = ts[0], ts[-1]
    span = last - first
    cutoff = min(last - cfg.holdout_fraction * span, subtract_months(last, cfg.holdout_min_months))
    h = int(np.searchsorted(ts.to_numpy(), np.datetime64(cutoff.replace(tzinfo=None), "us")))
    e = cfg.embargo_bars
    if h - e <= 0 or h >= n:
        raise DataError(
            f"history too short for a split: {n} bars, holdout from bar {h}, embargo {e} bars "
            f"({first:%Y-%m-%d}..{last:%Y-%m-%d})",
            stage="split",
            symbol=key.symbol,
        )
    hs, he = ts[h], ts[-1]
    expected = None
    warnings: list[str] = []
    if trades_per_year is not None:
        years = (he - hs) / dt.timedelta(days=365.25)
        expected = trades_per_year * years
        if expected < cfg.min_expected_holdout_trades:
            warnings.append(
                f"expected holdout trades {expected:.1f} < {cfg.min_expected_holdout_trades:g}"
                " (longer incubation)"
            )
    return Split(
        key=key,
        dev_start=first,
        dev_end=ts[h - e - 1],
        embargo_bars=e,
        holdout_start=hs,
        holdout_end=he,
        expected_holdout_trades=expected,
        warnings=tuple(warnings),
    )


class SplitManager:
    """Computes, registers and enforces splits; the only path to holdout bars."""

    def __init__(
        self,
        ledger: SplitLedger,
        cfg: SplitConfig,
        store: SnapshotStore | None = None,
        catalog: Catalog | None = None,
    ) -> None:
        self.ledger = ledger
        self.cfg = cfg
        self.store = store if store is not None else SnapshotStore()
        self.catalog = catalog if catalog is not None else Catalog(self.store.root)

    def _ts(self, key: SnapshotKey) -> pl.Series:
        df = self.store.read_snapshot(
            key.source, key.symbol, key.timeframe, key.snapshot_hash, columns=["ts"]
        )
        return df["ts"].sort()

    def compute(
        self,
        symbol: str,
        timeframe: str,
        snapshot: SeriesMetadata,
        trades_per_year: float | None = None,
    ) -> Split:
        """Compute the split of ``snapshot`` and register it (idempotent for equal bounds)."""
        if snapshot.symbol != symbol or snapshot.timeframe != timeframe:
            raise DataError(
                f"snapshot {snapshot.symbol} {snapshot.timeframe} does not match "
                f"{symbol} {timeframe}",
                stage="split",
                symbol=symbol,
            )
        key = snapshot.key()
        split = compute_split(self._ts(key), key, self.cfg, trades_per_year)
        for w in split.warnings:
            log.warning("%s %s: %s", symbol, timeframe, w)
        existing = self.ledger.get_split(key)
        if existing is None:
            is_ref = (
                self.catalog.has_reference(symbol, timeframe)
                and self.catalog.get_reference(symbol, timeframe).snapshot_hash == key.snapshot_hash
            )
            self.ledger.register_snapshot(snapshot, is_reference=is_ref)
            self.ledger.add_split(split)
            return split
        stored = _stored_boundaries(existing)
        if stored != split.boundaries():
            raise DataError(
                f"split of {key.short()} is already registered with other boundaries "
                f"({stored}); a moved boundary would leak holdout bars",
                stage="split",
                symbol=symbol,
            )
        return split

    def registered(self, snapshot: SeriesMetadata) -> Split:
        """The registered split of ``snapshot`` (computed and registered on first use)."""
        key = snapshot.key()
        existing = self.ledger.get_split(key)
        if existing is None:
            return self.compute(snapshot.symbol, snapshot.timeframe, snapshot)
        return Split(
            key=key,
            **_stored_boundaries(existing),
            expected_holdout_trades=existing.get("expected_holdout_trades"),
        )

    def reference(self, symbol: str, timeframe: str) -> SeriesMetadata:
        """Reference snapshot of ``(symbol, timeframe)``; refused if its quality is critical."""
        meta = self.catalog.get_reference(symbol, timeframe)
        ensure_usable(self.catalog, meta.key())
        return meta

    def development_bars(self, snapshot: SeriesMetadata) -> pl.DataFrame:
        split = self.registered(snapshot)
        key = snapshot.key()
        df = self.store.read_snapshot(key.source, key.symbol, key.timeframe, key.snapshot_hash)
        return df.filter(pl.col("ts") <= split.dev_end).sort("ts")

    def open_holdout(self, candidate_id: str, symbol: str, timeframe: str) -> pl.DataFrame:
        """Holdout bars of the reference snapshot -- once per candidate, logged first."""
        meta = self.reference(symbol, timeframe)
        split = self.registered(meta)
        self.ledger.record_holdout_access(
            candidate_id,
            {
                **split.key.model_dump(),
                "holdout_start": split.holdout_start.isoformat(),
                "holdout_end": split.holdout_end.isoformat(),
            },
        )
        key = split.key
        df = self.store.read_snapshot(key.source, key.symbol, key.timeframe, key.snapshot_hash)
        return df.filter(pl.col("ts") >= split.holdout_start).sort("ts")


class DataAccess:
    """Bars for the pipeline: the **development segment only** of the reference snapshot."""

    def __init__(self, splits: SplitManager) -> None:
        self._splits = splits

    def bars(self, symbol: str, timeframe: str) -> pl.DataFrame:
        return self._splits.development_bars(self._splits.reference(symbol, timeframe))

    def arrays(self, symbol: str, timeframe: str) -> dict[str, np.ndarray[Any, Any]]:
        """Development bars as NumPy arrays (``ts`` as int64 microseconds UTC)."""
        df = self.bars(symbol, timeframe)
        out = {c: df[c].to_numpy() for c in df.columns if c != "ts"}
        out["ts"] = df["ts"].dt.epoch("us").to_numpy()
        return out

    def split(self, symbol: str, timeframe: str) -> Split:
        """Split boundaries (no bars) of the reference snapshot."""
        return self._splits.registered(self._splits.reference(symbol, timeframe))
