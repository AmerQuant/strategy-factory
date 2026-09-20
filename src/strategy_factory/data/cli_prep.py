"""``sfac data quality`` (F-0.1.6) and ``sfac data resample`` (F-0.1.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import polars as pl
import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.data.catalog import Catalog, _row_to_meta
from strategy_factory.data.cli import data_app, print_table
from strategy_factory.data.config import (
    load_quality_config,
    load_resample_config,
)
from strategy_factory.data.quality import QUALITY_DIR, check_snapshot
from strategy_factory.data.resample import flags_file, resample
from strategy_factory.data.schedule import ResampleMode
from strategy_factory.data.store import SnapshotStore

SUMMARY_FILE = "summary.md"
#: D-391: one summary per ``(source, timeframe)`` -- the Alpaca 1D group alone is ~6.7 k rows and
#: must not share a file with the 1H group, let alone with Dukascopy.
GROUP_SUMMARY = "summary_{source}_{timeframe}.md"
#: Rows printed to the console before the table is replaced by its per-group counts.
DEFAULT_MAX_ROWS = 50


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


@data_app.command("quality")
def quality_cmd(
    symbol: Annotated[str | None, typer.Option(help="Only this symbol.")] = None,
    timeframe: Annotated[str | None, typer.Option(help="Only this timeframe.")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Every catalog snapshot.")] = False,
    config: Annotated[Path | None, typer.Option(help="Quality config YAML.")] = None,
    max_rows: Annotated[
        int, typer.Option(help="Print at most this many rows; the files hold all of them.")
    ] = DEFAULT_MAX_ROWS,
) -> None:
    """Run the quality checks, write _quality/<hash>.json|.md, record quality_status."""
    if not all_ and symbol is None:
        raise _fail("give --symbol (optionally --timeframe) or --all")
    try:
        cfg = load_quality_config(config)
        store = SnapshotStore()
        catalog = Catalog(store.root)
        rows = catalog.list_snapshots(symbol=symbol, timeframe=timeframe)
        if rows.height == 0:
            typer.echo("no matching snapshots in the catalog")
            return
        out = []
        for row in rows.iter_rows(named=True):
            rep = check_snapshot(_row_to_meta(row), store, catalog, cfg)
            miss = rep.check("missing_bars")
            out.append(
                {
                    "symbol": rep.snapshot.symbol,
                    "timeframe": rep.snapshot.timeframe,
                    "source": rep.snapshot.source,
                    "snapshot": rep.snapshot.snapshot_hash[:12],
                    "status": rep.status,
                    "missing_pct": miss.details.get("pct", 0.0) if miss.status == "fail" else 0.0,
                    "break_local": rep.schedule.get("break_hour_local"),
                    "break_utc": rep.schedule.get("modal_break_hour_utc"),
                    "failed": ", ".join(f"{c.code}:{c.severity}" for c in rep.failed()),
                }
            )
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    table = pl.DataFrame(out)
    print_table(table.head(max_rows) if table.height > max_rows else table)
    if table.height > max_rows:
        typer.echo(f"... {table.height - max_rows} more row(s); the summaries below hold all.")
    written = _write_group_summaries(store.root / QUALITY_DIR, table)
    _write_index(store.root / QUALITY_DIR, catalog)
    counts = table.group_by("status").len().sort("status").rows()
    typer.echo(f"{table.height} snapshot(s): " + ", ".join(f"{s} {n}" for s, n in counts))
    for path in written:
        typer.echo(f"  {path.name}")
    typer.echo(f"reports: {(store.root / QUALITY_DIR).as_posix()}")


def _markdown_table(columns: list[str], rows: list[tuple[object, ...]]) -> list[str]:
    head = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    return head + ["| " + " | ".join(str(v) for v in r) + " |" for r in rows]


def _write_group_summaries(quality_dir: Path, table: pl.DataFrame) -> list[Path]:
    """One file per ``(source, timeframe)`` present in this run (D-391); others are untouched."""
    written: list[Path] = []
    for (source, timeframe), group in sorted(
        table.group_by(["source", "timeframe"]), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        path = quality_dir / GROUP_SUMMARY.format(source=source, timeframe=timeframe)
        lines = [f"# Quality summary -- {source} {timeframe}", ""]
        lines += _markdown_table(group.columns, list(group.iter_rows()))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(path)
    return written


def _write_index(quality_dir: Path, catalog: Catalog) -> None:
    """``summary.md``: every group in the catalog with its snapshot and status counts (D-391).

    Built from the catalog, not from this run, so the groups a partial run did not touch stay in
    the index with their recorded status.
    """
    rows = catalog.table()
    statuses = sorted(set(rows["quality_status"].to_list())) if rows.height else []
    lines = [
        "# Quality summary index",
        "",
        "One report per `(source, timeframe)` (D-391); counts come from the catalog.",
        "",
    ]
    table_rows: list[tuple[object, ...]] = []
    for (source, timeframe), group in sorted(
        rows.group_by(["source", "timeframe"]), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        per = dict(group.group_by("quality_status").len().rows())
        name = GROUP_SUMMARY.format(source=source, timeframe=timeframe)
        table_rows.append(
            (
                source,
                timeframe,
                group.height,
                *(per.get(s, 0) for s in statuses),
                f"[{name}]({name})",
            )
        )
    lines += _markdown_table(["source", "timeframe", "snapshots", *statuses, "report"], table_rows)
    (quality_dir / SUMMARY_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


@data_app.command("resample")
def resample_cmd(
    symbol: Annotated[str, typer.Option(help="Canonical symbol (reference snapshot).")],
    from_tf: Annotated[str, typer.Option("--from", help="Source timeframe, e.g. 1H.")],
    to_tf: Annotated[str, typer.Option("--to", help="Target timeframe: 1D or 4H.")],
    mode: Annotated[
        str, typer.Option(help="research (default) or broker_session (parity only).")
    ] = "research",
    set_reference: Annotated[
        bool, typer.Option(help="Make the result the reference (research mode only).")
    ] = False,
    config: Annotated[Path | None, typer.Option(help="Resample config YAML.")] = None,
) -> None:
    """Resample the reference snapshot of SYMBOL to a higher timeframe (new snapshot)."""
    if mode not in ("research", "broker_session"):
        raise _fail("--mode must be research or broker_session")
    if mode == "broker_session" and set_reference:
        raise _fail("broker_session snapshots are for parity tests and never the reference")
    try:
        store = SnapshotStore()
        catalog = Catalog(store.root)
        parent = catalog.get_reference(symbol, from_tf)
        stored, res = resample(
            parent,
            to_tf,
            cast(ResampleMode, mode),
            store=store,
            catalog=catalog,
            cfg=load_resample_config(config),
            qcfg=load_quality_config(),
        )
        assert stored.snapshot_hash is not None
        made_ref = mode == "research" and (
            set_reference or not catalog.has_reference(symbol, to_tf)
        )
        if made_ref:
            catalog.set_reference(symbol, to_tf, stored.snapshot_hash, note=f"resample {mode}")
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(
        f"{symbol} {from_tf}->{to_tf} ({mode}): {stored.row_count} bars, snapshot "
        f"{stored.snapshot_hash[:12]}{' (reference)' if made_ref else ''}"
    )
    if res.dropped:
        typer.echo("partial periods dropped: " + ", ".join(res.dropped))
    typer.echo(
        f"flagged bars: {res.flags.height} "
        f"({flags_file(store.root, stored.snapshot_hash).as_posix()})"
    )
