"""D-702: retire the stale and superseded clean-layer snapshots, before re-deriving.

Local only -- reads and writes `SFAC_DATA_ROOT`, never `SFAC_RAW_ROOT`::

    uv run python scripts/ingest/T04k_rederive_quarantine.py            # dry run: lists only
    uv run python scripts/ingest/T04k_rederive_quarantine.py --apply

Retires, per D-702, only clean-layer snapshots that are not and have never been a reference:

* current clean snapshots whose stored metadata is stale (`metadata_stale` in the summary);
* derived snapshots no current summary row points at (superseded by a later pass);

and moves the first-layout flat logs `_clean/<symbol>.csv`. **Nothing is deleted**: every file is
moved under `<store>/_quarantine/T04k_D-702_<utc>/` with its relative path, together with its
per-hash log, provenance and quality report, and `manifest.csv` lists every item. The catalog
refuses a raw snapshot and anything that was ever a reference (`Catalog.retire`). Emptying the
quarantine is a separate, human decision.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt

import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_clean import CLEAN_DIR, SHORT_DAYS_FILE, SUMMARY_FILE
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.store import SnapshotStore, safe_component


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="retire and move; default is a dry run")
    args = ap.parse_args()
    store, catalog = SnapshotStore(), Catalog()
    clean_dir = store.root / CLEAN_DIR
    summary = pl.read_csv(clean_dir / SUMMARY_FILE, infer_schema_length=None)
    derived = catalog.table().filter(
        (pl.col("source") == "alpaca")
        & (pl.col("timeframe") == "1D")
        & pl.col("derived_from").is_not_null()
    )
    current = set(summary.filter(pl.col("status") == "cleaned")["snapshot_hash"].to_list())
    stale = set(
        summary.filter((pl.col("status") == "cleaned") & (pl.col("metadata_stale") == True))[  # noqa: E712
            "snapshot_hash"
        ].to_list()
    )
    superseded = set(derived["snapshot_hash"].to_list()) - current
    retire = derived.filter(pl.col("snapshot_hash").is_in(sorted(stale | superseded)))
    flat = [f for f in clean_dir.glob("*.csv") if f.name not in (SUMMARY_FILE, SHORT_DAYS_FILE)]
    print(
        f"derived in catalog {derived.height}; current {len(current)}; "
        f"stale {len(stale)}; superseded {len(superseded)}; to retire {retire.height}; "
        f"first-layout flat logs {len(flat)}"
    )
    if not args.apply:
        print("dry run: nothing changed (pass --apply)")
        return 0

    run = store.root / "_quarantine" / f"T04k_D-702_{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}"
    run.mkdir(parents=True)
    manifest: list[dict[str, str]] = []
    rows = catalog.retire(sorted(retire["snapshot_hash"].to_list()), note="D-702 re-derivation")
    for r in rows.iter_rows(named=True):
        h, sym = r["snapshot_hash"], r["symbol"]
        why = "stale" if h in stale else "superseded"
        for p in store.quarantine(r["source"], sym, r["timeframe"], h, run):
            manifest.append({"kind": why, "symbol": sym, "snapshot_hash": h, "moved_to": str(p)})
        extras = [clean_dir / safe_component(sym) / f"{h}{ext}" for ext in (".csv", ".json")]
        extras += [store.root / QUALITY_DIR / f"{h}{ext}" for ext in (".json", ".md")]
        for p in extras:
            if p.exists():
                target = run / p.relative_to(store.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                p.replace(target)
                manifest.append(
                    {"kind": why, "symbol": sym, "snapshot_hash": h, "moved_to": str(target)}
                )
    for f in flat:
        target = run / f.relative_to(store.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        f.replace(target)
        manifest.append(
            {"kind": "flat_log", "symbol": f.stem, "snapshot_hash": "", "moved_to": str(target)}
        )
    with (run / "manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["kind", "symbol", "snapshot_hash", "moved_to"], lineterminator="\n")
        w.writeheader()
        w.writerows(manifest)
    print(f"retired {rows.height} snapshot(s), moved {len(manifest)} file(s) -> {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
