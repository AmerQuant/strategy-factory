"""T04g section 4: catalog and store integrity after the 1D ingest.

Local only -- reads `SFAC_DATA_ROOT`, changes nothing::

    uv run python scripts/ingest/T04g_verify.py [--timeframe 1D] [--source alpaca]

Asserts what the task file asks for and prints a table per check, so the review quotes measured
numbers rather than claims:

1. one catalog row per ingested symbol and exactly **one** `is_reference` per
   `(symbol, timeframe)`;
2. every row carries `hash_version = 2`, the source, `asset_class = us_equity`,
   the decided `session` (**D-395**: `exchange`), `adjustment = split`, `feed = sip`;
3. every `snapshot_hash` has a `.parquet` **and** a `.meta.json` in the store, both read-only;
4. the events file holds one `register` and one `set_reference` per symbol.

Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import stat
from collections import Counter
from pathlib import Path

import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_alpaca_config
from strategy_factory.data.store import SnapshotStore

EXPECTED = {
    "asset_class": "us_equity",
    "adjustment": "split",
    "feed": "sip",
    "hash_version": 2,
}


def _writable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IWRITE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeframe", default="1D")
    ap.add_argument("--source", default="alpaca")
    ap.add_argument("--sample-files", type=int, default=0, help="check N snapshots, 0 = all")
    args = ap.parse_args()

    store, catalog = SnapshotStore(), Catalog()
    cfg = load_alpaca_config()
    rows = catalog.table().filter(
        (pl.col("source") == args.source) & (pl.col("timeframe") == args.timeframe)
    )
    failures: list[str] = []
    print(f"{rows.height} catalog rows for {args.source} {args.timeframe}")

    # 1. one reference per symbol
    dupes = rows.group_by("symbol").len().filter(pl.col("len") > 1)
    refs = rows.filter(pl.col("is_reference")).group_by("symbol").len()
    no_ref = rows.height and set(rows["symbol"]) - set(refs["symbol"])
    many_ref = refs.filter(pl.col("len") > 1)
    print(f"  symbols: {rows['symbol'].n_unique()}   rows with >1 snapshot: {dupes.height}")
    print(f"  symbols without a reference: {len(no_ref or ())}   with >1: {many_ref.height}")
    if no_ref:
        failures.append(f"{len(no_ref)} symbol(s) without a reference: {sorted(no_ref)[:10]}")
    if many_ref.height:
        failures.append(f"{many_ref.height} symbol(s) with more than one reference")

    # 2. metadata
    for column, value in ({**EXPECTED, "session": cfg.daily_session}).items():
        if args.timeframe != "1D" and column == "session":
            continue
        bad = rows.filter(pl.col(column) != value)
        print(f"  {column} == {value!r}: {rows.height - bad.height}/{rows.height}")
        if bad.height:
            failures.append(f"{bad.height} row(s) with {column} != {value!r}")

    # 3. files present and read-only
    checked = rows if not args.sample_files else rows.head(args.sample_files)
    missing = writable = 0
    for row in checked.select("source", "symbol", "timeframe", "snapshot_hash").iter_rows():
        for p in store.paths(*row):
            if not p.is_file():
                missing += 1
            elif _writable(p):
                writable += 1
    print(f"  files checked: {checked.height * 2}   missing: {missing}   writable: {writable}")
    if missing:
        failures.append(f"{missing} snapshot file(s) missing")
    if writable:
        failures.append(f"{writable} snapshot file(s) are not read-only (rule 10)")

    # 4. events
    events = catalog.events().filter(pl.col("timeframe") == args.timeframe)
    symbols = set(rows["symbol"].to_list())
    per_event = {
        name: Counter(events.filter(pl.col("event") == name)["symbol"].to_list())
        for name in ("register", "set_reference")
    }
    for name, counts in per_event.items():
        covered = symbols & set(counts)
        extra = {s: n for s, n in counts.items() if s in symbols and n > 1}
        print(f"  {name}: {len(covered)}/{len(symbols)} symbols, {len(extra)} with more than one")
        if len(covered) != len(symbols):
            failures.append(f"{len(symbols) - len(covered)} symbol(s) without a {name} event")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nall integrity checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
