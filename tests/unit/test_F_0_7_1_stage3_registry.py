"""F-0.7.1 / F-0.7.2 / F-0.7.3 / F-3.1 / D-160 / D-651: what stage 3 writes to the registry.

A candidate per stage-2 selection whose ``parent_id`` is the stage-2 candidate (a foreign key:
the stage-2 rows must exist), **one trial per fine-grid cell per segment** (whole, half 1, half
2 -- ``cells_run`` = trial rows), every gate criterion with its value and verdict, and an
artifact row per ``summary.json`` and per stored trade set.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixtures.edge_stage import resolved_config
from fixtures.entry_stage import entry_config_file, entry_context, stage2_run
from fixtures.screen_stage import planted_series
from sqlalchemy import Engine, func, select

from strategy_factory.registry import tables as T
from strategy_factory.registry.writer import RegistryWriter
from strategy_factory.stages.optimize import EntryStage
from strategy_factory.stages.optimize_artifact import EntryOptimisation

pytestmark = pytest.mark.db


def test_F_0_7_1_stage3_registry_rows(registry_engine: Engine, tmp_path: Path) -> None:
    symbols = ("AAPL",)
    series = planted_series(symbols)
    cfg = resolved_config(symbols)
    writer = RegistryWriter(registry_engine)
    run1 = writer.start_run(cfg.canonical(), seed=cfg.seed, code_version="test")
    run2 = writer.start_run(cfg.canonical(), seed=cfg.seed, code_version="test")
    stage2_run(tmp_path, series, symbols, registry=writer, run_ids=(run1, run2))
    run3 = writer.start_run(cfg.canonical(), seed=cfg.seed, code_version="test")
    ctx = entry_context(tmp_path, series, symbols, registry=writer, run_id=run3, s02_run=str(run2))
    stage = EntryStage(stage_config_path=entry_config_file(tmp_path, fine_grid={"max_cells": 120}))
    result = stage.run([("AAPL", "1D")], ctx)

    arts = [
        EntryOptimisation.model_validate_json(p.read_text(encoding="utf-8"))
        for p in (tmp_path / str(run3) / "s03_entry").glob("*/summary.json")
    ]
    assert arts
    with registry_engine.connect() as conn:
        cands = (
            conn.execute(select(T.candidates).where(T.candidates.c.run_id == run3)).mappings().all()
        )
        parents = {
            r["id"]
            for r in conn.execute(
                select(T.candidates).where(T.candidates.c.run_id == run2)
            ).mappings()
        }
        trials = conn.execute(select(T.trials).where(T.trials.c.run_id == run3)).mappings().all()
        gates = (
            conn.execute(select(T.gate_results).where(T.gate_results.c.run_id == run3))
            .mappings()
            .all()
        )
        n_art = conn.execute(
            select(func.count()).select_from(T.artifacts).where(T.artifacts.c.run_id == run3)
        ).scalar_one()
    assert len(cands) == len(arts)
    assert {c["parent_id"] for c in cands} <= parents  # every parent is a stage-2 candidate
    assert {c["status"] for c in cands if c["id"] in result.passed} <= {"active"}
    assert sum(1 for c in cands if c["status"] == "active") == len(result.passed)
    # D-160: every cell on every segment is a trial
    assert len(trials) == sum(a.cells_run for a in arts)
    per_cand: dict[str, int] = {}
    for t in trials:
        per_cand[t["candidate_id"]] = per_cand.get(t["candidate_id"], 0) + 1
        assert t["stage"] == "s03_entry" and t["family_id"] == t["params"]["method"]
        assert t["params"]["segment"] in {"whole", "h1", "h2"}
    assert per_cand == {a.identity.candidate_id: a.cells_run for a in arts}
    # one row per (candidate, cell, segment): no cell counted twice, none missing
    keys = {
        (
            t["candidate_id"],
            json.dumps(t["params"]["params"], sort_keys=True),
            t["params"]["segment"],
        )
        for t in trials
    }
    assert len(keys) == len(trials)
    for a in arts:
        for c in a.surface:
            for seg in ("whole", "h1", "h2"):
                assert (a.identity.candidate_id, json.dumps(c.params, sort_keys=True), seg) in keys
    # every criterion of every candidate, D-648's included
    assert len(gates) == 5 * len(arts)
    assert {g["criterion"] for g in gates} == {
        "spp_median_target",
        "stability_ratio",
        "plateau_area",
        "plateau_cells",
        "selected_in_both_halves",
    }
    assert n_art == len(arts) + len(result.passed)
