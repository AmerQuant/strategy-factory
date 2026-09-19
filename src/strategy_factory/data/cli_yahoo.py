"""``sfac data download yahoo`` and ``sfac data ingest yahoo``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.data.adapters.yahoo import YahooAdapter
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_alpaca import download_app, ingest_app
from strategy_factory.data.config import load_yahoo_config
from strategy_factory.data.download.ratelimit import TLSVerificationError
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.download.yahoo import (
    AuxSeries,
    YFinanceClient,
    latest_raw,
    load_aux_universe,
    run_yahoo_download,
)
from strategy_factory.data.store import SnapshotStore

ConfigOpt = Annotated[Path | None, typer.Option("--config", help="Yahoo config YAML.")]
TickersOpt = Annotated[str | None, typer.Option(help="Comma-separated tickers (default: all).")]


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _select(tickers: str | None, universe: Path) -> list[AuxSeries]:
    all_ = load_aux_universe(universe)
    if not tickers:
        return all_
    wanted = {t.strip() for t in tickers.split(",") if t.strip()}
    unknown = wanted - {s.ticker for s in all_}
    if unknown:
        raise SfacError(f"tickers not in {universe}: {sorted(unknown)}")
    return [s for s in all_ if s.ticker in wanted]


@download_app.command("yahoo")
def download_yahoo(tickers: TickersOpt = None, config: ConfigOpt = None) -> None:
    """Download full daily history (new immutable raw version per run)."""
    try:
        cfg = load_yahoo_config(config)
        series = _select(tickers, cfg.universe_file)
        report = run_yahoo_download(series, raw_root(), cfg, YFinanceClient())
    except TLSVerificationError as exc:
        raise _fail(f"STOP: {exc}. Certificate verification is never disabled.") from exc
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    for r in report.revisions:
        typer.echo(
            f"{r['ticker']}: revision check vs {r['previous']}: {r['changed_rows']} changed of "
            f"{r['common_rows']} common rows (max |diff| {r['max_abs_diff']:.6g})"
        )
    typer.echo(f"yahoo: stored {len(report.stored)}, failed {len(report.failed)}")
    for f in report.failed:
        typer.echo(f"  {f['ticker']}: {f['error']}", err=True)
    if report.failed:
        raise typer.Exit(code=2)


@ingest_app.command("yahoo")
def ingest_yahoo(
    tickers: TickersOpt = None,
    set_reference: Annotated[
        bool, typer.Option("--set-reference", help="Make new snapshots the reference.")
    ] = False,
    config: ConfigOpt = None,
) -> None:
    """Latest raw version per ticker -> daily snapshot + catalog."""
    try:
        cfg = load_yahoo_config(config)
        series = _select(tickers, cfg.universe_file)
        root, store, catalog, adapter = raw_root(), SnapshotStore(), Catalog(), YahooAdapter()
        failed = 0
        for s in series:
            try:
                path = latest_raw(root, s.ticker)
                if path is None:
                    raise SfacError(f"no raw file for {s.ticker}; run `sfac data download yahoo`")
                df, meta = adapter.to_canonical(
                    [path],
                    ticker=s.ticker,
                    symbol=s.symbol,
                    close_time_local=s.close_time_local,
                    close_tz=s.close_tz,
                    close_time_status=s.close_time_status,
                )
                stored = store.write_snapshot(df, meta)
                catalog.register(stored)
                ref = set_reference or not catalog.has_reference(s.symbol, "1D")
                if ref and stored.snapshot_hash:
                    catalog.set_reference(s.symbol, "1D", stored.snapshot_hash, note="yahoo ingest")
                first = stored.first_ts.date() if stored.first_ts else None
                last = stored.last_ts.date() if stored.last_ts else None
                typer.echo(
                    f"{s.symbol:<5} {s.ticker:<9} rows={stored.row_count} {first}..{last} "
                    f"volume={stored.volume_quality}{' (reference)' if ref else ''}"
                )
            except SfacError as exc:
                failed += 1
                typer.echo(f"{s.ticker}: FAILED {exc}", err=True)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    if failed:
        raise typer.Exit(code=2)
