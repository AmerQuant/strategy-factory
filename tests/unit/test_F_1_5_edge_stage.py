"""F-1.5 / F-1.8 / F-1.9 and D-601 … D-617: stage 1 end to end on synthetic series.

* a planted mean-reversion edge scores high, a random walk sits near the middle (F-1.5);
* every gate criterion, failed in turn, is named, and its threshold comes from the config
  (F-1.8, F-0.8.1, rule 1);
* probes_run equals the probes evaluated (D-605); excess and consistency follow D-613;
* trades are kept only for the accepted probes of passing profiles (D-608);
* the same seed reproduces every number; serial and parallel runs are bit-identical (D-607);
* the artifacts validate against the EdgeProfile schema (F-1.9), and a series too short for a
  split is skipped and listed, not profiled.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from fixtures.edge_stage import (
    GATES,
    FakeData,
    FakeReferences,
    make_task,
    resolved_config,
    stage_config,
    synthetic_bars,
)

from strategy_factory.gates.engine import GateEngine
from strategy_factory.pipeline.executor import ExecutorConfig, LocalExecutor, SerialExecutor
from strategy_factory.stages.base import RunContext
from strategy_factory.stages.edge import EdgeStage, compute_profile
from strategy_factory.stages.edge_profile import EdgeProfile

PLANTED = synthetic_bars(2000, 1, phi=-0.35)
WALK = synthetic_bars(2000, 1, phi=0.0)


@pytest.fixture(scope="module")
def planted() -> Any:
    return compute_profile(make_task(PLANTED))


@pytest.fixture(scope="module")
def walk() -> Any:
    return compute_profile(make_task(WALK))


# -- F-1.5: planted edge high, random walk near the middle ------------------------------------
def test_F_1_5_a_planted_mean_reversion_edge_scores_high(planted: Any) -> None:
    prof = planted.profile
    pct = [p.percentile for p in prof.probes if p.percentile is not None]
    assert np.median(pct) >= 95
    assert prof.profile.passed and prof.profile.ess["total"] >= 50
    assert len(prof.profile.accepted_groups) >= 3


def test_F_1_5_a_random_walk_sits_near_the_middle(walk: Any) -> None:
    prof = walk.profile
    pct = [p.percentile for p in prof.probes if p.percentile is not None]
    assert 20 <= np.median(pct) <= 80
    assert not prof.profile.passed and prof.profile.ess["total"] < 50


def test_F_1_5_trend_probes_do_not_see_a_mean_reversion_edge() -> None:
    """The long drift-free MR series gives TF probes nothing (percentiles not high)."""
    prof = compute_profile(make_task(PLANTED, edge_type="TF")).profile
    assert not prof.profile.passed
    assert prof.probes_run == 8 and {p.group for p in prof.probes} >= {"ma", "ichimoku"}


# -- D-605 / D-613: the statistics ------------------------------------------------------------
def test_F_1_5_d605_probes_run_counts_every_probe_evaluated(planted: Any) -> None:
    prof = planted.profile
    assert prof.probes_run == len(prof.probes) == 9
    assert sorted(p.name for p in prof.probes) == sorted(stage_config().probes_of("MR"))


def test_F_1_5_d613_excess_is_the_mean_minus_the_probes_own_baseline(planted: Any) -> None:
    for p in planted.profile.probes:
        assert p.excess_atr == pytest.approx(p.mean_atr - p.baseline_mean_atr)
        # 2000 consecutive calendar days from 2012-01-02 end in 2017: six calendar years
        assert p.years_counted + p.years_excluded == 6
        assert 0.0 <= p.positive_year_share <= 1.0


def test_F_1_5_d613_the_ess_medians_run_over_every_probe(planted: Any) -> None:
    prof = planted.profile
    excess = [p.excess_atr for p in prof.probes]
    assert prof.profile.ess["raw"]["magnitude"] == pytest.approx(float(np.median(excess)))


# -- F-1.8: every criterion, failed in turn, is named; thresholds from the config --------------
def gates_with(tmp_path: Path, stage: str, metric: str, threshold: float) -> Path:
    data = yaml.safe_load(GATES.read_text(encoding="utf-8"))
    for crit in data["stages"][stage]:
        if crit["metric"] == metric:
            crit["threshold"] = threshold
    path = tmp_path / f"{stage}_{metric}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("stage", "metric", "threshold"),
    [
        ("s01_probe", "n_trades", 10_000),
        ("s01_probe", "probe_percentile", 100.5),
        ("s01_probe", "profit_factor", 100.0),
        ("s01_probe", "probe_q_value", 0.0),
        ("s01_edge", "accepted_probe_groups", 99),
        ("s01_edge", "ess", 100.5),
    ],
)
def test_F_1_8_each_criterion_fails_by_name_from_the_config(
    tmp_path: Path, stage: str, metric: str, threshold: float
) -> None:
    out = compute_profile(make_task(PLANTED, gates=gates_with(tmp_path, stage, metric, threshold)))
    prof = out.profile
    assert not prof.profile.passed  # the planted edge passes with the repo gates
    if stage == "s01_probe":
        assert all(metric in p.failed_criteria for p in prof.probes)
        assert not any(p.accepted for p in prof.probes)
    else:
        failed = [g.metric for g in prof.profile.gate if not g.passed]
        assert failed == [metric]
        line = next(g for g in prof.profile.gate if g.metric == metric)
        assert line.threshold == threshold  # rule 1: the number came from the file


# -- D-608: trades for the accepted probes of passing profiles only ----------------------------
def test_F_1_9_d608_trades_only_for_accepted_probes_of_passing_profiles(
    planted: Any, walk: Any
) -> None:
    accepted = {p.name for p in planted.profile.probes if p.accepted}
    assert set(planted.trades) == accepted and accepted
    assert walk.trades == {}


# -- D-607: reproducible, seeded per probe ------------------------------------------------------
def test_F_1_5_d607_the_same_seed_reproduces_every_number(planted: Any) -> None:
    again = compute_profile(make_task(PLANTED)).profile
    assert again.model_dump_json() == planted.profile.model_dump_json()
    other = compute_profile(make_task(PLANTED, run_seed=43)).profile
    assert [p.baseline_mean_atr for p in other.probes] != [
        p.baseline_mean_atr for p in planted.profile.probes
    ]


# -- the stage end to end: artifacts, index, skips, serial vs parallel -------------------------
def run_stage(tmp_path: Path, executor: Any, symbols: tuple[str, ...] = ("AAPL", "MSFT")) -> Path:
    cfg = resolved_config(symbols)
    series = {
        (s, "1D"): synthetic_bars(1200, i, phi=-0.35 if i == 0 else 0.0)
        for i, s in enumerate(symbols)
    }
    refs = FakeReferences(
        {(s, "1D"): cfg.data_snapshots[s]["1D"].snapshot_hash for s in symbols},
        quality={(symbols[-1], "1D"): "warning"},
    )
    ctx = RunContext(
        config=cfg,
        data=FakeData(series),  # type: ignore[arg-type]
        references=refs,  # type: ignore[arg-type]
        executor=executor,
        gates=GateEngine.from_file(GATES),
        artifacts_root=tmp_path,
        code_version="test",
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    stage = EdgeStage(stage_config_path=tmp_path / "s01.yaml", batch_units=3)
    stage_cfg = stage_config(simulations=100)
    (tmp_path / "s01.yaml").write_text(
        yaml.safe_dump(stage_cfg.model_dump(mode="json")), encoding="utf-8"
    )
    stage.run([(s, "1D") for s in symbols], ctx)
    return tmp_path / "dry-run" / "s01_edge"


def test_F_1_9_the_stage_writes_valid_profiles_and_the_index(tmp_path: Path) -> None:
    out = run_stage(tmp_path / "a", SerialExecutor())
    summaries = sorted(out.glob("*/summary.json"))
    assert len(summaries) == 2 * 2 * 2  # symbols x edge types x directions (D-604)
    for path in summaries:
        prof = EdgeProfile.model_validate_json(path.read_text(encoding="utf-8"))
        assert prof.schema_version == "1" and prof.probes_run in (8, 9)
    schema = json.loads((out / "edge_profile.schema.json").read_text(encoding="utf-8"))
    assert schema["title"] == "EdgeProfile"
    index = (out / "index.csv").read_text(encoding="utf-8").splitlines()
    assert len(index) == 1 + 8
    assert any(",warning," in row for row in index)  # D-610: the caveat reaches the index


def test_F_1_9_a_series_too_short_for_a_split_is_listed_not_profiled(tmp_path: Path) -> None:
    cfg = resolved_config(("AAPL",))
    ctx = RunContext(
        config=cfg,
        data=FakeData({("AAPL", "1D"): synthetic_bars(300, 0)}, too_short={("AAPL", "1D")}),  # type: ignore[arg-type]
        references=FakeReferences({("AAPL", "1D"): cfg.data_snapshots["AAPL"]["1D"].snapshot_hash}),  # type: ignore[arg-type]
        executor=SerialExecutor(),
        gates=GateEngine.from_file(GATES),
        artifacts_root=tmp_path,
        code_version="test",
    )
    res = EdgeStage().run([("AAPL", "1D")], ctx)
    rows = (
        (tmp_path / "dry-run" / "s01_edge" / "index.csv").read_text(encoding="utf-8").splitlines()
    )
    assert len(rows) == 2 and ",skipped," in rows[1] and "D-008" in rows[1]
    assert res.summary["1D"] == {"profiles": 0, "passed": 0, "skipped": 1}


def test_F_1_9_a_moved_reference_is_refused(tmp_path: Path) -> None:
    from strategy_factory.core.errors import DataError

    cfg = resolved_config(("AAPL",))
    ctx = RunContext(
        config=cfg,
        data=FakeData({("AAPL", "1D"): synthetic_bars(600, 0)}),  # type: ignore[arg-type]
        references=FakeReferences({("AAPL", "1D"): "f" * 64}),  # type: ignore[arg-type]
        executor=SerialExecutor(),
        gates=GateEngine.from_file(GATES),
        artifacts_root=tmp_path,
        code_version="test",
    )
    with pytest.raises(DataError, match="reference moved"):
        EdgeStage().run([("AAPL", "1D")], ctx)


def test_F_1_5_d607_serial_and_parallel_runs_are_bit_identical(tmp_path: Path) -> None:
    serial = run_stage(tmp_path / "serial", SerialExecutor())
    parallel = run_stage(
        tmp_path / "parallel", LocalExecutor(ExecutorConfig(workers=2, numba_threads=1))
    )
    a = {p.relative_to(serial): p.read_bytes() for p in serial.rglob("*") if p.is_file()}
    b = {p.relative_to(parallel): p.read_bytes() for p in parallel.rglob("*") if p.is_file()}
    assert a.keys() == b.keys() and a == b
