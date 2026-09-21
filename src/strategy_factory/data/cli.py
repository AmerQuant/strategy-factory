"""``sfac data ...`` commands (catalog inspection; downloads and ingest are added by T04x)."""

from __future__ import annotations

from typing import Annotated

import polars as pl
import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.data.catalog import Catalog

data_app = typer.Typer(help="Market data: catalog, downloads, ingest.", no_args_is_help=True)

LIST_COLUMNS = [
    "symbol",
    "timeframe",
    "source",
    "snapshot_hash",
    "row_count",
    "first_ts",
    "last_ts",
    "is_reference",
    "adjustment",
    "session",
    "quality_status",
]


def _fail(exc: SfacError) -> typer.Exit:
    typer.echo(f"error: {exc}", err=True)
    return typer.Exit(code=1)


def print_table(df: pl.DataFrame) -> None:
    """Print a frame as an ASCII table (safe on any console encoding)."""
    with pl.Config(
        tbl_formatting="ASCII_FULL_CONDENSED",
        tbl_hide_dataframe_shape=True,
        tbl_hide_column_data_types=True,
        tbl_rows=-1,
        tbl_cols=-1,
        tbl_width_chars=250,
        fmt_str_lengths=40,
    ):
        typer.echo(str(df))


@data_app.command("list")
def list_cmd(
    symbol: Annotated[str | None, typer.Option(help="Filter by symbol.")] = None,
    timeframe: Annotated[
        str | None, typer.Option(help="Filter by timeframe (1D, 1H, ...).")
    ] = None,
    source: Annotated[str | None, typer.Option(help="Filter by source.")] = None,
) -> None:
    """List catalog snapshots."""
    try:
        cat = Catalog().list_snapshots(symbol=symbol, timeframe=timeframe, source=source)
    except SfacError as exc:
        raise _fail(exc) from exc
    if cat.height == 0:
        typer.echo("catalog is empty (no matching snapshots)")
        return
    view = cat.select(LIST_COLUMNS).with_columns(pl.col("snapshot_hash").str.slice(0, 12))
    print_table(view)
    typer.echo(f"{cat.height} snapshot(s)")


@data_app.command("show")
def show_cmd(
    symbol: Annotated[str, typer.Argument(help="Canonical symbol.")],
    timeframe: Annotated[str, typer.Argument(help="Timeframe (1D, 1H, ...).")],
) -> None:
    """Show the reference snapshot's metadata for SYMBOL and TIMEFRAME."""
    try:
        meta = Catalog().get_reference(symbol, timeframe)
    except SfacError as exc:
        raise _fail(exc) from exc
    for key, value in meta.model_dump().items():
        if key == "raw_refs":
            typer.echo(f"{key:<15}: {len(meta.raw_refs)} file(s)")
            for ref in meta.raw_refs:
                typer.echo(f"{'':<17}{ref.sha256[:12]}  {ref.path}")
            continue
        typer.echo(f"{key:<15}: {value}")


def _register_subcommands() -> None:
    from strategy_factory.data import (  # noqa: F401  (register commands)
        cli_clean,
        cli_dukascopy,
        cli_prep,
        cli_reuse,
        cli_yahoo,
    )
    from strategy_factory.data.cli_alpaca import (
        coverage_app,
        download_app,
        ingest_app,
        reference_app,
        universe_app,
    )

    data_app.add_typer(download_app, name="download")
    data_app.add_typer(ingest_app, name="ingest")
    data_app.add_typer(coverage_app, name="coverage")
    data_app.add_typer(universe_app, name="universe")
    data_app.add_typer(reference_app, name="reference")


_register_subcommands()
