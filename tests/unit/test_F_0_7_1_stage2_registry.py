"""F-0.7.1 / F-0.7.2 / F-0.7.3 / F-2.3 / D-636: what stage 2 writes to the registry.

A candidate per (profile, method) whose ``parent_id`` is the stage-1 candidate (a foreign key:
the stage-1 rows must exist), **one trial per grid cell** (``cells_run`` = trial rows, D-160),
every gate criterion with its value and verdict, and an artifact row per ``summary.json`` and
per stored trade set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.edge_stage import resolved_config
from fixtures.screen_stage import planted_series, screen_config_file, screen_context, stage1_run
from sqlalchemy import Engine, func, select

from strategy_factory.registry import tables as T
from strategy_factory.registry.writer import RegistryWriter
from strategy_factory.stages.screen import ScreenStage
from strategy_factory.stages.screen_artifact import MethodScreen

pytestmark = pytest.mark.db


def test_F_0_7_1_stage2_registry_rows(registry_engine: Engine, tmp_path: Path) -> None:
    symbols = ("AAPL",)
    series = planted_series(symbols)
    cfg = resolved_config(symbols)
    writer = RegistryWriter(registry_engine)
    run1 = writer.start_run(cfg.canonical(), seed=cfg.seed, code_version="test")
    stage1_run(tmp_path, series, symbols, registry=writer, run_id=run1)
    run2 = writer.start_run(cfg.canonical(), seed=cfg.seed, code_version="test")
    ctx = screen_context(tmp_path, series, symbols, registry=writer, run_id=run2, s01_run=str(run1))
    result = ScreenStage(stage_config_path=screen_config_file(tmp_path)).run([("AAPL", "1D")], ctx)

    arts = [
        MethodScreen.model_validate_json(p.read_text(encoding="utf-8"))
        for p in (tmp_path / str(run2) / "s02_screen").glob("*/summary.json")
    ]
    assert arts
    with registry_engine.connect() as conn:
        cands = (
            conn.execute(select(T.candidates).where(T.candidates.c.run_id == run2)).mappings().all()
        )
        parents = {
            r["id"]
            for r in conn.execute(
                select(T.candidates).where(T.candidates.c.run_id == run1)
            ).mappings()
        }
        trials = conn.execute(select(T.trials).where(T.trials.c.run_id == run2)).mappings().all()
        gates = (
            conn.execute(select(T.gate_results).where(T.gate_results.c.run_id == run2))
            .mappings()
            .all()
        )
        n_art = conn.execute(
            select(func.count()).select_from(T.artifacts).where(T.artifacts.c.run_id == run2)
        ).scalar_one()
    assert len(cands) == len(arts)
    assert {c["parent_id"] for c in cands} <= parents  # every parent is a stage-1 candidate
    assert {c["status"] for c in cands if c["id"] in result.passed} == {"active"}
    assert sum(1 for c in cands if c["status"] == "active") == len(result.passed)
    # D-160: every cell is a trial
    assert len(trials) == sum(a.cells_run for a in arts)
    per_cand: dict[str, int] = {}
    for t in trials:
        per_cand[t["candidate_id"]] = per_cand.get(t["candidate_id"], 0) + 1
        assert t["stage"] == "s02_screen" and t["family_id"] == t["params"]["method"]
    assert per_cand == {a.identity.candidate_id: a.cells_run for a in arts}
    # every criterion of every method, including D-629's
    assert len(gates) == 5 * len(arts)
    assert {g["criterion"] for g in gates} >= {"method_q_value", "overlap_with_selected"}
    assert n_art == len(arts) + len(result.passed)
