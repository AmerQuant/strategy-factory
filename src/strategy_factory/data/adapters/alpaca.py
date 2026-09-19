"""Alpaca SIP raw chunks -> canonical bars (F-0.1.2).

* ``ts`` = bar start in UTC as returned by Alpaca.
* **Daily:** Alpaca stamps a daily bar at midnight America/New_York (04:00/05:00 UTC);
  it is re-stamped at the **session date 00:00 UTC**.
* **Hourly:** only hour-aligned bars whose New-York start is ``first_bar`` (09:00) or later
  and whose end is at or before the session close are kept: 09:00..15:00 on regular days,
  09:00..12:00 on 13:00 early-close days; each day's close comes from
  ``configs/calendars/nyse_sessions.csv`` (Alpaca calendar). The 09:00
  bar contains 09:00-09:30 pre-market prints (``session="RTH_hour_aligned"``).
* Overlapping raw chunks are de-duplicated when rows are identical; a timestamp with
  differing values in two chunks is a critical :class:`DataError`.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.config import AlpacaConfig
from strategy_factory.data.download.alpaca_reference import load_sessions
from strategy_factory.data.hashing import file_sha256
from strategy_factory.data.schema import RawRef, SeriesMetadata, Session

HOURLY_NOTE = (
    "Hour-aligned SIP bars labelled 09:00-15:00 America/New_York (bar start); the 09:00 bar "
    "includes 09:00-09:30 pre-market prints; extended-hours bars dropped; early-close days "
    "end with the 12:00 bar."
)
DAILY_NOTE = "Alpaca SIP daily bar as delivered; stamped at the session date 00:00 UTC."
VALUE_COLS = ["o", "h", "l", "c", "v", "n", "vw"]


def _minutes(hhmm: str) -> int:
    t = dt.time.fromisoformat(hhmm)
    return t.hour * 60 + t.minute


def read_raw(raw_paths: list[Path]) -> pl.DataFrame:
    frames = []
    for p in raw_paths:
        df = pl.read_parquet(p)
        cols = [c for c in ["t", *VALUE_COLS] if c in df.columns]
        frames.append(df.select(cols).with_columns(pl.lit(p.name).alias("_file")))
    if not frames:
        raise DataError("no raw files given")
    return pl.concat(frames, how="diagonal_relaxed")


def dedupe(raw: pl.DataFrame, symbol: str) -> pl.DataFrame:
    """Drop identical duplicate rows; raise on conflicting values for one timestamp."""
    cols = [c for c in ["t", *VALUE_COLS] if c in raw.columns]
    uniq = raw.select(cols).unique(maintain_order=True)
    conflicts = uniq.group_by("t").len().filter(pl.col("len") > 1)
    if conflicts.height:
        examples = ", ".join(sorted(conflicts["t"].to_list())[:5])
        raise DataError(
            f"{conflicts.height} timestamps have conflicting values across raw chunks "
            f"(e.g. {examples})",
            stage="adapter:alpaca",
            symbol=symbol,
        )
    return uniq


class AlpacaAdapter:
    """``Adapter`` implementation for Alpaca SIP split-adjusted bars."""

    def __init__(
        self,
        config: AlpacaConfig | None = None,
        sessions: dict[dt.date, tuple[str, str]] | None = None,
    ) -> None:
        self.config = config or AlpacaConfig()
        self._sessions = sessions

    @property
    def sessions(self) -> dict[dt.date, tuple[str, str]]:
        """date -> (open_local, close_local) of every NYSE session (Alpaca calendar)."""
        if self._sessions is None:
            self._sessions = load_sessions(self.config.hourly_session.sessions_file)
        return self._sessions

    def to_canonical(
        self, raw_paths: list[Path], **params: Any
    ) -> tuple[pl.DataFrame, SeriesMetadata]:
        timeframe: str = params["timeframe"]
        symbol: str = params["symbol"]
        raw = dedupe(read_raw(raw_paths), symbol)
        bars = raw.select(
            pl.col("t").str.to_datetime(time_unit="us", time_zone="UTC").alias("ts"),
            pl.col("o").cast(pl.Float64).alias("open"),
            pl.col("h").cast(pl.Float64).alias("high"),
            pl.col("l").cast(pl.Float64).alias("low"),
            pl.col("c").cast(pl.Float64).alias("close"),
            pl.col("v").cast(pl.Float64).alias("volume"),
            pl.col("vw").cast(pl.Float64).alias("vwap"),
            pl.col("n").cast(pl.Int64).alias("trades"),
        ).sort("ts")
        tz = self.config.hourly_session.timezone
        session: Session
        if timeframe == "1D":
            bars = self._daily(bars, tz)
            session, note = self.config.daily_session, DAILY_NOTE
        elif timeframe == "1H":
            bars = self._hourly(bars, tz)
            session, note = "RTH_hour_aligned", HOURLY_NOTE
        else:
            raise DataError(f"unsupported timeframe {timeframe!r}", symbol=symbol)
        meta = SeriesMetadata(
            source="alpaca",
            source_symbol=symbol,
            symbol=symbol,
            asset_class="us_equity",
            timeframe=timeframe,
            price_type="trade",
            adjustment="split",
            session=session,
            feed="sip",
            volume_quality="full",
            original_tz="UTC",
            bar_label="start",
            raw_refs=tuple(RawRef(path=p.as_posix(), sha256=file_sha256(p)) for p in raw_paths),
            downloaded_at=_downloaded_at(raw_paths),
            notes=note,
        )
        return bars, meta

    @staticmethod
    def _daily(bars: pl.DataFrame, tz: str) -> pl.DataFrame:
        session_date = pl.col("ts").dt.convert_time_zone(tz).dt.date()
        out = bars.with_columns(
            session_date.cast(pl.Datetime("us")).dt.replace_time_zone("UTC").alias("ts")
        )
        dups = out.height - out["ts"].n_unique()
        if dups:
            raise DataError(
                f"{dups} daily bars map to an already used session date", stage="adapter:alpaca"
            )
        return out

    def _hourly(self, bars: pl.DataFrame, tz: str) -> pl.DataFrame:
        cfg = self.config.hourly_session
        local = pl.col("ts").dt.convert_time_zone(tz)
        start_min = local.dt.hour().cast(pl.Int32) * 60 + local.dt.minute().cast(pl.Int32)
        closes = pl.DataFrame(
            {
                "_date": list(self.sessions),
                "_close_min": [_minutes(c) for _, c in self.sessions.values()],
            },
            schema={"_date": pl.Date, "_close_min": pl.Int32},
        )
        with_close = bars.with_columns(local.dt.date().alias("_date")).join(
            closes, on="_date", how="left"
        )
        close_min = pl.col("_close_min").fill_null(_minutes(cfg.regular_close))
        keep = (
            (local.dt.minute() == 0)
            & (local.dt.second() == 0)
            & (start_min >= _minutes(cfg.first_bar))
            & (start_min + 60 <= close_min)
        )
        return with_close.filter(keep).drop("_date", "_close_min")


def _downloaded_at(raw_paths: list[Path]) -> dt.datetime | None:
    stamps = []
    for p in raw_paths:
        m = p.with_name(p.name + ".manifest.json")
        if m.is_file():
            value = json.loads(m.read_text(encoding="utf-8")).get("downloaded_at")
            if value:
                stamps.append(dt.datetime.fromisoformat(value).astimezone(dt.UTC))
    return max(stamps) if stamps else None
