"""Read-only lookups in the raw daily price files (D-028: the raw store is never modified).

Used by the broker-symbol mapping (T06b, D-341) to compare the broker's quote sample with our
own last close, which catches a ticker that means a different company at the broker. The files
are the Alpaca daily downloads, ``<root>/<SYMBOL>/<year>[.vN].parquet`` with the raw Alpaca
columns (``t`` ISO timestamp, ``c`` close); the newest version of a year wins.

This is a **diagnostic** path: it never feeds a backtest, so it reads the raw files directly
instead of going through the snapshot store and :class:`DataAccess`.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import polars as pl

_YEAR_FILE = re.compile(r"^(?P<year>\d{4})(?:\.v(?P<version>\d+))?\.parquet$")
_MAX_LOOKBACK_YEARS = 12  # a delisted symbol may have no bars for years


def _files_by_year(symbol_dir: Path) -> dict[int, Path]:
    """Newest version of each year's file."""
    best: dict[int, tuple[int, Path]] = {}
    for path in symbol_dir.glob("*.parquet"):
        m = _YEAR_FILE.match(path.name)
        if not m:
            continue
        year, version = int(m.group("year")), int(m.group("version") or 1)
        if year not in best or version > best[year][0]:
            best[year] = (version, path)
    return {year: path for year, (_, path) in best.items()}


def last_close_on_or_before(symbol: str, day: dt.date, root: Path) -> tuple[float, dt.date] | None:
    """``(close, date)`` of the last daily bar at or before ``day``; ``None`` if there is none."""
    symbol_dir = root / symbol
    if not symbol_dir.is_dir():
        return None
    files = _files_by_year(symbol_dir)
    for year in sorted((y for y in files if y <= day.year), reverse=True)[:_MAX_LOOKBACK_YEARS]:
        df = pl.read_parquet(files[year], columns=["t", "c"])
        if df.height == 0:
            continue
        ts = pl.col("t").str.slice(0, 10).str.to_date()
        rows = df.with_columns(ts.alias("d")).filter(pl.col("d") <= day).sort("d")
        if rows.height:
            last = rows.tail(1).to_dicts()[0]
            return float(last["c"]), last["d"]
    return None
