"""T04l (D-710): is the Alpaca corporate-actions feed complete enough to be evidence?

Local only; reads the raw corporate-action files (read-only, D-028) and the store's catalog; prints,
changes nothing::

    uv run python scripts/analysis/T04l_feed_scope.py

A missing row is evidence of nothing unless the feed covers the market. This checks: rows per type
and year (process_date); distinct symbols across all files; known events (AVGO 2024-07-15 10:1,
GOOGL 2022-07-18 20:1, TSLA 2022-08-25 3:1, Plum Creek -> Weyerhaeuser 2016); and whether the
symbols are confined to a subset (still listed today, tradable, in our universe).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.download.alpaca_reference import latest_action_files
from strategy_factory.data.download.rawfiles import raw_root

SYMBOL_FIELDS = (
    "symbol",
    "old_symbol",
    "new_symbol",
    "acquirer_symbol",
    "acquiree_symbol",
    "source_symbol",
    "alternate_symbol",
)
KNOWN = [
    ("forward_splits", "AVGO", "2024-07"),
    ("forward_splits", "GOOGL", "2022-07"),
    ("forward_splits", "TSLA", "2022-08"),
    ("forward_splits", "NVDA", "2024-06"),
    ("forward_splits", "AAPL", "2020-08"),
    ("stock_mergers", "PCL", "2016"),
    ("cash_dividends", "AAPL", ""),
    ("cash_dividends", "JNJ", ""),
    ("cash_dividends", "KO", ""),
]


def _load(folder: Path) -> dict[str, list[dict[str, Any]]]:
    """The **latest** download of each answer key (the library's selection, D-711)."""
    files = {k: p for k, p in latest_action_files(folder).items() if k != "name_changes"}
    for p in files.values():
        print(f"  reading {p.name}")
    return {k: json.loads(p.read_text(encoding="utf-8")) for k, p in files.items()}


def _date(row: dict[str, Any]) -> str:
    for k in ("process_date", "ex_date", "effective_date", "payable_date"):
        if row.get(k):
            return str(row[k])
    return ""


def main() -> None:
    root = raw_root()
    data = _load(root / "reference" / "alpaca" / "corporate_actions")
    symbols: set[str] = set()
    per_year: list[dict[str, Any]] = []
    for key, rows in data.items():
        for r in rows:
            for f in SYMBOL_FIELDS:
                if r.get(f):
                    symbols.add(str(r[f]))
            per_year.append({"type": key, "year": _date(r)[:4]})
    years = (
        pl.DataFrame(per_year)
        .group_by("type", "year")
        .len()
        .pivot(on="year", index="type", values="len")
        .fill_null(0)
    )
    cols = ["type", *sorted(c for c in years.columns if c != "type")]
    pl.Config.set_tbl_cols(20)
    pl.Config.set_tbl_rows(20)
    print(years.select(cols).sort("type"))
    print(f"distinct symbols across the {len(data)} files: {len(symbols)}")
    all_rows = [r for rows in data.values() for r in rows]
    per_year_all = pl.DataFrame([{"year": _date(r)[:4]} for r in all_rows]).group_by("year").len()
    print("rows per year, all types:", sorted(per_year_all.rows()))
    blank = sum(1 for r in all_rows if not any(r.get(k) for k in r if k.endswith("cusip")))
    print(f"rows without any CUSIP: {blank} of {len(all_rows)}")

    print("known events:")
    for key, sym, when in KNOWN:
        hits = [
            (_date(r), {k: v for k, v in r.items() if k.endswith(("symbol", "cusip", "rate"))})
            for r in data.get(key, [])
            if sym in {str(r.get(f)) for f in SYMBOL_FIELDS} and _date(r).startswith(when)
        ]
        print(f"  {key:<15} {sym:<6} {when or 'any':<8} -> {len(hits)} row(s) {hits[:2]}")

    # is the symbol set a subset of something?
    assets = pl.read_csv(
        root / "reference" / "alpaca" / "alpaca_assets_2026-09-20.v2.csv", infer_schema_length=0
    )
    active = set(assets.filter(pl.col("status") == "active")["symbol"].to_list())
    tradable = set(assets.filter(pl.col("tradable") == "True")["symbol"].to_list())
    listed = set(assets["symbol"].to_list())
    daily = set(pl.read_csv("configs/universe/us_equity_daily.csv")["symbol"].to_list())
    hourly = set(pl.read_csv("configs/universe/us_equity_hourly.csv")["symbol"].to_list())
    for name, ref in [
        ("in today's Alpaca asset list (any status)", listed),
        ("active today", active),
        ("tradable today", tradable),
        ("in our daily universe", daily),
        ("in our hourly universe", hourly),
    ]:
        print(f"  feed symbols {name}: {len(symbols & ref)} of {len(symbols)}")
    divs = {str(r.get("symbol")) for r in data.get("cash_dividends", [])}
    print(
        f"  dividend payers in the feed: {len(divs)}; of the hourly universe: {len(divs & hourly)}"
    )
    first = (
        pl.DataFrame([{"year": _date(r)[:4]} for r in data.get("cash_dividends", [])])
        .group_by("year")
        .len()
        .sort("year")
    )
    print("  cash dividends per year:", first.rows())


if __name__ == "__main__":
    main()
