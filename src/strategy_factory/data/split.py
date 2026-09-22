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
**only** path to holdout bars: it first checks the calling stage, then records the access in
``holdout_access`` (one-shot per candidate; a second call raises
:class:`HoldoutAccessError`), then reads the bars.

**Stage guard (D-306, T10b):** only stage 6 may open a holdout. The allowed stage is the
module constant :data:`HOLDOUT_STAGE`, deliberately **not** a config value: D-306 requires it
to be enforced in code, so no YAML, environment variable or pipeline config can widen it. Any
other ``stage`` raises :class:`HoldoutAccessError` **before** the ledger is touched, so a
wrong caller never spends a candidate's one-shot access.

Conversion pairs (D-316) are auxiliary inputs read over the **traded** symbol's window, never
beyond its end: :meth:`DataAccess.conversion_bars` for the development segment, and
:meth:`SplitManager.open_holdout_with_conversion` together with the traded candidate's
one-shot holdout access. Only configured conversion pairs (never the traded symbol) can be
read this way, and neither records nor consumes the conversion pair's own holdout.

Auxiliary series (``asset_class aux``: VIX, the indices, the dollar; T04m) are **never
candidates**: :meth:`SplitManager.compute`, :meth:`~SplitManager.registered` and
:meth:`~SplitManager.development_bars` refuse them, so an aux series never gets a split or a
holdout record. They are read only through the as-of join of
:mod:`strategy_factory.data.auxiliary` over a **traded** symbol's window:
:meth:`DataAccess.aux` for the development segment, and
:meth:`SplitManager.open_holdout_with_inputs` together with the traded candidate's one-shot
holdout access (the D-316 pattern).
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any, Protocol

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from strategy_factory.core.errors import DataError, HoldoutAccessError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.auxiliary import AuxView, build_view
from strategy_factory.data.catalog import Catalog, Splice
from strategy_factory.data.config import AuxConfig, SplitConfig, load_aux_config
from strategy_factory.data.conversion import FxConversionConfig
from strategy_factory.data.quality import ensure_usable
from strategy_factory.data.schema import SeriesMetadata, SnapshotKey
from strategy_factory.data.store import SnapshotStore

log = get_logger(__name__)
_BOUNDARIES = ("dev_start", "dev_end", "embargo_bars", "holdout_start", "holdout_end")

#: The only stage allowed to open a holdout (D-306). A constant in code on purpose: it is
#: **not** read from any config, so no YAML can widen holdout access. Changing it means
#: changing this line, which shows up in a code review.
HOLDOUT_STAGE = "s06_robust"


class HistoryTooShortError(DataError):
    """The snapshot is too short for a development / embargo / holdout split."""


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


def _refuse_aux(snapshot: SeriesMetadata) -> None:
    """An aux series is never a candidate: no split, no development read, no holdout (T04m)."""
    if snapshot.asset_class == "aux":
        raise DataError(
            f"{snapshot.symbol} is an auxiliary series (asset class aux): never a candidate; "
            "read it next to a traded symbol through DataAccess.aux (F-0.1.11)",
            stage="split",
            symbol=snapshot.symbol,
        )


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
        raise HistoryTooShortError(
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
        fx_config: FxConversionConfig | None = None,
        aux_config: AuxConfig | None = None,
    ) -> None:
        self.ledger = ledger
        self.cfg = cfg
        self._fx_config = fx_config  # conversion pairs (D-316); loaded on first use
        self._aux_config = aux_config  # aux as-of rules (F-0.1.11); loaded on first use
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
        _refuse_aux(snapshot)
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
        _refuse_aux(snapshot)
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
        _refuse_aux(snapshot)
        split = self.registered(snapshot)
        key = snapshot.key()
        df = self.store.read_snapshot(key.source, key.symbol, key.timeframe, key.snapshot_hash)
        return df.filter(pl.col("ts") <= split.dev_end).sort("ts")

    @staticmethod
    def _check_stage(stage: str) -> None:
        """Refuse every caller but stage 6, before anything is read or recorded (D-306)."""
        if stage != HOLDOUT_STAGE:
            raise HoldoutAccessError(
                f"stage {stage!r} may not open a holdout: only {HOLDOUT_STAGE!r} may (D-306). "
                "The allowed stage is a constant in code and cannot be changed by a config",
                stage=stage,
            )

    def open_holdout(
        self, candidate_id: str, symbol: str, timeframe: str, *, stage: str
    ) -> pl.DataFrame:
        """Holdout bars of the reference snapshot -- once per candidate, logged first.

        ``stage`` is the calling stage id; anything but :data:`HOLDOUT_STAGE` raises (D-306).
        """
        self._check_stage(stage)
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

    def _conversion_arrays(
        self, pair: str, traded_symbol: str, timeframe: str, start: dt.datetime, end: dt.datetime
    ) -> dict[str, np.ndarray[Any, Any]]:
        """Conversion-pair bars in the traded window ``[start, end]`` (D-316); private.

        ``pair`` must be a conversion pair of ``configs/data/fx_conversion.yaml`` and not the
        traded symbol, so this can never read a traded symbol's holdout. Callers pass only the
        traded symbol's own development or holdout window.
        """
        from strategy_factory.data.conversion import load_fx_config

        if self._fx_config is None:
            self._fx_config = load_fx_config()
        allowed = {rule.pair for rule in self._fx_config.pairs.values()}
        if pair == traded_symbol or pair not in allowed:
            raise DataError(
                f"{pair!r} is not a conversion pair for {traded_symbol} (D-316)",
                stage="split",
                symbol=traded_symbol,
            )
        key = self.reference(pair, timeframe).key()
        df = self.store.read_snapshot(
            key.source,
            key.symbol,
            key.timeframe,
            key.snapshot_hash,
            columns=["ts", "open", "close"],
        )
        df = df.filter((pl.col("ts") >= start) & (pl.col("ts") <= end)).sort("ts")
        epoch = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        window = [(t - epoch) // dt.timedelta(microseconds=1) for t in (start, end)]
        return {
            "ts": df["ts"].dt.epoch("us").to_numpy(),
            "open": df["open"].to_numpy(),
            "close": df["close"].to_numpy(),
            "window_us": np.asarray(window, dtype=np.int64),
        }

    def open_holdout_with_conversion(
        self, candidate_id: str, symbol: str, timeframe: str, pairs: tuple[str, ...], *, stage: str
    ) -> tuple[pl.DataFrame, dict[str, dict[str, np.ndarray[Any, Any]]]]:
        """Holdout bars of ``symbol`` (one-shot, logged) plus its conversion pairs over the
        same window (with ``window_us``); the pairs' own holdouts are not consumed (D-316).

        ``stage`` is checked exactly as in :meth:`open_holdout` (D-306), before anything is
        read: a refused caller neither reads a conversion pair nor spends the one-shot access.
        """
        bars, conv, _ = self.open_holdout_with_inputs(
            candidate_id, symbol, timeframe, pairs=pairs, stage=stage
        )
        return bars, conv

    def open_holdout_with_inputs(
        self,
        candidate_id: str,
        symbol: str,
        timeframe: str,
        *,
        pairs: tuple[str, ...] = (),
        aux: tuple[str, ...] = (),
        stage: str,
    ) -> tuple[pl.DataFrame, dict[str, dict[str, np.ndarray[Any, Any]]], dict[str, AuxView]]:
        """Holdout bars of ``symbol`` (one-shot, logged) plus its conversion pairs (D-316) and
        its aux series (T04m, F-0.1.11) over the same window, in **one** access.

        Neither the pairs' nor the aux series' own holdouts are consumed or recorded. The stage
        is checked first (D-306) and every input is validated before the one-shot access is
        spent, so a refused caller reads nothing and spends nothing.
        """
        self._check_stage(stage)
        split = self.registered(self.reference(symbol, timeframe))
        for pair in pairs:  # validate before the one-shot access is spent
            self._conversion_arrays(
                pair, symbol, timeframe, split.holdout_start, split.holdout_start
            )
        for name in aux:
            self._aux_reference(name, symbol)
        bars = self.open_holdout(candidate_id, symbol, timeframe, stage=stage)
        conv = {
            pair: self._conversion_arrays(
                pair, symbol, timeframe, split.holdout_start, split.holdout_end
            )
            for pair in pairs
        }
        traded = self.reference(symbol, timeframe)
        ts = bars["ts"].dt.epoch("us").to_numpy()
        views = {name: self._aux_view(name, traded, ts) for name in aux}
        return bars, conv, views

    def _aux_reference(self, aux_symbol: str, traded_symbol: str) -> SeriesMetadata:
        if aux_symbol == traded_symbol:
            raise DataError(
                f"{aux_symbol!r} cannot be an aux input of itself", stage="split", symbol=aux_symbol
            )
        meta = self.reference(aux_symbol, "1D")
        if meta.asset_class != "aux":
            raise DataError(
                f"{aux_symbol!r} is not an auxiliary series (asset class {meta.asset_class})",
                stage="split",
                symbol=traded_symbol,
            )
        return meta

    def _aux_view(
        self, aux_symbol: str, traded: SeriesMetadata, traded_ts_us: np.ndarray[Any, Any]
    ) -> AuxView:
        """``aux_symbol`` aligned to ``traded``'s bars ``traded_ts_us`` (F-0.1.11); private.

        Callers pass only the traded symbol's own development or holdout bars.
        """
        if self._aux_config is None:
            self._aux_config = load_aux_config()
        rules = self._aux_config.aux
        meta = self._aux_reference(aux_symbol, traded.symbol)
        key = meta.key()
        df = self.store.read_snapshot(
            key.source,
            key.symbol,
            key.timeframe,
            key.snapshot_hash,
            columns=["ts", "open", "high", "low", "close"],
        ).sort("ts")
        arrays = {c: df[c].to_numpy() for c in ("open", "high", "low", "close")}
        arrays["ts"] = df["ts"].dt.epoch("us").to_numpy()
        return build_view(
            meta,
            arrays,
            traded,
            np.asarray(traded_ts_us, dtype=np.int64),
            extra_lag_days=rules.unverified_extra_lag_days,
            max_stale_sessions=rules.max_stale_sessions,
            sessions_file=rules.sessions_file,
        )


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

    def splices(self, symbol: str, timeframe: str) -> tuple[Splice, ...]:
        """The re-use markers of the reference snapshot (D-709, D-713): a ``research_window``
        entry says the series was derived to start at an unsettled boundary. Read-only: no bar,
        split or holdout is touched; the stage decides what to do with it."""
        return self._splits.catalog.splices(self._splits.reference(symbol, timeframe).key())

    def aux(self, aux_symbol: str, traded_symbol: str, timeframe: str) -> AuxView:
        """``aux_symbol`` aligned to ``traded_symbol``'s **development** bars (F-0.1.11).

        Only aux values final before the last development bar's decision instant are returned;
        the aux series has no split of its own and none is registered (T04m).
        """
        traded = self._splits.reference(traded_symbol, timeframe)
        ts = self._splits.development_bars(traded)["ts"].dt.epoch("us").to_numpy()
        return self._splits._aux_view(aux_symbol, traded, ts)

    def conversion_bars(
        self, pair: str, traded_symbol: str, timeframe: str
    ) -> dict[str, np.ndarray[Any, Any]]:
        """Conversion-pair bars over the **traded** symbol's development window (D-316).

        The window is ``dev_start .. dev_end`` of ``traded_symbol``'s split, never beyond its
        end, whatever the pair's own split is; the pair's holdout is not consumed.
        """
        split = self.split(traded_symbol, timeframe)
        return self._splits._conversion_arrays(
            pair, traded_symbol, timeframe, split.dev_start, split.dev_end
        )
