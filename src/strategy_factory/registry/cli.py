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
    """Print the reproduction plan of a trial and verify its cost inputs (T10b).

    Exits with code 1 when the cost configs no longer produce what the run recorded: a rerun
    would use other costs, which is not a reproduction (CLAUDE.md rules 4 and 8).
    """
    from strategy_factory.core.config import check_cost_inputs

    try:
        plan = reproduction_plan(make_engine(), trial)
    except SfacError as exc:
        raise _fail(exc) from exc
    typer.echo(format_plan(plan))
    try:
        problems = check_cost_inputs(plan["config"])
    except SfacError as exc:
        raise _fail(exc) from exc
    if not problems:
        typer.echo("\ncost inputs: OK (the current configs reproduce the recorded costs)")
        return
    if problems == ["cost_inputs are not recorded in the run config (the run predates T10b)"]:
        typer.echo(f"\nwarning: {problems[0]}", err=True)
        return
    typer.echo("\nerror: the cost inputs of this run cannot be reproduced:", err=True)
    for problem in problems:
        typer.echo(f"  - {problem}", err=True)
    raise typer.Exit(code=1)
