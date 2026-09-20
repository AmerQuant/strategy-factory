"""``sfac data download alpaca``, ``sfac data ingest alpaca``, ``sfac data universe us-equity``."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Annotated

import typer

from strategy_factory.core.errors import ConfigError, SfacError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_alpaca_config
from strategy_factory.data.download.alpaca import load_credentials, make_client, run_download
from strategy_factory.data.download.alpaca_reference import (
    build_sessions_csv,
    build_symbol_changes,
    fetch_calendar,
    fetch_name_changes,
)
from strategy_factory.data.download.ratelimit import PermanentError, TLSVerificationError
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.ingest import IngestResult, ingest_alpaca_symbol, raw_symbols
from strategy_factory.data.store import SnapshotStore
from strategy_factory.data.universe import (
    build_daily_universe,
    build_hourly_universe,
    fetch_pit_csv,
    load_changes,
    pit_members,
    pit_symbols_of,
)

download_app = typer.Typer(help="Download raw data into SFAC_RAW_ROOT.", no_args_is_help=True)
ingest_app = typer.Typer(help="Build canonical snapshots from raw files.", no_args_is_help=True)
reference_app = typer.Typer(
    help="Reference data (calendar, symbol changes) into SFAC_RAW_ROOT + configs.",
    no_args_is_help=True,
)
universe_app = typer.Typer(
    help="Build universe files under configs/universe/.", no_args_is_help=True
)

ConfigOpt = Annotated[Path | None, typer.Option("--config", help="Alpaca config YAML.")]


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _symbols_from(universe: Path | None, symbols: str | None) -> list[str]:
    if symbols:
        return [s.strip() for s in symbols.split(",") if s.strip()]
    if universe is None:
        raise ConfigError("give --universe <csv> or --symbols A,B,...")
    with universe.open(encoding="utf-8", newline="") as fh:
        return [r["symbol"] for r in csv.DictReader(fh)]


@download_app.command("alpaca")
def download_alpaca(
    timeframe: Annotated[str, typer.Option(help="1D or 1H.")],
    universe: Annotated[
        Path | None, typer.Option(help="Universe CSV with a 'symbol' column.")
    ] = None,
    symbols: Annotated[
        str | None, typer.Option(help="Comma-separated symbols (overrides --universe).")
    ] = None,
    start: Annotated[
        str | None, typer.Option(help="YYYY-MM-DD (default: config history_start).")
    ] = None,
    end: Annotated[
        str | None, typer.Option(help="YYYY-MM-DD inclusive (default: yesterday UTC).")
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """Download Alpaca SIP split-adjusted bars (resumable, immutable raw files)."""
    try:
        cfg = load_alpaca_config(config)
        syms = _symbols_from(universe, symbols)
        d0 = dt.date.fromisoformat(start) if start else cfg.history_start
        d1 = (
            dt.date.fromisoformat(end)
            if end
            else dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1)
        )
        report = run_download(make_client(cfg), syms, timeframe, d0, d1, raw_root(), cfg)
    except TLSVerificationError as exc:
        raise _fail(
            f"STOP: {exc}. Certificate verification is never disabled; see the review notes."
        ) from exc
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(
        f"alpaca {timeframe}: {report.requested_symbols} symbols; "
        f"chunks written {report.chunks_written}, skipped (complete) {report.chunks_skipped}; "
        f"rows {report.rows_written}; failed batches {len(report.failed_batches)}; "
        f"missing symbols {len(report.missing_symbols)}"
    )
    if report.failed_batches:
        raise typer.Exit(code=2)


@ingest_app.command("alpaca")
def ingest_alpaca(
    timeframe: Annotated[str, typer.Option(help="1D or 1H.")],
    symbols: Annotated[
        str | None, typer.Option(help="Comma-separated symbols (default: all raw).")
    ] = None,
    set_reference: Annotated[
        bool, typer.Option("--set-reference", help="Make new snapshots the reference.")
    ] = False,
    config: ConfigOpt = None,
) -> None:
    """Raw Alpaca chunks -> validated snapshots + catalog (with split check)."""
    try:
        cfg = load_alpaca_config(config)
        root = raw_root()
        syms = _symbols_from(None, symbols) if symbols else raw_symbols(root, timeframe)
        store, catalog = SnapshotStore(), Catalog()
        pit_map = pit_symbols_of(Path("configs") / "universe" / "us_equity_hourly.csv")
        results: list[IngestResult] = []
        for sym in syms:
            try:
                results.append(
                    ingest_alpaca_symbol(
                        sym,
                        timeframe,
                        root,
                        store,
                        catalog,
                        cfg,
                        set_reference=set_reference,
                        pit_symbol=pit_map.get(sym),
                    )
                )
            except SfacError as exc:
                typer.echo(f"{sym}: FAILED {exc}", err=True)
                results.append(IngestResult(sym, "failed"))
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    for r in results:
        ref = " (reference)" if r.is_reference else ""
        hash_ = (r.snapshot_hash or "")[:12]
        warn = f"  {r.split_warning}" if r.split_warning else ""
        typer.echo(f"{r.symbol:<8} {r.status:<9} {hash_:<12} rows={r.rows}{ref}{warn}")
    failed = sum(r.status == "failed" for r in results)
    ingested = sum(r.status == "ingested" for r in results)
    typer.echo(f"{len(results)} symbols: {ingested} ingested, {failed} failed")
    if failed:
        raise typer.Exit(code=2)


@universe_app.command("us-equity")
def universe_us_equity(
    out_dir: Annotated[Path, typer.Option(help="Output folder.")] = Path("configs") / "universe",
    pit_csv: Annotated[
        Path | None, typer.Option(help="Use this PIT CSV instead of downloading.")
    ] = None,
    use_latest_pit: Annotated[
        bool,
        typer.Option("--use-latest-pit", help="Use the latest stored PIT CSV (no download)."),
    ] = False,
    config: ConfigOpt = None,
) -> None:
    """Build us_equity_daily.csv and us_equity_hourly.csv (downloads the PIT list)."""
    try:
        cfg = load_alpaca_config(config)
        root = raw_root()
        n_daily = build_daily_universe(root, out_dir / "us_equity_daily.csv")
        pit = pit_csv or (latest_pit_csv(root) if use_latest_pit else fetch_pit_csv(root))
        symbols_csv = root / "reference" / "marketscanner" / "symbols.csv"
        auto = out_dir / "symbol_changes.csv"
        changes = load_changes(auto, out_dir / "symbol_changes_manual.csv")
        counts = build_hourly_universe(
            pit,
            symbols_csv,
            cfg.history_start,
            out_dir / "us_equity_hourly.csv",
            changes=changes,
            changes_file=auto if auto.is_file() else None,
        )
    except TLSVerificationError as exc:
        raise _fail(f"STOP: {exc}") from exc
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"daily universe: {n_daily} symbols; hourly universe: {counts} (PIT file {pit})")


CALENDAR_OUT = Path("configs") / "calendars" / "nyse_sessions.csv"


@reference_app.command("alpaca-calendar")
def reference_alpaca_calendar(
    start: Annotated[str, typer.Option(help="First date YYYY-MM-DD.")] = "2016-01-01",
    end: Annotated[str | None, typer.Option(help="Last date (default: 31 Dec this year).")] = None,
) -> None:
    """Fetch the NYSE session calendar (Alpaca) and write configs/calendars/nyse_sessions.csv."""
    try:
        root = raw_root()
        d0 = dt.date.fromisoformat(start)
        d1 = dt.date.fromisoformat(end) if end else dt.date(dt.date.today().year, 12, 31)
        raw = fetch_calendar(load_credentials(), d0, d1, root)
        n = build_sessions_csv(raw, CALENDAR_OUT)
        msg = f"calendar: {n} sessions {d0}..{d1} -> {CALENDAR_OUT} (raw {raw})"
    except TLSVerificationError as exc:
        raise _fail(f"STOP: {exc}. Certificate verification is never disabled.") from exc
    except (SfacError, PermanentError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(msg)


@reference_app.command("alpaca-symbol-changes")
def reference_alpaca_symbol_changes(
    start: Annotated[str, typer.Option(help="First date YYYY-MM-DD.")] = "2016-01-01",
    pit_csv: Annotated[
        Path | None, typer.Option(help="PIT CSV (default: latest in raw/reference/sp500_pit).")
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """Fetch Alpaca name changes and write configs/universe/symbol_changes.csv for PIT tickers."""
    try:
        cfg = load_alpaca_config(config)
        root = raw_root()
        pit = pit_csv or latest_pit_csv(root)
        tickers = pit_members(pit, cfg.history_start)["symbol"].to_list()
        raw = fetch_name_changes(
            load_credentials(), dt.date.fromisoformat(start), dt.date.today(), root
        )
        out = Path("configs") / "universe" / "symbol_changes.csv"
        n = build_symbol_changes(raw, tickers, out.with_name("symbol_changes_manual.csv"), out)
    except TLSVerificationError as exc:
        raise _fail(f"STOP: {exc}. Certificate verification is never disabled.") from exc
    except (SfacError, PermanentError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"symbol changes: {n} rows for {len(tickers)} PIT tickers -> {out} (raw {raw})")


def latest_pit_csv(root: Path) -> Path:
    files = sorted((root / "reference" / "sp500_pit").glob("fja05680_sp500_*.csv"))
    if not files:
        raise SfacError("no PIT CSV in raw/reference/sp500_pit; run `sfac data universe us-equity`")
    return files[-1]
