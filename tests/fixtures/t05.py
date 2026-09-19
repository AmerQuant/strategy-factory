"""Synthetic series and an in-memory split ledger for the T05 tests."""

from __future__ import annotations

import datetime as dt
import zoneinfo
from typing import Any

import numpy as np
import polars as pl

from fixtures.bars import make_meta
from strategy_factory.core.errors import HoldoutAccessError
from strategy_factory.data.schema import SeriesMetadata, SnapshotKey

NY = zoneinfo.ZoneInfo("America/New_York")
UTC_TS = pl.Datetime("us", "UTC")
FAKE_HASH = "a" * 64  # in-memory tests: a key without a stored file (the store replaces it)


def bars_from_close(ts: list[dt.datetime], close: np.ndarray, **extra: Any) -> pl.DataFrame:
    """Valid OHLCV bars around ``close`` (open = previous close)."""
    close = np.asarray(close, dtype=np.float64)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * 1.001
    low = np.minimum(open_, close) * 0.999
    data: dict[str, Any] = {
        "ts": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.full(len(ts), 100.0) + np.arange(len(ts)),
    }
    data.update(extra)
    df = pl.DataFrame(data)
    return df.with_columns(pl.col("ts").cast(UTC_TS))


def random_close(n: int, seed: int = 1, start: float = 100.0, vol: float = 0.002) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(0.0, vol, n)))


def fx_hours(
    start: dt.datetime, end: dt.datetime, break_hour_ny: int | None = None
) -> list[dt.datetime]:
    """Hourly bar starts of a 24x5 market: Sun 17:00 .. Fri 17:00 New York, minus the break."""
    out = []
    t = start
    while t <= end:
        local = t.astimezone(NY)
        wm = (local.isoweekday() - 1) * 1440 + local.hour * 60
        in_week = wm >= 6 * 1440 + 17 * 60 or wm < 4 * 1440 + 17 * 60
        if in_week and local.hour != break_hour_ny:
            out.append(t)
        t += dt.timedelta(hours=1)
    return out


def fx_bars(
    start: dt.datetime, end: dt.datetime, break_hour_ny: int | None = None, seed: int = 1
) -> pl.DataFrame:
    ts = fx_hours(start, end, break_hour_ny)
    return bars_from_close(ts, random_close(len(ts), seed))


def hourly(start: dt.datetime, n: int) -> list[dt.datetime]:
    return [start + dt.timedelta(hours=i) for i in range(n)]


def fx_meta(**overrides: Any) -> SeriesMetadata:
    base: dict[str, Any] = {
        "source": "dukascopy",
        "source_symbol": "EURUSD",
        "symbol": "EURUSD",
        "asset_class": "fx",
        "timeframe": "1H",
        "price_type": "mid",
        "adjustment": "raw",
        "session": "24x5",
        "feed": "none",
        "volume_quality": "partial",
        "original_tz": "UTC",
        "snapshot_hash": FAKE_HASH,
    }
    base.update(overrides)
    return make_meta(**base)


def crypto_meta(**overrides: Any) -> SeriesMetadata:
    base: dict[str, Any] = {
        "source": "test",
        "source_symbol": "BTCUSD",
        "symbol": "BTCUSD",
        "asset_class": "crypto",
        "timeframe": "1H",
        "price_type": "trade",
        "adjustment": "raw",
        "session": "24x7",
        "feed": "none",
        "volume_quality": "full",
        "original_tz": "UTC",
        "snapshot_hash": FAKE_HASH,
    }
    base.update(overrides)
    return make_meta(**base)


class MemoryLedger:
    """In-memory :class:`~strategy_factory.data.split.SplitLedger` with the one-shot rule."""

    def __init__(self) -> None:
        self.snapshots: dict[SnapshotKey, bool] = {}
        self.splits: dict[SnapshotKey, dict[str, Any]] = {}
        self.accesses: dict[str, dict[str, Any]] = {}

    def register_snapshot(self, meta: SeriesMetadata, is_reference: bool) -> None:
        self.snapshots[meta.key()] = is_reference

    def get_split(self, key: SnapshotKey) -> dict[str, Any] | None:
        return self.splits.get(key)

    def add_split(self, split: Any) -> None:
        assert split.key in self.snapshots, "split before snapshot registration (FK)"
        assert split.key not in self.splits, "one split per snapshot key (unique)"
        self.splits[split.key] = {
            **split.boundaries(),
            "expected_holdout_trades": split.expected_holdout_trades,
        }

    def record_holdout_access(self, candidate_id: str, result: dict[str, Any]) -> None:
        if candidate_id in self.accesses:
            raise HoldoutAccessError(f"holdout already accessed for {candidate_id!r}")
        self.accesses[candidate_id] = result
