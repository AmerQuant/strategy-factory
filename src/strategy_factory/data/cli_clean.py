"""``sfac data clean daily`` -- the derived clean daily snapshot (T04k).

D-396 (extremes), D-398 (frozen stretches, re-use boundary), D-399 (never trim on an ambiguous
signature) and D-700 (the re-use discriminator is the company name). A re-use boundary is applied
in this order, and the first rule that decides wins:

1. a **leading** pad (D-398 (3)) is padding, not a re-use signature: trimmed, the symbol stays;
2. the MS-US-1D cross-check: ``unadjusted_split`` takes the **D-397** path -- no clean snapshot,
   history untouched, the symbol listed with its ``--refresh`` command;
3. the **company names** (D-700): only ``re_use`` trims; anything else keeps the full history and
   is listed for the supervisor.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import polars as pl
import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.adapters.alpaca import AlpacaAdapter
from strategy_factory.data.catalog import Catalog, _row_to_meta
from strategy_factory.data.clean_daily import clean_daily
from strategy_factory.data.cli import data_app
from strategy_factory.data.config import (
    load_alpaca_config,
    load_known_splits,
    load_quality_config,
)
from strategy_factory.data.crosscheck import (
    UNADJUSTED_SPLIT,
    UNSETTLED,
    CrosscheckVerdict,
    settle_boundary,
)
from strategy_factory.data.daily_session import (
    breaches,
    expected_bars,
    raw_extremes,
    rth_extremes,
)
from strategy_factory.data.download.alpaca import latest_chunks
from strategy_factory.data.download.alpaca_reference import load_sessions
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.ingest import crosscheck_file
from strategy_factory.data.name_evidence import (
    NameChange,
    changes_by_symbol,
    load_assets,
    load_name_changes,
    settle_by_name,
)
from strategy_factory.data.relisting import TRIM, SeriesVerdict, analyse_series
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split_check import read_crosscheck_csv
from strategy_factory.data.store import SnapshotStore, safe_component

log = get_logger(__name__)

#: Where the changed-bar logs live: one CSV per symbol, beside the store's other reports.
CLEAN_DIR = "_clean"
SUMMARY_FILE = "clean_daily_summary.csv"
SUMMARY_COLUMNS = [
    "symbol",
    "status",
    "raw_bars",
    "clean_bars",
    "changed_bars",
    "boundary_trim",
    "frozen_cut",
    "extreme_cap",
    "wick_clip",
    "boundary_reason",
    "boundary_date",
    "crosscheck_verdict",
    "crosscheck_evidence",
    "name_verdict",
    "name_evidence",
    "near_identical",
    "boundary_applied",
    "snapshot_hash",
    "note",
]

#: The boundary-setting rows of a relisting verdict (a leading pad has its own rule).
_BREAK_REASONS = ("stale_run", "trading_gap")


@dataclass(frozen=True)
class NameSources:
    """D-700 evidence, loaded once per run."""

    assets: dict[str, str]
    changes: dict[str, list[NameChange]]
    window_days: int


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _breach_frame(
    symbol: str, daily: pl.DataFrame, root: Path, cfg: Any, expected: pl.DataFrame
) -> pl.DataFrame | None:
    """The T04i breach frame for ``symbol``, or ``None`` when it has no hourly raw data."""
    hourly_files = latest_chunks(root, "1H", symbol)
    if not hourly_files:
        return None
    hourly, _ = AlpacaAdapter(cfg).to_canonical(hourly_files, timeframe="1H", symbol=symbol)
    if hourly.height == 0:
        return None
    tz = cfg.hourly_session.timezone
    raw = raw_extremes(
        pl.concat([pl.read_parquet(f).select("t", "h", "l") for f in hourly_files]), tz
    )
    return breaches(daily, rth_extremes(hourly, tz), raw, symbol, expected=expected)


def _settle(
    symbol: str, verdict: SeriesVerdict, daily: pl.DataFrame, root: Path, cfg: Any
) -> CrosscheckVerdict:
    """D-399: decide whether this symbol's boundary may be applied at all."""
    boundary = dt.date.fromisoformat(verdict.boundary_date)
    frame = daily.with_columns(pl.col("ts").dt.date().alias("d")).sort("d")
    dates = frame["d"].to_list()
    closes = frame["close"].to_list()
    idx = next((i for i, d in enumerate(dates) if d >= boundary), None)
    if idx is None or idx == 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "the boundary is not inside the series")
    before, after = closes[idx - 1], closes[idx]
    if before <= 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "the close before the boundary is not positive")
    path = crosscheck_file(root, symbol)
    cross = read_crosscheck_csv(path) if path.is_file() else None
    return settle_boundary(
        symbol,
        dates[idx - 1],
        dates[idx],
        after / before,
        cross,
        cfg.split_check.match_tolerance,
        cfg.split_check.jump_threshold,
    )


@data_app.command("clean")
def clean_cmd(
    timeframe: Annotated[str, typer.Option(help="Only 1D is supported (T04k).")] = "1D",
    symbols: Annotated[str | None, typer.Option(help="Comma-separated subset.")] = None,
    set_reference: Annotated[
        bool, typer.Option("--set-reference", help="Make the clean snapshot the reference.")
    ] = False,
    limit: Annotated[
        int | None, typer.Option(help="Only the first N symbols (a smoke run).")
    ] = None,
) -> None:
    """Derive the clean daily snapshot per symbol (D-396, D-398, D-399); never an overwrite."""
    if timeframe != "1D":
        raise _fail("only --timeframe 1D is supported (T04k)")
    try:
        store, catalog = SnapshotStore(), Catalog()
        alpaca, quality = load_alpaca_config(), load_quality_config()
        root = raw_root()
        expected = expected_bars(
            load_sessions(alpaca.hourly_session.sessions_file), alpaca.hourly_session.first_bar
        )
        splits = {
            k.symbol: frozenset({k.date})
            for k in load_known_splits(alpaca.split_check.known_splits_file)
        }
        names = NameSources(
            load_assets(root / alpaca.relisting.names_file),
            changes_by_symbol(load_name_changes(root / alpaca.relisting.name_changes_file)),
            alpaca.relisting.rename_window_days,
        )
        rows = catalog.table().filter(
            (pl.col("source") == "alpaca")
            & (pl.col("timeframe") == timeframe)
            & pl.col("is_reference")
        )
        wanted = {s.strip() for s in symbols.split(",")} if symbols else None
        if wanted:
            rows = rows.filter(pl.col("symbol").is_in(sorted(wanted)))
        if limit:
            rows = rows.head(limit)
    except SfacError as exc:
        raise _fail(str(exc)) from exc

    out_dir = store.root / CLEAN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    for i, row in enumerate(rows.iter_rows(named=True), 1):
        summary.append(
            _clean_symbol(
                row,
                store,
                catalog,
                alpaca,
                quality,
                root,
                expected,
                splits,
                names,
                out_dir,
                set_reference,
            )
        )
        if i % 250 == 0:
            typer.echo(f"  {i}/{rows.height} symbols")

    table = pl.DataFrame(summary, infer_schema_length=None).select(SUMMARY_COLUMNS)
    table.write_csv(out_dir / SUMMARY_FILE)
    counts = dict(table.group_by("status").len().rows())
    typer.echo(
        f"{table.height} symbol(s): "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        + f"; changed bars {int(table['changed_bars'].sum())}"
    )
    typer.echo(f"logs: {out_dir.as_posix()}")


def _clean_symbol(
    row: dict[str, Any],
    store: SnapshotStore,
    catalog: Catalog,
    alpaca: Any,
    quality: Any,
    root: Path,
    expected: pl.DataFrame,
    splits: dict[str, frozenset[dt.date]],
    names: NameSources,
    out_dir: Path,
    set_reference: bool,
) -> dict[str, Any]:
    symbol = row["symbol"]
    out: dict[str, Any] = {c: 0 if c.endswith("_bars") else "" for c in SUMMARY_COLUMNS}
    out.update(symbol=symbol, status="unchanged", crosscheck_verdict="", note="")
    out["near_identical"] = False
    out["boundary_applied"] = False
    for arm in ("boundary_trim", "frozen_cut", "extreme_cap", "wick_clip"):
        out[arm] = 0
    try:
        raw_meta = _row_to_meta(row)
        daily = store.read_snapshot("alpaca", symbol, "1D", row["snapshot_hash"])
        out["raw_bars"] = daily.height
        breach = _breach_frame(symbol, daily, root, alpaca, expected)
        verdict = analyse_series(
            symbol,
            [d.date() for d in daily["ts"].to_list()],
            daily["high"].to_list(),
            daily["low"].to_list(),
            daily["close"].to_list(),
            alpaca.split_check.jump_threshold,
            splits.get(symbol, frozenset()),
            alpaca.relisting.gap_days,
            alpaca.relisting.frozen_min_sessions,
        )
        apply_boundary = True
        if verdict.verdict == TRIM:
            out["boundary_reason"] = verdict.boundary_reason
            out["boundary_date"] = verdict.boundary_date
            apply_boundary = False
            if verdict.boundary_reason == "leading_padding":
                apply_boundary = True  # D-398 (3): padding before a listing, not a re-use
            else:
                settled = _settle(symbol, verdict, daily, root, alpaca)
                out["crosscheck_verdict"] = settled.verdict
                out["crosscheck_evidence"] = settled.evidence
                if settled.verdict == UNADJUSTED_SPLIT:
                    # D-399 / D-700 (3): the D-397 path. No clean snapshot, history untouched.
                    out["status"] = "unadjusted_split"
                    out["note"] = (
                        "D-397: run `uv run sfac data download alpaca --timeframe 1D "
                        f"--symbols {symbol} --start 2016-01-01 --refresh`, then re-check"
                    )
                    out["snapshot_hash"] = row["snapshot_hash"]
                    return out
                named = settle_by_name(
                    symbol,
                    _break_start(verdict),
                    dt.date.fromisoformat(verdict.boundary_date),
                    names.assets,
                    names.changes.get(symbol, []),
                    names.window_days,
                )
                out["name_verdict"] = named.verdict
                out["name_evidence"] = named.evidence
                out["near_identical"] = named.near_identical
                apply_boundary = named.may_trim
            out["boundary_applied"] = apply_boundary
        clean, changes = clean_daily(
            daily,
            symbol,
            quality,
            breaches=breach,
            verdict=verdict,
            frozen_sessions=alpaca.relisting.frozen_min_sessions,
            apply_boundary=apply_boundary,
        )
        out["clean_bars"] = clean.height
        out["changed_bars"] = changes.height
        for arm, n in changes.group_by("arm").len().rows():
            out[arm] = n
        if changes.height == 0:
            # Identical content: the raw snapshot already IS the clean series. Writing it again
            # would return the same hash (rule 10), so nothing is written and the reference stays.
            out["snapshot_hash"] = row["snapshot_hash"]
            return out
        changes.write_csv(out_dir / f"{safe_component(symbol)}.csv")
        stored = store.write_snapshot(clean, _clean_meta(raw_meta, out, changes))
        catalog.register(stored)
        out["snapshot_hash"] = stored.snapshot_hash or ""
        out["status"] = "cleaned"
        if set_reference and stored.snapshot_hash:
            catalog.set_reference(symbol, "1D", stored.snapshot_hash, note="T04k clean daily")
    except Exception as exc:  # one bad symbol must not stop 6,707; it is reported in the summary
        out["status"] = "failed"
        out["note"] = f"{type(exc).__name__}: {exc}"
        log.error("%s: clean failed: %s", symbol, exc)
    return out


def _break_start(verdict: SeriesVerdict) -> dt.date:
    """Where the boundary-setting break begins: the last real bar before a gap, or the first
    padded bar of a frozen stretch (``last_date_before_gap`` of that evidence row)."""
    rows = [
        r
        for r in verdict.rows
        if r["reason"] in _BREAK_REASONS and str(r["first_date_after_gap"]) <= verdict.boundary_date
    ]
    last = max(rows, key=lambda r: str(r["first_date_after_gap"]))
    return dt.date.fromisoformat(str(last["last_date_before_gap"]))


def _clean_meta(raw: SeriesMetadata, out: dict[str, Any], changes: pl.DataFrame) -> SeriesMetadata:
    """The derived snapshot's metadata: ``derived_from`` the raw key, with the arm counts."""
    applied = {arm: int(n) for arm, n in changes.group_by("arm").len().rows()}
    note = (
        f"T04k clean daily (D-396/D-398/D-399/D-700): {changes.height} changed bar(s) - "
        + ", ".join(f"{k} {v}" for k, v in sorted(applied.items()))
        + f". Raw snapshot {raw.snapshot_hash}."
    )
    return raw.model_copy(
        update={
            "snapshot_hash": None,
            "derived_from": raw.key(),
            "notes": (raw.notes + " " + note).strip(),
        }
    )
