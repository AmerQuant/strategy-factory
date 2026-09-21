"""``sfac data reuse`` -- T04l: re-used tickers decided by CUSIP, in 1D and 1H (D-705 ... D-713).

For every symbol with a 1D or 1H reference, the **base** snapshot is that reference -- or, when it
is already a T04l snapshot, the snapshot it was derived from, so a re-run never derives from its
own output. Candidate boundaries: the ones T04k kept (``_clean/clean_daily_summary.csv``) and
every gap of ``relisting.gap_days`` or more in the base series, 1D and 1H alike (D-708). Each is
decided by :mod:`cusip_evidence` and :mod:`reuse`; the plan applies to **both** timeframes (D-707).

A symbol whose plan cuts its history gets, per timeframe, a **derived** snapshot starting at the
plan's start (``derived_from`` the base; the boundaries, their decisions and evidence in its notes,
its log and its provenance JSON), which becomes the reference with ``--set-reference`` (D-713). The
base stays in the store; an unsettled boundary marks the base ``full_history`` and the derived
snapshot ``research_window`` (D-709). An unadjusted split takes the D-397 path: nothing is derived,
the symbol is listed with its ``--refresh`` command.

Outputs under ``<SFAC_DATA_ROOT>/_reuse/``: ``T04l_reuse_summary.csv`` (one row per symbol and
timeframe acted on), ``T04l_decisions.csv`` (one row per boundary), and per derived snapshot
``<tf>/<symbol>/<hash>.csv`` (the log: what was cut and why) and ``.json`` (provenance).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

import polars as pl
import typer

from strategy_factory.core.config import config_hash
from strategy_factory.core.errors import SfacError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.catalog import Catalog, Splice, _row_to_meta
from strategy_factory.data.cli import data_app
from strategy_factory.data.cli_clean import (
    CLEAN_DIR,
    SUMMARY_FILE,
    _hourly_evidence,
)
from strategy_factory.data.config import (
    AlpacaConfig,
    load_alpaca_config,
    load_quality_config,
    load_split_config,
)
from strategy_factory.data.crosscheck import UNSETTLED as X_UNSETTLED
from strategy_factory.data.crosscheck import CrosscheckVerdict, settle_boundary
from strategy_factory.data.cusip_evidence import (
    BOTH,
    DIFFERENT_ISSUER,
    Event,
    classify,
    load_events,
)
from strategy_factory.data.daily_session import expected_bars
from strategy_factory.data.download.alpaca_reference import latest_action_files, load_sessions
from strategy_factory.data.download.rawfiles import MANIFEST_SUFFIX, raw_root
from strategy_factory.data.ingest import crosscheck_file
from strategy_factory.data.quality import check_snapshot
from strategy_factory.data.reuse import (
    SPLIT,
    UNSETTLED,
    Boundary,
    Decision,
    Plan,
    decide,
    long_gaps,
    plan,
    splice_reason,
)
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split import HistoryTooShortError, compute_split
from strategy_factory.data.split_check import read_crosscheck_csv
from strategy_factory.data.store import SnapshotStore, safe_component

log = get_logger(__name__)

REUSE_DIR = "_reuse"
SUMMARY = "T04l_reuse_summary.csv"
DECISIONS = "T04l_decisions.csv"
#: The notes of every T04l snapshot start their T04l part with this; ``_base`` follows it back.
T04L_TAG = "T04l re-use"
DECISION_IDS = ("D-705", "D-708", "D-709", "D-712", "D-713")
TIMEFRAMES = ("1D", "1H")
KEY_FIELDS = ("source", "symbol", "timeframe", "snapshot_hash")


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _base(row: dict[str, Any], table: pl.DataFrame) -> dict[str, Any]:
    """The snapshot T04l derives from: the reference, unless it is itself a T04l snapshot."""
    seen = 0
    while T04L_TAG in (row["notes"] or "") and row["derived_from"] and seen < 5:
        # the full key: identical bars under two symbols share a content hash
        parent = json.loads(row["derived_from"])
        rows = table.filter(pl.all_horizontal([pl.col(k) == parent[k] for k in KEY_FIELDS]))
        if rows.height == 0:
            break
        row = rows.row(0, named=True)
        seen += 1
    return row


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


def _split_check(
    symbol: str, daily: pl.DataFrame, resumes: dt.date, root: Path, alpaca: AlpacaConfig
) -> CrosscheckVerdict:
    """D-709 change 1: the known-split cross-check that settled AVGO, at this boundary."""
    frame = daily.with_columns(pl.col("ts").dt.date().alias("d")).sort("d")
    before = frame.filter(
        (pl.col("d") < resumes)
        & ~((pl.col("high") == pl.col("low")) & (pl.col("low") == pl.col("close")))
    )
    after = frame.filter(pl.col("d") >= resumes)
    if before.height == 0 or after.height == 0:
        return CrosscheckVerdict(symbol, X_UNSETTLED, "no real bar on one side of the boundary")
    c0, c1 = before["close"][-1], after["close"][0]
    if c0 <= 0:
        return CrosscheckVerdict(symbol, X_UNSETTLED, "the close before the break is not positive")
    path = crosscheck_file(root, symbol)
    cross = read_crosscheck_csv(path) if path.is_file() else None
    return settle_boundary(
        symbol,
        before["d"][-1],
        after["d"][0],
        c1 / c0,
        cross,
        alpaca.split_check.match_tolerance,
        alpaca.split_check.jump_threshold,
        alpaca.split_check.crosscheck_window_days,
    )


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


def _splices(p: Plan, role: str) -> tuple[Splice, ...]:
    return tuple(
        Splice.model_validate(
            {
                "boundary": d.boundary.resumes,
                "role": role,
                "reason": d.reason,
                "evidence": f"{d.boundary.source}: {d.evidence.describe()}",
            }
        )
        for d in p.unsettled
    )


def _note(p: Plan, base_hash: str, fp: str) -> str:
    parts = "; ".join(
        f"{d.boundary.resumes} {d.action}" + (f" ({d.reason})" if d.action == UNSETTLED else "")
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


@data_app.command("reuse")
def reuse_cmd(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated subset.")] = None,
    set_reference: Annotated[
        bool, typer.Option("--set-reference", help="Make the derived snapshots the references.")
    ] = False,
) -> None:
    """T04l: decide re-used tickers by CUSIP; derive 1D/1H snapshots from the boundary (D-713)."""
    try:
        store, catalog = SnapshotStore(), Catalog()
        alpaca, quality = load_alpaca_config(), load_quality_config()
        split_cfg = load_split_config()
        root = raw_root()
        evidence_dir = root / alpaca.reuse.corporate_actions_dir
        events, _ = load_events(evidence_dir)
        files = _evidence_files(evidence_dir)
        fp = config_hash(
            {
                "relisting": alpaca.relisting.model_dump(mode="json"),
                "split_check": alpaca.split_check.model_dump(mode="json"),
                "reuse": alpaca.reuse.model_dump(mode="json"),
                "evidence": files,
            }
        )
        expected = expected_bars(
            load_sessions(alpaca.hourly_session.sessions_file), alpaca.hourly_session.first_bar
        )
        kept = _t04k_candidates(store.root / CLEAN_DIR)
        table = catalog.table()
    except SfacError as exc:
        raise _fail(str(exc)) from exc

    refs = table.filter(
        (pl.col("source") == "alpaca")
        & pl.col("timeframe").is_in(list(TIMEFRAMES))
        & pl.col("is_reference")
    )
    wanted = {s.strip() for s in symbols.split(",")} if symbols else None
    names = sorted(set(refs["symbol"].to_list()) & (wanted or set(refs["symbol"].to_list())))
    out_dir = store.root / REUSE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    window = alpaca.relisting.rename_window_days
    summary: list[dict[str, Any]] = []
    decisions_out: list[dict[str, Any]] = []
    for i, symbol in enumerate(names, 1):
        if i % 500 == 0:
            typer.echo(f"  {i}/{len(names)} symbols")
        try:
            done = _reuse_symbol(
                symbol,
                refs.filter(pl.col("symbol") == symbol),
                table,
                kept.get(symbol, []),
                events.get(symbol, []),
                store,
                catalog,
                alpaca,
                quality,
                split_cfg,
                root,
                expected,
                window,
                fp,
                files,
                out_dir,
                set_reference,
            )
        except SfacError as exc:
            log.error("%s: T04l failed: %s", symbol, exc)
            summary.append({"symbol": symbol, "timeframe": "", "kind": "failed", "note": str(exc)})
            continue
        if done is None:
            continue
        rows, decs = done
        summary += rows
        decisions_out += decs

    pl.DataFrame(summary, infer_schema_length=None).write_csv(out_dir / SUMMARY)
    pl.DataFrame(decisions_out, infer_schema_length=None).write_csv(out_dir / DECISIONS)
    table_out = pl.DataFrame(summary, infer_schema_length=None)
    counts = (
        {f"{tf} {kind}": n for tf, kind, n in table_out.group_by("timeframe", "kind").len().rows()}
        if table_out.height
        else {}
    )
    typer.echo(f"{len(names)} symbol(s) read; acted on: {counts}")
    typer.echo(f"decisions: {len(decisions_out)} boundary(ies); outputs: {out_dir.as_posix()}")


def _reuse_symbol(
    symbol: str,
    refs: pl.DataFrame,
    table: pl.DataFrame,
    kept: list[Boundary],
    events: list[Event],
    store: SnapshotStore,
    catalog: Catalog,
    alpaca: AlpacaConfig,
    quality: Any,
    split_cfg: Any,
    root: Path,
    expected: pl.DataFrame,
    window: int,
    fp: str,
    files: dict[str, str],
    out_dir: Path,
    set_reference: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    bases: dict[str, dict[str, Any]] = {}
    bars: dict[str, pl.DataFrame] = {}
    for tf in TIMEFRAMES:
        r = refs.filter(pl.col("timeframe") == tf)
        if r.height:
            base = _base(r.row(0, named=True), table)
            bases[tf] = base
            bars[tf] = store.read_snapshot("alpaca", symbol, tf, base["snapshot_hash"])
    boundaries = list(kept)
    gap_days = alpaca.relisting.gap_days
    daily_gaps = long_gaps(bars["1D"]["ts"], gap_days) if "1D" in bars else []
    boundaries += [Boundary(r, "long gap 1D", None, g) for r, g in daily_gaps]
    for r_h, g_h in long_gaps(bars["1H"]["ts"], gap_days) if "1H" in bars else []:
        boundaries.append(
            Boundary(_same_break(r_h, g_h, daily_gaps, kept), "long gap 1H", None, g_h)
        )
    if not boundaries:
        return None
    # one boundary per date: a break seen in 1D and in 1H (or also kept by T04k) is one break
    unique: dict[dt.date, Boundary] = {}
    for b in boundaries:
        seen = unique.get(b.resumes)
        if seen is None:
            unique[b.resumes] = b
            continue
        unique[b.resumes] = Boundary(
            b.resumes,
            "+".join(sorted(set(seen.source.split("+")) | {b.source})),
            seen.name_verdict or b.name_verdict,
            seen.gap_days or b.gap_days,
        )
    decisions: list[Decision] = []
    for b in sorted(unique.values(), key=lambda b: b.resumes):
        ev = classify(events, b.resumes, window)
        split_verdict, split_evidence = None, ""
        if ev.coverage == BOTH and ev.relation != DIFFERENT_ISSUER:
            daily = bars.get("1D", bars.get("1H"))
            assert daily is not None
            xc = _split_check(symbol, daily, b.resumes, root, alpaca)
            split_verdict, split_evidence = xc.verdict, xc.evidence
        action = decide(b, ev, split_verdict)
        reason = splice_reason(b, ev) if action == UNSETTLED else ""
        decisions.append(Decision(b, action, reason, ev, split_verdict, split_evidence))
    p = plan(decisions)
    decs = [_decision_row(symbol, d) for d in p.decisions]
    rows: list[dict[str, Any]] = []
    if p.kind == "none":
        return rows, decs
    for tf, base in bases.items():
        row: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": tf,
            "kind": p.kind,
            "start": p.start.isoformat() if p.start else "",
            "base_hash": base["snapshot_hash"],
            "base_bars": bars[tf].height,
            "new_hash": "",
            "new_bars": 0,
            "removed_bars": 0,
            "unsettled": "|".join(str(d.boundary.resumes) for d in p.unsettled),
            "split_ok": "",
            "metadata_stale": False,
            "reference_moved": False,
            "note": "",
        }
        rows.append(row)
        if p.kind == SPLIT:
            row["note"] = (
                f"D-397: run `uv run sfac data download alpaca --timeframe {tf} --symbols "
                f"{symbol} --start {alpaca.history_start} --refresh`, then re-check"
            )
            continue
        assert p.start is not None
        df = bars[tf].sort("ts")
        cut = df.filter(pl.col("ts").dt.date() >= p.start)
        if cut.height == df.height:
            row["note"] = "no bar before the start in this timeframe: nothing to cut"
            continue
        if cut.height == 0:
            row["note"] = "no bar from the start on in this timeframe"
            continue
        base_meta = _row_to_meta(base)
        intended = base_meta.model_copy(
            update={
                "snapshot_hash": None,
                "derived_from": base_meta.key(),
                "notes": (base_meta.notes + " " + _note(p, base["snapshot_hash"], fp)).strip(),
            }
        )
        stored = store.write_snapshot(cut, intended)
        row["metadata_stale"] = stored.notes != intended.notes
        catalog.register(stored, note=f"{T04L_TAG}: {p.kind} from {p.start}")
        digest = stored.snapshot_hash or ""
        row.update(new_hash=digest, new_bars=cut.height, removed_bars=df.height - cut.height)
        _write_log(out_dir, tf, symbol, digest, df, cut, p, base, fp, files)
        if p.unsettled:
            catalog.mark_splices(
                base_meta.key(), _splices(p, "full_history"), note=f"{T04L_TAG}: D-709"
            )
            catalog.mark_splices(
                stored.key(), _splices(p, "research_window"), note=f"{T04L_TAG}: D-713"
            )
            _quality(store, catalog, quality, alpaca, root, expected, base_meta, tf, symbol)
        _quality(store, catalog, quality, alpaca, root, expected, stored, tf, symbol)
        if tf == "1D":
            try:
                compute_split(cut["ts"], stored.key(), split_cfg)
                row["split_ok"] = True
            except HistoryTooShortError:
                row["split_ok"] = False
        if set_reference:
            catalog.set_reference(symbol, tf, digest, note=f"{T04L_TAG}: {p.kind} from {p.start}")
            row["reference_moved"] = True
    return rows, decs


def _quality(
    store: SnapshotStore,
    catalog: Catalog,
    quality: Any,
    alpaca: AlpacaConfig,
    root: Path,
    expected: pl.DataFrame,
    meta: SeriesMetadata,
    tf: str,
    symbol: str,
) -> None:
    """The report of a snapshot T04l wrote or marked -- judged on its own bars (T04k §7.4)."""
    breaches = coverage = None
    if tf == "1D":
        hourly = _hourly_evidence(symbol, root, alpaca, quality, expected)
        if hourly is not None:
            key = meta.key()
            series = store.read_snapshot(key.source, key.symbol, key.timeframe, key.snapshot_hash)
            breaches, coverage = hourly.breaches(series), hourly.coverage
    check_snapshot(meta, store, catalog, quality, breaches=breaches, coverage=coverage)


def _write_log(
    out_dir: Path,
    tf: str,
    symbol: str,
    digest: str,
    df: pl.DataFrame,
    cut: pl.DataFrame,
    p: Plan,
    base: dict[str, Any],
    fp: str,
    files: dict[str, str],
) -> None:
    """The log (what was cut, and why) and the provenance of one derived snapshot. Replaying it
    -- the base's bars from ``start`` on -- reproduces the snapshot."""
    folder = out_dir / tf / safe_component(symbol)
    folder.mkdir(parents=True, exist_ok=True)
    removed = df.filter(pl.col("ts").dt.date() < p.start)
    pl.DataFrame(
        [
            {
                "symbol": symbol,
                "timeframe": tf,
                "arm": p.kind,
                "start": str(p.start),
                "removed_from": str(removed["ts"].min()),
                "removed_to": str(removed["ts"].max()),
                "removed_bars": removed.height,
                "evidence": "; ".join(
                    f"{d.boundary.resumes} {d.action}: {d.evidence.describe()}" for d in p.decisions
                ),
            }
        ]
    ).write_csv(folder / f"{digest}.csv")
    (folder / f"{digest}.json").write_text(
        json.dumps(
            {
                "task": "T04l",
                "decisions": list(DECISION_IDS),
                "symbol": symbol,
                "timeframe": tf,
                "derived_from": base["snapshot_hash"],
                "config_hash": fp,
                "evidence_files": files,
                "kind": p.kind,
                "start": str(p.start),
                "base_bars": df.height,
                "bars": cut.height,
                "boundaries": [
                    {
                        "resumes": str(d.boundary.resumes),
                        "source": d.boundary.source,
                        "action": d.action,
                        "reason": d.reason,
                        "evidence": d.evidence.describe(),
                        "split_verdict": d.split_verdict,
                    }
                    for d in p.decisions
                ],
                "unsettled": [str(d.boundary.resumes) for d in p.unsettled],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
