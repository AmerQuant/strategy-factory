"""``sfac streams check`` -- the three stream guards against a git base (D-357 (4))."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated

import typer

from strategy_factory.core.errors import ConfigError, SfacError
from strategy_factory.core.streams import (
    DEFAULT_OWNERSHIP,
    check_all,
    load_ownership,
    read_migrations,
)

streams_app = typer.Typer(
    help="Guards for the two parallel streams (D-355, D-357).", no_args_is_help=True
)
ALEMBIC_VERSIONS = Path("src") / "strategy_factory" / "registry" / "alembic" / "versions"
GUARD_TITLES = {
    "paths": "path ownership (D-357 (2))",
    "ids": "decision / pending ids (D-355 ranges)",
    "alembic": "a single Alembic head (D-357 (4))",
}


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError(f"git failed: {exc}") from exc
    if out.returncode != 0:
        raise ConfigError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def changed_paths(base: str) -> list[str]:
    """Paths this branch changes against the merge base with ``base``."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    return [p for p in _git("diff", "--name-only", f"{merge_base}..HEAD").splitlines() if p]


def added_rows(base: str, files: tuple[str, ...]) -> list[str]:
    """Lines this branch **adds** to ``files`` (without the leading ``+``)."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    diff = _git("diff", "-U0", f"{merge_base}..HEAD", "--", *files)
    return [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def base_rows(base: str, files: tuple[str, ...]) -> list[str]:
    """The rows those files already had at the merge base."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    rows: list[str] = []
    for name in files:
        try:
            rows += _git("show", f"{merge_base}:{name}").splitlines()
        except ConfigError:  # the file did not exist there yet
            continue
    return rows


@streams_app.command("check")
def streams_check(
    base: Annotated[str, typer.Option(help="Branch to compare against.")] = "origin/main",
    branch: Annotated[
        str | None, typer.Option(help="Branch name (default: the current one).")
    ] = None,
    ownership: Annotated[Path, typer.Option(help="Ownership file.")] = DEFAULT_OWNERSHIP,
    versions: Annotated[Path, typer.Option(help="Alembic versions folder.")] = ALEMBIC_VERSIONS,
) -> None:
    """Run the three stream guards; exits 1 and names every problem when one fails."""
    try:
        name = branch if branch is not None else _git("branch", "--show-current").strip()
        rules = load_ownership(ownership)
        files = rules.append_only or (
            "docs/decisions/decisions_log.md",
            "docs/decisions/pending.md",
        )
        results = check_all(
            name,
            changed_paths(base),
            added_rows(base, files),
            base_rows(base, files),
            read_migrations(versions),
            rules,
        )
    except SfacError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    stream = rules.stream_of_branch(name)
    where = f"stream {stream}" if stream else "no stream prefix (grandfathered)"
    typer.echo(f"branch {name!r} vs {base}: {where}")
    failed = False
    for guard, problems in results.items():
        if problems:
            failed = True
            typer.echo(f"\nFAIL {GUARD_TITLES[guard]}:", err=True)
            for problem in problems:
                typer.echo(f"  - {problem}", err=True)
        else:
            typer.echo(f"ok   {GUARD_TITLES[guard]}")
    if failed:
        raise typer.Exit(code=1)
