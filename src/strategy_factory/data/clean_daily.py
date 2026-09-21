"""The derived **clean** daily series: the four arms of D-396, D-398 and D-399 (T04k).

T04g put the raw daily bars in the store as they are. This module builds the series the research
pipeline actually reads, as a **new** snapshot (rule 10 -- never an overwrite, never a raw edit),
and it accounts for **every** bar it changes or removes.

Four arms, in the order they are applied, each named in the changed-bar log:

``boundary_trim`` (D-398 (2)/(3), gated by D-399)
    the ticker was re-used or the series opens with pre-listing padding: the history starts at the
    boundary. Never applied on an ambiguous signature -- the caller settles that with the
    all-adjusted cross-check first and passes the decided verdict in.
``frozen_cut`` (D-398 (1))
    a frozen stretch -- consecutive bars with an identical close and zero true range -- is removed
    whatever caused it. It is feed padding, not data.
``extreme_cap`` (D-396)
    a daily high or low the hourly feed does not support is capped to that session's **RTH** hourly
    range. Only where the hourly side is real: **a short hourly day is not evidence**
    (``incomplete_hourly_day``) and neither is a missing one (``no_raw_hours``) -- on such a day the
    bar is left exactly as it is and nothing about it is called clean (supervisor, 2026-09-21).
``wick_clip`` (D-396)
    where there is no usable hourly evidence, a wick flagged by :func:`wick_outliers` is clipped to
    the bar's body (max/min of open and close).

``open``, ``close`` and ``volume`` are **never** touched; only the extremes, and whole bars when an
arm removes them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

import polars as pl

from strategy_factory.data.config import DailyWickOutlierConfig, QualityConfig
from strategy_factory.data.daily_session import (
    EXTENDED_HOURS,
    INCOMPLETE_HOURLY_DAY,
    NO_RAW_HOURS,
    UNEXPLAINED,
)
from strategy_factory.data.relisting import (
    EXCLUDE,
    TRIM,
    SeriesVerdict,
    frozen_stretches,
)

ARM_BOUNDARY_TRIM: Final = "boundary_trim"
ARM_FROZEN_CUT: Final = "frozen_cut"
ARM_EXTREME_CAP: Final = "extreme_cap"
ARM_WICK_CLIP: Final = "wick_clip"

#: The breach classes whose hourly side is real enough to correct a daily bar from.
CORRECTABLE: Final = frozenset({EXTENDED_HOURS, UNEXPLAINED})
#: The breach classes that are **not evidence**: the bar is left alone and is not called clean.
NOT_EVIDENCE: Final = frozenset({INCOMPLETE_HOURLY_DAY, NO_RAW_HOURS})

LOG_COLUMNS: Final = [
    "symbol",
    "session_date",
    "arm",
    "field",
    "old",
    "new",
    "evidence",
]


def wick_outliers(daily: pl.DataFrame, cfg: DailyWickOutlierConfig) -> pl.DataFrame:
    """Per bar: is the high or the low beyond the body by **both** thresholds? (D-396)

    Returns ``idx, session_date, atr, body_high, body_low, flag_high, flag_low`` plus the two
    measured excesses per side, so the changed-bar log can quote the evidence the arm acted on.
    Requiring **both** an ATR multiple and a percentage is what keeps a genuinely volatile day:
    a wide-but-real bar clears the percentage and not the multiple, a bad print clears both.
    """
    frame = daily if "atr" in daily.columns else _with_atr(daily)
    body_high = pl.max_horizontal("open", "close")
    body_low = pl.min_horizontal("open", "close")
    out = frame.with_columns(
        body_high.alias("body_high"),
        body_low.alias("body_low"),
    ).with_columns(
        (pl.col("high") - pl.col("body_high")).alias("excess_high"),
        (pl.col("body_low") - pl.col("low")).alias("excess_low"),
    )
    atr_ok_high = (pl.col("atr") > 0) & (pl.col("excess_high") > cfg.k1_atr * pl.col("atr"))
    atr_ok_low = (pl.col("atr") > 0) & (pl.col("excess_low") > cfg.k1_atr * pl.col("atr"))
    pct_high = pl.col("excess_high") / pl.col("close") * 100.0
    pct_low = pl.col("excess_low") / pl.col("close") * 100.0
    return (
        out.with_columns(
            pct_high.alias("excess_high_pct"),
            pct_low.alias("excess_low_pct"),
        )
        .with_columns(
            (atr_ok_high & (pl.col("excess_high_pct") > cfg.k2_pct)).alias("flag_high"),
            (atr_ok_low & (pl.col("excess_low_pct") > cfg.k2_pct)).alias("flag_low"),
            (pl.col("excess_high") / pl.col("atr")).alias("excess_high_atr"),
            (pl.col("excess_low") / pl.col("atr")).alias("excess_low_atr"),
            pl.col("ts").dt.date().alias("session_date"),
        )
        .with_row_index("idx")
    )


def _with_atr(daily: pl.DataFrame, length: int = 14) -> pl.DataFrame:
    prev_close = pl.col("close").shift(1)
    true_range = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    return daily.with_columns(
        true_range.rolling_mean(window_size=length, min_samples=length).alias("atr")
    )


def _log(
    symbol: str,
    session_date: dt.date,
    arm: str,
    field: str,
    old: float | None,
    new: float | None,
    evidence: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "session_date": session_date.isoformat(),
        "arm": arm,
        "field": field,
        "old": old,
        "new": new,
        "evidence": evidence,
    }


def clean_daily(
    daily: pl.DataFrame,
    symbol: str,
    cfg: QualityConfig,
    breaches: pl.DataFrame | None = None,
    verdict: SeriesVerdict | None = None,
    frozen_sessions: int | None = None,
    apply_boundary: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """``(clean daily frame, changed-bar log)``; the input frame is never modified.

    ``breaches`` is :func:`strategy_factory.data.daily_session.breaches` output for this symbol;
    without it the ``extreme_cap`` arm does nothing and every flagged wick goes to ``wick_clip``.
    ``verdict`` is :func:`strategy_factory.data.relisting.analyse_series` output; ``apply_boundary``
    is the **D-399 gate** -- the caller sets it to ``False`` when the cross-check could not settle
    the signature, and the history is then kept in full.
    """
    if daily.height == 0:
        return daily, pl.DataFrame(schema={c: pl.Utf8() for c in LOG_COLUMNS})

    frame = daily.sort("ts")
    dates = [d.date() if isinstance(d, dt.datetime) else d for d in frame["ts"].to_list()]
    rows: list[dict[str, Any]] = []
    drop: set[int] = set()

    # --- 1. boundary_trim (D-398 (2)/(3), gated by D-399) ---------------------------------
    boundary_idx = 0
    if verdict is not None and verdict.verdict == TRIM and apply_boundary and verdict.boundary_date:
        target = dt.date.fromisoformat(verdict.boundary_date)
        boundary_idx = next((i for i, d in enumerate(dates) if d >= target), len(dates))
        evidence = (
            f"D-398 ({verdict.boundary_reason}): history starts {verdict.boundary_date}; "
            f"{verdict.dropped_from}..{verdict.dropped_to} dropped"
        )
        for i in range(boundary_idx):
            drop.add(i)
            rows.append(
                _log(symbol, dates[i], ARM_BOUNDARY_TRIM, "bar", frame["close"][i], None, evidence)
            )
    elif verdict is not None and verdict.verdict == EXCLUDE:
        # D-398 (4): no boundary can be placed. Nothing is trimmed here; the symbol is excluded
        # through configs/universe/us_equity_daily_excluded.csv, which the ingest reads.
        pass

    # --- 2. frozen_cut (D-398 (1)) ---------------------------------------------------------
    minimum = frozen_sessions if frozen_sessions is not None else _default_frozen()
    for start, end in frozen_stretches(
        frame["high"].to_list(), frame["low"].to_list(), frame["close"].to_list(), minimum
    ):
        evidence = (
            f"D-398 (1): {end - start + 1} padded sessions at {frame['close'][start]} "
            f"({dates[start]}..{dates[end]}), high == low == close"
        )
        for i in range(start, end + 1):
            if i in drop:
                continue  # already ahead of the boundary
            drop.add(i)
            rows.append(
                _log(symbol, dates[i], ARM_FROZEN_CUT, "bar", frame["close"][i], None, evidence)
            )

    # --- 3 and 4: the extremes, on the bars that survive ------------------------------------
    caps = _cap_targets(breaches, cfg)
    flags = wick_outliers(frame, cfg.daily_wick_outlier)
    highs = list(frame["high"])
    lows = list(frame["low"])
    for i, day in enumerate(dates):
        if i in drop:
            continue
        cap = caps.get(day)
        if cap is not None:
            for field, values, bound, better in (
                ("high", highs, cap["rth_high"], highs[i] > cap["rth_high"]),
                ("low", lows, cap["rth_low"], lows[i] < cap["rth_low"]),
            ):
                if better:
                    rows.append(
                        _log(
                            symbol,
                            day,
                            ARM_EXTREME_CAP,
                            field,
                            values[i],
                            bound,
                            f"D-396 ({cap['breach_class']}): RTH hourly range "
                            f"{cap['rth_low']}..{cap['rth_high']} from {cap['rth_bars']} of "
                            f"{cap['expected_bars']} expected bars",
                        )
                    )
                    values[i] = bound
            continue  # a day with usable hourly evidence is never wick-clipped as well
        if day in _not_evidence(breaches):
            continue  # a short or missing hourly day corrects nothing (supervisor, 2026-09-21)
        row = flags.row(i, named=True)
        if row["flag_high"]:
            rows.append(
                _log(
                    symbol,
                    day,
                    ARM_WICK_CLIP,
                    "high",
                    highs[i],
                    row["body_high"],
                    f"D-396: high {row['excess_high_atr']:.1f} x ATR(14) and "
                    f"{row['excess_high_pct']:.1f} % beyond the body",
                )
            )
            highs[i] = row["body_high"]
        if row["flag_low"]:
            rows.append(
                _log(
                    symbol,
                    day,
                    ARM_WICK_CLIP,
                    "low",
                    lows[i],
                    row["body_low"],
                    f"D-396: low {row['excess_low_atr']:.1f} x ATR(14) and "
                    f"{row['excess_low_pct']:.1f} % beyond the body",
                )
            )
            lows[i] = row["body_low"]

    clean = (
        frame.with_columns(pl.Series("high", highs), pl.Series("low", lows))
        .with_row_index("_i")
        .filter(~pl.col("_i").is_in(sorted(drop)))
        .drop("_i")
    )
    log = pl.DataFrame(rows, schema=_log_schema()) if rows else pl.DataFrame(schema=_log_schema())
    return clean.select(daily.columns), log.sort("session_date", "arm", "field")


def _log_schema() -> dict[str, pl.DataType]:
    return {
        "symbol": pl.Utf8(),
        "session_date": pl.Utf8(),
        "arm": pl.Utf8(),
        "field": pl.Utf8(),
        "old": pl.Float64(),
        "new": pl.Float64(),
        "evidence": pl.Utf8(),
    }


def _default_frozen() -> int:
    from strategy_factory.data.relisting import DEFAULT_FROZEN_SESSIONS

    return DEFAULT_FROZEN_SESSIONS


def _cap_targets(
    breaches: pl.DataFrame | None, cfg: QualityConfig
) -> dict[dt.date, dict[str, Any]]:
    """The days whose daily extreme may be capped: a real breach with a real hourly side."""
    if breaches is None or breaches.height == 0:
        return {}
    usable = breaches.filter(
        pl.col("breach_class").is_in(sorted(CORRECTABLE))
        & (pl.col("breach_bps") > cfg.daily_extreme_unsupported.eps_bps)
    )
    return {r["session_date"]: r for r in usable.iter_rows(named=True)}


def _not_evidence(breaches: pl.DataFrame | None) -> set[dt.date]:
    """Session dates whose hourly side is short or missing -- never corrected, never cleared."""
    if breaches is None or breaches.height == 0:
        return set()
    return set(
        breaches.filter(pl.col("breach_class").is_in(sorted(NOT_EVIDENCE)))[
            "session_date"
        ].to_list()
    )
