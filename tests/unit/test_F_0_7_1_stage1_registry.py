"""F-0.7.1 / F-0.7.2 / F-0.7.3 / D-616: what stage 1 writes to the registry.

One candidate per profile, **one trial per probe evaluated** (``family_id`` = edge type; the
baseline simulations are not trials, D-012), so ``probes_run`` equals the trial rows; every
gate criterion of every probe and of the profile, with its value, threshold and verdict; an
artifact row per ``summary.json`` and per stored trade set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.edge_stage import (
    GATES,
    FakeData,
    FakeReferences,
    resolved_config,
    stage_config,
    synthetic_bars,
)
from sqlalchemy import Engine, func, select

from strategy_factory.gates.engine import GateEngine
from strategy_factory.pipeline.executor import SerialExecutor
from strategy_factory.registry import tables as T
from strategy_factory.registry.writer import RegistryWriter
from strategy_factory.stages.base import RunContext
from strategy_factory.stages.edge import EdgeStage
from strategy_factory.stages.edge_profile import EdgeProfile

pytestmark = pytest.mark.db


def test_F_0_7_1_stage1_registry_rows(registry_engine: Engine, tmp_path: Path) -> None:
    import yaml

    cfg = resolved_config(("AAPL",))
    writer = RegistryWriter(registry_engine)
    run_id = writer.start_run(cfg.canonical(), seed=cfg.seed, code_version="test")
    ctx = RunContext(
        config=cfg,
        data=FakeData({("AAPL", "1D"): synthetic_bars(1200, 0, phi=-0.35)}),  # type: ignore[arg-type]
        references=FakeReferences(  # type: ignore[arg-type]
            {("AAPL", "1D"): cfg.data_snapshots["AAPL"]["1D"].snapshot_hash}
        ),
        executor=SerialExecutor(),
        gates=GateEngine.from_file(GATES),
        artifacts_root=tmp_path,
        code_version="test",
        registry=writer,
        run_id=run_id,
    )
    stage_file = tmp_path / "s01.yaml"
    stage_file.write_text(
        yaml.safe_dump(stage_config(simulations=100).model_dump(mode="json")), encoding="utf-8"
    )
    result = EdgeStage(stage_config_path=stage_file).run([("AAPL", "1D")], ctx)

    with registry_engine.connect() as conn:
        cands = conn.execute(select(T.candidates)).mappings().all()
        trials = conn.execute(select(T.trials)).mappings().all()
        gates = conn.execute(select(T.gate_results)).mappings().all()
        arts = conn.execute(select(func.count()).select_from(T.artifacts)).scalar_one()
    assert len(cands) == 4  # MR/TF x long/short (D-604)
    profiles = {
        p.identity.candidate_id: p
        for p in (
            EdgeProfile.model_validate_json(f.read_text(encoding="utf-8"))
            for f in (tmp_path / str(run_id) / "s01_edge").glob("*/summary.json")
        )
    }
    assert set(profiles) == {c["id"] for c in cands}
    for c in cands:
        prof = profiles[c["id"]]
        mine = [t for t in trials if t["candidate_id"] == c["id"]]
        assert len(mine) == prof.probes_run  # D-605 / F-0.7.1: trials = evaluated configs
        assert {t["family_id"] for t in mine} == {c["edge_type"]}
        assert {t["params"]["probe"] for t in mine} == {p.name for p in prof.probes}
        # rule 8 / D-606: which stage constants produced each trial is in the registry
        assert {t["params"]["stage_config_hash"] for t in mine} == {prof.identity.stage_config_hash}
        assert c["status"] == ("active" if prof.profile.passed else "rejected")
        rows = [g for g in gates if g["candidate_id"] == c["id"]]
        # four s01_probe criteria per probe, two s01_edge criteria per profile (F-0.7.3)
        assert sum(g["stage"] == "s01_probe" for g in rows) == 4 * prof.probes_run
        assert sum(g["stage"] == "s01_edge" for g in rows) == 2
        assert all(":" in g["criterion"] for g in rows if g["stage"] == "s01_probe")
    stored_trades = sum(1 for a in result.artifacts if a.kind == "trades")
    assert arts == len(cands) + stored_trades and stored_trades > 0  # the planted MR passes
