"""``sfac funnel``: run, inspect, reproduce and report a funnel run (F-X.2, T15a §3)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

import typer

funnel_app = typer.Typer(help="The funnel: stages 1 -> 2 -> 3 with the control (T15a).")


@funnel_app.command("run")
def funnel_run(
    config: Annotated[Path, typer.Argument(help="Funnel config (configs/funnel/*.yaml).")],
    no_control: Annotated[
        bool,
        typer.Option(
            "--no-control",
            help="Skip the reshuffled-returns control (D-653): recorded in the run row and "
            "printed on the report's first page.",
        ),
    ] = False,
    fresh: Annotated[
        bool, typer.Option("--fresh", help="Start a new funnel run instead of resuming.")
    ] = False,
    workers: Annotated[
        int | None,
        typer.Option("--workers", help="Executor workers (1 Numba thread each); operational."),
    ] = None,
    notes: Annotated[str, typer.Option("--notes", help="Free text stored on the run.")] = "",
) -> None:
    """Run (or resume) a funnel: every stage and its control, per timeframe."""
    from strategy_factory.pipeline.funnel_run import run_funnel

    result, folder = run_funnel(
        config, no_control=no_control, fresh=fresh, workers=workers, notes=notes
    )
    typer.echo(f"funnel     : {result.funnel_id}{' (resumed)' if result.resumed else ''}")
    typer.echo(f"source     : {result.source.id if result.source else 'real'}")
    typer.echo(f"control    : {'yes' if result.control else 'NO (--no-control)'}")
    for o in result.stages:
        tf, stage, arm = o.slot
        tag = "reused" if o.reused else ""
        typer.echo(f"{tf:<4} {stage:<11} {arm:<8} {o.status:<6} {o.run_id or '-':<37} {tag}")
    typer.echo(f"folder     : {folder}")
    typer.echo(f"seconds    : {result.seconds:.0f}")


@funnel_app.command("status")
def funnel_status(
    funnel_id: Annotated[str, typer.Argument(help="Funnel run id.")],
) -> None:
    """Show a funnel run and its stage runs."""
    from strategy_factory.registry.engine import make_engine
    from strategy_factory.registry.funnel import FunnelRegistry

    reg = FunnelRegistry(make_engine())
    fid = uuid.UUID(funnel_id)
    row = reg.funnel(fid)
    typer.echo(f"funnel     : {fid}  status {row['status']}  source {row['source']}")
    typer.echo(f"control    : {row['control']}  code {row['code_version']}  seed {row['seed']}")
    for (tf, stage, arm), s in sorted(reg.stages(fid).items()):
        typer.echo(f"{tf:<4} {stage:<11} {arm:<8} {s.status:<8} {s.run_id or '-'}")


@funnel_app.command("reproduce")
def funnel_reproduce(
    funnel_id: Annotated[str, typer.Argument(help="Funnel run id to rebuild.")],
    workers: Annotated[
        int | None,
        typer.Option("--workers", help="Executor workers (1 Numba thread each); operational."),
    ] = None,
) -> None:
    """Re-run a funnel from its registry rows and compare every artifact (F-0.7.4)."""
    from strategy_factory.pipeline.funnel_run import reproduce

    report = reproduce(funnel_id, workers=workers)
    typer.echo(f"original     : {report.original}")
    typer.echo(f"reproduction : {report.reproduction}")
    typer.echo(f"files        : {report.compared_files}")
    if report.identical:
        typer.echo("identical    : yes (run ids and run-config hashes normalised)")
        return
    typer.echo(f"identical    : NO -- {len(report.differences)} difference(s)", err=True)
    for d in report.differences[:50]:
        typer.echo(f"  {d}", err=True)
    raise typer.Exit(code=1)
