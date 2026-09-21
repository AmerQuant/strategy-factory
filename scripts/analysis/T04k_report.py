"""T04k: the aggregates the review quotes, from the clean pass's own outputs.

Local only -- reads `SFAC_DATA_ROOT/_clean/` and the T04i breach CSV, writes CSVs under
`docs/reviews/`, changes nothing in the store::

    uv run python scripts/analysis/T04k_report.py

* `T04k_boundaries.csv`        -- the 280 re-use candidates: boundary, the D-399 price test, the
  D-700 name test, and what happened (trimmed / kept / D-397);
* `T04k_changes_per_symbol.csv` -- changed bars per symbol and arm;
* `T04k_changes_per_date.csv`   -- changed bars per date and arm (feed-wide events show here);
* `T04k_incomplete_hourly_dates.csv` -- the `incomplete_hourly_day` dates with symbol counts: the
  days the hourly series is not evidence (supervisor, 2026-09-21).

The per-bar logs themselves (every changed bar, old and new value, arm and evidence) stay in the
store at `_clean/<symbol>.csv`; they are ~227 k rows and belong with the snapshots they describe.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from strategy_factory.data.cli_clean import CLEAN_DIR, SUMMARY_FILE
from strategy_factory.data.store import SnapshotStore, safe_component

OUT = Path("docs") / "reviews"
BREACHES = OUT / "T04i_breach_days.csv"


def _outcome(row: dict[str, object]) -> str:
    if row["status"] == "unadjusted_split":
        return "D-397 (unadjusted_split)"
    if row["boundary_reason"] == "leading_padding":
        return "trimmed (leading padding, D-398 (3))"
    if row["name_verdict"] == "re_use":
        return "trimmed (re_use, D-700)"
    return f"kept ({row['name_verdict']})"


def main() -> None:
    store = SnapshotStore()
    clean_dir = store.root / CLEAN_DIR
    summary = pl.read_csv(clean_dir / SUMMARY_FILE, infer_schema_length=None)
    OUT.mkdir(parents=True, exist_ok=True)

    trims = summary.filter(
        pl.col("boundary_reason").is_not_null() & (pl.col("boundary_reason") != "")
    )
    trims = trims.with_columns(
        pl.struct(pl.all()).map_elements(_outcome, return_dtype=pl.Utf8).alias("outcome")
    )
    trims.select(
        "symbol",
        "boundary_reason",
        "boundary_date",
        "crosscheck_verdict",
        "name_verdict",
        "outcome",
        "boundary_trim",
        "near_identical",
        "name_evidence",
        "crosscheck_evidence",
    ).sort("outcome", "symbol").write_csv(OUT / "T04k_boundaries.csv")

    # Only the symbols this pass cleaned: a log an earlier pass left for a symbol that is now
    # unchanged (or on the D-397 path) must not be counted.
    cleaned = {
        safe_component(x) for x in summary.filter(pl.col("status") == "cleaned")["symbol"].to_list()
    }
    logs = [f for f in clean_dir.glob("*.csv") if f.name != SUMMARY_FILE and f.stem in cleaned]
    frames = [pl.read_csv(f, infer_schema_length=None) for f in logs]
    changes = pl.concat([f for f in frames if f.height], how="vertical_relaxed")
    per_symbol = (
        changes.group_by("symbol", "arm")
        .len()
        .pivot(on="arm", index="symbol", values="len")
        .fill_null(0)
    )
    per_symbol.sort("symbol").write_csv(OUT / "T04k_changes_per_symbol.csv")
    per_date = (
        changes.group_by("session_date", "arm")
        .len()
        .pivot(on="arm", index="session_date", values="len")
        .fill_null(0)
    )
    per_date.sort("session_date").write_csv(OUT / "T04k_changes_per_date.csv")

    breaches = pl.read_csv(BREACHES, infer_schema_length=None)
    incomplete = (
        breaches.filter(pl.col("breach_class") == "incomplete_hourly_day")
        .group_by("session_date")
        .agg(pl.len().alias("symbols"), pl.col("rth_bars").median().alias("median_rth_bars"))
        .sort("symbols", descending=True)
    )
    incomplete.write_csv(OUT / "T04k_incomplete_hourly_dates.csv")

    print(f"symbols: {summary.height}")
    print(summary.group_by("status").len().sort("status"))
    print("\nthe 280 boundaries by reason and outcome:")
    print(trims.group_by("boundary_reason", "outcome").len().sort("boundary_reason", "outcome"))
    print(f"\nchanged-bar rows: {changes.height} over {changes['symbol'].n_unique()} symbols")
    print(changes.group_by("arm").len().sort("arm"))
    print("\nworst incomplete_hourly_day dates:")
    print(incomplete.head(10))


if __name__ == "__main__":
    main()
