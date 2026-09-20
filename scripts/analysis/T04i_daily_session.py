"""T04i (D-033): run the daily-vs-RTH breach analysis over every symbol with both timeframes.

Local only: it reads `SFAC_RAW_ROOT`, runs `AlpacaAdapter` **in memory** and writes no snapshot
and no catalog row (D-382, extended by D-358 to both timeframes)::

    uv run python scripts/analysis/T04i_daily_session.py [--symbols A,B] [--out-dir DIR]

Outputs, under `--out-dir` (default `docs/reviews/`):

* `T04i_breach_days.csv`   -- one row per breach day: symbol, date, the two breaches in bps,
  the class (`extended_hours` / `unexplained` / `no_raw_hours`) and the prices behind it;
* `T04i_symbol_coverage.csv` -- per symbol: hourly years covered, days compared, breach counts
  per class. The coverage columns are what D-358 requires the review to state.

The decision rule is fixed before the numbers are seen (T04i section 2): the daily range must be
inside the RTH hourly range on **every** compared day for `daily_session: RTH`; otherwise the
label stays `exchange` and the report says how often and by how much.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import polars as pl

from strategy_factory.data.adapters.alpaca import AlpacaAdapter
from strategy_factory.data.config import load_alpaca_config
from strategy_factory.data.daily_session import (
    EXTENDED_HOURS,
    INCOMPLETE_HOURLY_DAY,
    NO_RAW_HOURS,
    UNEXPLAINED,
    breaches,
    compared_days,
    covered_years,
    expected_bars,
    raw_extremes,
    rth_extremes,
)
from strategy_factory.data.download.alpaca_reference import load_sessions
from strategy_factory.data.download.rawfiles import raw_root

SPLIT_DIR = ("us_equity", "alpaca_sip_split")
OUT_DIR = Path("docs") / "reviews"
BREACH_FILE = "T04i_breach_days.csv"
COVERAGE_FILE = "T04i_symbol_coverage.csv"


def latest_year_files(folder: Path) -> list[Path]:
    """The newest version of each raw year file (``2026.v2.parquet`` beats ``2026.parquet``)."""
    latest: dict[str, Path] = {}
    for f in sorted(folder.glob("*.parquet")):
        latest[f.name.split(".")[0]] = f
    return list(latest.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", help="Comma-separated subset (default: every symbol with both).")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    root = raw_root()
    cfg = load_alpaca_config()
    adapter = AlpacaAdapter(cfg)
    tz = cfg.hourly_session.timezone
    daily_dir, hourly_dir = root.joinpath(*SPLIT_DIR, "1D"), root.joinpath(*SPLIT_DIR, "1H")
    expected = expected_bars(
        load_sessions(cfg.hourly_session.sessions_file), cfg.hourly_session.first_bar
    )
    # symbol class for the "breaches by class" table: the hourly universe says etf vs index member
    classes: dict[str, str] = {}
    universe = Path("configs") / "universe" / "us_equity_hourly.csv"
    if universe.is_file():
        with universe.open(encoding="utf-8", newline="") as fh:
            classes = {r["symbol"]: r["reason"] for r in csv.DictReader(fh)}

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = sorted(
            p.name for p in hourly_dir.iterdir() if p.is_dir() and (daily_dir / p.name).is_dir()
        )

    all_breaches: list[pl.DataFrame] = []
    coverage: list[dict[str, object]] = []
    for i, sym in enumerate(symbols, 1):
        d_files, h_files = latest_year_files(daily_dir / sym), latest_year_files(hourly_dir / sym)
        if not d_files or not h_files:
            continue
        try:
            daily, _ = adapter.to_canonical(d_files, timeframe="1D", symbol=sym)
            hourly, _ = adapter.to_canonical(h_files, timeframe="1H", symbol=sym)
        except Exception as exc:  # one bad symbol must not stop the sweep; it is reported
            coverage.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if daily.height == 0 or hourly.height == 0:
            continue
        rth = rth_extremes(hourly, tz)
        raw = raw_extremes(
            pl.concat([pl.read_parquet(f).select("t", "h", "l") for f in h_files]), tz
        )
        found = breaches(daily, rth, raw, sym, expected=expected).with_columns(
            pl.lit(classes.get(sym, "unknown")).alias("symbol_class")
        )
        all_breaches.append(found)
        counts = dict(found.group_by("breach_class").len().iter_rows())
        years = covered_years(rth)
        coverage.append(
            {
                "symbol": sym,
                "hourly_years": "|".join(str(y) for y in years),
                "hourly_year_count": len(years),
                "days_compared": compared_days(daily, rth),
                "breach_days": found.height,
                EXTENDED_HOURS: counts.get(EXTENDED_HOURS, 0),
                UNEXPLAINED: counts.get(UNEXPLAINED, 0),
                INCOMPLETE_HOURLY_DAY: counts.get(INCOMPLETE_HOURLY_DAY, 0),
                NO_RAW_HOURS: counts.get(NO_RAW_HOURS, 0),
                "symbol_class": classes.get(sym, "unknown"),
                "high_side_days": int(found["high_side"].sum()),
                "low_side_days": int(found["low_side"].sum()),
                "both_sides_days": int((found["high_side"] & found["low_side"]).sum()),
                "max_breach_bps": round(found["breach_bps"].max() or 0.0, 2),
                "error": "",
            }
        )
        if i % 100 == 0:
            print(f"  {i}/{len(symbols)} symbols", flush=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    table = (
        pl.concat(all_breaches).sort("breach_bps", descending=True)
        if all_breaches
        else pl.DataFrame()
    )
    if table.height:
        table.select(
            "symbol",
            "session_date",
            "breach_class",
            pl.col("breach_bps").round(3),
            pl.col("breach_high_bps").round(3),
            pl.col("breach_low_bps").round(3),
            pl.col("breach_atr_frac").round(3),
            "high_side",
            "low_side",
            "symbol_class",
            "daily_high",
            "daily_low",
            "daily_close",
            "rth_high",
            "rth_low",
            "raw_high",
            "raw_low",
            "rth_bars",
            "expected_bars",
            "raw_bars",
        ).write_csv(args.out_dir / BREACH_FILE)
    fields = [
        "symbol",
        "hourly_years",
        "hourly_year_count",
        "days_compared",
        "breach_days",
        "symbol_class",
        "high_side_days",
        "low_side_days",
        "both_sides_days",
        EXTENDED_HOURS,
        UNEXPLAINED,
        INCOMPLETE_HOURLY_DAY,
        NO_RAW_HOURS,
        "max_breach_bps",
        "error",
    ]
    with (args.out_dir / COVERAGE_FILE).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in coverage])

    days = sum(int(r.get("days_compared", 0) or 0) for r in coverage)
    print(f"\n{len(coverage)} symbols, {days} session days compared")
    print(
        f"breach days: {table.height}" + (f" ({100 * table.height / days:.2f} %)" if days else "")
    )
    if table.height:
        print(table.group_by("breach_class").len().sort("len", descending=True))
    print(f"-> {args.out_dir / BREACH_FILE}")
    print(f"-> {args.out_dir / COVERAGE_FILE}")


if __name__ == "__main__":
    main()
