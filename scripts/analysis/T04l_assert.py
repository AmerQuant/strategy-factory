"""D-714: assert the T04l layer is clean before (and after) ``--set-reference``.

Local only; changes nothing::

    uv run python scripts/analysis/T04l_assert.py

For every symbol and timeframe the last ``sfac data reuse`` acted on:

* 0 ``metadata_stale`` (the stored notes are this run's);
* the derived snapshot is in the catalog, ``derived_from`` set, its notes carry this run's config
  hash and name its base; its log and provenance exist;
* the base exists and still carries the full history; a research window's base carries a
  ``full_history`` marker and the window a ``research_window`` marker naming its start;
* the T04l layer in the catalog is exactly the snapshots this run wrote (nothing left over).

Prints where the references stand. Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import sys

import polars as pl

from strategy_factory.data.catalog import Catalog, _row_to_meta
from strategy_factory.data.cli_reuse import REUSE_DIR, SUMMARY, T04L_TAG
from strategy_factory.data.store import SnapshotStore, safe_component


def main() -> int:
    store, catalog = SnapshotStore(), Catalog()
    summary = pl.read_csv(store.root / REUSE_DIR / SUMMARY, infer_schema_length=None)
    table = catalog.table()
    fails: dict[str, list[str]] = {}

    def fail(kind: str, what: str) -> None:
        fails.setdefault(kind, []).append(what)

    derived = summary.filter(pl.col("new_hash").is_not_null() & (pl.col("new_hash") != ""))
    stale = derived.filter(pl.col("metadata_stale").cast(pl.Utf8).str.to_lowercase() == "true")
    for s, tf in stale.select("symbol", "timeframe").rows():
        fail("metadata_stale", f"{s} {tf}")
    configs: set[str] = set()
    moved = 0
    for r in derived.iter_rows(named=True):
        sym, tf, h = r["symbol"], r["timeframe"], r["new_hash"]
        what = f"{sym} {tf}"
        rows = table.filter(
            (pl.col("symbol") == sym) & (pl.col("timeframe") == tf) & (pl.col("snapshot_hash") == h)
        )
        if rows.height != 1:
            fail("not in catalog", what)
            continue
        row = rows.row(0, named=True)
        notes = row["notes"] or ""
        prov_path = store.root / REUSE_DIR / tf / safe_component(sym) / f"{h}.json"
        if not prov_path.is_file() or not prov_path.with_suffix(".csv").is_file():
            fail("log or provenance missing", what)
            continue
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        configs.add(prov["config_hash"])
        if f"config {prov['config_hash'][:16]}" not in notes:
            fail("notes lack this run's config hash", what)
        if f"Base snapshot {r['base_hash']}" not in notes or not row["derived_from"]:
            fail("notes do not name the base / no derived_from", what)
        base = table.filter(
            (pl.col("symbol") == sym)
            & (pl.col("timeframe") == tf)
            & (pl.col("snapshot_hash") == r["base_hash"])
        )
        if base.height != 1:
            fail("base missing", what)
            continue
        if r["kind"] == "research_window":
            b = catalog.splices(_row_to_meta(base.row(0, named=True)).key())
            w = catalog.splices(_row_to_meta(row).key())
            if not any(s.role == "full_history" for s in b):
                fail("base without full_history marker", what)
            if [str(s.boundary) for s in w] != [r["start"]]:
                fail("window marker does not name its start", what)
        moved += int(bool(row["is_reference"]))
    layer = table.filter(pl.col("notes").str.contains(T04L_TAG, literal=True))
    extra = set(layer["snapshot_hash"].to_list()) - set(derived["new_hash"].to_list())
    if extra:
        fail("T04l snapshots not written by this run", f"{len(extra)}")
    if len(configs) > 1:
        fail("more than one config hash", ", ".join(sorted(c[:16] for c in configs)))

    print(f"derived {derived.height} (by timeframe: {derived.group_by('timeframe').len().rows()})")
    print(f"T04l layer in the catalog {layer.height}; config {', '.join(c[:16] for c in configs)}")
    print(f"metadata_stale {stale.height}; references on a derived snapshot {moved}")
    if fails:
        for kind, items in sorted(fails.items()):
            print(f"FAIL {kind}: {len(items)} -> {', '.join(items[:20])}")
        return 1
    print("OK: 0 stale; every derived snapshot carries this run's config, its base and its marker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
