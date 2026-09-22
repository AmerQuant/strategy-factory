"""T04l: the aggregates the review quotes, from the reuse pass's own outputs.

Local only -- reads ``<SFAC_DATA_ROOT>/_reuse/`` and the catalog; writes CSVs under ``docs/reviews/``;
changes nothing in the store::

    uv run python scripts/analysis/T04l_report.py

* ``T04l_decisions.csv``          -- every candidate boundary: its evidence and its action;
* ``T04l_references_moved.csv``   -- per symbol and timeframe: base (full history) -> derived snapshot,
  the kind (trim / research window), the start, and whether the reference has moved yet;
* ``T04l_same_issuer.csv``        -- the same-CUSIP / same-issuer boundaries and their split verdict
  (D-709 change 1);
* ``T04l_unadjusted_split.csv``   -- the D-397 path, with the ``--refresh`` command.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_reuse import DECISIONS, REUSE_DIR, SUMMARY
from strategy_factory.data.store import SnapshotStore

OUT = Path("docs") / "reviews"
NAMED = ["MBLY", "SE", "SNOW", "CTRA", "PCL", "Q", "CSRA", "AYA", "HAWK", "DOW", "EMC", "CIVI"]


def main() -> None:
    store, catalog = SnapshotStore(), Catalog()
    folder = store.root / REUSE_DIR
    dec = pl.read_csv(folder / DECISIONS, infer_schema_length=None)
    summ = pl.read_csv(folder / SUMMARY, infer_schema_length=None)
    OUT.mkdir(parents=True, exist_ok=True)
    dec.write_csv(OUT / "T04l_decisions.csv")
    summ.sort("symbol", "timeframe").write_csv(OUT / "T04l_references_moved.csv")
    same = dec.filter(pl.col("relation").is_in(["same_cusip", "same_issuer"]))
    same.write_csv(OUT / "T04l_same_issuer.csv")
    summ.filter(pl.col("kind") == "unadjusted_split").write_csv(OUT / "T04l_unadjusted_split.csv")

    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_width_chars(200)
    sources = dec.with_columns(
        pl.when(pl.col("source").str.contains("T04k"))
        .then(pl.lit("T04k kept"))
        .otherwise(pl.lit("long gap only"))
        .alias("from")
    )
    print("boundaries:", dec.height, "on", dec["symbol"].n_unique(), "symbols")
    print(sources.group_by("from", "action").len().sort("from", "action"))
    print(dec.group_by("action", "reason").len().sort("action", "reason"))
    print("same CUSIP / same issuer -> split cross-check:")
    print(same.group_by("relation", "split_verdict").len())
    print("per symbol and timeframe:")
    print(summ.group_by("timeframe", "kind").len().sort("timeframe", "kind"))
    d1 = summ.filter((pl.col("timeframe") == "1D") & pl.col("new_hash").is_not_null())
    if d1.height:
        ok = d1["split_ok"].cast(pl.Utf8).str.to_lowercase()
        print(
            f"1D derived: {d1.height}; splittable (D-008) {int((ok == 'true').sum())}, "
            f"too short {int((ok == 'false').sum())}; bars kept {int(d1['new_bars'].sum())} "
            f"of {int(d1['base_bars'].sum())}"
        )
    print("metadata_stale:", summ.filter(pl.col("metadata_stale").cast(pl.Utf8) == "true").height)
    table = catalog.table()
    marked = table.filter(pl.col("splices") != "[]")
    print("catalog snapshots carrying a marker:", marked.group_by("timeframe").len().rows())
    print("named:")
    print(
        dec.filter(pl.col("symbol").is_in(NAMED))
        .select("symbol", "resumes", "source", "coverage", "relation", "action", "reason")
        .sort("symbol")
    )


if __name__ == "__main__":
    main()
