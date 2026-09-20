"""T04g sections 2 and 3: the split-check and quality aggregates the review quotes.

Local only -- reads `SFAC_RAW_ROOT` and `SFAC_DATA_ROOT`, changes nothing::

    uv run python scripts/ingest/T04g_report.py [--timeframe 1D] [--out docs/reviews]

Prints, and writes as CSVs beside the review:

* the split-check **verdict distribution** and the symbols carrying a split warning;
* **every known split** with its verdict (T04e's expectation is `adjusted`; a known split that is
  not is a finding, D-397);
* how many symbols had **no cross-check file**;
* the **quality aggregate**: count per `quality_status`, the twenty worst `missing_pct`, every
  `critical`, and the count of snapshots whose `zero_volume` or `stale_prices` check failed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_alpaca_config, load_known_splits
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.store import SnapshotStore


def _split_report(root: Path, timeframe: str) -> pl.DataFrame:
    path = root / "_reports" / f"alpaca_split_check_{timeframe}.csv"
    if not path.is_file():
        return pl.DataFrame()
    return pl.read_csv(path, infer_schema_length=10_000)


def _quality_rows(store: SnapshotStore, catalog: Catalog, timeframe: str) -> pl.DataFrame:
    """Read the per-snapshot JSON reports of the ingested snapshots (source alpaca)."""
    rows: list[dict[str, object]] = []
    cat = catalog.table().filter(
        (pl.col("source") == "alpaca") & (pl.col("timeframe") == timeframe)
    )
    for symbol, digest, status in cat.select(
        "symbol", "snapshot_hash", "quality_status"
    ).iter_rows():
        path = store.root / QUALITY_DIR / f"{digest}.json"
        if not path.is_file():
            rows.append(
                {
                    "symbol": symbol,
                    "status": status or "unchecked",
                    "report": False,
                    "missing_pct": 0.0,
                    "skipped": "",
                    "failed": "",
                }
            )
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        checks = {c["code"]: c for c in data.get("checks", [])}
        miss = checks.get("missing_bars", {})
        rows.append(
            {
                "symbol": symbol,
                "status": data.get("status", status),
                "report": True,
                "missing_pct": float((miss.get("details") or {}).get("pct", 0.0) or 0.0),
                "skipped": ",".join(
                    code for code, c in checks.items() if c.get("status") == "skipped"
                ),
                "failed": ",".join(code for code, c in checks.items() if c.get("status") == "fail"),
            }
        )
    return pl.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeframe", default="1D")
    ap.add_argument("--out", type=Path, default=Path("docs") / "reviews")
    args = ap.parse_args()

    root, cfg = raw_root(), load_alpaca_config()
    store, catalog = SnapshotStore(), Catalog()
    args.out.mkdir(parents=True, exist_ok=True)

    # --- 2. split check ---------------------------------------------------------------------
    split = _split_report(root, args.timeframe)
    if split.height:
        dist = split.group_by("verdict").len().sort("len", descending=True)
        print(f"split-check rows: {split.height} over {split['symbol'].n_unique()} symbols")
        for verdict, n in dist.rows():
            print(f"  {verdict:24} {n:>6}")
        no_cross = split.filter(pl.col("verdict") == "no_crosscheck")["symbol"].n_unique()
        print(f"  symbols with at least one no_crosscheck row: {no_cross}")

        known = load_known_splits(cfg.split_check.known_splits_file)
        wanted = pl.DataFrame(
            [
                {"symbol": k.symbol, "date": k.date.isoformat(), "ratio_expected": k.ratio}
                for k in known
            ]
        )
        got = wanted.join(
            split.select("symbol", "date", "verdict", "ratio", "ratio_crosscheck"),
            on=["symbol", "date"],
            how="left",
        ).with_columns(pl.col("verdict").fill_null("not in the report"))
        print("\nknown splits:")
        for r in got.iter_rows(named=True):
            print(f"  {r['symbol']:6} {r['date']}  x{r['ratio_expected']:<5g} {r['verdict']}")
        got.write_csv(args.out / f"T04g_known_splits_{args.timeframe}.csv")
        warn = split.filter(
            pl.col("verdict").is_in(
                ["unadjusted", "unexplained_ingested", "unexplained_crosscheck", "mismatch"]
            )
        )
        warn.write_csv(args.out / f"T04g_split_warnings_{args.timeframe}.csv")
        print(
            f"\n{warn['symbol'].n_unique()} symbol(s) carry a split warning "
            f"-> T04g_split_warnings_{args.timeframe}.csv"
        )

    # --- 3. quality -------------------------------------------------------------------------
    q = _quality_rows(store, catalog, args.timeframe)
    if q.height:
        print(
            f"\nquality reports: {q.height} snapshots, {q.filter(~pl.col('report')).height} without a report file"
        )
        for status, n in q.group_by("status").len().sort("len", descending=True).rows():
            print(f"  {status:12} {n:>6}")
        skipped = q.filter(pl.col("skipped").str.len_chars() > 0)
        print(f"  snapshots with a SKIPPED check: {skipped.height}")
        if skipped.height:
            for code, n in (
                skipped.select(pl.col("skipped").str.split(",").alias("c"))
                .explode("c")
                .group_by("c")
                .len()
                .sort("len", descending=True)
                .rows()
            ):
                print(f"    {code:24} {n:>6}")
        for code in ("zero_volume", "stale_prices", "missing_bars", "session_violations"):
            n = q.filter(pl.col("failed").str.contains(code)).height
            print(f"  failed {code:20} {n:>6}")
        worst = q.sort("missing_pct", descending=True).head(20)
        print("\n20 worst missing_pct:")
        for r in worst.iter_rows(named=True):
            print(f"  {r['symbol']:8} {r['missing_pct']:8.3f}%  {r['status']}  {r['failed']}")
        q.write_csv(args.out / f"T04g_quality_{args.timeframe}.csv")
        crit = q.filter(pl.col("status") == "critical")
        print(f"\ncritical: {crit.height}")
        for r in crit.iter_rows(named=True):
            print(f"  {r['symbol']:8} {r['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
