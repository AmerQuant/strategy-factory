"""F-0.7.4 (partial): `sfac reproduce --trial` prints the reproduction plan."""

from __future__ import annotations

import pytest
from fixtures.registry_db import schema_url
from sqlalchemy import Engine, select
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.registry import tables as T
from strategy_factory.registry.writer import CandidateRecord, RegistryWriter, config_hash

SNAP = "d" * 64
CONFIG = {
    "pipeline": "mvp_daily",
    "data_snapshots": {"SPY": {"1D": {"source": "alpaca", "snapshot_hash": SNAP}}},
}


@pytest.mark.db
def test_F_0_7_4_reproduce_prints_plan(
    registry_engine: Engine,
    registry_schema: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = RegistryWriter(registry_engine)
    run_id = w.start_run(CONFIG, seed=4242, code_version="e" * 40)
    w.upsert_candidate(
        CandidateRecord(
            id="C9",
            run_id=run_id,
            symbol="SPY",
            timeframe="1D",
            direction="long",
            edge_type="MR",
            spec={"x": 1},
            spec_hash="f" * 64,
            current_stage="s03",
        )
    )
    with w:
        row = {
            "run_id": run_id,
            "stage": "s03_entry",
            "candidate_id": "C9",
            "family_id": "fam",
            "spec_hash": "f" * 64,
            "params": {"rsi_n": 2, "thr": 10},
        }
        w.add_trials([row])
    with registry_engine.connect() as conn:
        trial_id = conn.execute(select(T.trials.c.id)).scalar_one()

    monkeypatch.setenv(
        "SFAC_DB_URL", schema_url(registry_schema).render_as_string(hide_password=False)
    )
    result = CliRunner().invoke(app, ["reproduce", "--trial", str(trial_id)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "partial - execution after T08" in out
    assert config_hash(CONFIG) in out
    assert "e" * 40 in out  # code version
    assert "4242" in out  # seed
    assert "f" * 64 in out  # spec hash
    assert '"rsi_n": 2' in out and '"thr": 10' in out  # params
    assert SNAP in out and "config.data_snapshots.SPY.1D.snapshot_hash" in out

    missing = CliRunner().invoke(app, ["reproduce", "--trial", "999999"])
    assert missing.exit_code == 1 and "unknown trial" in missing.output
