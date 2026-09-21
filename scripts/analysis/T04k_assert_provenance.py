"""T04k / D-702: assert every current clean snapshot carries **its own** provenance.

Run after the re-derivation, before ``--set-reference``. Local only; changes nothing::

    uv run python scripts/analysis/T04k_assert_provenance.py

For every symbol the last pass cleaned (``_clean/clean_daily_summary.csv``, status ``cleaned``):

* the snapshot is in the store and the catalog, ``derived_from`` the raw snapshot it names;
* its catalog notes carry **this run's** config hash (``config <16 hex>``);
* the arm counts in its notes equal its log (``_clean/<symbol>/<hash>.csv``) and its provenance JSON;
* the provenance names the same raw snapshot and config hash;
* the summary does not flag it ``metadata_stale``.

Every unchanged symbol must name its raw snapshot. Exits non-zero on the first kind of failure
and prints every failing symbol.
"""

from __future__ import annotations

import json
import re
import sys

import polars as pl

from strategy_factory.core.config import config_hash
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_clean import CLEAN_DIR, SUMMARY_FILE
from strategy_factory.data.config import load_alpaca_config, load_quality_config
from strategy_factory.data.store import SnapshotStore, safe_component

ARMS = re.compile(r"changed bar\(s\) - ([^.]*)\.")


def _fingerprint() -> str:
    alpaca, quality = load_alpaca_config(), load_quality_config()
    return config_hash(
        {
            "daily_wick_outlier": quality.daily_wick_outlier.model_dump(mode="json"),
            "daily_extreme_unsupported": quality.daily_extreme_unsupported.model_dump(mode="json"),
            "relisting": alpaca.relisting.model_dump(mode="json"),
            "split_check": alpaca.split_check.model_dump(mode="json"),
        }
    )


def _note_arms(notes: str, fp16: str) -> dict[str, int] | None:
    """The arm counts of the T04k note that carries ``fp16`` (``None`` if there is none)."""
    tail = notes.split(f"config {fp16}: ", 1)
    if len(tail) != 2:
        return None
    m = ARMS.search(tail[1])
    if m is None:
        return None
    out: dict[str, int] = {}
    for part in m.group(1).split(", "):
        arm, n = part.rsplit(" ", 1)
        out[arm] = int(n)
    return out


def main() -> int:
    store, catalog = SnapshotStore(), Catalog()
    clean_dir = store.root / CLEAN_DIR
    summary = pl.read_csv(clean_dir / SUMMARY_FILE, infer_schema_length=None)
    table = catalog.table().filter((pl.col("source") == "alpaca") & (pl.col("timeframe") == "1D"))
    by_hash = {r["snapshot_hash"]: r for r in table.iter_rows(named=True)}
    fp = _fingerprint()
    fp16 = fp[:16]
    fails: dict[str, list[str]] = {}

    def fail(kind: str, symbol: str) -> None:
        fails.setdefault(kind, []).append(symbol)

    statuses = summary.group_by("status").len().sort("status")
    cleaned = summary.filter(pl.col("status") == "cleaned")
    for r in cleaned.iter_rows(named=True):
        symbol, digest = r["symbol"], r["snapshot_hash"]
        row = by_hash.get(digest)
        if row is None:
            fail("not in catalog", symbol)
            continue
        if not (
            store.root / "alpaca" / safe_component(symbol) / "1D" / f"{digest}.parquet"
        ).exists():
            fail("parquet missing", symbol)
        if not row["derived_from"]:
            fail("no derived_from", symbol)
        if r.get("metadata_stale") in (True, "true", "True"):
            fail("metadata_stale", symbol)
        note_arms = _note_arms(row["notes"] or "", fp16)
        if note_arms is None:
            fail("notes lack this run's config hash", symbol)
            continue
        folder = clean_dir / safe_component(symbol)
        log = pl.read_csv(folder / f"{digest}.csv", infer_schema_length=None)
        log_arms = {a: int(n) for a, n in log.group_by("arm").len().rows()}
        prov = json.loads((folder / f"{digest}.json").read_text(encoding="utf-8"))
        if note_arms != log_arms:
            fail("notes arms != log", symbol)
        if prov["arms"] != log_arms or prov["changed_bars"] != log.height:
            fail("provenance arms != log", symbol)
        if prov["config_hash"] != fp:
            fail("provenance config hash", symbol)
        raw = by_hash.get(prov["derived_from"])
        if (
            raw is None
            or raw["derived_from"]
            or f"Raw snapshot {prov['derived_from']}." not in row["notes"]
        ):
            fail("derived_from not the raw snapshot", symbol)

    unchanged = summary.filter(pl.col("status") != "cleaned")
    for r in unchanged.iter_rows(named=True):
        row = by_hash.get(r["snapshot_hash"])
        if r["status"] != "failed" and (row is None or row["derived_from"]):
            fail("unchanged symbol does not name its raw snapshot", r["symbol"])

    print(statuses)
    print(f"config hash {fp}")
    print(f"cleaned {cleaned.height}: checked store, catalog, notes, log and provenance")
    if fails:
        for kind, symbols in sorted(fails.items()):
            print(f"FAIL {kind}: {len(symbols)} -> {', '.join(sorted(symbols)[:30])}")
        return 1
    print(
        "OK: every current clean snapshot carries this run's config hash and the arms its log lists"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
