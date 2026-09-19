"""`sfac config validate|resolve` (F-0.8.2), `sfac universe list|validate|generate` (F-0.9.1)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from strategy_factory.core.config import (
    config_hash,
    load_pipeline_config,
    resolve_config,
    validate_config,
)
from strategy_factory.core.errors import SfacError
from strategy_factory.core.universe import (
    DEFAULT_UNIVERSE,
    generate_universe,
    load_universe,
    validate_universe,
    write_universe,
)

config_app = typer.Typer(help="Pipeline configs: validate and resolve.", no_args_is_help=True)
universe_app = typer.Typer(help="Universe registry.", no_args_is_help=True)
UniverseOpt = Annotated[Path | None, typer.Option("--universe", help="Universe YAML.")]


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


@config_app.command("validate")
def config_validate(file: Annotated[Path, typer.Argument(help="Pipeline config YAML.")]) -> None:
    """Schema, universe membership, timeframes and stage gates of a pipeline config."""
    try:
        cfg = load_pipeline_config(file)
        validate_config(cfg, file)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(
        f"ok: {len(cfg.symbols)} symbol(s) x {len(cfg.timeframes)} timeframe(s), "
        f"stages {list(cfg.stages)}"
    )


@config_app.command("resolve")
def config_resolve(file: Annotated[Path, typer.Argument(help="Pipeline config YAML.")]) -> None:
    """Print the config with data_snapshots resolved from the catalog references."""
    try:
        resolved = resolve_config(load_pipeline_config(file), config_path=file)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(json.dumps(resolved.canonical(), indent=2, sort_keys=True))
    typer.echo(f"config_hash: {config_hash(resolved)}")


@universe_app.command("list")
def universe_list(
    asset_class: Annotated[str | None, typer.Option(help="Filter by asset class.")] = None,
    group: Annotated[str | None, typer.Option(help="Filter by group.")] = None,
    universe: UniverseOpt = None,
) -> None:
    """List universe symbols (counts per asset class at the end)."""
    try:
        u = load_universe(universe)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    rows = [
        e
        for e in u.symbols
        if (asset_class is None or e.asset_class == asset_class)
        and (group is None or e.group == group)
    ]
    for e in rows:
        typer.echo(
            f"{e.symbol:<16} {e.asset_class:<11} {e.reference_source:<10} "
            f"{','.join(e.timeframes):<7} {e.calendar:<5} {e.group:<11} "
            f"{e.cost_profile or '-':<20} {'tradable' if e.tradable else 'not tradable'}"
        )
    counts = Counter(e.asset_class for e in rows)
    typer.echo(
        f"{len(rows)} symbol(s): " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    )


@universe_app.command("validate")
def universe_validate(universe: UniverseOpt = None) -> None:
    """One reference source per symbol, cost profiles, catalog source and asset class."""
    from strategy_factory.data.store import data_root

    try:
        u = load_universe(universe)
        try:
            root: Path | None = data_root()
        except SfacError:
            root = None
        problems = validate_universe(u, catalog_root=root)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    if problems:
        for p in problems[:50]:
            typer.echo(f"  {p}", err=True)
        raise _fail(f"{len(problems)} universe problem(s)")
    tradable = sum(1 for e in u.symbols if e.tradable)
    counts = Counter(e.asset_class for e in u.symbols)
    typer.echo(
        f"ok: {len(u.symbols)} symbols ({tradable} tradable): "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        + ("" if root else " [catalog not checked: SFAC_DATA_ROOT unset]")
    )


@universe_app.command("generate")
def universe_generate(
    out: Annotated[Path, typer.Option(help="Output YAML.")] = DEFAULT_UNIVERSE,
) -> None:
    """Regenerate configs/universe.yaml from configs/universe/*.csv and the cost assignments."""
    try:
        u = generate_universe()
        write_universe(u, out)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    counts = Counter(e.asset_class for e in u.symbols)
    typer.echo(
        f"wrote {out.as_posix()}: {len(u.symbols)} symbols ("
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        + ")"
    )
