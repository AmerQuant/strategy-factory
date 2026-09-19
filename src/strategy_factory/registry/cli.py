"""``sfac db upgrade|status`` and ``sfac reproduce --trial <id>``."""

from __future__ import annotations

from typing import Annotated

import typer

from strategy_factory.core.errors import SfacError
from strategy_factory.registry.engine import make_engine
from strategy_factory.registry.migrations import (
    current_revision,
    head_revision,
    row_counts,
    upgrade,
)
from strategy_factory.registry.queries import format_plan, reproduction_plan

db_app = typer.Typer(
    help="Registry database (PostgreSQL): migrations and status.", no_args_is_help=True
)


def _fail(exc: SfacError) -> typer.Exit:
    typer.echo(f"error: {exc}", err=True)
    return typer.Exit(code=1)


@db_app.command("upgrade")
def db_upgrade(revision: Annotated[str, typer.Argument(help="Target revision.")] = "head") -> None:
    """Apply Alembic migrations (default: head)."""
    try:
        engine = make_engine()
        before = current_revision(engine)
        upgrade(engine, revision)
        after = current_revision(engine)
    except SfacError as exc:
        raise _fail(exc) from exc
    typer.echo(f"registry schema: {before or 'empty'} -> {after}")


@db_app.command("status")
def db_status() -> None:
    """Current revision and row counts per table."""
    try:
        engine = make_engine()
        rev = current_revision(engine)
        head = head_revision()
        typer.echo(f"revision : {rev or 'none (run `sfac db upgrade`)'} (head: {head})")
        if rev is None:
            return
        for table, n in row_counts(engine).items():
            typer.echo(f"{table:<16} {n:>12,}")
    except SfacError as exc:
        raise _fail(exc) from exc


def reproduce(
    trial: Annotated[int, typer.Option("--trial", help="Trial id from the registry.")],
) -> None:
    """Print the reproduction plan of a trial (partial: execution after T08)."""
    try:
        plan = reproduction_plan(make_engine(), trial)
    except SfacError as exc:
        raise _fail(exc) from exc
    typer.echo(format_plan(plan))
