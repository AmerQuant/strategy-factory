"""F-0.1.2 (T04h, D-386): the raw coverage report and the gate in front of an ingest.

A raw Alpaca series is one immutable parquet per calendar year (``<YEAR>.parquet``, refreshed
versions ``<YEAR>.vN.parquet``). A **gap** is a year inside the required span with **no file**, or
whose latest file's manifest says ``complete: false`` (a year downloaded while it was still running
and never refreshed). A file that holds zero bars is present -- the download asked and the feed had
nothing (a year before a listing or after a delisting) -- and says so in its ``row_count``.

The required span per symbol is ``[start, last complete year]``: ``start`` is ``history_start``'s
year (default) or, with ``require_from = first_data_year``, the symbol's first year that holds a
bar. The current year is partial and never required. A symbol with no file misses every year.

Pure apart from reading the raw files; nothing here writes into ``SFAC_RAW_ROOT``.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import polars as pl

from strategy_factory.data.config import CoverageConfig
from strategy_factory.data.download.alpaca import latest_chunks
from strategy_factory.data.download.dukascopy import (
    SIDES,
    Instrument,
    Series,
    instrument_start,
    last_complete_month,
    latest_months,
    month_start,
    months,
)
from strategy_factory.data.download.rawfiles import MANIFEST_SUFFIX

COVERAGE_COLUMNS = [
    "symbol",
    "year",
    "file",
    "row_count",
    "complete",
    "required",
    "missing",
    "incomplete",
]


def _row_count(path: Path) -> int:
    """Bars in a raw year file: its manifest's ``row_count``, else the parquet itself."""
    manifest = path.with_name(path.name + MANIFEST_SUFFIX)
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(data.get("row_count"), int):
            return int(data["row_count"])
    return pl.read_parquet(path).height


def _complete(path: Path) -> bool | None:
    manifest = path.with_name(path.name + MANIFEST_SUFFIX)
    if not manifest.is_file():
        return None
    value = json.loads(manifest.read_text(encoding="utf-8")).get("complete")
    return bool(value) if value is not None else None


def coverage_frame(
    raw_root: Path,
    timeframe: str,
    symbols: list[str],
    history_start: dt.date,
    cfg: CoverageConfig,
    today: dt.date,
) -> pl.DataFrame:
    """One row per symbol and year from ``history_start`` to ``today``: the latest file of that
    year, its bar count, whether the year is required and whether it is missing."""
    first, last_complete = history_start.year, today.year - 1
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        files = {int(p.name.split(".")[0]): p for p in latest_chunks(raw_root, timeframe, symbol)}
        counts = {year: _row_count(p) for year, p in files.items()}
        with_bars = [y for y, n in counts.items() if n > 0]
        start = first
        if cfg.require_from == "first_data_year" and with_bars:
            start = max(first, min(with_bars))
        for year in range(first, today.year + 1):
            path = files.get(year)
            required = start <= year <= last_complete
            complete = _complete(path) if path else None
            rows.append(
                {
                    "symbol": symbol,
                    "year": year,
                    "file": path.name if path else None,
                    "row_count": counts.get(year),
                    "complete": complete,
                    "required": required,
                    "missing": required and path is None,
                    "incomplete": required and path is not None and complete is False,
                }
            )
    schema = {
        "symbol": pl.Utf8,
        "year": pl.Int32,
        "file": pl.Utf8,
        "row_count": pl.Int64,
        "complete": pl.Boolean,
        "required": pl.Boolean,
        "missing": pl.Boolean,
        "incomplete": pl.Boolean,
    }
    return pl.DataFrame(rows, schema=schema).select(COVERAGE_COLUMNS)


def coverage_gaps(frame: pl.DataFrame) -> dict[str, list[int]]:
    """``{symbol: [years]}`` for every symbol with a gap -- a required year with no file or with
    an incomplete one (empty when the gate passes)."""
    gap = pl.col("missing") | pl.col("incomplete")
    missing = frame.filter(gap).group_by("symbol").agg(pl.col("year").sort())
    return {s: list(y) for s, y in sorted(missing.rows())}


def describe_gaps(gaps: dict[str, list[int]], limit: int = 20) -> str:
    """A message naming the symbols and years, for the refusal and the CLI summary."""
    parts = [f"{s} {','.join(str(y) for y in ys)}" for s, ys in list(gaps.items())[:limit]]
    more = f" ... and {len(gaps) - limit} more" if len(gaps) > limit else ""
    total = sum(len(v) for v in gaps.values())
    return (
        f"{len(gaps)} symbol(s), {total} missing or incomplete year(s): " + "; ".join(parts) + more
    )


# -- Dukascopy (T04j) --------------------------------------------------------------------------

DUKASCOPY_COLUMNS = ["symbol", "month", "bid", "ask", "bid_rows", "ask_rows", "required", "missing"]


def dukascopy_coverage_frame(
    raw_root: Path,
    series: str,
    instruments: Sequence[Instrument],
    first: dt.date,
    today: dt.date,
) -> pl.DataFrame:
    """One row per instrument and month from ``first`` (or the instrument's own start, from its
    universe notes) to the last complete month: whether a bid and an ask file exist (the latest
    version of each), their rows (from the manifest, for the report only), and ``missing`` -- a
    required month without a file on **either** side. The verdict rests on the files present,
    never on a manifest field (D-711); the adapter refuses one-sided bars, so a month on one side
    only is a gap too. The current month is never required (the downloader never stores it)."""
    last = last_complete_month(today)
    rows: list[dict[str, object]] = []
    for inst in instruments:
        start = month_start(first)
        own = instrument_start(inst.notes, cast(Series, series))
        if own is not None:
            start = max(start, month_start(own))
        sides = {
            side: {p.name[:7]: p for p in latest_months(raw_root, series, inst.instrument_id, side)}
            for side in SIDES
        }
        for m in months(month_start(first), last):
            key = f"{m:%Y-%m}"
            bid, ask = sides["bid"].get(key), sides["ask"].get(key)
            required = m >= start
            rows.append(
                {
                    "symbol": inst.symbol,
                    "month": key,
                    "bid": bid is not None,
                    "ask": ask is not None,
                    "bid_rows": _manifest_rows(bid),
                    "ask_rows": _manifest_rows(ask),
                    "required": required,
                    "missing": required and (bid is None or ask is None),
                }
            )
    schema = {
        "symbol": pl.Utf8,
        "month": pl.Utf8,
        "bid": pl.Boolean,
        "ask": pl.Boolean,
        "bid_rows": pl.Int64,
        "ask_rows": pl.Int64,
        "required": pl.Boolean,
        "missing": pl.Boolean,
    }
    return pl.DataFrame(rows, schema=schema).select(DUKASCOPY_COLUMNS)


def dukascopy_gaps(frame: pl.DataFrame) -> dict[str, list[str]]:
    """``{symbol: [missing months]}`` (empty when the gate passes)."""
    missing = frame.filter(pl.col("missing")).group_by("symbol").agg(pl.col("month").sort())
    return {s: list(m) for s, m in sorted(missing.rows())}


def describe_month_gaps(gaps: dict[str, list[str]], limit: int = 12) -> str:
    """Symbols and their missing months, first and last, for the refusal and the report."""
    parts = [f"{s} {len(ms)} month(s) ({ms[0]}..{ms[-1]})" for s, ms in list(gaps.items())[:limit]]
    more = f" ... and {len(gaps) - limit} more symbol(s)" if len(gaps) > limit else ""
    total = sum(len(v) for v in gaps.values())
    return f"{len(gaps)} symbol(s), {total} missing month(s): " + "; ".join(parts) + more


def _manifest_rows(path: Path | None) -> int | None:
    if path is None:
        return None
    manifest = path.with_name(path.name + MANIFEST_SUFFIX)
    if not manifest.is_file():
        return None
    value = json.loads(manifest.read_text(encoding="utf-8")).get("row_count")
    return int(value) if isinstance(value, int) else None
