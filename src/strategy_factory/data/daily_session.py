"""Daily-vs-RTH breach analysis for the Alpaca daily session decision (T04i, D-033).

The Alpaca **daily** bar covers the exchange session, which includes pre- and post-market
prints; the **hourly** series keeps only the bars labelled 09:00-15:00 New York (D-023). So the
daily high/low can sit outside the range the hourly bars ever show. Whether that happens, how
often and by how much decides D-033 -- and it matters beyond the label, because the engine
checks stops against the daily high and low: a level the market never traded at fires a stop
that could not have fired.

Every breach day is classified against the **raw** hourly file, which still holds the
extended-hours bars the adapter drops:

``extended_hours``
    the daily extreme lies inside the full raw hourly range for that session date -- a real
    trade outside 09:30-16:00. Whether it is reachable depends on the broker's hours.
``unexplained``
    no raw hourly bar, at any hour, reaches the daily extreme. Nothing in the hourly feed
    supports that price: a bad print, or the two feeds disagreeing.
``incomplete_hourly_day``
    the session has fewer hourly bars than its calendar close implies (7 on a regular day, 4 on
    a 13:00 half-day). The RTH range is then built from part of the session, so a "breach" says
    nothing about the data -- it says the hourly download has not finished that day. Checked
    **first**, because it explains away breaches that would otherwise look unexplained.
``no_raw_hours``
    the session date has no raw hourly bars at all (a year the hourly download has not
    reached), so the day cannot be classified.

Nothing here writes a snapshot or touches the raw store (D-382).
"""

from __future__ import annotations

from datetime import date
from typing import Final

import polars as pl

#: A breach must exceed this share of the daily close to count; below it the difference is
#: float noise or a rounding difference between the two feeds, not a price level.
BREACH_EPS_BPS: Final = 0.05

EXTENDED_HOURS: Final = "extended_hours"
UNEXPLAINED: Final = "unexplained"
NO_RAW_HOURS: Final = "no_raw_hours"
INCOMPLETE_HOURLY_DAY: Final = "incomplete_hourly_day"


def expected_bars(sessions: dict[date, tuple[str, str]], first_bar: str) -> pl.DataFrame:
    """``session_date, expected_bars`` from the NYSE calendar: 7 regular, 4 on a 13:00 close."""
    first = _minutes(first_bar)
    return pl.DataFrame(
        {
            "session_date": list(sessions),
            "expected_bars": [max(0, (_minutes(c) - first) // 60) for _, c in sessions.values()],
        },
        schema={"session_date": pl.Date(), "expected_bars": pl.UInt32()},
    )


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def rth_extremes(hourly: pl.DataFrame, timezone: str) -> pl.DataFrame:
    """``session_date, rth_high, rth_low, rth_bars`` from **canonical** hourly bars."""
    return (
        hourly.with_columns(
            pl.col("ts").dt.convert_time_zone(timezone).dt.date().alias("session_date")
        )
        .group_by("session_date")
        .agg(
            pl.col("high").max().alias("rth_high"),
            pl.col("low").min().alias("rth_low"),
            pl.len().alias("rth_bars"),
        )
    )


def raw_extremes(raw_hourly: pl.DataFrame, timezone: str) -> pl.DataFrame:
    """``session_date, raw_high, raw_low, raw_bars`` from **raw** hourly bars (all hours).

    ``raw_hourly`` is the union of the raw year files: a ``t`` column of RFC-3339 strings plus
    ``h`` and ``l``. These are the bars the adapter's session filter drops.
    """
    empty_schema = {
        "session_date": pl.Date(),
        "raw_high": pl.Float64(),
        "raw_low": pl.Float64(),
        "raw_bars": pl.UInt32(),
    }
    if raw_hourly.height == 0:  # a symbol or year the hourly download has not reached
        return pl.DataFrame(schema=empty_schema)
    ts = pl.col("t").str.to_datetime(time_unit="us", time_zone="UTC")
    return (
        raw_hourly.select(
            ts.dt.convert_time_zone(timezone).dt.date().alias("session_date"),
            pl.col("h").cast(pl.Float64).alias("h"),
            pl.col("l").cast(pl.Float64).alias("l"),
        )
        .group_by("session_date")
        .agg(
            pl.col("h").max().alias("raw_high"),
            pl.col("l").min().alias("raw_low"),
            pl.len().alias("raw_bars"),
        )
    )


def with_atr(daily: pl.DataFrame, length: int = 14) -> pl.DataFrame:
    """Add ``atr`` -- the rolling mean true range -- so a breach can be sized against the bar."""
    prev_close = pl.col("close").shift(1)
    true_range = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    return daily.sort("ts").with_columns(
        true_range.rolling_mean(window_size=length, min_samples=length).alias("atr")
    )


def breaches(
    daily: pl.DataFrame,
    rth: pl.DataFrame,
    raw: pl.DataFrame,
    symbol: str,
    eps_bps: float = BREACH_EPS_BPS,
    expected: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """One row per session date present in both timeframes, with the breach and its class.

    ``daily`` is the canonical daily frame (``ts`` at the session date, 00:00 UTC). Breaches are
    reported in basis points of that day's close, so they are comparable across symbols and
    price levels.
    """
    frame = daily if "atr" in daily.columns else with_atr(daily)
    day = frame.select(
        pl.col("ts").dt.date().alias("session_date"),
        pl.col("high").alias("daily_high"),
        pl.col("low").alias("daily_low"),
        pl.col("close").alias("daily_close"),
        pl.col("atr"),
    )
    joined = day.join(rth, on="session_date", how="inner").join(raw, on="session_date", how="left")
    if expected is None:
        joined = joined.with_columns(pl.lit(None, dtype=pl.UInt32).alias("expected_bars"))
    else:
        joined = joined.join(expected, on="session_date", how="left")
    bps = 1e4 / pl.col("daily_close")
    out = joined.with_columns(
        ((pl.col("daily_high") - pl.col("rth_high")) * bps).alias("breach_high_bps"),
        ((pl.col("rth_low") - pl.col("daily_low")) * bps).alias("breach_low_bps"),
    ).with_columns(
        pl.max_horizontal("breach_high_bps", "breach_low_bps").alias("breach_bps"),
    )
    out = out.with_columns(
        pl.when(pl.col("atr") > 0)
        .then(
            pl.max_horizontal("breach_high_bps", "breach_low_bps")
            * pl.col("daily_close")
            / 1e4
            / pl.col("atr")
        )
        .otherwise(None)
        .alias("breach_atr_frac"),
        (pl.col("breach_high_bps") > eps_bps).alias("high_side"),
        (pl.col("breach_low_bps") > eps_bps).alias("low_side"),
    )
    high_ok = pl.col("daily_high") <= pl.col("raw_high") * (1 + eps_bps / 1e4)
    low_ok = pl.col("daily_low") >= pl.col("raw_low") * (1 - eps_bps / 1e4)
    explained = (pl.when(pl.col("breach_high_bps") > eps_bps).then(high_ok).otherwise(True)) & (
        pl.when(pl.col("breach_low_bps") > eps_bps).then(low_ok).otherwise(True)
    )
    return (
        out.with_columns(
            pl.lit(symbol).alias("symbol"),
            pl.when(
                pl.col("expected_bars").is_not_null()
                & (pl.col("rth_bars") < pl.col("expected_bars"))
            )
            .then(pl.lit(INCOMPLETE_HOURLY_DAY))
            .when(pl.col("raw_bars").is_null())
            .then(pl.lit(NO_RAW_HOURS))
            .when(explained)
            .then(pl.lit(EXTENDED_HOURS))
            .otherwise(pl.lit(UNEXPLAINED))
            .alias("breach_class"),
        )
        .filter(pl.col("breach_bps") > eps_bps)
        .sort("session_date")
    )


def compared_days(daily: pl.DataFrame, rth: pl.DataFrame) -> int:
    """Session dates present in both timeframes (the denominator of every share reported)."""
    day = daily.select(pl.col("ts").dt.date().alias("session_date"))
    return day.join(rth.select("session_date"), on="session_date", how="inner").height


def covered_years(rth: pl.DataFrame) -> list[int]:
    """Calendar years for which the hourly side has any bar (D-358: state the coverage)."""
    if rth.height == 0:
        return []
    years = rth["session_date"].dt.year().unique().to_list()
    return sorted(int(y) for y in years)
