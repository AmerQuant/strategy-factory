"""D-714: retire every T04l snapshot (none ever a reference) before the one final re-derivation.

Local only -- reads and writes `SFAC_DATA_ROOT`, never `SFAC_RAW_ROOT`::

    uv run python scripts/ingest/T04l_rederive_quarantine.py            # dry run: lists only
    uv run python scripts/ingest/T04l_rederive_quarantine.py --apply

The T04l layer is every catalog snapshot whose notes carry the T04l tag. It is retired with the
D-702 tools: ``Catalog.retire`` refuses a raw snapshot and anything that is or ever was a reference,
so a mistake here stops before anything changes. **Nothing is deleted**: each snapshot moves under
``<store>/_quarantine/T04l_D-714_<utc>/`` with its relative path, together with its log and
provenance (``_reuse/<tf>/<symbol>/<hash>.csv|json``) and its quality report, and ``manifest.csv``
lists every item. The markers on the bases (the current references) stay; the re-run rewrites them.
Emptying the quarantine is a separate, human decision.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt

import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_reuse import REUSE_DIR, T04L_TAG
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.store import SnapshotStore, safe_component


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="retire and move; default is a dry run")
    args = ap.parse_args()
    store, catalog = SnapshotStore(), Catalog()
    layer = catalog.table().filter(pl.col("notes").str.contains(T04L_TAG, literal=True))
    refs = layer.filter(pl.col("is_reference")).height
    ever = catalog.events().filter(
        (pl.col("event") == "set_reference")
        & pl.col("snapshot_hash").is_in(layer["snapshot_hash"].to_list())
    )
    print(
        f"T04l snapshots {layer.height} (1D {layer.filter(pl.col('timeframe') == '1D').height}, "
        f"1H {layer.filter(pl.col('timeframe') == '1H').height}); references {refs}; "
        f"ever a reference {ever.height}"
    )
    if not args.apply:
        print("dry run: nothing changed (pass --apply)")
        return 0

    run = store.root / "_quarantine" / f"T04l_D-714_{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}"
    run.mkdir(parents=True)
    manifest: list[dict[str, str]] = []
    rows = catalog.retire(sorted(layer["snapshot_hash"].to_list()), note="D-714 re-derivation")
    for r in rows.iter_rows(named=True):
        h, sym, tf = r["snapshot_hash"], r["symbol"], r["timeframe"]
        item = {"kind": "t04l", "symbol": sym, "timeframe": tf, "snapshot_hash": h}
        for p in store.quarantine(r["source"], sym, tf, h, run):
            manifest.append({**item, "moved_to": str(p)})
        extras = [
            store.root / REUSE_DIR / tf / safe_component(sym) / f"{h}{ext}"
            for ext in (".csv", ".json")
        ]
        extras += [store.root / QUALITY_DIR / f"{h}{ext}" for ext in (".json", ".md")]
        for p in extras:
            if p.exists():
                target = run / p.relative_to(store.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                p.replace(target)
                manifest.append({**item, "moved_to": str(target)})
    with (run / "manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, ["kind", "symbol", "timeframe", "snapshot_hash", "moved_to"], lineterminator="\n"
        )
        w.writeheader()
        w.writerows(manifest)
    print(f"retired {rows.height} snapshot(s), moved {len(manifest)} file(s) -> {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
