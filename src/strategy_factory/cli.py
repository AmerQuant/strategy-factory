"""Command-line interface: ``sfac`` (Typer)."""

from __future__ import annotations

import platform
import sys
from typing import Annotated

import typer

from strategy_factory import __version__
from strategy_factory.core.cli import config_app, universe_app
from strategy_factory.core.cli_streams import streams_app
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
app.add_typer(config_app, name="config")
app.add_typer(universe_app, name="universe")
app.add_typer(streams_app, name="streams")
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


def utf8_output() -> None:
    """Write the CLI's stdout and stderr as UTF-8, whatever the locale (D-379, P-53).

    Redirected to a file or a pipe -- as the PowerShell scripts log it -- Python writes with
    the locale codec, cp1252 on Windows, and a message or help text with a character it
    lacks (``→``, ``≤``, ``₁₀``) crashed the command at its last step. ``replace`` keeps an
    unencodable character from ever raising. A stream without ``reconfigure`` (a test
    runner's capture) is left alone.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def run() -> None:
    """The ``sfac`` entry point: set the output encoding once, then run the app."""
    utf8_output()
    app()


if __name__ == "__main__":  # pragma: no cover
    run()
