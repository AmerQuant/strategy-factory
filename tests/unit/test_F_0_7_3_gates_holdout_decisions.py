"""F-0.7.3: gate results, one-shot holdout (DB-enforced), decisions with a reason."""

from __future__ import annotations

import uuid

import pytest
from fixtures.registry_db import RUN_CONFIG
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError

from strategy_factory.core.errors import HoldoutAccessError, RegistryError
from strategy_factory.registry import tables as T
from strategy_factory.registry.queries import gate_history
from strategy_factory.registry.writer import CandidateRecord, GateResultRecord, RegistryWriter


def setup_candidate(engine: Engine) -> tuple[RegistryWriter, uuid.UUID]:
    w = RegistryWriter(engine)
    run_id = w.start_run(RUN_CONFIG, seed=1, code_version="c" * 40)
    w.upsert_candidate(
        CandidateRecord(
            id="C1",
            run_id=run_id,
            symbol="SPY",
            timeframe="1D",
            direction="short",
            edge_type="TF",
            spec={},
            spec_hash="h",
            current_stage="s06",
        )
    )
    return w, run_id


@pytest.mark.db
def test_F_0_7_3_gate_results_stored_with_all_fields(registry_engine: Engine) -> None:
    w, run_id = setup_candidate(registry_engine)
    common = {"run_id": run_id, "candidate_id": "C1", "stage": "s06_robust", "critical": True}
    rows = [
        GateResultRecord(
            **common,
            criterion="wf_efficiency",
            metric_value=0.62,
            op=">=",
            threshold=0.5,
            passed=True,
            reason="ok",
        ),
        GateResultRecord(
            **common,
            criterion="cost_x2_ratio",
            metric_value=None,
            op=">",
            threshold=1.0,
            passed=False,
            reason="not computable: 0 trades",
        ),
    ]
    w.add_gate_results(rows)
    hist = gate_history(registry_engine, "C1")
    assert len(hist) == 2
    for stored, rec in zip(hist, rows, strict=True):
        for field, value in rec.model_dump().items():
            assert stored[field] == value, field
        assert stored["created_at"] is not None


@pytest.mark.db
def test_F_0_7_3_second_holdout_access_raises_even_from_another_connection(
    registry_engine: Engine, second_engine: Engine
) -> None:
    w, _ = setup_candidate(registry_engine)
    w.record_holdout_access("C1", {"net_profit": 12.5})
    with pytest.raises(HoldoutAccessError, match="already accessed") as exc:
        RegistryWriter(second_engine).record_holdout_access("C1", {"net_profit": 99.0})
    assert exc.value.stage == "holdout"
    # the constraint itself (not Python state) blocks it: a raw insert also fails
    with pytest.raises(IntegrityError), second_engine.begin() as conn:
        conn.execute(insert(T.holdout_access).values(candidate_id="C1", result={}))


@pytest.mark.db
def test_F_0_7_3_decision_needs_a_reason(registry_engine: Engine) -> None:
    w, _ = setup_candidate(registry_engine)
    for bad in ("", "   "):
        with pytest.raises(RegistryError, match="non-empty reason"):
            w.add_decision("C1", "analyst-a", "reject", bad)
    with pytest.raises(RegistryError, match="return_to_stage"):
        w.add_decision("C1", "analyst-a", "return", "redo robustness")
    # the CHECK constraint enforces it in the database too
    with pytest.raises(IntegrityError), registry_engine.begin() as conn:
        conn.execute(
            insert(T.decisions).values(
                candidate_id="C1", analyst="a", decision="reject", reason=" "
            )
        )
    assert w.add_decision("C1", "analyst-a", "approve", "all gates passed") > 0
