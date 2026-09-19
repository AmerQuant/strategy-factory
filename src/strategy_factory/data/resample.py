"""Resampling to higher timeframes (F-0.1.7).

Rules (fixed decisions of T05):

* Only 24-hour markets are resampled: ``fx``, ``metal``, ``energy_cfd``, ``index_cfd`` and
  ``crypto``. ``us_equity`` daily bars come from the Alpaca daily snapshots and US hourly
  bars are never aggregated to 4H, so ``us_equity`` is rejected (as are asset classes
  without a defined day rule yet).
* ``research`` mode: day boundary 00:00 UTC; Saturday/Sunday bars of the 24x5 markets are
  merged into Monday (no daily bar is ever stamped on a weekend); 4H = fixed UTC blocks
  00-04, 04-08, ...
* ``broker_session`` mode (parity tests only): periods start at the configured session
  start (e.g. 17:00 America/New_York); a daily bar is stamped with its trading date.
* Aggregation: OHLC first/max/min/last; ``volume`` and ``trades`` summed; ``vwap``
  volume-weighted; ``spread`` last.
* Partial periods at the start and end (an expected source bar of the period lies before
  the first / after the last source bar) are dropped. Every kept bar built from fewer than
  ``min_source_fraction`` of its expected source bars is flagged; flags are written to
  ``SFAC_DATA_ROOT/_resample/<snapshot_hash>.flags.csv`` and counted in the notes.
* The result is a new snapshot (``derived_from`` = parent key) stored through the store
  and the catalog.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import QualityConfig, ResampleConfig
from strategy_factory.data.schedule import (
    MARKETS_24H,
    MARKETS_24X5,
    TF_STEP,
    ResampleMode,
    expected_24h,
    learn_break,
    period_start,
)
from strategy_factory.data.schema import SeriesMetadata, canonical_columns
from strategy_factory.data.store import SnapshotStore

RESAMPLE_DIR = "_resample"
TARGETS = ("1H", "4H", "1D")


@dataclass(frozen=True)
class ResampleResult:
    bars: pl.DataFrame
    flags: pl.DataFrame  # ts, source_bars, expected_bars
    dropped: tuple[str, ...] = ()  # partial edge periods that were dropped
    break_hour_local: int | None = None
    rules: dict[str, str] = field(default_factory=dict)


def _check_request(meta: SeriesMetadata, target_tf: str) -> None:
    if meta.asset_class == "us_equity":
        why = (
            "4H bars are built only for 24-hour markets"
            if target_tf == "4H"
            else "US equity daily bars come from the Alpaca daily snapshots"
        )
        raise DataError(f"us_equity is not resampled: {why}", stage="resample", symbol=meta.symbol)
    if meta.asset_class not in MARKETS_24H:
        raise DataError(
            f"resampling is defined only for 24-hour markets {sorted(MARKETS_24H)}, "
            f"not {meta.asset_class!r}",
            stage="resample",
            symbol=meta.symbol,
        )
    if target_tf not in TARGETS:
        raise DataError(f"target timeframe must be one of {TARGETS}", symbol=meta.symbol)
    src, tgt = TF_STEP[meta.timeframe], TF_STEP[target_tf]
    if src >= tgt or tgt % src:
        raise DataError(
            f"cannot resample {meta.timeframe} to {target_tf} (target must be a coarser "
            "multiple of the source)",
            stage="resample",
            symbol=meta.symbol,
        )


def _aggregations(columns: list[str]) -> list[pl.Expr]:
    aggs = [
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
        pl.len().alias("_n"),
    ]
    if "vwap" in columns:
        has = pl.col("vwap").is_not_null()
        num = (pl.col("vwap") * pl.col("volume")).filter(has).sum()
        den = pl.col("volume").filter(has).sum()
        aggs.append(pl.when(den > 0).then(num / den).otherwise(None).alias("vwap"))
    if "trades" in columns:
        aggs.append(
            pl.when(pl.col("trades").count() > 0)
            .then(pl.col("trades").sum())
            .otherwise(None)
            .alias("trades")
        )
    if "spread" in columns:
        aggs.append(pl.col("spread").last())
    return aggs


def resample_bars(
    df: pl.DataFrame,
    meta: SeriesMetadata,
    target_tf: str,
    mode: ResampleMode,
    cfg: ResampleConfig,
    qcfg: QualityConfig,
) -> ResampleResult:
    """Aggregate ``df`` (canonical bars of ``meta``) to ``target_tf`` (pure function)."""
    _check_request(meta, target_tf)
    empty = pl.DataFrame(schema={"ts": pl.Datetime("us", "UTC"), "source_bars": pl.Int64,
                                 "expected_bars": pl.Int64})  # fmt: skip
    df = df.sort("ts")
    if df.height == 0:
        return ResampleResult(df, empty)
    step = TF_STEP[meta.timeframe]
    brk = None
    if meta.asset_class in MARKETS_24X5 and step <= dt.timedelta(hours=1):
        brk = learn_break(df["ts"], step, qcfg.weekly_window, qcfg.break_detection).hour_local
    pstart = period_start(
        pl.col("ts"), target_tf, meta.asset_class, mode, cfg.broker_session
    ).alias("_p")
    grouped = (
        df.with_columns(pstart)
        .group_by("_p", maintain_order=True)
        .agg(_aggregations(df.columns))
        .rename({"_p": "ts"})
        .sort("ts")
    )

    # expected source bars per period (same schedule as the quality check)
    first, last = df["ts"][0], df["ts"][-1]
    fine = expected_24h(
        meta.asset_class,
        meta.timeframe,
        first - dt.timedelta(days=7),
        last + dt.timedelta(days=7),
        qcfg.weekly_window,
        brk,
        step=step,
    )
    exp = pl.DataFrame({"ts": fine}).with_columns(pstart)
    per_period = exp.group_by("_p").agg(pl.len().alias("_exp")).rename({"_p": "ts"})
    grouped = grouped.join(per_period, on="ts", how="left").with_columns(
        pl.col("_exp").fill_null(0)
    )

    p_first, p_last = grouped["ts"][0], grouped["ts"][-1]
    dropped: list[str] = []
    if exp.filter((pl.col("_p") == p_first) & (pl.col("ts") < first)).height:
        dropped.append(f"start {p_first.isoformat()}")
    if exp.filter((pl.col("_p") == p_last) & (pl.col("ts") > last)).height:
        dropped.append(f"end {p_last.isoformat()}")
    keep = pl.lit(True)
    if dropped and dropped[0].startswith("start"):
        keep = keep & (pl.col("ts") != p_first)
    if any(d.startswith("end") for d in dropped):
        keep = keep & (pl.col("ts") != p_last)
    grouped = grouped.filter(keep)

    flags = grouped.filter(
        pl.col("_n") < cfg.min_source_fraction * pl.col("_exp")
    ).select("ts", pl.col("_n").cast(pl.Int64).alias("source_bars"),
             pl.col("_exp").cast(pl.Int64).alias("expected_bars"))  # fmt: skip
    bars = grouped.select(canonical_columns(grouped))
    rules = {
        "mode": mode,
        "source_timeframe": meta.timeframe,
        "target_timeframe": target_tf,
        "day_boundary": (
            "00:00 UTC; Sat/Sun merged into Monday"
            if mode == "research" and meta.asset_class in MARKETS_24X5
            else "00:00 UTC"
            if mode == "research"
            else f"session start {cfg.broker_session.start} {cfg.broker_session.timezone}"
        ),
        "aggregation": "OHLC first/max/min/last; volume,trades sum; vwap volume-weighted; "
        "spread last",
    }
    return ResampleResult(bars, flags, tuple(dropped), brk, rules)


def _notes(res: ResampleResult, parent: SeriesMetadata, cfg: ResampleConfig) -> str:
    r = res.rules
    parts = [
        f"resampled {r['source_timeframe']}->{r['target_timeframe']} mode={r['mode']}",
        f"from {parent.key().short()}",
        f"day boundary: {r['day_boundary']}",
        r["aggregation"],
    ]
    if res.break_hour_local is not None:
        parts.append(f"source daily break {res.break_hour_local:02d}:00 local")
    if res.dropped:
        parts.append("partial periods dropped: " + ", ".join(res.dropped))
    parts.append(
        f"{res.flags.height} bar(s) below {cfg.min_source_fraction:g} of the expected source "
        f"bars (list in {RESAMPLE_DIR}/<snapshot_hash>.flags.csv)"
    )
    return "; ".join(parts)


def resample(
    parent: SeriesMetadata,
    target_tf: str,
    mode: ResampleMode = "research",
    *,
    store: SnapshotStore,
    catalog: Catalog,
    cfg: ResampleConfig,
    qcfg: QualityConfig,
) -> tuple[SeriesMetadata, ResampleResult]:
    """Resample a stored snapshot; store + register the result (returns its metadata)."""
    key = parent.key()
    df = store.read_snapshot(key.source, key.symbol, key.timeframe, key.snapshot_hash)
    res = resample_bars(df, parent, target_tf, mode, cfg, qcfg)
    if res.bars.height == 0:
        raise DataError("resampling produced no complete bars", stage="resample", symbol=key.symbol)
    meta = parent.model_copy(
        update={
            "timeframe": target_tf,
            "notes": _notes(res, parent, cfg),
            "derived_from": key,
            "snapshot_hash": None,
            "row_count": None,
            "first_ts": None,
            "last_ts": None,
            "created_at": None,
        }
    )
    stored = store.write_snapshot(res.bars, SeriesMetadata.model_validate(meta.model_dump()))
    catalog.register(stored, note=f"resample {key.timeframe}->{target_tf} {mode}")
    flags_path = store.root / RESAMPLE_DIR / f"{stored.snapshot_hash}.flags.csv"
    flags_path.parent.mkdir(parents=True, exist_ok=True)
    res.flags.write_csv(flags_path)
    return stored, res


def flags_file(root: Path, snapshot_hash: str) -> Path:
    return root / RESAMPLE_DIR / f"{snapshot_hash}.flags.csv"
