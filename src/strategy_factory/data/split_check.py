"""Split consistency check between an ingested series and a cross-check source (F-0.1.9).

Day-over-day close ratios of the ingested (split-adjusted) series are compared with the
cross-check series (the raw copy of MS-US-1D, Alpaca SIP ``adjustment=all``):

* on every **known split** date of the symbol (``configs/data/known_splits.csv``) the
  ingested ratio must be within ``jump_threshold`` of 1 -> ``adjusted``; a ratio close to
  ``1/split_ratio`` -> ``unadjusted``;
* every other day where either series moves more than ``jump_threshold``:
  ``market_move_both`` if both moved alike (``|ln(r_a / r_x)| <= match_tolerance``),
  otherwise ``unexplained_ingested`` / ``unexplained_crosscheck`` / ``mismatch``.

A mismatch is a warning (written to the snapshot notes); it never blocks an ingest.
"""

from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path

import polars as pl

from strategy_factory.data.config import KnownSplit, SplitCheckConfig

WARNING_VERDICTS = frozenset(
    {"unadjusted", "unexplained_ingested", "unexplained_crosscheck", "mismatch"}
)
REPORT_COLUMNS = [
    "symbol",
    "timeframe",
    "date",
    "ratio",
    "ratio_crosscheck",
    "split_ratio",
    "verdict",
]


def daily_closes(df: pl.DataFrame, tz: str | None = None) -> pl.DataFrame:
    """(date, close): last close per date; ``tz`` converts intraday UTC bars to local dates."""
    ts = pl.col("ts").dt.convert_time_zone(tz) if tz else pl.col("ts")
    return (
        df.sort("ts")
        .group_by(ts.dt.date().alias("date"), maintain_order=True)
        .agg(pl.col("close").last())
        .sort("date")
    )


def read_crosscheck_csv(path: Path) -> pl.DataFrame:
    """MS-US-1D candle file (``date,open,high,low,close,volume``) -> (date, close)."""
    df = pl.read_csv(path, columns=["date", "close"], schema_overrides={"date": pl.Utf8})
    return df.select(pl.col("date").str.to_date("%Y-%m-%d"), pl.col("close").cast(pl.Float64))


def _ratios(closes: pl.DataFrame, name: str) -> pl.DataFrame:
    return closes.sort("date").select(
        "date", (pl.col("close") / pl.col("close").shift(1)).alias(name)
    )


def check_splits(
    symbol: str,
    timeframe: str,
    ingested: pl.DataFrame,
    crosscheck: pl.DataFrame | None,
    known: list[KnownSplit],
    cfg: SplitCheckConfig,
) -> list[dict[str, object]]:
    """Rows for the split-check report. ``ingested``/``crosscheck`` are (date, close)."""
    a = _ratios(ingested, "ratio")
    if crosscheck is not None and crosscheck.height:
        joined = a.join(_ratios(crosscheck, "ratio_crosscheck"), on="date", how="left")
    else:
        joined = a.with_columns(pl.lit(None, dtype=pl.Float64).alias("ratio_crosscheck"))
    thr, tol = cfg.jump_threshold, cfg.match_tolerance
    splits = {k.date: k.ratio for k in known if k.symbol == symbol}
    first, last = ingested["date"].min(), ingested["date"].max()
    rows: list[dict[str, object]] = []

    def row(
        date: dt.date, ra: float | None, rx: float | None, sr: float | None, verdict: str
    ) -> None:
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "date": date.isoformat(),
                "ratio": None if ra is None else round(ra, 6),
                "ratio_crosscheck": None if rx is None else round(rx, 6),
                "split_ratio": sr,
                "verdict": verdict,
            }
        )

    by_date = {r["date"]: r for r in joined.iter_rows(named=True)}
    for d, factor in sorted(splits.items()):
        if first is None or not (first < d <= last):  # type: ignore[operator]
            continue
        r = by_date.get(d)
        ra = r["ratio"] if r else None
        rx = r["ratio_crosscheck"] if r else None
        if ra is None:
            row(d, None, rx, factor, "no_data_on_split_date")
        elif abs(ra - 1) <= thr:
            row(d, ra, rx, factor, "adjusted")
        elif abs(math.log(ra * factor)) <= thr:
            row(d, ra, rx, factor, "unadjusted")
        else:
            row(d, ra, rx, factor, "mismatch")

    for r in joined.iter_rows(named=True):
        d, ra, rx = r["date"], r["ratio"], r["ratio_crosscheck"]
        if ra is None or d in splits:
            continue
        jump_a = abs(ra - 1) > thr
        jump_x = rx is not None and abs(rx - 1) > thr
        if not (jump_a or jump_x):
            continue
        if rx is None:
            verdict = "no_crosscheck"
        elif abs(math.log(ra / rx)) <= tol:
            verdict = "market_move_both"
        elif jump_a and not jump_x:
            verdict = "unexplained_ingested"
        elif jump_x and not jump_a:
            verdict = "unexplained_crosscheck"
        else:
            verdict = "mismatch"
        row(d, ra, rx, None, verdict)
    return rows


def warning_note(rows: list[dict[str, object]]) -> str:
    bad = [r for r in rows if r["verdict"] in WARNING_VERDICTS]
    if not bad:
        return ""
    items = ", ".join(f"{r['date']} {r['verdict']}" for r in bad[:5])
    return f"SPLIT-CHECK WARNING ({len(bad)}): {items}"


def write_report(path: Path, symbol: str, rows: list[dict[str, object]]) -> Path:
    """Merge ``rows`` into the report CSV, replacing earlier rows of ``symbol``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    kept: list[dict[str, object]] = []
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            kept = [dict(r) for r in csv.DictReader(fh) if r["symbol"] != symbol]
    merged = sorted([*kept, *rows], key=lambda r: (str(r["symbol"]), str(r["date"])))
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(merged)
    tmp.replace(path)
    return path
