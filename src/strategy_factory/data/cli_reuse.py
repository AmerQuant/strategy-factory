"""``sfac data reuse`` -- T04l: re-used tickers decided by CUSIP, in 1D and 1H (D-705 ... D-713).

**Base.** For every symbol with a 1D or 1H reference, the base is that reference -- or, when it is
already a T04l snapshot, the base its notes name ("Base snapshot <hash>", looked up by the full
key), so a re-run never derives from its own output. The base carries the full history and, when a
boundary stays unsettled, the ``full_history`` marker (D-709).

**Candidates.** The boundaries T04k kept (``_clean/clean_daily_summary.csv``) and every gap of
``relisting.gap_days`` or more in the base series, 1D and 1H (D-708); an hourly gap that overlaps
a daily break is that break, dated as the daily series dates it. Each boundary is judged on the
rows between its neighbours only (the next holder's rows are not evidence about this one).

**Derived snapshots** (D-713), which become the references only with ``--set-reference``:

* **1D** -- re-derived **from raw** exactly as T04k derives it (``clean_daily``, every arm), with
  the T04l start as the boundary: ``derived_from`` the raw snapshot, the base named in the notes;
* **1H** -- the raw hourly series from the start on: ``derived_from`` the raw hourly snapshot.

Unsettled -> the base is marked ``full_history`` and the derived snapshot ``research_window``. An
unadjusted split (the D-397 path) derives nothing; the base is marked (reason
``unadjusted_split``) and listed with its ``--refresh`` command. A plan that no longer cuts (new
evidence) puts the base back as the reference and clears its marker. A snapshot whose stored notes
are not the ones this run would write (``metadata_stale``, D-392) is never made a reference.

Outputs under ``<SFAC_DATA_ROOT>/_reuse/``: ``T04l_reuse_summary.csv`` (one row per symbol and
timeframe acted on), ``T04l_decisions.csv`` (one row per boundary), and per derived snapshot
``<tf>/<symbol>/<hash>.csv`` (the log) and ``.json`` (provenance).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Any

import polars as pl
import typer

from strategy_factory.core.config import config_hash
from strategy_factory.core.errors import SfacError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.catalog import Catalog, Splice, _row_to_meta
from strategy_factory.data.clean_daily import clean_daily
from strategy_factory.data.cli import data_app
from strategy_factory.data.cli_clean import CLEAN_DIR, SUMMARY_FILE, _hourly_evidence
from strategy_factory.data.config import (
    AlpacaConfig,
    load_alpaca_config,
    load_quality_config,
    load_split_config,
)
from strategy_factory.data.crosscheck import UNADJUSTED_SPLIT, settle_boundary
from strategy_factory.data.cusip_evidence import (
    BOTH,
    DIFFERENT_ISSUER,
    MIXED,
    Event,
    SplitRecord,
    classify,
    load_events,
    load_splits,
)
from strategy_factory.data.daily_session import expected_bars
from strategy_factory.data.download.alpaca_reference import latest_action_files, load_sessions
from strategy_factory.data.download.rawfiles import MANIFEST_SUFFIX, raw_root
from strategy_factory.data.ingest import crosscheck_file
from strategy_factory.data.quality import check_snapshot
from strategy_factory.data.relisting import TRIM, SeriesVerdict
from strategy_factory.data.reuse import (
    SPLIT_MATCH,
    Boundary,
    Decision,
    Plan,
    decide,
    long_gaps,
    plan,
    split_test,
)
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split import HistoryTooShortError, compute_split
from strategy_factory.data.split_check import read_crosscheck_csv
from strategy_factory.data.store import SnapshotStore, safe_component

log = get_logger(__name__)

REUSE_DIR = "_reuse"
SUMMARY = "T04l_reuse_summary.csv"
DECISIONS = "T04l_decisions.csv"
#: The notes of every T04l snapshot carry this; ``_base`` follows their "Base snapshot" back.
T04L_TAG = "T04l re-use"
DECISION_IDS = ("D-705", "D-708", "D-709", "D-712", "D-713")
TIMEFRAMES = ("1D", "1H")
KEY_FIELDS = ("source", "symbol", "timeframe", "snapshot_hash")
_BASE = re.compile(r"Base snapshot ([0-9a-f]{64})")


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _row(table: pl.DataFrame, source: str, symbol: str, tf: str, digest: str) -> dict[str, Any]:
    rows = table.filter(
        (pl.col("source") == source)
        & (pl.col("symbol") == symbol)
        & (pl.col("timeframe") == tf)
        & (pl.col("snapshot_hash") == digest)
    )
    return rows.row(0, named=True) if rows.height else {}


def _base(row: dict[str, Any], table: pl.DataFrame) -> dict[str, Any]:
    """The full-history snapshot behind a reference: itself, or the base a T04l snapshot names --
    by the full key (identical bars under two symbols share a content hash)."""
    notes = row["notes"] or ""
    found = _BASE.findall(notes) if T04L_TAG in notes else []
    if not found:
        return row
    base = _row(table, row["source"], row["symbol"], row["timeframe"], found[-1])
    return base or row


def _raw_1d(table: pl.DataFrame, symbol: str) -> dict[str, Any]:
    """The raw daily snapshot T04k derives from (``derived_from`` empty; the latest one)."""
    rows = table.filter(
        (pl.col("source") == "alpaca")
        & (pl.col("symbol") == symbol)
        & (pl.col("timeframe") == "1D")
        & pl.col("derived_from").is_null()
    ).sort("created_at")
    return rows.row(-1, named=True) if rows.height else {}


def _t04k_candidates(clean_dir: Path) -> dict[str, list[Boundary]]:
    """The boundaries T04k kept: a re-use boundary it found but did not apply (D-700)."""
    path = clean_dir / SUMMARY_FILE
    if not path.is_file():
        return {}
    summary = pl.read_csv(path, infer_schema_length=None)
    kept = summary.filter(
        pl.col("boundary_reason").is_not_null()
        & (pl.col("boundary_reason") != "")
        & (pl.col("boundary_applied").cast(pl.Utf8).str.to_lowercase() == "false")
    )
    out: dict[str, list[Boundary]] = {}
    for sym, date, verdict in kept.select("symbol", "boundary_date", "name_verdict").rows():
        out.setdefault(sym, []).append(
            Boundary(dt.date.fromisoformat(str(date)), "T04k kept", verdict or None)
        )
    return out


def _same_break(
    resumes_1h: dt.date,
    gap_1h: int,
    daily_gaps: list[tuple[dt.date, int]],
    kept: list[Boundary],
) -> dt.date:
    """The daily date of the break an hourly gap belongs to. The hourly series may resume on a
    different day than the daily one (``PCL``: 1D 2025-08-01, 1H 2025-09-12); judged at the later
    date, the new holder's first rows would land on the before side. An hourly gap that overlaps a
    daily gap -- or contains a boundary T04k kept -- is that break, dated as the daily series
    dates it; otherwise it keeps its own date."""
    lo = resumes_1h - dt.timedelta(days=gap_1h)
    for r, g in daily_gaps:
        if lo < r and r - dt.timedelta(days=g) < resumes_1h:
            return r
    for b in kept:
        if lo < b.resumes <= resumes_1h:
            return b.resumes
    return resumes_1h


def _boundaries(
    kept: list[Boundary], bars: dict[str, pl.DataFrame], gap_days: int
) -> list[Boundary]:
    """Every candidate, one per date (a break seen by T04k, in 1D and in 1H is one break)."""
    daily_gaps = long_gaps(bars["1D"]["ts"], gap_days) if "1D" in bars else []
    found = list(kept) + [Boundary(r, "long gap 1D", None, g) for r, g in daily_gaps]
    if "1H" in bars:
        for r_h, g_h in long_gaps(bars["1H"]["ts"], gap_days):
            found.append(
                Boundary(_same_break(r_h, g_h, daily_gaps, kept), "long gap 1H", None, g_h)
            )
    unique: dict[dt.date, Boundary] = {}
    for b in found:
        seen = unique.get(b.resumes)
        if seen is None:
            unique[b.resumes] = b
            continue
        unique[b.resumes] = Boundary(
            b.resumes,
            "+".join(sorted(set(seen.source.split("+")) | {b.source})),
            seen.name_verdict or b.name_verdict,
            max(seen.gap_days or 0, b.gap_days or 0) or None,
        )
    return sorted(unique.values(), key=lambda b: b.resumes)


def _between(events: list[Event], lo: dt.date | None, hi: dt.date | None) -> list[Event]:
    """The rows between a boundary's neighbours: the previous holder's rows before ``lo`` and the
    next holder's from ``hi`` on are not evidence about this break."""
    a = lo.isoformat() if lo else ""
    b = hi.isoformat() if hi else "9999"
    return [e for e in events if a <= e.date < b]


def _split_verdict(
    symbol: str,
    daily: pl.DataFrame,
    resumes: dt.date,
    ev: Any,
    splits: list[SplitRecord],
    root: Path,
    alpaca: AlpacaConfig,
) -> tuple[str, str]:
    """D-709 change 1: the known-split test at this break (``reuse.split_test``), with the D-399
    cross-check as a second witness -- an unadjusted split by either takes the D-397 path."""
    frame = daily.with_columns(pl.col("ts").dt.date().alias("d")).sort("d")
    before = frame.filter(
        (pl.col("d") < resumes)
        & ~((pl.col("high") == pl.col("low")) & (pl.col("low") == pl.col("close")))
    )
    after = frame.filter(pl.col("d") >= resumes)
    if before.height == 0 or after.height == 0 or before["close"][-1] <= 0:
        return "unexplained_jump", "no real bar on one side of the break: the test cannot run"
    d0, d1 = before["d"][-1], after["d"][0]
    ratio = after["close"][0] / before["close"][-1]
    sc = alpaca.split_check
    verdict, text = split_test(ratio, d0, d1, ev, splits, sc.jump_threshold, sc.match_tolerance)
    path = crosscheck_file(root, symbol)
    cross = read_crosscheck_csv(path) if path.is_file() else None
    xc = settle_boundary(
        symbol,
        d0,
        d1,
        ratio,
        cross,
        sc.match_tolerance,
        sc.jump_threshold,
        sc.crosscheck_window_days,
    )
    if xc.verdict == UNADJUSTED_SPLIT:
        return SPLIT_MATCH, f"{text}; D-399 cross-check: {xc.evidence}"
    return verdict, f"{text}; D-399 cross-check: {xc.verdict} ({xc.evidence})"


def _evidence_files(folder: Path) -> dict[str, str]:
    """``file name -> sha256`` of the evidence read (from its manifest when there is one)."""
    out: dict[str, str] = {}
    for path in latest_action_files(folder).values():
        manifest = path.with_name(path.name + MANIFEST_SUFFIX)
        if manifest.is_file():
            out[path.name] = json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
        else:
            out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _splices(decisions: tuple[Decision, ...], role: str) -> tuple[Splice, ...]:
    return tuple(
        Splice.model_validate(
            {
                "boundary": d.boundary.resumes,
                "break_start": d.boundary.break_start,
                "role": role,
                "reason": d.reason,
                "evidence": f"{d.boundary.source}: {d.evidence.describe()}"
                + (f"; {d.split_evidence}" if d.split_evidence else ""),
            }
        )
        for d in decisions
    )


def _note(p: Plan, base_hash: str, fp: str) -> str:
    parts = "; ".join(
        f"{d.boundary.resumes} {d.action}" + (f" ({d.reason})" if d.reason else "")
        for d in p.decisions
    )
    what = (
        f"research window from {p.start}: the last unsettled boundary; full history in the base"
        if p.kind == "research_window"
        else f"history starts {p.start}: a proven re-use (different issuer)"
    )
    return (
        f"{T04L_TAG} ({'/'.join(DECISION_IDS)}), config {fp[:16]}: {what}. Boundaries: {parts}. "
        f"Base snapshot {base_hash}."
    )


def _decision_row(symbol: str, d: Decision) -> dict[str, Any]:
    e = d.evidence
    return {
        "symbol": symbol,
        "resumes": d.boundary.resumes.isoformat(),
        "break_start": d.boundary.break_start.isoformat() if d.boundary.break_start else "",
        "source": d.boundary.source,
        "gap_days": d.boundary.gap_days,
        "name_verdict": d.boundary.name_verdict,
        "coverage": e.coverage,
        "relation": e.relation,
        "action": d.action,
        "reason": d.reason,
        "cusips_before": "|".join(e.before),
        "cusips_after": "|".join(e.after),
        "types_before": "|".join(e.types_before),
        "types_after": "|".join(e.types_after),
        "ceased_before": "|".join(e.ceased_before),
        "dropped_rekeyed": e.dropped_rekeyed,
        "split_verdict": d.split_verdict,
        "split_evidence": d.split_evidence,
    }


class _Ctx:
    """What one run shares across symbols."""

    def __init__(self, set_reference: bool) -> None:
        self.store, self.catalog = SnapshotStore(), Catalog()
        self.alpaca, self.quality = load_alpaca_config(), load_quality_config()
        self.split_cfg = load_split_config()
        self.root = raw_root()
        evidence_dir = self.root / self.alpaca.reuse.corporate_actions_dir
        self.events, _ = load_events(evidence_dir)
        self.splits = load_splits(evidence_dir)
        self.files = _evidence_files(evidence_dir)
        self.fp = config_hash(
            {
                "relisting": self.alpaca.relisting.model_dump(mode="json"),
                "split_check": self.alpaca.split_check.model_dump(mode="json"),
                "reuse": self.alpaca.reuse.model_dump(mode="json"),
                "daily_wick_outlier": self.quality.daily_wick_outlier.model_dump(mode="json"),
                "daily_extreme_unsupported": self.quality.daily_extreme_unsupported.model_dump(
                    mode="json"
                ),
                "evidence": self.files,
            }
        )
        self.expected = expected_bars(
            load_sessions(self.alpaca.hourly_session.sessions_file),
            self.alpaca.hourly_session.first_bar,
        )
        self.kept = _t04k_candidates(self.store.root / CLEAN_DIR)
        self.out_dir = self.store.root / REUSE_DIR
        self.window = self.alpaca.relisting.rename_window_days
        self.set_reference = set_reference


@data_app.command("reuse")
def reuse_cmd(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated subset.")] = None,
    set_reference: Annotated[
        bool, typer.Option("--set-reference", help="Make the derived snapshots the references.")
    ] = False,
) -> None:
    """T04l: decide re-used tickers by CUSIP; derive 1D/1H snapshots from the boundary (D-713)."""
    try:
        ctx = _Ctx(set_reference)
        table = ctx.catalog.table()
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    refs = table.filter(
        (pl.col("source") == "alpaca")
        & pl.col("timeframe").is_in(list(TIMEFRAMES))
        & pl.col("is_reference")
    )
    wanted = {s.strip() for s in symbols.split(",")} if symbols else None
    names = sorted(set(refs["symbol"].to_list()) & (wanted or set(refs["symbol"].to_list())))
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    decisions_out: list[dict[str, Any]] = []
    for i, symbol in enumerate(names, 1):
        if i % 500 == 0:
            typer.echo(f"  {i}/{len(names)} symbols")
        try:
            rows, decs = _reuse_symbol(symbol, refs.filter(pl.col("symbol") == symbol), table, ctx)
        except SfacError as exc:
            log.error("%s: T04l failed: %s", symbol, exc)
            summary.append({"symbol": symbol, "timeframe": "", "kind": "failed", "note": str(exc)})
            continue
        summary += rows
        decisions_out += decs
    out = pl.DataFrame(summary, infer_schema_length=None)
    out.write_csv(ctx.out_dir / SUMMARY)
    pl.DataFrame(decisions_out, infer_schema_length=None).write_csv(ctx.out_dir / DECISIONS)
    counts = (
        {f"{tf} {kind}": n for tf, kind, n in out.group_by("timeframe", "kind").len().rows()}
        if out.height
        else {}
    )
    typer.echo(f"{len(names)} symbol(s) read; acted on: {counts}")
    typer.echo(f"decisions: {len(decisions_out)} boundary(ies); outputs: {ctx.out_dir.as_posix()}")


def _decisions(
    symbol: str, bars: dict[str, pl.DataFrame], ctx: _Ctx, kept: list[Boundary]
) -> list[Decision]:
    boundaries = _boundaries(kept, bars, ctx.alpaca.relisting.gap_days)
    events = ctx.events.get(symbol, [])
    window = dt.timedelta(days=ctx.window)
    out: list[Decision] = []
    for k, b in enumerate(boundaries):
        lo = boundaries[k - 1].resumes - window if k else None
        hi = boundaries[k + 1].resumes - window if k + 1 < len(boundaries) else None
        ev = classify(_between(events, lo, hi), b.resumes, ctx.window, b.break_start)
        split_verdict = split_evidence = None
        if ev.coverage == BOTH and ev.relation not in (DIFFERENT_ISSUER, MIXED):
            daily = bars.get("1D", bars.get("1H"))
            assert daily is not None
            split_verdict, split_evidence = _split_verdict(
                symbol, daily, b.resumes, ev, ctx.splits, ctx.root, ctx.alpaca
            )
        action, reason = decide(b, ev, split_verdict)
        out.append(Decision(b, action, reason, ev, split_verdict, split_evidence or ""))
    return out


def _reuse_symbol(
    symbol: str, refs: pl.DataFrame, table: pl.DataFrame, ctx: _Ctx
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current: dict[str, dict[str, Any]] = {}
    bases: dict[str, dict[str, Any]] = {}
    bars: dict[str, pl.DataFrame] = {}
    for tf in TIMEFRAMES:
        r = refs.filter(pl.col("timeframe") == tf)
        if r.height:
            current[tf] = r.row(0, named=True)
            bases[tf] = _base(current[tf], table)
            bars[tf] = ctx.store.read_snapshot("alpaca", symbol, tf, bases[tf]["snapshot_hash"])
    p = plan(_decisions(symbol, bars, ctx, ctx.kept.get(symbol, [])))
    decs = [_decision_row(symbol, d) for d in p.decisions]
    rows: list[dict[str, Any]] = []
    for tf, base in bases.items():
        base_meta = _row_to_meta(base)
        moved_before = current[tf]["snapshot_hash"] != base["snapshot_hash"]
        if p.kind == "none":
            # new evidence may undo an earlier cut: the base is the reference, unmarked
            if ctx.catalog.mark_splices(base_meta.key(), (), note=f"{T04L_TAG}: cleared"):
                _quality(ctx, base_meta, tf, symbol)
            if moved_before and ctx.set_reference:
                ctx.catalog.set_reference(
                    symbol, tf, base["snapshot_hash"], note=f"{T04L_TAG}: base restored"
                )
                rows.append({"symbol": symbol, "timeframe": tf, "kind": "restored"})
            continue
        row: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": tf,
            "kind": p.kind,
            "start": p.start.isoformat() if p.start else "",
            "base_hash": base["snapshot_hash"],
            "base_bars": bars[tf].height,
            "new_hash": "",
            "derived_from": "",
            "new_bars": 0,
            "removed_bars": 0,
            "marked": "|".join(str(d.boundary.resumes) for d in p.marked),
            "split_ok": "",
            "metadata_stale": False,
            "reference_moved": False,
            "note": "",
        }
        rows.append(row)
        if ctx.catalog.mark_splices(
            base_meta.key(), _splices(p.marked, "full_history"), note=f"{T04L_TAG}: D-709"
        ):
            _quality(ctx, base_meta, tf, symbol)
        if p.kind == "unadjusted_split":
            row["note"] = (
                f"D-397: run `uv run sfac data download alpaca --timeframe {tf} --symbols "
                f"{symbol} --start {ctx.alpaca.history_start} --refresh`, then re-check"
            )
            if moved_before and ctx.set_reference:
                ctx.catalog.set_reference(
                    symbol, tf, base["snapshot_hash"], note=f"{T04L_TAG}: D-397 path, base restored"
                )
            continue
        assert p.start is not None
        derived = _derive(symbol, tf, base, bars[tf], table, p, ctx)
        if derived is None:
            row["note"] = "no bar before the start in this timeframe: nothing to cut"
            continue
        stored, intended, parent, n_bars, removed, cut_ts = derived
        row["metadata_stale"] = stored.notes != intended.notes
        digest = stored.snapshot_hash or ""
        row.update(
            new_hash=digest,
            derived_from=parent,
            new_bars=n_bars,
            removed_bars=removed,
        )
        ctx.catalog.mark_splices(
            stored.key(), _splices(p.window, "research_window"), note=f"{T04L_TAG}: D-713"
        )
        _quality(ctx, stored, tf, symbol)
        if tf == "1D":
            try:
                compute_split(cut_ts, stored.key(), ctx.split_cfg)
                row["split_ok"] = True
            except HistoryTooShortError:
                row["split_ok"] = False
        if ctx.set_reference:
            if row["metadata_stale"]:
                row["note"] = "reference NOT moved: stored notes are not this run's (D-392)"
            else:
                ctx.catalog.set_reference(
                    symbol, tf, digest, note=f"{T04L_TAG}: {p.kind} from {p.start}"
                )
                row["reference_moved"] = True
    return rows, decs


def _derive(
    symbol: str,
    tf: str,
    base: dict[str, Any],
    base_bars: pl.DataFrame,
    table: pl.DataFrame,
    p: Plan,
    ctx: _Ctx,
) -> tuple[SeriesMetadata, SeriesMetadata, str, int, int, pl.Series] | None:
    """Write the derived snapshot; ``None`` when this timeframe has nothing before the start."""
    assert p.start is not None
    if base_bars.filter(pl.col("ts").dt.date() < p.start).height == 0:
        return None
    note = _note(p, base["snapshot_hash"], ctx.fp)
    folder = ctx.out_dir / tf / safe_component(symbol)
    folder.mkdir(parents=True, exist_ok=True)
    if tf == "1D":
        raw = _raw_1d(table, symbol) or base
        raw_meta = _row_to_meta(raw)
        raw_bars = ctx.store.read_snapshot("alpaca", symbol, "1D", raw["snapshot_hash"])
        forced = SeriesVerdict(
            symbol,
            TRIM,
            boundary_date=p.start.isoformat(),
            dropped_from=str(raw_bars["ts"].min()),
            dropped_to=str(p.start),
            boundary_reason=f"T04l {p.kind}",
        )
        hourly = _hourly_evidence(symbol, ctx.root, ctx.alpaca, ctx.quality, ctx.expected)
        clean, changes = clean_daily(
            raw_bars,
            symbol,
            ctx.quality,
            breaches=hourly.breaches(raw_bars) if hourly is not None else None,
            verdict=forced,
            frozen_sessions=ctx.alpaca.relisting.frozen_min_sessions,
            apply_boundary=True,
            has_hourly=hourly is not None,
        )
        parent_meta, series, log = raw_meta, clean, changes
    else:
        parent_meta = _row_to_meta(base)
        series = base_bars.sort("ts").filter(pl.col("ts").dt.date() >= p.start)
        removed = base_bars.filter(pl.col("ts").dt.date() < p.start)
        span = f"{removed['ts'].min()!s}..{removed['ts'].max()!s}"
        log = pl.DataFrame(
            [
                {
                    "symbol": symbol,
                    "session_date": str(p.start),
                    "arm": f"T04l {p.kind}",
                    "field": "bars",
                    "old": f"{removed.height} bars {span}",
                    "new": "",
                    "evidence": f"history starts {p.start}",
                }
            ]
        )
    intended = parent_meta.model_copy(
        update={
            "snapshot_hash": None,
            "derived_from": parent_meta.key(),
            "notes": (parent_meta.notes + " " + note).strip(),
        }
    )
    stored = ctx.store.write_snapshot(series, intended)
    ctx.catalog.register(stored, note=f"{T04L_TAG}: {p.kind} from {p.start}")
    digest = stored.snapshot_hash or ""
    log.write_csv(folder / f"{digest}.csv")
    (folder / f"{digest}.json").write_text(
        json.dumps(
            {
                "task": "T04l",
                "decisions": list(DECISION_IDS),
                "symbol": symbol,
                "timeframe": tf,
                "derived_from": parent_meta.snapshot_hash,
                "base": base["snapshot_hash"],
                "config_hash": ctx.fp,
                "evidence_files": ctx.files,
                "kind": p.kind,
                "start": str(p.start),
                "base_bars": base_bars.height,
                "bars": series.height,
                "boundaries": [_decision_row(symbol, d) for d in p.decisions],
                "marked": [str(d.boundary.resumes) for d in p.marked],
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    removed_n = base_bars.height - series.height
    return stored, intended, parent_meta.snapshot_hash or "", series.height, removed_n, series["ts"]


def _quality(ctx: _Ctx, meta: SeriesMetadata, tf: str, symbol: str) -> None:
    """The report of a snapshot T04l wrote or marked -- judged on its own bars (T04k §7.4)."""
    breaches = coverage = None
    if tf == "1D":
        hourly = _hourly_evidence(symbol, ctx.root, ctx.alpaca, ctx.quality, ctx.expected)
        if hourly is not None:
            key = meta.key()
            series = ctx.store.read_snapshot(
                key.source, key.symbol, key.timeframe, key.snapshot_hash
            )
            breaches, coverage = hourly.breaches(series), hourly.coverage
    check_snapshot(meta, ctx.store, ctx.catalog, ctx.quality, breaches=breaches, coverage=coverage)
