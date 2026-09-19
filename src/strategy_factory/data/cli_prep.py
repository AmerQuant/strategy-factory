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


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


@data_app.command("quality")
def quality_cmd(
    symbol: Annotated[str | None, typer.Option(help="Only this symbol.")] = None,
    timeframe: Annotated[str | None, typer.Option(help="Only this timeframe.")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Every catalog snapshot.")] = False,
    config: Annotated[Path | None, typer.Option(help="Quality config YAML.")] = None,
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
    print_table(table)
    summary = store.root / QUALITY_DIR / SUMMARY_FILE
    lines = ["# Quality summary", "", "| " + " | ".join(table.columns) + " |"]
    lines.append("|" + "---|" * len(table.columns))
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in table.iter_rows()]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    counts = table.group_by("status").len().sort("status").rows()
    typer.echo(f"{table.height} snapshot(s): " + ", ".join(f"{s} {n}" for s, n in counts))
    typer.echo(f"reports: {(store.root / QUALITY_DIR).as_posix()}")


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
