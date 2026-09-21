"""F-0.1.2 (T04h, D-386): the raw coverage report and the gate in front of an ingest.

A raw Alpaca series is one immutable parquet per calendar year (``<YEAR>.parquet``, refreshed
versions ``<YEAR>.vN.parquet``). A **gap** is a year inside the required span with **no file**; a
file that holds zero bars is present (the download asked and the feed had nothing), and says so in
its manifest ``row_count``.

The required span per symbol is ``[start, last complete year]``: ``start`` is ``history_start``'s
year or, with ``require_from = first_data_year``, the symbol's first year that holds a bar -- a
symbol listed in 2019 has no 2016 bars and must not trip the gate. The current year is partial and
never a gap. A symbol with no file at all misses every year of the span.

Pure apart from reading the raw files; nothing here writes into ``SFAC_RAW_ROOT``.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from strategy_factory.data.config import CoverageConfig
from strategy_factory.data.download.alpaca import latest_chunks
from strategy_factory.data.download.rawfiles import MANIFEST_SUFFIX

COVERAGE_COLUMNS = ["symbol", "year", "file", "row_count", "complete", "required", "missing"]


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
            rows.append(
                {
                    "symbol": symbol,
                    "year": year,
                    "file": path.name if path else None,
                    "row_count": counts.get(year),
                    "complete": _complete(path) if path else None,
                    "required": required,
                    "missing": required and path is None,
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
    }
    return pl.DataFrame(rows, schema=schema).select(COVERAGE_COLUMNS)


def coverage_gaps(frame: pl.DataFrame) -> dict[str, list[int]]:
    """``{symbol: [missing years]}`` for every symbol with a gap (empty when the gate passes)."""
    missing = frame.filter(pl.col("missing")).group_by("symbol").agg(pl.col("year").sort())
    return {s: list(y) for s, y in sorted(missing.rows())}


def describe_gaps(gaps: dict[str, list[int]], limit: int = 20) -> str:
    """A message naming the symbols and years, for the refusal and the CLI summary."""
    parts = [f"{s} {','.join(str(y) for y in ys)}" for s, ys in list(gaps.items())[:limit]]
    more = f" ... and {len(gaps) - limit} more" if len(gaps) > limit else ""
    total = sum(len(v) for v in gaps.values())
    return f"{len(gaps)} symbol(s), {total} missing year(s): " + "; ".join(parts) + more
