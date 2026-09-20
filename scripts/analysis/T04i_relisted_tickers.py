"""T04i (D-383): the relisted-ticker candidate list that T04g's exclusions come from.

Local only -- reads `SFAC_RAW_ROOT`, writes no snapshot::

    uv run python scripts/analysis/T04i_relisted_tickers.py [--out PATH]

Sweeps every symbol of `configs/universe/us_equity_daily.csv` for the re-used-ticker
fingerprint (see `strategy_factory.data.relisting`): a trading gap of at least 200 calendar
days followed by a level break beyond the split check's `jump_threshold` that no known split
explains. Writes `docs/reviews/T04i_relisted_candidates.csv`.

The result is a **candidate list**: D-383 excludes a re-used ticker "for now", but which rows
become exclusions is the supervisor's call, so nothing here edits
`configs/universe/us_equity_daily_excluded.csv`.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import polars as pl

from strategy_factory.data.config import load_alpaca_config, load_known_splits
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.relisting import (
    DEFAULT_GAP_DAYS,
    DEFAULT_STALE_DAYS,
    relisting_candidates,
)

DAILY_DIR = ("us_equity", "alpaca_sip_split", "1D")
UNIVERSE = Path("configs") / "universe" / "us_equity_daily.csv"
OUT_DEFAULT = Path("docs") / "reviews" / "T04i_relisted_candidates.csv"
COLUMNS = [
    "symbol",
    "reason",
    "last_date_before_gap",
    "first_date_after_gap",
    "gap_days",
    "stale_bars",
    "close_before",
    "close_after",
    "ratio",
]


def latest_year_files(folder: Path) -> list[Path]:
    latest: dict[str, Path] = {}
    for f in sorted(folder.glob("*.parquet")):
        latest[f.name.split(".")[0]] = f
    return list(latest.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--gap-days", type=int, default=DEFAULT_GAP_DAYS)
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    ap.add_argument("--symbols", help="Comma-separated subset (default: the daily universe).")
    args = ap.parse_args()

    root, cfg = raw_root(), load_alpaca_config()
    daily_dir = root.joinpath(*DAILY_DIR)
    splits = {
        k.symbol: frozenset({k.date}) for k in load_known_splits(cfg.split_check.known_splits_file)
    }
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        with UNIVERSE.open(encoding="utf-8", newline="") as fh:
            symbols = [r["symbol"] for r in csv.DictReader(fh)]

    rows: list[dict[str, object]] = []
    for i, sym in enumerate(symbols, 1):
        files = latest_year_files(daily_dir / sym)
        if not files:
            continue
        frame = (
            pl.concat([pl.read_parquet(f).select("t", "c") for f in files])
            .drop_nulls("c")
            .with_columns(pl.col("t").str.slice(0, 10).str.to_date().alias("d"))
            .sort("d")
        )
        if frame.height < 2:
            continue
        rows += relisting_candidates(
            sym,
            frame["d"].to_list(),
            frame["c"].to_list(),
            cfg.split_check.jump_threshold,
            splits.get(sym, frozenset()),
            args.gap_days,
            args.stale_days,
        )
        if i % 500 == 0:
            print(f"  {i}/{len(symbols)} symbols, {len(rows)} candidates", flush=True)

    rows.sort(key=lambda r: abs(float(r["ratio"]) - 1.0), reverse=True)  # worst break first
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(symbols)} symbols scanned, {len(rows)} candidates -> {args.out}")
    for r in rows[:15]:
        print(
            f"  {r['symbol']:6} {r['reason']:12} {r['last_date_before_gap']} -> "
            f"{r['first_date_after_gap']} ({r['gap_days']} d, {r['stale_bars']} stale bars)  "
            f"{r['close_before']} -> {r['close_after']}"
        )


if __name__ == "__main__":
    main()
