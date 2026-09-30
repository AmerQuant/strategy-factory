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
from strategy_factory.data.config import (
    DukascopyConfig,
    QualityConfig,
    SplitConfig,
    load_dukascopy_config,
    load_quality_config,
    load_resample_config,
    load_split_config,
)
from strategy_factory.data.coverage import (
    Window,
    describe_month_gaps,
    dukascopy_coverage_frame,
    dukascopy_gaps,
    dukascopy_windows,
)
from strategy_factory.data.download.dukascopy import (
    Instrument,
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
from strategy_factory.data.resample import resample_bars
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split import HistoryTooShortError, compute_split
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
    expect_window: Annotated[
        list[str] | None,
        typer.Option(
            "--expect-window",
            help="SYMBOL=FIRST..LAST (YYYY-MM): the window a caller measured (D-717); an "
            "instrument whose window has moved since is refused and nothing is written for it.",
        ),
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """Raw bid/ask months -> mid snapshots with spread + catalog, over each instrument's complete
    window (D-661). The D-717 re-measure is the resume command's (scripts/pilots/T04j_resume.py),
    which passes the windows it measured with --expect-window."""
    if series != "h1":
        raise _fail("only --series h1 is ingested (m1 is used later by the spread-profile task)")
    try:
        cfg = load_dukascopy_config(config)
        insts = _select(instruments, cfg.universe_file)
        root = raw_root()
        # T04j (D-386 copied; per instrument, D-657; the window, D-661): an instrument is ingested
        # over its longest contiguous complete window ending at the last complete month -- never
        # across a gap, never with a month still being written (``is_settled``). No window, or a
        # window too short for D-008: it waits and nothing is written for it. No --allow-gaps.
        windows = dukascopy_windows(_coverage(root, series, insts, cfg))
        expected = _parse_expected(expect_window or [])
        adapter = DukascopyAdapter(cfg)
        split_cfg, quality = load_split_config(), load_quality_config()
        waiting: dict[str, str] = {}
        failed = 0
        ready: list[tuple[Instrument, Window, pl.DataFrame, SeriesMetadata]] = []
        for inst in insts:
            w = windows.get(inst.symbol)
            if w is None or w.first is None:
                gap = w.bounding_gap if w else "no required month"
                waiting[inst.symbol] = f"no complete window ({gap} missing)"
                continue
            if inst.symbol in expected and expected[inst.symbol] != (w.first, w.last):
                failed += 1
                first, last = expected[inst.symbol]
                typer.echo(
                    f"{inst.symbol}: REFUSED the window moved since it was measured "
                    f"({first}..{last} -> {w.first}..{w.last}); nothing written, re-run the "
                    "resume command",
                    err=True,
                )
                continue
            try:
                bid, ask = raw_pairs(root, series, inst.instrument_id)
                paths = [p for p in bid + ask if w.first <= p.name[:7] <= w.last]
                df, meta = adapter.to_canonical(
                    paths,
                    series=series,
                    symbol=inst.symbol,
                    instrument=inst.instrument_id,
                    asset_class=inst.asset_class,
                )
            except SfacError as exc:
                failed += 1
                typer.echo(f"{inst.symbol}: FAILED {exc}", err=True)
                continue
            short = d008_short(df, meta, split_cfg, quality)
            if short:
                waiting[inst.symbol] = (
                    f"window {w.first}..{w.last} ({w.years} y) shorter than D-008 on {short}"
                )
                continue
            if not w.complete:
                note = (
                    f"D-661 window {w.first}..{w.last}: {w.missing_before} month(s) missing "
                    f"before it, the latest {w.bounding_gap}"
                )
                meta = meta.model_copy(update={"notes": f"{meta.notes}; {note}".lstrip("; ")})
            ready.append((inst, w, df, meta))
        if not ready and not failed:
            raise _fail(
                "nothing ingested (no --allow-gaps): "
                + "; ".join(f"{s} {why}" for s, why in waiting.items())
                + ". See `sfac data coverage dukascopy`."
            )
        store, catalog = SnapshotStore(), Catalog()
        for inst, w, df, meta in ready:
            try:
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
                        note="rehash v1→v2" if rehash else f"dukascopy ingest {w.first}..{w.last}",
                    )
                flag = " (reference)" if ref else ""
                short_hash = (stored.snapshot_hash or "")[:12]
                typer.echo(
                    f"{inst.symbol:<16} {short_hash} rows={stored.row_count} "
                    f"window={w.first}..{w.last}{'' if w.complete else ' (D-661)'}{flag}"
                )
            except SfacError as exc:
                failed += 1
                typer.echo(f"{inst.symbol}: FAILED {exc}", err=True)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    if waiting:
        typer.echo(
            f"waiting (not ingested, D-661): {len(waiting)} instrument(s): "
            + "; ".join(f"{s} {why}" for s, why in waiting.items())
        )
    if failed:
        raise typer.Exit(code=2)


def _parse_expected(values: list[str]) -> dict[str, tuple[str, str]]:
    """``SYMBOL=FIRST..LAST`` -> ``{SYMBOL: (FIRST, LAST)}``."""
    out: dict[str, tuple[str, str]] = {}
    for value in values:
        symbol, sep, span = value.partition("=")
        first, dots, last = span.partition("..")
        if not (sep and dots and first and last):
            raise SfacError(f"--expect-window must be SYMBOL=YYYY-MM..YYYY-MM, got {value!r}")
        out[symbol.strip().upper()] = (first.strip(), last.strip())
    return out


def d008_short(
    bars: pl.DataFrame, meta: SeriesMetadata, split_cfg: SplitConfig, quality: QualityConfig
) -> str | None:
    """``None`` when the 1H bars and their D-032 daily series (research mode, in memory) both
    admit a D-008 split; else the timeframe(s) that do not (D-661: such a window waits)."""
    key = meta.model_copy(update={"snapshot_hash": "0" * 64}).key()
    daily = resample_bars(bars.sort("ts"), meta, "1D", "research", load_resample_config(), quality)
    short = []
    for tf, ts in (("1H", bars.sort("ts")["ts"]), ("1D", daily.bars["ts"])):
        try:
            compute_split(ts, key, split_cfg)
        except HistoryTooShortError:
            short.append(tf)
    return ", ".join(short) or None


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


COVERAGE_REPORT = "dukascopy_coverage_{series}.csv"


def _coverage(
    root: Path, series: str, insts: list[Instrument], cfg: DukascopyConfig
) -> pl.DataFrame:
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
