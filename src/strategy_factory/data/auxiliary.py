"""Auxiliary series next to a traded symbol: the as-of join (F-0.1.11, D-014, D-718, D-719).

(The module is not called ``aux``: that is a reserved device name on Windows.)

An aux series (VIX, an index, the dollar) is **never a candidate**; a filter reads it next to a
traded symbol, and only through this join (T04m). Pure functions on NumPy arrays; the reading
itself (reference snapshots, development window, holdout) is :mod:`strategy_factory.data.split`.

**Final instant** of an aux bar (``ts`` = its session date at 00:00 UTC): the session date at
``value_final_time_local`` in ``value_final_tz`` -- the latest instant the provider's published
schedule lets the day's value change (D-718). A ``to_verify`` series has no verified time: its
base instant is 24:00 of the session date in the series' own zone, and it gets
``unverified_extra_lag_days`` more (D-014). The lag is added in local calendar days, so DST never
shifts it.

**Decision instant** of a traded bar i (rule 3: signals use data up to the close of bar i): the
bar's end -- ``ts + step`` intraday, and for a daily bar the end of its session in the consuming
symbol's calendar: the NYSE close (early closes included) for US equities, 24:00 UTC for the 24x5
markets (D-010, D-032).

**The rule:** bar i reads the latest aux bar whose final instant is **strictly before** its
decision instant. A value stays usable for ``max_stale_sessions`` traded sessions of the
consuming symbol after the session in which it became usable (the first session of the consumer's
calendar that ends after its final instant); later bars get ``idx = -1`` (D-719). Sessions are
counted on the calendar, not on the bars read, so the count never depends on where a window
starts. A value final before the consumer calendar's first day has an unknown age and counts as
stale (the NYSE calendar file starts 2016-01-04).

A filter computes its indicator **on the aux bars** (causal) and reads it at ``idx``.
"""

from __future__ import annotations

import datetime as dt
import zoneinfo
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from strategy_factory.core.errors import DataError
from strategy_factory.data.download.alpaca_reference import load_sessions
from strategy_factory.data.schedule import MARKETS_24X5
from strategy_factory.data.schema import SeriesMetadata, SnapshotKey

I64 = npt.NDArray[np.int64]
F64 = npt.NDArray[np.float64]

AuxCalendar = Literal["nyse", "nyse_bond", "weekdays"]
AUX_CALENDARS: tuple[str, ...] = ("nyse", "nyse_bond", "weekdays")
AUX_CALENDAR_NOTE = "aux_calendar="
US_PER_DAY = 86_400_000_000
US_PER_HOUR = 3_600_000_000
NYSE_TZ = "America/New_York"
_STEP_US = {
    "1m": 60_000_000,
    "5m": 300_000_000,
    "15m": 900_000_000,
    "1H": US_PER_HOUR,
    "4H": 4 * US_PER_HOUR,
}
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
_EPOCH_DATE = dt.date(1970, 1, 1)


def aux_calendar_of(notes: str) -> str | None:
    """The ``aux_calendar=`` recorded in an aux snapshot's notes (D-720), or None."""
    for part in notes.split(";"):
        part = part.strip()
        if part.startswith(AUX_CALENDAR_NOTE):
            value = part[len(AUX_CALENDAR_NOTE) :].strip()
            return value if value in AUX_CALENDARS else None
    return None


def _us(t: dt.datetime) -> int:
    return (t - _EPOCH) // dt.timedelta(microseconds=1)


def _day(ts_us: int) -> dt.date:
    return _EPOCH_DATE + dt.timedelta(days=int(ts_us // US_PER_DAY))


def final_instants(ts_us: I64, meta: SeriesMetadata, extra_lag_days: int) -> I64:
    """Final instant (µs UTC) of each aux bar (see the module docstring); ascending."""
    verified = meta.value_final_status == "verified"
    if verified:
        if not (meta.value_final_time_local and meta.value_final_tz):
            raise DataError(
                "aux series marked verified without a close time and zone (D-718)",
                symbol=meta.symbol,
            )
        tz = zoneinfo.ZoneInfo(meta.value_final_tz)
        at, shift, lag = dt.time.fromisoformat(meta.value_final_time_local), 0, 0
    else:  # not verified: 24:00 of the session date in the series' zone, + the lag (D-718)
        zone = meta.value_final_tz or meta.original_tz
        if not zone or zone == "unknown":
            raise DataError(
                "aux series without a final time or a zone: its final instant is undefined",
                symbol=meta.symbol,
            )
        tz, at, shift, lag = zoneinfo.ZoneInfo(zone), dt.time(0), 1, extra_lag_days
    out = np.empty(len(ts_us), dtype=np.int64)
    for i, t in enumerate(np.asarray(ts_us, dtype=np.int64)):
        day = _day(int(t)) + dt.timedelta(days=shift + lag)
        out[i] = _us(dt.datetime.combine(day, at, tzinfo=tz))
    if out.size > 1 and np.any(np.diff(out) <= 0):
        raise DataError("aux final instants are not strictly increasing", symbol=meta.symbol)
    return out


@dataclass(frozen=True)
class SessionCalendar:
    """Sessions of the **consuming** symbol: date (days since the epoch) and end (µs UTC)."""

    kind: Literal["nyse", "24x5"]
    days: I64
    end_us: I64

    def index_of(self, days: I64) -> I64:
        idx = np.searchsorted(self.days, days)
        ok = (idx < self.days.size) & (self.days[np.minimum(idx, self.days.size - 1)] == days)
        if not bool(np.all(ok)):
            bad = _day(int(days[~ok][0]) * US_PER_DAY)
            raise DataError(f"traded bar on {bad} is not a session of the {self.kind} calendar")
        return idx.astype(np.int64)


def nyse_calendar(sessions_file: Path) -> SessionCalendar:
    """NYSE sessions ending at their close (early closes included)."""
    sessions = load_sessions(sessions_file)
    tz = zoneinfo.ZoneInfo(NYSE_TZ)
    dates = sorted(sessions)
    days = np.array([(d - _EPOCH_DATE).days for d in dates], dtype=np.int64)
    end = np.array(
        [
            _us(dt.datetime.combine(d, dt.time.fromisoformat(sessions[d][1]), tzinfo=tz))
            for d in dates
        ],
        dtype=np.int64,
    )
    return SessionCalendar("nyse", days, end)


def weekday_calendar(first: dt.date, last: dt.date) -> SessionCalendar:
    """Monday..Friday, each ending at 24:00 UTC (the 24x5 trading day, D-010)."""
    lo, hi = (first - _EPOCH_DATE).days, (last - _EPOCH_DATE).days
    days = np.arange(lo, hi + 1, dtype=np.int64)
    days = days[((days + 3) % 7) < 5]  # 1970-01-01 was a Thursday (weekday 3)
    return SessionCalendar("24x5", days, (days + 1) * US_PER_DAY)


def consumer_calendar(
    asset_class: str, sessions_file: Path, first: dt.date, last: dt.date
) -> SessionCalendar:
    """The session calendar of a traded symbol of ``asset_class``."""
    if asset_class == "us_equity":
        return nyse_calendar(sessions_file)
    if asset_class in MARKETS_24X5:
        return weekday_calendar(first, last)
    raise DataError(f"no session calendar for an aux join on asset class {asset_class!r}")


def bar_sessions(ts_us: I64, timeframe: str, cal: SessionCalendar) -> I64:
    """Index into ``cal`` of the session each traded bar belongs to."""
    ts = np.asarray(ts_us, dtype=np.int64)
    if timeframe == "1D":
        days = ts // US_PER_DAY
    elif cal.kind == "nyse":
        tz = zoneinfo.ZoneInfo(NYSE_TZ)
        days = np.array(
            [
                (
                    (_EPOCH + dt.timedelta(microseconds=int(t))).astimezone(tz).date() - _EPOCH_DATE
                ).days
                for t in ts
            ],
            dtype=np.int64,
        )
    else:  # 24x5 intraday: the UTC date; Saturday and Sunday hours belong to Monday (D-010)
        days = ts // US_PER_DAY
        weekday = (days + 3) % 7
        days = np.where(weekday == 5, days + 2, np.where(weekday == 6, days + 1, days))
    return cal.index_of(days)


def decision_instants(ts_us: I64, timeframe: str, cal: SessionCalendar, sessions: I64) -> I64:
    """End of each traded bar: ``ts + step`` intraday, the session's end for daily bars."""
    if timeframe == "1D":
        return cal.end_us[sessions]
    if timeframe not in _STEP_US:
        raise DataError(f"unknown timeframe {timeframe!r} for an aux join")
    return np.asarray(ts_us, dtype=np.int64) + _STEP_US[timeframe]


def asof_index(
    decision_us: I64, final_us: I64, usable_session: I64, sessions: I64, max_stale_sessions: int
) -> I64:
    """Per traded bar: the latest aux bar final strictly before its decision, or -1 (D-719)."""
    if final_us.size == 0:  # nothing final before the window's end
        return np.full(np.shape(decision_us), -1, dtype=np.int64)
    j = np.searchsorted(final_us, decision_us, side="left").astype(np.int64) - 1
    has = j >= 0
    age = sessions - usable_session[np.maximum(j, 0)]
    return np.where(has & (age <= max_stale_sessions), j, -1).astype(np.int64)


@dataclass(frozen=True)
class AuxView:
    """An aux series aligned to a traded symbol's bars (read it through ``idx``)."""

    key: SnapshotKey  # the aux snapshot read -- the run records it (rule 8)
    traded: SnapshotKey
    ts: I64  # aux bar starts, ascending
    open: F64
    high: F64
    low: F64
    close: F64
    final_us: I64  # final instant of each aux bar (lag applied)
    idx: I64  # per traded bar: index into the aux arrays, -1 = none or stale
    decision_us: I64  # the traded bars' decision instants

    def at_bars(self, values: npt.NDArray[Any]) -> F64:
        """``values`` (one per aux bar, e.g. an indicator) read at each traded bar; NaN at -1."""
        v = np.asarray(values, dtype=np.float64)
        if v.shape != self.close.shape:
            raise DataError("values must have one entry per aux bar")
        out = np.full(self.idx.shape, np.nan)
        ok = self.idx >= 0
        out[ok] = v[self.idx[ok]]
        return out


def build_view(
    aux_meta: SeriesMetadata,
    aux: dict[str, npt.NDArray[Any]],
    traded_meta: SeriesMetadata,
    traded_ts_us: I64,
    *,
    extra_lag_days: int,
    max_stale_sessions: int,
    sessions_file: Path,
) -> AuxView:
    """Align ``aux`` (arrays ``ts, open, high, low, close``) to the traded bars ``traded_ts_us``.

    Only aux bars final before the **last** traded bar's decision instant are returned, so
    nothing after the window's end is ever visible.
    """
    if aux_meta.asset_class != "aux":
        raise DataError(f"{aux_meta.symbol} is not an auxiliary series", symbol=aux_meta.symbol)
    traded_ts = np.asarray(traded_ts_us, dtype=np.int64)
    if traded_ts.size == 0:
        raise DataError("no traded bars to align to", symbol=traded_meta.symbol)
    aux_ts = np.asarray(aux["ts"], dtype=np.int64)
    final = final_instants(aux_ts, aux_meta, extra_lag_days)
    first = min(_day(int(traded_ts[0])), _day(int(aux_ts[0])) if aux_ts.size else _day(0))
    last = _day(int(traded_ts[-1])) + dt.timedelta(days=7)
    cal = consumer_calendar(traded_meta.asset_class, sessions_file, first, last)
    sessions = bar_sessions(traded_ts, traded_meta.timeframe, cal)
    decision = decision_instants(traded_ts, traded_meta.timeframe, cal, sessions)
    keep = final < int(decision.max())
    final = final[keep]
    usable = np.searchsorted(cal.end_us, final, side="right").astype(np.int64)
    # a value final before the consumer calendar's first day: its age is unknown -> stale
    usable[final < cal.days[0] * US_PER_DAY] = -(max_stale_sessions + 1)
    idx = asof_index(decision, final, usable, sessions, max_stale_sessions)
    return AuxView(
        key=aux_meta.key(),
        traded=traded_meta.key(),
        ts=aux_ts[keep],
        open=np.asarray(aux["open"], dtype=np.float64)[keep],
        high=np.asarray(aux["high"], dtype=np.float64)[keep],
        low=np.asarray(aux["low"], dtype=np.float64)[keep],
        close=np.asarray(aux["close"], dtype=np.float64)[keep],
        final_us=final,
        idx=idx,
        decision_us=decision,
    )
