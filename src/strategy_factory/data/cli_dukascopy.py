"""``sfac data download dukascopy`` and ``sfac data ingest dukascopy``."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated, cast

import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.data.adapters.dukascopy import DukascopyAdapter
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_alpaca import download_app, ingest_app
from strategy_factory.data.config import load_dukascopy_config
from strategy_factory.data.download.dukascopy import (
    Series,
    Tool,
    add_months,
    last_complete_month,
    load_instruments,
    raw_pairs,
    run_dukascopy_download,
)
from strategy_factory.data.download.ratelimit import TLSVerificationError
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.store import SnapshotStore

ConfigOpt = Annotated[Path | None, typer.Option("--config", help="Dukascopy config YAML.")]


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _select(instruments: str | None, universe: Path) -> list:  # type: ignore[type-arg]
    all_ = load_instruments(universe)
    if not instruments:
        return all_
    wanted = {s.strip().lower() for s in instruments.split(",") if s.strip()}
    unknown = wanted - {i.instrument_id for i in all_}
    if unknown:
        raise SfacError(f"instruments not in {universe}: {sorted(unknown)}")
    return [i for i in all_ if i.instrument_id in wanted]


@download_app.command("dukascopy")
def download_dukascopy(
    series: Annotated[
        str, typer.Option(help="h1 (research, from h1_start) or m1 (spread, last N months).")
    ],
    instruments: Annotated[
        str | None, typer.Option(help="Comma-separated instrument ids (default: all).")
    ] = None,
    from_: Annotated[
        str | None, typer.Option("--from", help="First month YYYY-MM (default from config).")
    ] = None,
    to: Annotated[
        str | None, typer.Option("--to", help="Last month YYYY-MM (default: last complete month).")
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """Download Dukascopy bid+ask months with the pinned dukascopy-node CLI."""
    if series not in ("h1", "m1"):
        raise _fail("--series must be h1 or m1")
    try:
        cfg = load_dukascopy_config(config)
        insts = _select(instruments, cfg.universe_file)
        today = dt.datetime.now(dt.UTC).date()
        last = dt.date.fromisoformat(to + "-01") if to else last_complete_month(today)
        if from_:
            first = dt.date.fromisoformat(from_ + "-01")
        elif series == "h1":
            first = cfg.h1_start
        else:
            first = add_months(last_complete_month(today), -(cfg.m1_months - 1))
        report = run_dukascopy_download(
            insts, cast(Series, series), first, last, raw_root(), cfg, Tool.locate(cfg), today
        )
    except TLSVerificationError as exc:
        raise _fail(f"STOP: {exc}. Certificate verification is never disabled.") from exc
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(
        f"dukascopy {series}: stored {report.stored} month files ({report.rows} rows), "
        f"skipped {report.skipped}, empty {len(report.empty)}, failed {len(report.failed)}"
    )
    if report.failed:
        raise typer.Exit(code=2)


@ingest_app.command("dukascopy")
def ingest_dukascopy(
    series: Annotated[
        str, typer.Option(help="Only h1 is ingested now (m1 feeds the spread profile later).")
    ] = "h1",
    instruments: Annotated[
        str | None, typer.Option(help="Comma-separated instrument ids (default: all).")
    ] = None,
    set_reference: Annotated[
        bool, typer.Option("--set-reference", help="Make new snapshots the reference.")
    ] = False,
    rehash: Annotated[
        bool,
        typer.Option(
            "--rehash",
            help="Re-ingest to hash_version 2 and move the reference (event note 'rehash v1→v2').",
        ),
    ] = False,
    config: ConfigOpt = None,
) -> None:
    """Raw bid/ask months -> mid snapshots with spread + catalog."""
    if series != "h1":
        raise _fail("only --series h1 is ingested (m1 is used later by the spread-profile task)")
    try:
        cfg = load_dukascopy_config(config)
        insts = _select(instruments, cfg.universe_file)
        root, store, catalog = raw_root(), SnapshotStore(), Catalog()
        adapter = DukascopyAdapter(cfg)
        failed = 0
        for inst in insts:
            try:
                bid, ask = raw_pairs(root, series, inst.instrument_id)
                df, meta = adapter.to_canonical(
                    bid + ask,
                    series=series,
                    symbol=inst.symbol,
                    instrument=inst.instrument_id,
                    asset_class=inst.asset_class,
                )
                stored = store.write_snapshot(df, meta)
                catalog.register(stored)
                ref = (
                    set_reference
                    or rehash
                    or not catalog.has_reference(inst.symbol, stored.timeframe)
                )
                if ref and stored.snapshot_hash:
                    catalog.set_reference(
                        inst.symbol,
                        stored.timeframe,
                        stored.snapshot_hash,
                        note="rehash v1→v2" if rehash else "dukascopy ingest",
                    )
                flag = " (reference)" if ref else ""
                short = (stored.snapshot_hash or "")[:12]
                typer.echo(f"{inst.symbol:<16} {short} rows={stored.row_count}{flag}")
            except SfacError as exc:
                failed += 1
                typer.echo(f"{inst.symbol}: FAILED {exc}", err=True)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    if failed:
        raise typer.Exit(code=2)
