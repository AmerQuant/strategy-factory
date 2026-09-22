"""Expected bar schedules and resampling periods (F-0.1.6, F-0.1.7).

* **24x5 markets** (``fx``, ``metal``, ``energy_cfd``, ``index_cfd``): a bar is expected when
  its local start (``weekly_window.timezone``) lies in ``[week_open, week_close)`` and its
  local hour is not the daily break. The break is *learned from the data*
  (:func:`learn_break`): the local hour most often missing inside the trading day.
* **crypto**: every bar, 24x7.
* **us_equity**: the NYSE sessions of ``configs/calendars/nyse_sessions.csv`` -- daily bars
  at the session date 00:00 UTC; hourly bars from ``us_equity_first_bar`` while the bar
  starts before the session close (``RTH_hour_aligned``).
* **aux** (T04m, D-720): daily bars on the series' own calendar, from ``aux_calendar=`` in its
  notes: ``nyse``, ``nyse_bond`` (NYSE minus the US bond-market closures) or ``weekdays``.
* other asset classes: no expected schedule yet (checks that need one are skipped).

:func:`period_start` maps bar starts to the start of their resampling period (research:
day boundary 00:00 UTC, weekend hours of 24x5 markets merged into Monday, fixed UTC 4H
blocks; broker_session: periods from the configured session start, parity only).
"""

from __future__ import annotations

import csv
import datetime as dt
import zoneinfo
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl

from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.data.config import (
    BreakDetectionConfig,
    BrokerSessionConfig,
    QualityConfig,
    WeeklyWindowConfig,
    week_minute,
)
from strategy_factory.data.download.alpaca_reference import load_sessions

ResampleMode = Literal["research", "broker_session"]
MARKETS_24X5 = frozenset({"fx", "metal", "energy_cfd", "index_cfd"})
MARKETS_24H = MARKETS_24X5 | {"crypto"}
TF_STEP: dict[str, dt.timedelta] = {
    "1m": dt.timedelta(minutes=1),
    "5m": dt.timedelta(minutes=5),
    "15m": dt.timedelta(minutes=15),
    "1H": dt.timedelta(hours=1),
    "4H": dt.timedelta(hours=4),
    "1D": dt.timedelta(days=1),
}
_EVERY = {"1m": "1m", "5m": "5m", "15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}
UTC_TS = pl.Datetime("us", "UTC")


def utc_grid(start: dt.datetime, end: dt.datetime, step: dt.timedelta) -> pl.Series:
    """Bar starts ``start, start + step, ... <= end`` (UTC)."""
    if end < start:
        return pl.Series("ts", [], dtype=UTC_TS)
    return pl.datetime_range(start, end, step, eager=True, time_zone="UTC").cast(UTC_TS)


def in_week_window(ts: pl.Series, window: WeeklyWindowConfig) -> pl.Series:
    """True where the local bar start lies in ``[week_open, week_close)``."""
    local = ts.dt.convert_time_zone(window.timezone)
    wm = (
        (local.dt.weekday().cast(pl.Int32) - 1) * 1440
        + local.dt.hour().cast(pl.Int32) * 60
        + local.dt.minute().cast(pl.Int32)
    )
    lo, hi = week_minute(window.week_open), week_minute(window.week_close)
    return (wm >= lo) | (wm < hi) if lo > hi else (wm >= lo) & (wm < hi)


def local_hour(ts: pl.Series, tz: str) -> pl.Series:
    return ts.dt.convert_time_zone(tz).dt.hour().cast(pl.Int32)


@dataclass(frozen=True)
class BreakInfo:
    """Daily break of a 24x5 market learned from the data."""

    timezone: str
    hour_local: int | None  # None: no break found
    share: float  # share of trading days on which that local hour is missing
    modal_hour_utc: int | None  # most frequent UTC hour of the missing break bars

    def as_dict(self) -> dict[str, object]:
        return {
            "timezone": self.timezone,
            "break_hour_local": self.hour_local,
            "share": round(self.share, 4),
            "modal_break_hour_utc": self.modal_hour_utc,
        }


def learn_break(
    ts: pl.Series, step: dt.timedelta, window: WeeklyWindowConfig, cfg: BreakDetectionConfig
) -> BreakInfo:
    """Modal missing local hour inside the trading week (short gaps only)."""
    none = BreakInfo(window.timezone, None, 0.0, None)
    if ts.len() < 2 or step > dt.timedelta(hours=1):
        return none
    present = ts.sort().unique(maintain_order=True)
    grid = utc_grid(present[0], present[-1], step)
    frame = pl.DataFrame({"ts": grid}).with_columns(
        in_window=in_week_window(grid, window),
        present=grid.is_in(present.implode()),
        hour=local_hour(grid, window.timezone),
        hour_utc=grid.dt.hour().cast(pl.Int32),
    )
    frame = frame.with_columns(missing=pl.col("in_window") & ~pl.col("present"))
    frame = frame.with_columns(run=(pl.col("missing") != pl.col("missing").shift(1)).cum_sum())
    run_len = frame.group_by("run").agg(pl.len().alias("run_len"))
    frame = frame.join(run_len, on="run", how="left")
    max_slots = int(dt.timedelta(hours=cfg.max_gap_hours) / step)
    short = frame.filter(pl.col("missing") & (pl.col("run_len") <= max_slots))
    if short.height == 0:
        return none
    counts = short.group_by("hour").len().sort(["len", "hour"], descending=[True, False])
    hour = int(counts["hour"][0])
    expected = frame.filter(pl.col("in_window") & (pl.col("hour") == hour)).height
    share = counts["len"][0] / expected if expected else 0.0
    if share < cfg.min_share:
        return BreakInfo(window.timezone, None, share, None)
    utc = (
        short.filter(pl.col("hour") == hour)
        .group_by("hour_utc")
        .len()
        .sort(["len", "hour_utc"], descending=[True, False])
    )
    return BreakInfo(window.timezone, hour, share, int(utc["hour_utc"][0]))


def period_start(
    ts: pl.Expr,
    timeframe: str,
    asset_class: str,
    mode: ResampleMode = "research",
    broker: BrokerSessionConfig | None = None,
) -> pl.Expr:
    """Start (UTC) of the ``timeframe`` period that contains bar start ``ts``.

    research: 1D = UTC date 00:00, Saturday/Sunday bars of 24x5 markets belong to Monday;
    intraday = fixed UTC blocks (00-04, 04-08, ... for 4H).
    broker_session: periods start at ``broker.start`` local; a daily bar is stamped with
    its trading date (the date on which the session ends) at 00:00 UTC.
    """
    if mode == "research":
        if timeframe == "1D":
            day = ts.dt.truncate("1d")
            if asset_class in MARKETS_24X5:
                wd = ts.dt.weekday()
                shift = (
                    pl.when(wd == 7)
                    .then(pl.duration(days=1))
                    .when(wd == 6)
                    .then(pl.duration(days=2))
                    .otherwise(pl.duration(days=0))
                )
                day = day + shift
            return day
        return ts.dt.truncate(_EVERY[timeframe])
    cfg = broker or BrokerSessionConfig()
    start = dt.time.fromisoformat(cfg.start)
    offset = dt.timedelta(hours=start.hour, minutes=start.minute)
    local = ts.dt.convert_time_zone(cfg.timezone).dt.replace_time_zone(None) - offset
    if timeframe == "1D":
        day = local.dt.truncate("1d") + pl.duration(days=1 if offset else 0)
        return day.dt.replace_time_zone("UTC")
    block = local.dt.truncate(_EVERY[timeframe]) + offset
    return block.dt.replace_time_zone(cfg.timezone, ambiguous="earliest").dt.convert_time_zone(
        "UTC"
    )


def mode_of(notes: str) -> ResampleMode:
    """Resampling mode recorded in a derived snapshot's notes (research by default)."""
    return "broker_session" if "mode=broker_session" in notes else "research"


@dataclass(frozen=True)
class ExpectedSchedule:
    starts: pl.Series | None  # expected bar starts (UTC) in [first, last]; None = unknown
    reason: str  # why there is no schedule, or how it was built
    break_info: BreakInfo | None = None
    # bars outside [lo, hi) are not judged (e.g. beyond the NYSE calendar's range)
    coverage: tuple[dt.datetime, dt.datetime] | None = None


def expected_24h(
    asset_class: str,
    timeframe: str,
    first: dt.datetime,
    last: dt.datetime,
    window: WeeklyWindowConfig,
    break_hour: int | None,
    step: dt.timedelta | None = None,
    mode: ResampleMode = "research",
    broker: BrokerSessionConfig | None = None,
) -> pl.Series:
    """Expected starts of a 24x5/24x7 series; coarse timeframes via the hourly grid."""
    fine = step or min(TF_STEP[timeframe], dt.timedelta(hours=1))
    lo = (first - dt.timedelta(days=8)).replace(minute=0, second=0, microsecond=0)
    grid = utc_grid(lo, last + dt.timedelta(days=8), fine)
    keep = pl.Series([True] * grid.len())
    if asset_class in MARKETS_24X5:
        keep = in_week_window(grid, window)
        if break_hour is not None:
            keep = keep & (local_hour(grid, window.timezone) != break_hour)
    fine_ts = grid.filter(keep)
    if TF_STEP[timeframe] <= fine:
        starts = fine_ts
    else:
        starts = (
            pl.DataFrame({"ts": fine_ts})
            .select(period_start(pl.col("ts"), timeframe, asset_class, mode, broker))
            .to_series()
            .unique()
            .sort()
        )
    return starts.filter((starts >= first) & (starts <= last)).alias("ts")


def expected_us_equity(
    timeframe: str,
    first: dt.datetime,
    last: dt.datetime,
    sessions: dict[dt.date, tuple[str, str]],
    cfg: QualityConfig,
) -> pl.Series:
    tz = zoneinfo.ZoneInfo(cfg.us_equity_timezone)
    first_bar = dt.time.fromisoformat(cfg.us_equity_first_bar)
    out: list[dt.datetime] = []
    for day in sorted(d for d in sessions if first.date() <= d <= last.date()):
        if timeframe == "1D":
            out.append(dt.datetime.combine(day, dt.time(0), tzinfo=dt.UTC))
            continue
        close = dt.datetime.combine(day, dt.time.fromisoformat(sessions[day][1]), tzinfo=tz)
        bar = dt.datetime.combine(day, first_bar, tzinfo=tz)
        while bar < close:
            out.append(bar.astimezone(dt.UTC))
            bar += dt.timedelta(hours=1)
    starts = pl.Series("ts", out, dtype=UTC_TS)
    return starts.filter((starts >= first) & (starts <= last))


def expected_schedule(
    ts: pl.Series,
    asset_class: str,
    timeframe: str,
    cfg: QualityConfig,
    notes: str = "",
    sessions_file: Path | None = None,
) -> ExpectedSchedule:
    """Expected bar starts between the first and last bar of ``ts`` (see module docstring)."""
    if ts.len() == 0:
        return ExpectedSchedule(None, "empty series")
    first, last = ts.min(), ts.max()
    assert isinstance(first, dt.datetime) and isinstance(last, dt.datetime)
    if asset_class in MARKETS_24H:
        info = None
        if asset_class in MARKETS_24X5 and TF_STEP[timeframe] <= dt.timedelta(hours=1):
            info = learn_break(ts, TF_STEP[timeframe], cfg.weekly_window, cfg.break_detection)
        hour = info.hour_local if info else None
        starts = expected_24h(
            asset_class, timeframe, first, last, cfg.weekly_window, hour, mode=mode_of(notes)
        )
        what = "24x7" if asset_class == "crypto" else f"24x5 window {cfg.weekly_window.timezone}"
        return ExpectedSchedule(starts, what, info)
    if asset_class == "us_equity" and timeframe in ("1D", "1H"):
        path = sessions_file or cfg.sessions_file
        if not path.is_file():
            return ExpectedSchedule(None, f"NYSE session calendar not found ({path.as_posix()})")
        sessions = load_sessions(path)
        lo, hi = min(sessions), max(sessions)
        starts = expected_us_equity(timeframe, first, last, sessions, cfg)
        cover = (
            dt.datetime.combine(lo, dt.time(0), tzinfo=dt.UTC),
            dt.datetime.combine(hi + dt.timedelta(days=1), dt.time(0), tzinfo=dt.UTC),
        )
        return ExpectedSchedule(
            starts, f"NYSE sessions {lo}..{hi} ({path.as_posix()})", coverage=cover
        )
    if asset_class == "aux" and timeframe == "1D":
        return expected_aux(first, last, notes, cfg, sessions_file)
    return ExpectedSchedule(None, f"no expected schedule for {asset_class} {timeframe}")


def load_bond_closures(path: Path) -> set[dt.date]:
    """US bond-market closures on NYSE sessions (``us_bond_market_closures.csv``, D-720)."""
    if not path.is_file():
        raise ConfigError("US bond-market closure calendar not found", config_path=path)
    with path.open(encoding="utf-8", newline="") as fh:
        return {dt.date.fromisoformat(r["date"]) for r in csv.DictReader(fh)}


def expected_aux(
    first: dt.datetime,
    last: dt.datetime,
    notes: str,
    cfg: QualityConfig,
    sessions_file: Path | None = None,
) -> ExpectedSchedule:
    """Expected daily bars of an aux series, from its own calendar (D-720, never an exemption):
    ``nyse``; ``nyse_bond`` = NYSE sessions minus the US bond-market closures; ``weekdays``."""
    from strategy_factory.data.auxiliary import aux_calendar_of

    kind = aux_calendar_of(notes)
    if kind is None:  # never a silent skip: that is the exemption D-720 forbids
        raise DataError(
            "aux series without an aux_calendar note: its schedule cannot be checked (D-720); "
            "re-ingest it from configs/universe/aux_yahoo.csv"
        )
    if kind == "weekdays":
        days = pl.date_range(first.date(), last.date(), "1d", eager=True)
        days = days.filter(days.dt.weekday() <= 5)
        starts = days.cast(pl.Datetime("us")).dt.replace_time_zone("UTC").alias("ts")
        return ExpectedSchedule(starts, "aux calendar weekdays (every weekday)")
    path = sessions_file or cfg.sessions_file
    sessions = load_sessions(path)
    what = f"aux calendar nyse: NYSE sessions ({path.as_posix()})"
    if kind == "nyse_bond":
        closed = load_bond_closures(cfg.bond_closures_file)
        sessions = {d: v for d, v in sessions.items() if d not in closed}
        what = (
            f"aux calendar nyse_bond: NYSE sessions minus US bond-market closures "
            f"({cfg.bond_closures_file.as_posix()})"
        )
    lo, hi = min(sessions), max(sessions)
    cover = (
        dt.datetime.combine(lo, dt.time(0), tzinfo=dt.UTC),
        dt.datetime.combine(hi + dt.timedelta(days=1), dt.time(0), tzinfo=dt.UTC),
    )
    starts = expected_us_equity("1D", first, last, sessions, cfg)
    return ExpectedSchedule(starts, f"{what} {lo}..{hi}", coverage=cover)
