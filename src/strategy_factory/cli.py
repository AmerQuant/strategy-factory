"""Command-line interface: ``sfac`` (Typer)."""

from __future__ import annotations

import platform
import sys
from typing import Annotated

import typer

from strategy_factory import __version__
from strategy_factory.core.env import resolve_env
from strategy_factory.core.logging import get_logger, setup_logging
from strategy_factory.costs.cli import costs_app
from strategy_factory.data.cli import data_app
from strategy_factory.registry.cli import db_app, reproduce

app = typer.Typer(
    name="sfac",
    help="Strategy Factory: standard, reproducible, auditable strategy-research funnel.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(data_app, name="data")
app.add_typer(db_app, name="db")
app.add_typer(costs_app, name="costs")
app.command("reproduce")(reproduce)

INFO_ENV_KEYS = ("SFAC_DATA_ROOT", "SFAC_ARTIFACTS_ROOT")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"sfac {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Print the package version and exit.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level: DEBUG, INFO, WARNING, ERROR."),
    ] = "INFO",
) -> None:
    """Global options shared by every command."""
    try:
        setup_logging(log_level)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--log-level") from exc


@app.command()
def info() -> None:
    """Show Python, package, platform and resolved environment roots."""
    get_logger(__name__).debug("resolving environment")
    typer.echo(f"sfac version     : {__version__}")
    typer.echo(f"python           : {sys.version.split()[0]} ({sys.executable})")
    typer.echo(f"platform         : {platform.platform()}")
    for key, (value, origin) in resolve_env(INFO_ENV_KEYS).items():
        shown = value if value is not None else "not set"
        suffix = f"  (from {origin})" if value is not None else ""
        typer.echo(f"{key:<17}: {shown}{suffix}")


if __name__ == "__main__":  # pragma: no cover
    app()
