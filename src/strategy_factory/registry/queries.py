"""Registry reads (F-0.7.2, F-0.7.3, F-0.7.4)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, literal, select

from strategy_factory.core.errors import RegistryError
from strategy_factory.registry.tables import candidates, gate_results, pipeline_runs, trials


def _ancestors_cte(candidate_id: str) -> Any:
    """Recursive CTE: the candidate itself (depth 0) and every ancestor via ``parent_id``."""
    base = select(candidates.c.id, candidates.c.parent_id, literal(0).label("depth")).where(
        candidates.c.id == candidate_id
    )
    tree = base.cte("lineage", recursive=True)
    step = select(candidates.c.id, candidates.c.parent_id, (tree.c.depth + 1).label("depth")).join(
        tree, candidates.c.id == tree.c.parent_id
    )
    return tree.union_all(step)


def trial_count(engine: Engine, candidate_id: str, include_lineage: bool = True) -> int:
    """Trials of the candidate, plus those of all its ancestors when ``include_lineage``."""
    if include_lineage:
        tree = _ancestors_cte(candidate_id)
        stmt = (
            select(func.count())
            .select_from(trials)
            .where(trials.c.candidate_id.in_(select(tree.c.id)))
        )
    else:
        stmt = select(func.count()).select_from(trials).where(trials.c.candidate_id == candidate_id)
    with engine.connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def trials_by_family(engine: Engine, family_id: str) -> list[dict[str, Any]]:
    stmt = select(trials).where(trials.c.family_id == family_id).order_by(trials.c.id)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(stmt)]


def candidate_lineage(engine: Engine, candidate_id: str) -> list[dict[str, Any]]:
    """Candidates from the root ancestor down to ``candidate_id`` (inclusive)."""
    tree = _ancestors_cte(candidate_id)
    stmt = (
        select(candidates, tree.c.depth)
        .join(tree, candidates.c.id == tree.c.id)
        .order_by(tree.c.depth.desc())
    )
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(stmt)]
    if not rows:
        raise RegistryError(f"unknown candidate {candidate_id!r}", stage="registry")
    return rows


def gate_history(engine: Engine, candidate_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(gate_results)
        .where(gate_results.c.candidate_id == candidate_id)
        .order_by(gate_results.c.created_at, gate_results.c.id)
    )
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(stmt)]


# --------------------------------------------------------------------------------------
# Reproduction plan (F-0.7.4, partial)
# --------------------------------------------------------------------------------------
def _snapshot_hashes(obj: Any, path: str = "config") -> list[tuple[str, str]]:
    """(json path, value) of every ``*snapshot_hash`` key found in the config."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}"
            if isinstance(k, str) and k.endswith("snapshot_hash") and isinstance(v, str):
                out.append((here, v))
            else:
                out += _snapshot_hashes(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _snapshot_hashes(v, f"{path}[{i}]")
    return out


def reproduction_plan(engine: Engine, trial_id: int) -> dict[str, Any]:
    """Everything needed to re-run a trial: run record, spec, params, data snapshot(s)."""
    stmt = (
        select(
            trials,
            pipeline_runs.c.config,
            pipeline_runs.c.config_hash,
            pipeline_runs.c.code_version,
            pipeline_runs.c.seed,
            pipeline_runs.c.status.label("run_status"),
        )
        .join(pipeline_runs, pipeline_runs.c.id == trials.c.run_id)
        .where(trials.c.id == trial_id)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
        if row is None:
            raise RegistryError(f"unknown trial {trial_id}", stage="reproduce")
        m = dict(row._mapping)
        cand = None
        if m["candidate_id"] is not None:
            c = conn.execute(select(candidates).where(candidates.c.id == m["candidate_id"])).first()
            cand = dict(c._mapping) if c is not None else None
    return {
        "trial_id": m["id"],
        "run_id": str(m["run_id"]),
        "run_status": m["run_status"],
        "stage": m["stage"],
        "family_id": m["family_id"],
        "candidate_id": m["candidate_id"],
        "symbol": cand["symbol"] if cand else None,
        "timeframe": cand["timeframe"] if cand else None,
        "direction": cand["direction"] if cand else None,
        "config_hash": m["config_hash"],
        "code_version": m["code_version"],
        "seed": m["seed"],
        "spec_hash": m["spec_hash"],
        "params": m["params"],
        "snapshot_hashes": _snapshot_hashes(m["config"]),
        "config": m["config"],
    }


def format_plan(plan: dict[str, Any]) -> str:
    import json

    snaps = plan["snapshot_hashes"]
    lines = [
        f"Reproduction plan for trial {plan['trial_id']}",
        "STATUS: partial - execution after T08 (engine); this prints the plan only.",
        "",
        f"run_id        : {plan['run_id']} ({plan['run_status']})",
        f"stage         : {plan['stage']}   family: {plan['family_id']}",
        f"candidate     : {plan['candidate_id'] or '(stage-1 probe, no candidate)'}",
        f"instrument    : {plan['symbol']} {plan['timeframe']} {plan['direction']}",
        f"config_hash   : {plan['config_hash']}",
        f"code_version  : {plan['code_version']}   (git checkout this commit)",
        f"seed          : {plan['seed']}",
        f"spec_hash     : {plan['spec_hash']}",
        f"params        : {json.dumps(plan['params'], sort_keys=True)}",
    ]
    if snaps:
        lines += [f"snapshot_hash : {v}   ({p})" for p, v in snaps]
    else:
        lines.append("snapshot_hash : NOT RECORDED in the run config (cannot reproduce data)")
    lines += [
        "",
        "Steps: 1) git checkout <code_version>  2) load the snapshot(s) above from the store",
        "       3) rebuild the run config (its hash must equal config_hash)",
        "       4) run the stage with spec_hash + params and the seed  5) compare bit-for-bit",
    ]
    return "\n".join(lines)
