"""F-0.7.2: trial counts per candidate, with and without its lineage (recursive CTE)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine

from strategy_factory.registry.queries import candidate_lineage, trial_count, trials_by_family
from strategy_factory.registry.writer import CandidateRecord, RegistryWriter


def cand(run_id: uuid.UUID, cid: str, parent: str | None, stage: str) -> CandidateRecord:
    return CandidateRecord(
        id=cid,
        parent_id=parent,
        run_id=run_id,
        symbol="SPY",
        timeframe="1D",
        direction="long",
        edge_type="MR",
        spec={"id": cid},
        spec_hash=cid * 4,
        current_stage=stage,
    )


def trials(run_id: uuid.UUID, cid: str | None, n: int, family: str) -> list[dict[str, object]]:
    return [
        {
            "run_id": run_id,
            "stage": "s",
            "candidate_id": cid,
            "family_id": family,
            "spec_hash": "x",
            "params": {"i": i},
        }
        for i in range(n)
    ]


@pytest.mark.db
def test_F_0_7_2_three_generation_lineage_counts(registry_engine: Engine) -> None:
    w = RegistryWriter(registry_engine)
    run_id = w.start_run({"p": 1}, seed=1, code_version="c" * 40)
    w.upsert_candidate(cand(run_id, "G1", None, "s01"))
    w.upsert_candidate(cand(run_id, "G2", "G1", "s02"))
    w.upsert_candidate(cand(run_id, "G3", "G2", "s03"))
    w.upsert_candidate(cand(run_id, "OTHER", None, "s01"))  # unrelated branch
    with w:
        w.add_trials(trials(run_id, "G1", 40, "fam-edge"))
        w.add_trials(trials(run_id, "G2", 16, "fam-method"))
        w.add_trials(trials(run_id, "G3", 64, "fam-entry"))
        w.add_trials(trials(run_id, "OTHER", 9, "fam-edge"))
        w.add_trials(trials(run_id, None, 5, "fam-probe"))  # stage-1 probes, no candidate

    assert trial_count(registry_engine, "G3", include_lineage=False) == 64
    assert trial_count(registry_engine, "G3") == 64 + 16 + 40
    assert trial_count(registry_engine, "G2") == 16 + 40
    assert trial_count(registry_engine, "G1") == 40
    assert trial_count(registry_engine, "OTHER") == 9

    lineage = candidate_lineage(registry_engine, "G3")
    assert [r["id"] for r in lineage] == ["G1", "G2", "G3"]
    assert [r["depth"] for r in lineage] == [2, 1, 0]
    assert len(trials_by_family(registry_engine, "fam-edge")) == 49
