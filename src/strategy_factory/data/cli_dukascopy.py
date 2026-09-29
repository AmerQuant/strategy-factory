"""``sfac data download dukascopy`` and ``sfac data ingest dukascopy``."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated, cast

import polars as pl
import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.data.adapters.dukascopy import DukascopyAdapter
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_alpaca import coverage_app, download_app, ingest_app
from strategy_factory.data.config import DukascopyConfig, load_dukascopy_config
from strategy_factory.data.coverage import (
    describe_month_gaps,
    dukascopy_coverage_frame,
    dukascopy_gaps,
)
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
        root = raw_root()
        # T04j (D-386 copied, P-62; per instrument since D-657): an instrument with a gap is never
        # ingested -- it waits, and nothing is written for it; there is no --allow-gaps. A complete
        # instrument is ingested without waiting for the others.
        gaps = dukascopy_gaps(_coverage(root, series, insts, cfg))
        ready = [i for i in insts if i.symbol not in gaps]
        if not ready:
            raise _fail(
                f"{series} raw coverage has gaps, nothing ingested (no --allow-gaps): "
                f"{describe_month_gaps(gaps)}. See `sfac data coverage dukascopy`."
            )
        store, catalog = SnapshotStore(), Catalog()
        adapter = DukascopyAdapter(cfg)
        failed = 0
        for inst in ready:
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
    if gaps:
        typer.echo(
            f"waiting (not ingested, D-657): {describe_month_gaps(gaps)}. "
            "See `sfac data coverage dukascopy`."
        )
    if failed:
        raise typer.Exit(code=2)


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


COVERAGE_REPORT = "dukascopy_coverage_{series}.csv"


def _coverage(root: Path, series: str, insts: list, cfg: DukascopyConfig) -> pl.DataFrame:  # type: ignore[type-arg]
    return dukascopy_coverage_frame(root, series, insts, cfg.h1_start, _today())


@coverage_app.command("dukascopy")
def coverage_dukascopy(
    series: Annotated[str, typer.Option(help="Only h1 is gated now.")] = "h1",
    instruments: Annotated[
        str | None, typer.Option(help="Comma-separated instrument ids (default: all).")
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """Months present per instrument and side -> SFAC_RAW_ROOT/_reports/; exit 1 on a gap."""
    if series != "h1":
        raise _fail("only --series h1 is gated (T04j)")
    try:
        cfg = load_dukascopy_config(config)
        insts = _select(instruments, cfg.universe_file)
        root = raw_root()
        frame = _coverage(root, series, insts, cfg)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    out = root / "_reports" / COVERAGE_REPORT.format(series=series)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(out)
    per = (
        frame.filter(pl.col("required"))
        .group_by("symbol", maintain_order=True)
        .agg(
            pl.len().alias("required"),
            (~pl.col("bid")).sum().alias("no_bid"),
            (~pl.col("ask")).sum().alias("no_ask"),
            pl.col("missing").sum().alias("missing"),
        )
    )
    typer.echo(f"{len(insts)} instrument(s), {series}; report: {out}")
    typer.echo(f"  {'symbol':<16}{'required':>9}{'no bid':>8}{'no ask':>8}{'missing':>9}")
    for sym, req, nb, na, miss in per.rows():
        mark = "" if miss == 0 else "  <- gap"
        typer.echo(f"  {sym:<16}{req:>9}{nb:>8}{na:>8}{miss:>9}{mark}")
    gaps = dukascopy_gaps(frame)
    complete = len(insts) - len(gaps)
    typer.echo(f"complete: {complete} of {len(insts)} instrument(s)")
    if gaps:
        typer.echo(f"GAPS: {describe_month_gaps(gaps)}")
        raise typer.Exit(code=1)
    typer.echo("coverage gate: passed (every required month on both sides)")
