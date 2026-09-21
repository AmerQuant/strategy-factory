"""``sfac data clean daily`` -- the derived clean daily snapshot (T04k).

D-396 (extremes), D-398 (frozen stretches, re-use boundary), D-399 (never trim on an ambiguous
signature) and D-700 (the re-use discriminator is the company name). A re-use boundary is applied
in this order, and the first rule that decides wins:

1. a **leading** pad (D-398 (3)) is padding, not a re-use signature: trimmed, the symbol stays;
2. the MS-US-1D cross-check: ``unadjusted_split`` takes the **D-397** path -- no clean snapshot,
   history untouched, the symbol listed with its ``--refresh`` command;
3. the **company names** (D-700): only ``re_use`` trims; anything else keeps the full history and
   is listed for the supervisor.

The input is always the **raw** snapshot (``derived_from`` empty), never the current reference: a
re-run after ``--set-reference`` must re-derive from raw, or it would clean the clean series and
clip wicks a second time (T04k acceptance review, V3). Each clean snapshot gets its own changed-bar
log and provenance record, keyed by its hash, so a superseded snapshot never loses its log.

The quality report for the symbol's clean series -- the clean snapshot, or the raw one where
nothing changed -- is written in the same pass, **with the hourly evidence**, so
``daily_extreme_unsupported`` states every short or missing hourly day it could not check.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import polars as pl
import typer

from strategy_factory.core.config import config_hash
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
from strategy_factory.data.quality import check_snapshot
from strategy_factory.data.relisting import EXCLUDE, TRIM, SeriesVerdict, analyse_series
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split_check import read_crosscheck_csv
from strategy_factory.data.store import SnapshotStore, safe_component

log = get_logger(__name__)

#: Where the changed-bar logs live: ``_clean/<symbol>/<clean hash>.csv`` plus ``.json``.
CLEAN_DIR = "_clean"
SUMMARY_FILE = "clean_daily_summary.csv"
#: Every short or missing hourly day of every hourly symbol (the days that are not evidence).
SHORT_DAYS_FILE = "short_hourly_days.csv"
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
    "has_hourly",
    "short_hourly_days",
    "quality_status",
    "metadata_stale",
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


@dataclass(frozen=True)
class HourlyEvidence:
    """One symbol's hourly series, reduced to what the daily checks need."""

    symbol: str
    rth: pl.DataFrame
    raw: pl.DataFrame
    coverage: pl.DataFrame
    expected: pl.DataFrame
    eps_bps: float

    def breaches(self, daily: pl.DataFrame) -> pl.DataFrame:
        """The breach days of ``daily`` -- recomputed for whichever series is being judged.

        The quality report of a **clean** series must judge the clean bars: breaches computed on
        the raw bars would re-count every extreme ``extreme_cap`` already corrected (the first
        full pass flagged 620 hourly symbols that way).
        """
        return breaches(
            daily, self.rth, self.raw, self.symbol, eps_bps=self.eps_bps, expected=self.expected
        )


def _hourly_evidence(
    symbol: str,
    root: Path,
    alpaca: Any,
    quality: Any,
    expected: pl.DataFrame,
) -> HourlyEvidence | None:
    """The hourly evidence for ``symbol``, or ``None`` when it has no hourly series.

    ``coverage`` holds **every** hourly session with its bar count against the calendar, which is
    what finds a short day that does not breach (V2); ``breaches()`` only holds breach days.
    """
    hourly_files = latest_chunks(root, "1H", symbol)
    if not hourly_files:
        return None
    hourly, _ = AlpacaAdapter(alpaca).to_canonical(hourly_files, timeframe="1H", symbol=symbol)
    if hourly.height == 0:
        return None
    tz = alpaca.hourly_session.timezone
    raw = raw_extremes(
        pl.concat([pl.read_parquet(f).select("t", "h", "l") for f in hourly_files]), tz
    )
    rth = rth_extremes(hourly, tz)
    coverage = rth.join(expected, on="session_date", how="left").select(
        "session_date", "rth_bars", "expected_bars"
    )
    return HourlyEvidence(
        symbol, rth, raw, coverage, expected, quality.daily_extreme_unsupported.eps_bps
    )


def _settle(
    symbol: str, verdict: SeriesVerdict, daily: pl.DataFrame, root: Path, cfg: Any
) -> CrosscheckVerdict:
    """D-399: decide whether this symbol's boundary may be applied at all."""
    boundary = dt.date.fromisoformat(verdict.boundary_date)
    frame = daily.with_columns(pl.col("ts").dt.date().alias("d")).sort("d")
    dates = frame["d"].to_list()
    closes = frame["close"].to_list()
    highs, lows = frame["high"].to_list(), frame["low"].to_list()
    idx = next((i for i, d in enumerate(dates) if d >= boundary), None)
    if idx is None or idx == 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "the boundary is not inside the series")
    # The last REAL bar at or before the break's start: at a stale_run boundary the bar just
    # before the boundary is padding, and a ratio against a pad measures the pad (`TBRG`).
    start = _break_start(verdict)
    real = [i for i in range(idx) if dates[i] <= start and not (highs[i] == lows[i] == closes[i])]
    if not real:
        return CrosscheckVerdict(
            symbol, UNSETTLED, f"no real bar before the break at {start}; only padding"
        )
    i0 = real[-1]
    before, after = closes[i0], closes[idx]
    if before <= 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "the close before the break is not positive")
    path = crosscheck_file(root, symbol)
    cross = read_crosscheck_csv(path) if path.is_file() else None
    return settle_boundary(
        symbol,
        dates[i0],
        dates[idx],
        after / before,
        cross,
        cfg.split_check.match_tolerance,
        cfg.split_check.jump_threshold,
        cfg.split_check.crosscheck_window_days,
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
        rows = input_rows(catalog, timeframe)
        fingerprint = config_hash(
            {
                "daily_wick_outlier": quality.daily_wick_outlier.model_dump(mode="json"),
                "daily_extreme_unsupported": quality.daily_extreme_unsupported.model_dump(
                    mode="json"
                ),
                "relisting": alpaca.relisting.model_dump(mode="json"),
                "split_check": alpaca.split_check.model_dump(mode="json"),
            }
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
    short_days: list[dict[str, Any]] = []
    ctx = CleanContext(
        store, catalog, alpaca, quality, root, expected, splits, names, out_dir, fingerprint
    )
    for i, row in enumerate(rows.iter_rows(named=True), 1):
        summary.append(_clean_symbol(row, ctx, set_reference, short_days))
        if i % 250 == 0:
            typer.echo(f"  {i}/{rows.height} symbols")

    table = pl.DataFrame(summary, infer_schema_length=None).select(SUMMARY_COLUMNS)
    table.write_csv(out_dir / SUMMARY_FILE)
    pl.DataFrame(
        short_days,
        schema={
            "symbol": pl.Utf8(),
            "session_date": pl.Utf8(),
            "rth_bars": pl.Int64(),
            "expected_bars": pl.Int64(),
        },
    ).write_csv(out_dir / SHORT_DAYS_FILE)
    counts = dict(table.group_by("status").len().rows())
    typer.echo(
        f"{table.height} symbol(s): "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        + f"; changed bars {int(table['changed_bars'].sum())}"
    )
    typer.echo(f"logs: {out_dir.as_posix()}")


def input_rows(catalog: Catalog, timeframe: str = "1D") -> pl.DataFrame:
    """The **raw** Alpaca snapshot of every symbol -- never a derived one, whatever the reference.

    Selecting by ``is_reference`` would, once the clean snapshots are the references, feed the
    clean series back in and clip its wicks a second time (V3: 233 symbols, 302 more clips).
    """
    raw = catalog.table().filter(
        (pl.col("source") == "alpaca")
        & (pl.col("timeframe") == timeframe)
        & pl.col("derived_from").is_null()
    )
    # One raw snapshot per symbol: after a D-397 `--refresh` and re-ingest a symbol has two, and
    # the newest is the one the refresh produced (S-c).
    return raw.sort("created_at").unique(subset=["symbol"], keep="last", maintain_order=True)


@dataclass(frozen=True)
class CleanContext:
    """Everything one clean pass shares across symbols."""

    store: SnapshotStore
    catalog: Catalog
    alpaca: Any
    quality: Any
    root: Path
    expected: pl.DataFrame
    splits: dict[str, frozenset[dt.date]]
    names: NameSources
    out_dir: Path
    fingerprint: str


def _clean_symbol(
    row: dict[str, Any],
    ctx: CleanContext,
    set_reference: bool,
    short_days: list[dict[str, Any]],
) -> dict[str, Any]:
    symbol = row["symbol"]
    out: dict[str, Any] = {c: 0 if c.endswith("_bars") else "" for c in SUMMARY_COLUMNS}
    out.update(symbol=symbol, status="unchanged", crosscheck_verdict="", note="")
    out["near_identical"] = False
    out["boundary_applied"] = False
    out["metadata_stale"] = False
    out["has_hourly"] = False
    out["short_hourly_days"] = 0
    for arm in ("boundary_trim", "frozen_cut", "extreme_cap", "wick_clip"):
        out[arm] = 0
    alpaca, quality = ctx.alpaca, ctx.quality
    try:
        raw_meta = _row_to_meta(row)
        daily = ctx.store.read_snapshot("alpaca", symbol, "1D", row["snapshot_hash"])
        out["raw_bars"] = daily.height
        hourly = _hourly_evidence(symbol, ctx.root, alpaca, quality, ctx.expected)
        breach = hourly.breaches(daily) if hourly is not None else None
        coverage = hourly.coverage if hourly is not None else None
        out["has_hourly"] = hourly is not None
        if coverage is not None:
            short = (
                daily.select(pl.col("ts").dt.date().alias("session_date"))
                .join(coverage, on="session_date", how="left")
                .filter(
                    pl.col("rth_bars").is_null() | (pl.col("rth_bars") < pl.col("expected_bars"))
                )
            )
            out["short_hourly_days"] = short.height
            short_days += [
                {
                    "symbol": symbol,
                    "session_date": str(d),
                    "rth_bars": None if b is None else int(b),
                    "expected_bars": None if e is None else int(e),
                }
                for d, b, e in short.rows()
            ]
        verdict = analyse_series(
            symbol,
            [d.date() for d in daily["ts"].to_list()],
            daily["high"].to_list(),
            daily["low"].to_list(),
            daily["close"].to_list(),
            alpaca.split_check.jump_threshold,
            ctx.splits.get(symbol, frozenset()),
            alpaca.relisting.gap_days,
            alpaca.relisting.frozen_min_sessions,
        )
        if verdict.verdict == EXCLUDE:
            # D-398 (4): no boundary can be placed from the series. Never silent (S5).
            out["status"] = "exclude_boundary_unidentifiable"
            out["note"] = "D-398 (4): list in configs/universe/us_equity_daily_excluded.csv"
            out["snapshot_hash"] = row["snapshot_hash"]
            _quality(ctx, raw_meta, daily, hourly, out)
            return out
        apply_boundary = True
        if verdict.verdict == TRIM:
            out["boundary_reason"] = verdict.boundary_reason
            out["boundary_date"] = verdict.boundary_date
            apply_boundary = False
            if verdict.boundary_reason == "leading_padding":
                apply_boundary = True  # D-398 (3): padding before a listing, not a re-use
            else:
                settled = _settle(symbol, verdict, daily, ctx.root, alpaca)
                out["crosscheck_verdict"] = settled.verdict
                out["crosscheck_evidence"] = settled.evidence
                if settled.verdict == UNADJUSTED_SPLIT:
                    # D-399 / D-700 (3): the D-397 path. No clean snapshot, history untouched.
                    out["status"] = "unadjusted_split"
                    out["note"] = (
                        "D-397: run `uv run sfac data download alpaca --timeframe 1D "
                        f"--symbols {symbol} --start {alpaca.history_start} --refresh`, "
                        "then re-check"
                    )
                    out["snapshot_hash"] = row["snapshot_hash"]
                    _quality(ctx, raw_meta, daily, hourly, out)
                    return out
                named = settle_by_name(
                    symbol,
                    _break_start(verdict),
                    dt.date.fromisoformat(verdict.boundary_date),
                    ctx.names.assets,
                    ctx.names.changes.get(symbol, []),
                    ctx.names.window_days,
                    ctx.names.changes,
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
            has_hourly=coverage is not None,
        )
        out["clean_bars"] = clean.height
        out["changed_bars"] = changes.height
        for arm, n in changes.group_by("arm").len().rows():
            out[arm] = n
        if changes.height == 0:
            # Identical content: the raw snapshot already IS the clean series. Writing it again
            # would return the same hash (rule 10), so nothing is written and the reference stays.
            out["snapshot_hash"] = row["snapshot_hash"]
            _quality(ctx, raw_meta, daily, hourly, out)
            return out
        intended = _clean_meta(raw_meta, out, changes, ctx)
        stored = ctx.store.write_snapshot(clean, intended)
        # Identical content returns the metadata stored by whoever wrote it first (D-392: no
        # correction path). When an earlier pass wrote it, its notes can be stale or even name a
        # different arm (`AENT`: `frozen_cut 278` stored, `boundary_trim 278` now). Never silent:
        # the summary flags it, and the provenance JSON beside the log is the current record.
        out["metadata_stale"] = stored.notes != intended.notes
        ctx.catalog.register(stored)
        digest = stored.snapshot_hash or ""
        folder = ctx.out_dir / safe_component(symbol)
        folder.mkdir(parents=True, exist_ok=True)
        changes.write_csv(folder / f"{digest}.csv")
        (folder / f"{digest}.json").write_text(
            json.dumps(_provenance(raw_meta, out, changes, ctx), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        out["snapshot_hash"] = digest
        out["status"] = "cleaned"
        _quality(ctx, stored, clean, hourly, out)
        if set_reference and digest:
            ctx.catalog.set_reference(symbol, "1D", digest, note="T04k clean daily")
    except Exception as exc:  # one bad symbol must not stop 6,707; it is reported in the summary
        out["status"] = "failed"
        out["note"] = f"{type(exc).__name__}: {exc}"
        log.error("%s: clean failed: %s", symbol, exc)
    return out


def _quality(
    ctx: CleanContext,
    meta: SeriesMetadata,
    series: pl.DataFrame,
    hourly: HourlyEvidence | None,
    out: dict[str, Any],
) -> None:
    """The quality report for the series the research will read, judged on **that** series."""
    rep = check_snapshot(
        meta,
        ctx.store,
        ctx.catalog,
        ctx.quality,
        breaches=hourly.breaches(series) if hourly is not None else None,
        coverage=hourly.coverage if hourly is not None else None,
    )
    out["quality_status"] = rep.status


def _provenance(
    raw: SeriesMetadata, out: dict[str, Any], changes: pl.DataFrame, ctx: CleanContext
) -> dict[str, Any]:
    """The structured record of what was applied -- beside the log, keyed by the clean hash."""
    return {
        "task": "T04k",
        "decisions": ["D-396", "D-398", "D-399", "D-700"],
        "symbol": raw.symbol,
        "derived_from": raw.snapshot_hash,
        "config_hash": ctx.fingerprint,
        "arms": {arm: int(n) for arm, n in changes.group_by("arm").len().rows()},
        "changed_bars": changes.height,
        "raw_bars": out["raw_bars"],
        "clean_bars": out["clean_bars"],
        "boundary": {
            "date": out["boundary_date"] or None,
            "reason": out["boundary_reason"] or None,
            "applied": bool(out["boundary_applied"]),
            "crosscheck": out["crosscheck_verdict"] or None,
            "name_verdict": out["name_verdict"] or None,
            "name_evidence": out["name_evidence"] or None,
        },
        "has_hourly": bool(out["has_hourly"]),
        "short_hourly_days": out["short_hourly_days"],
    }


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


def _clean_meta(
    raw: SeriesMetadata, out: dict[str, Any], changes: pl.DataFrame, ctx: CleanContext
) -> SeriesMetadata:
    """The derived snapshot's metadata: ``derived_from`` the raw key, what was applied and the
    config hash of every threshold that decided it (task section 2)."""
    applied = {arm: int(n) for arm, n in changes.group_by("arm").len().rows()}
    note = (
        f"T04k clean daily (D-396/D-398/D-399/D-700), config {ctx.fingerprint[:16]}: "
        f"{changes.height} changed bar(s) - "
        + ", ".join(f"{k} {v}" for k, v in sorted(applied.items()))
        + f". Raw snapshot {raw.snapshot_hash}."
    )
    if out.get("boundary_applied"):
        note += (
            f" History starts {out['boundary_date']} ({out['boundary_reason']}; "
            f"D-398, evidence: {out.get('name_verdict') or 'leading padding'})."
        )
    elif out.get("boundary_date"):
        note += (
            f" Boundary {out['boundary_date']} NOT applied "
            f"({out.get('name_verdict') or out.get('crosscheck_verdict')}): full history kept."
        )
    return raw.model_copy(
        update={
            "snapshot_hash": None,
            "derived_from": raw.key(),
            "notes": (raw.notes + " " + note).strip(),
        }
    )
