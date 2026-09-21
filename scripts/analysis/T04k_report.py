"""T04k: the aggregates the review quotes, from the clean pass's own outputs.

Local only -- reads `SFAC_DATA_ROOT/_clean/`, the quality reports and the T04i artefacts; writes
CSVs under `docs/reviews/`; changes nothing in the store::

    uv run python scripts/analysis/T04k_report.py

* `T04k_boundaries.csv`              -- the 280 re-use candidates and what happened to each;
* `T04k_changes_per_symbol.csv`      -- changed bars per symbol and arm;
* `T04k_changes_per_date.csv`        -- changed bars per date and arm;
* `T04k_short_hourly_dates.csv`      -- **every** short or missing hourly day per date (not only
  the ones that breach), i.e. the days the hourly series is not evidence;
* `T04k_split_after_trim.csv`        -- whether each trimmed series still has a split (D-008);
* `T04k_suspects.csv`                -- what became of T04i's 29 `reverse_split_suspect` trims;
* `T04k_residual_breaches.csv`      -- every correctable breach day the clean series still has,
  with the side of the body at fault and its size (P-76). Needs every hourly series: slow.

The per-bar logs stay in the store at `_clean/<symbol>/<clean hash>.csv`, with a provenance JSON
beside each.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.catalog import Catalog, _row_to_meta
from strategy_factory.data.clean_daily import CORRECTABLE
from strategy_factory.data.cli_clean import (
    CLEAN_DIR,
    SHORT_DAYS_FILE,
    SUMMARY_FILE,
    _hourly_evidence,
)
from strategy_factory.data.config import (
    load_alpaca_config,
    load_quality_config,
    load_split_config,
)
from strategy_factory.data.daily_session import expected_bars
from strategy_factory.data.download.alpaca_reference import load_sessions
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.split import HistoryTooShortError, compute_split
from strategy_factory.data.store import SnapshotStore, safe_component

OUT = Path("docs") / "reviews"
VERDICTS = OUT / "T04i_relisting_verdicts.csv"
QUALITY_BEFORE = OUT / "T04g_quality_1D.csv"


def _outcome(row: dict[str, Any]) -> str:
    if row["status"] == "unadjusted_split":
        return "D-397 (unadjusted_split)"
    if row["boundary_reason"] == "leading_padding":
        return "trimmed (leading padding, D-398 (3))"
    if row["name_verdict"] == "re_use":
        return "trimmed (re_use, D-700)"
    return f"kept ({row['name_verdict']})"


def main() -> None:
    store, catalog = SnapshotStore(), Catalog()
    clean_dir = store.root / CLEAN_DIR
    summary = pl.read_csv(clean_dir / SUMMARY_FILE, infer_schema_length=None)
    OUT.mkdir(parents=True, exist_ok=True)

    # -- the 280 -----------------------------------------------------------------------------
    trims = summary.filter(
        pl.col("boundary_reason").is_not_null() & (pl.col("boundary_reason") != "")
    ).with_columns(
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

    # -- changed bars: only the logs of the current clean snapshots ----------------------------
    current = summary.filter(pl.col("status") == "cleaned").select("symbol", "snapshot_hash")
    frames = [
        pl.read_csv(clean_dir / safe_component(s) / f"{h}.csv", infer_schema_length=None)
        for s, h in current.rows()
    ]
    changes = pl.concat([f for f in frames if f.height], how="vertical_relaxed")
    for key, name in (("symbol", "per_symbol"), ("session_date", "per_date")):
        (
            changes.group_by(key, "arm")
            .len()
            .pivot(on="arm", index=key, values="len")
            .fill_null(0)
            .sort(key)
            .write_csv(OUT / f"T04k_changes_{name}.csv")
        )

    # -- every short or missing hourly day, per date ------------------------------------------
    short = pl.read_csv(clean_dir / SHORT_DAYS_FILE, infer_schema_length=None)
    per_date = (
        short.group_by("session_date")
        .agg(
            pl.len().alias("symbols"),
            pl.col("rth_bars").is_null().sum().alias("no_hourly_bar"),
            pl.col("rth_bars").median().alias("median_rth_bars"),
        )
        .sort("symbols", descending=True)
    )
    per_date.write_csv(OUT / "T04k_short_hourly_dates.csv")

    # -- D-008: does each trimmed series still have a split? -----------------------------------
    split_cfg = load_split_config()
    table = catalog.table()
    trimmed = trims.filter(pl.col("outcome").str.starts_with("trimmed")).select("symbol")
    rows: list[dict[str, Any]] = []
    for symbol, digest in trimmed.join(
        summary.select("symbol", "snapshot_hash"), on="symbol"
    ).rows():
        meta = _row_to_meta(table.filter(pl.col("snapshot_hash") == digest).row(0, named=True))
        bars = store.read_snapshot("alpaca", symbol, "1D", digest)
        try:
            compute_split(bars["ts"], meta.key(), split_cfg)
            ok = True
        except HistoryTooShortError:
            ok = False
        rows.append({"symbol": symbol, "clean_bars": bars.height, "has_split": ok})
    splits = pl.DataFrame(rows)
    splits.sort("symbol").write_csv(OUT / "T04k_split_after_trim.csv")

    # -- T04i's 29 reverse-split suspects -----------------------------------------------------
    with VERDICTS.open(encoding="utf-8", newline="") as fh:
        suspects = [r["symbol"] for r in csv.DictReader(fh) if r["reverse_split_suspect"] == "True"]
    sus = trims.filter(pl.col("symbol").is_in(suspects)).select(
        "symbol", "crosscheck_verdict", "name_verdict", "outcome", "crosscheck_evidence"
    )
    sus.sort("symbol").write_csv(OUT / "T04k_suspects.csv")

    # -- quality: the clean series' status against the raw series' status ----------------------
    before = pl.read_csv(QUALITY_BEFORE, infer_schema_length=None).select(
        "symbol", pl.col("status").alias("before")
    )
    after = summary.select("symbol", "has_hourly", pl.col("quality_status").alias("after"))
    joined = before.join(after, on="symbol")
    moved = joined.group_by("before", "after").len().sort("before")
    worse = joined.filter((pl.col("before") == "ok") & (pl.col("after") == "warning"))
    why: dict[tuple[str, bool], int] = {}
    for symbol, hourly in worse.select("symbol", "has_hourly").rows():
        digest = summary.filter(pl.col("symbol") == symbol)["snapshot_hash"][0]
        report = json.loads(
            (store.root / QUALITY_DIR / f"{digest}.json").read_text(encoding="utf-8")
        )
        for c in report["checks"]:
            if c["status"] == "fail" and c.get("severity") in ("warning", "critical"):
                why[(c["code"], bool(hourly))] = why.get((c["code"], bool(hourly)), 0) + 1

    # -- P-76: correctable breaches, raw against clean, over EVERY hourly symbol ---------------
    alpaca, quality = load_alpaca_config(), load_quality_config()
    root = raw_root()
    expected = expected_bars(
        load_sessions(alpaca.hourly_session.sessions_file), alpaca.hourly_session.first_bar
    )
    raw_ref = dict(
        table.filter(
            (pl.col("source") == "alpaca")
            & (pl.col("timeframe") == "1D")
            & pl.col("derived_from").is_null()
        )
        .select("symbol", "snapshot_hash")
        .rows()
    )
    raw_total = 0
    residual: list[dict[str, Any]] = []
    for symbol, digest in (
        summary.filter(pl.col("has_hourly")).select("symbol", "snapshot_hash").rows()
    ):
        ev = _hourly_evidence(symbol, root, alpaca, quality, expected)
        if ev is None:
            continue
        raw_bars = store.read_snapshot("alpaca", symbol, "1D", raw_ref[symbol])
        raw_total += (
            ev.breaches(raw_bars).filter(pl.col("breach_class").is_in(sorted(CORRECTABLE))).height
        )
        clean = store.read_snapshot("alpaca", symbol, "1D", digest)
        left = ev.breaches(clean).filter(pl.col("breach_class").is_in(sorted(CORRECTABLE)))
        body = clean.select(pl.col("ts").dt.date().alias("session_date"), "open", "close")
        for r in left.join(body, on="session_date").iter_rows(named=True):
            sides = []
            if r["high_side"]:
                sides.append("close" if r["close"] >= r["open"] else "open")
            if r["low_side"]:
                sides.append("close" if r["close"] <= r["open"] else "open")
            residual.append(
                {
                    "symbol": symbol,
                    "session_date": str(r["session_date"]),
                    "breach_class": r["breach_class"],
                    "breach_bps": r["breach_bps"],
                    "side": "+".join(sides),
                }
            )
    res = pl.DataFrame(residual)
    res.write_csv(OUT / "T04k_residual_breaches.csv")
    derived = table.filter(
        (pl.col("source") == "alpaca")
        & (pl.col("timeframe") == "1D")
        & pl.col("derived_from").is_not_null()
    )
    current = set(summary.filter(pl.col("status") == "cleaned")["snapshot_hash"].to_list())
    superseded = derived.filter(~pl.col("snapshot_hash").is_in(sorted(current))).height

    # -- print --------------------------------------------------------------------------------
    print(summary.group_by("status").len().sort("status"))
    print(trims.group_by("boundary_reason", "outcome").len().sort("boundary_reason", "outcome"))
    print(f"changed-bar rows: {changes.height} over {changes['symbol'].n_unique()} symbols")
    print(changes.group_by("arm").agg(pl.len(), pl.col("symbol").n_unique()).sort("arm"))
    print(f"short/missing hourly days: {short.height} over {short['symbol'].n_unique()} symbols")
    print(per_date.head(10))
    no_split = splits.filter(~pl.col("has_split")).height
    print(f"trimmed series without a split (D-008): {no_split} of {splits.height}")
    print(f"suspects among the trims: {sus.height}")
    print(sus.group_by("outcome").len())
    print("quality status, raw (T04g) -> clean series:")
    print(moved)
    print("ok -> warning, by failing check and hourly:", sorted(why.items()))
    print(f"correctable breach days over the hourly symbols: raw {raw_total}, clean {res.height}")
    if res.height:
        print(res.group_by("side").len().sort("len", descending=True))
        print(res.group_by("breach_class").len())
        q = res["breach_bps"]
        print(
            f"residual bps: median {q.median():.2f} p75 {q.quantile(0.75):.2f} "
            f"p90 {q.quantile(0.9):.2f} p99 {q.quantile(0.99):.1f} max {q.max():.1f}"
        )
    print(f"derived snapshots {derived.height}, current {len(current)}, superseded {superseded}")
    stale = summary.filter(pl.col("metadata_stale") == True).height  # noqa: E712
    print(f"current clean snapshots whose stored metadata is stale: {stale}")
    reports = list((store.root / QUALITY_DIR).glob("*.json"))
    carrying = sum(
        1
        for r in reports
        if "daily_wick_outlier"
        in {c["code"] for c in json.loads(r.read_text(encoding="utf-8"))["checks"]}
    )
    print(f"quality reports carrying the T04k checks: {carrying} of {len(reports)}")


if __name__ == "__main__":
    main()
