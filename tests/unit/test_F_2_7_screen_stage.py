"""F-2.3 / F-2.7 and the stage wiring of ``s02_screen`` (T13 §7-§9; D-622 ... D-636).

A real stage-1 run on planted mean-reversion series, then stage 2 on its passes.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from fixtures.edge_stage import GATES, flat_costs
from fixtures.screen_stage import (
    planted_series,
    screen_config_file,
    screen_context,
    stage1_run,
)

from strategy_factory.core.config import PipelineConfig, config_hash
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.gates.engine import GateEngine
from strategy_factory.metrics.family import overlap
from strategy_factory.pipeline.executor import ExecutorConfig, LocalExecutor
from strategy_factory.stages import screen as screen_mod
from strategy_factory.stages.screen import ScreenStage, candidate_id, method_cells
from strategy_factory.stages.screen_artifact import MethodScreen
from strategy_factory.stages.screen_config import load_s02_config, stage_config_hash
from strategy_factory.stats.edge import bh_qvalues

SYMBOLS = ("AAPL",)


def run(root: Path, **kw: Any) -> tuple[Path, Any]:
    series = planted_series(SYMBOLS)
    stage1_run(root, series, SYMBOLS)
    cfg_path = screen_config_file(root, **kw.pop("config", {}))
    ctx = screen_context(root, series, SYMBOLS, **kw)
    result = ScreenStage(stage_config_path=cfg_path).run([(s, "1D") for s in SYMBOLS], ctx)
    return root / "dry-run" / "s02_screen", result


def summaries(out: Path) -> list[MethodScreen]:
    return [
        MethodScreen.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(out.glob("*/summary.json"))
    ]


@pytest.fixture(scope="module")
def screened(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any, list[MethodScreen]]:
    out, result = run(tmp_path_factory.mktemp("s02"))
    return out, result, summaries(out)


def by_profile(arts: list[MethodScreen]) -> dict[str, list[MethodScreen]]:
    groups: dict[str, list[MethodScreen]] = {}
    for a in arts:
        groups.setdefault(a.identity.parent_id, []).append(a)
    return groups


# ------------------------------------------------------------------ artifacts (F-2.7, T13 §8)
def test_F_2_7_every_method_of_every_pass_has_a_valid_artifact(screened: Any) -> None:
    out, result, arts = screened
    cfg = load_s02_config(out.parents[1] / "s02.yaml")  # the config this run used
    groups = by_profile(arts)
    assert groups, "the planted edge must pass stage 1"
    for parent, mine in groups.items():
        edge = mine[0].identity.edge_type
        assert sorted(a.identity.method for a in mine) == sorted(cfg.methods_of(edge))
        for a in mine:
            assert a.cells_run == len(a.grid) == len(method_cells(a.identity.method))  # F-2.3
            assert a.identity.parent_id == parent and a.identity.unconfirmed is False
            assert a.identity.stage_config_hash == stage_config_hash(cfg)
    assert (out / "method_screen.schema.json").is_file()
    rows = list(csv.DictReader((out / "index.csv").open(encoding="utf-8")))
    assert len(rows) == len(arts)
    assert sum(r["selected"] == "True" for r in rows) == len(result.passed)


def test_F_2_7_trades_only_for_selected_methods(screened: Any) -> None:
    out, _, arts = screened
    for a in arts:
        assert (out / a.identity.candidate_id / "trades").exists() == a.selected


def test_F_2_6_selection_respects_the_cap_the_gate_and_the_overlap(screened: Any) -> None:
    _, _, arts = screened
    cfg = load_s02_config()
    for mine in by_profile(arts).values():
        chosen = [a for a in mine if a.selected]
        assert len(chosen) <= cfg.selection.max_candidates
        assert all(a.gate_passed for a in chosen)
        for a in chosen:
            assert all(v is None or v <= 0.6 for k, v in a.overlaps.items())
        ranks = sorted(a.family.rank for a in mine)
        assert ranks == list(range(1, len(mine) + 1))


def test_F_2_7_d629_method_q_is_bh_across_the_profile(screened: Any) -> None:
    _, _, arts = screened
    for mine in by_profile(arts).values():
        mine = sorted(mine, key=lambda a: a.identity.method)
        p = [a.baseline.p_value if a.baseline.p_value is not None else math.nan for a in mine]
        q = bh_qvalues(p)
        for a, qq in zip(mine, q, strict=True):
            if a.baseline.q_value is not None:
                assert a.baseline.q_value == pytest.approx(qq)
                assert a.gate_values["method_q_value"] == pytest.approx(qq)


# ------------------------------------------------------------------ the gate (F-2.7)
@pytest.mark.parametrize(
    ("metric", "bad"),
    [
        ("grid_median_target", -0.1),
        ("profitable_cell_share", 0.5),
        ("min_trades_good_cells", 12),
        ("overlap_with_selected", 0.7),
        ("method_q_value", 0.2),
    ],
)
def test_F_2_7_each_criterion_fails_by_name_from_the_config(metric: str, bad: float) -> None:
    gates = GateEngine.from_file(GATES)
    good = {
        "grid_median_target": 0.5,
        "profitable_cell_share": 0.8,
        "min_trades_good_cells": 200,
        "overlap_with_selected": 0.1,
        "method_q_value": 0.01,
    }
    assert gates.evaluate("s02_screen", "c", good, {"timeframe": "1D"}).passed
    res = gates.evaluate("s02_screen", "c", {**good, metric: bad}, {"timeframe": "1D"})
    assert [i.metric for i in res.failed()] == [metric]


def test_F_2_7_the_1h_trade_minimum_comes_from_the_override() -> None:
    gates = GateEngine.from_file(GATES)
    assert screen_mod._min_trades(gates, {"timeframe": "1D"}) == 30
    assert screen_mod._min_trades(gates, {"timeframe": "1H"}) == 100


def test_F_2_7_d623_the_gate_reads_costs_the_ranking_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wiring: with ruinous costs the family score and the rank do not move (zero-cost leg),
    while the gate's after-cost median falls. Swapping the legs fails this test."""

    def costs_with(spread: float) -> Any:
        return lambda sym, ac, tf, bars, *a: flat_costs(int(bars["close"].shape[0]), spread)

    monkeypatch.setattr(screen_mod, "_cost_arrays", costs_with(0.0))
    cheap = {a.identity.method + a.identity.direction: a for a in summaries(run(tmp_path / "a")[0])}
    monkeypatch.setattr(screen_mod, "_cost_arrays", costs_with(5.0))
    dear = {a.identity.method + a.identity.direction: a for a in summaries(run(tmp_path / "b")[0])}
    assert cheap.keys() == dear.keys()
    moved = 0
    for k, a in cheap.items():
        b = dear[k]
        assert a.family.total == b.family.total and a.family.rank == b.family.rank
        ga, gb = a.gate_values["grid_median_target"], b.gate_values["grid_median_target"]
        if ga is not None and gb is not None and gb < ga:
            moved += 1
    assert moved > len(cheap) // 2
    shares_fell = sum(
        1
        for k, a in cheap.items()
        if (a.gate_values["profitable_cell_share"] or 0)
        > (dear[k].gate_values["profitable_cell_share"] or 0)
    )
    assert shares_fell > len(cheap) // 2  # the gate's profitable share is the after-cost leg too
    assert not any(a.selected for a in dear.values())


# ------------------------------------------------------------------ D-607, control, refusals
def test_F_2_7_d607_serial_and_parallel_runs_are_bit_identical(tmp_path: Path) -> None:
    serial, _ = run(tmp_path / "serial")
    parallel, _ = run(
        tmp_path / "parallel", executor=LocalExecutor(ExecutorConfig(workers=2, numba_threads=1))
    )
    a = {p.parent.name: p.read_text(encoding="utf-8") for p in serial.glob("*/summary.json")}
    b = {p.parent.name: p.read_text(encoding="utf-8") for p in parallel.glob("*/summary.json")}
    assert a == b
    assert (serial / "index.csv").read_text(encoding="utf-8") == (parallel / "index.csv").read_text(
        encoding="utf-8"
    )


def test_F_2_7_the_control_changes_the_bars_and_the_ids(screened: Any, tmp_path: Path) -> None:
    _, _, real = screened
    out, _ = run(tmp_path, control="random_walk")
    ctrl = summaries(out)
    assert {a.identity.control for a in ctrl} == {"random_walk"}
    assert not {a.identity.candidate_id for a in ctrl} & {a.identity.candidate_id for a in real}
    r = {a.identity.method + a.identity.direction: a.grid for a in real}
    c = {a.identity.method + a.identity.direction: a.grid for a in ctrl}
    assert any(r[k] != c[k] for k in r)


def test_F_2_7_a_moved_reference_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="moved since stage 1"):
        run(tmp_path, hashes={("AAPL", "1D"): "f" * 64})


def test_F_2_7_a_control_stage1_run_is_refused_as_input(tmp_path: Path) -> None:
    series = planted_series(SYMBOLS)
    s01 = stage1_run(tmp_path, series, SYMBOLS)
    for p in s01.glob("*/summary.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        data["identity"]["control"] = "random_walk"
        p.write_text(json.dumps(data), encoding="utf-8")
    ctx = screen_context(tmp_path, series, SYMBOLS)
    with pytest.raises(ConfigError, match="control run"):
        ScreenStage(stage_config_path=screen_config_file(tmp_path)).run([("AAPL", "1D")], ctx)


def test_F_2_7_d628_unconfirmed_timeframes_are_flagged(tmp_path: Path) -> None:
    out, _ = run(tmp_path, config={"unconfirmed_timeframes": ["1D"]})
    assert {a.identity.unconfirmed for a in summaries(out)} == {True}


def test_F_2_7_d622_the_exits_are_stage_1s_and_cannot_be_restated(tmp_path: Path) -> None:
    cfg = load_s02_config()
    assert (
        cfg.exits["MR"].exit_signal == "prev_extreme" and cfg.exits["TF"].exit_signal == "reverse"
    )
    path = screen_config_file(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["exits"] = {
        "MR": {"applicable_groups": ["x"], "exit_signal": "reverse", "time_exit_bars": 9}
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="D-622"):
        load_s02_config(path)


def test_F_2_7_the_config_cannot_lose_a_method(tmp_path: Path) -> None:
    path = screen_config_file(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["methods"]["MR"] = [m for m in data["methods"]["MR"] if m != "mr_rsi"]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="mr_rsi"):
        load_s02_config(path)


def test_F_2_7_d636_candidate_id_carries_parent_method_control_and_config() -> None:
    base = {"parent_id": "p", "method": "mr_rsi", "control": "none", "stage_config_hash": "h"}
    ids = {candidate_id(**base)}
    for k, v in [
        ("parent_id", "q"),
        ("method", "mr_ibs"),
        ("control", "random_walk"),
        ("stage_config_hash", "g"),
    ]:
        ids.add(candidate_id(**{**base, k: v}))
    assert len(ids) == 5


def test_F_2_7_operational_settings_change_no_id() -> None:
    """``batch_units`` changes no number (D-607), so it must not change the hash or the ids."""
    cfg = load_s02_config()
    assert stage_config_hash(cfg) == stage_config_hash(cfg.model_copy(update={"batch_units": 7}))
    other = cfg.model_copy(update={"good_region_share": 0.5})
    assert stage_config_hash(cfg) != stage_config_hash(other)


# ------------------------------------------------------------------ inputs and the run command
def test_F_2_7_stage_inputs_expand_to_the_stage1_passes(tmp_path: Path) -> None:
    series = planted_series(("AAPL", "MSFT"))
    stage1_run(tmp_path, series, ("AAPL", "MSFT"))
    rows = list(
        csv.DictReader((tmp_path / "dry-run" / "s01_edge" / "index.csv").open(encoding="utf-8"))
    )
    passing = sorted({r["symbol"] for r in rows if r["passed"] == "True"})
    assert passing  # the planted edge passes stage 1
    assert list(screen_mod.stage1_pass_symbols(tmp_path, "dry-run", ["1D"])) == passing
    assert screen_mod.stage1_pass_symbols(tmp_path, "dry-run", ["1H"]) == ()


def _pipeline_yaml(path: Path, **data: Any) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_F_2_7_sfac_run_dispatches_by_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from strategy_factory.pipeline import stage_run

    calls: list[str] = []
    monkeypatch.setattr(stage_run, "run_stage1", lambda p, **kw: calls.append("s01"))
    monkeypatch.setattr(stage_run, "run_stage2", lambda p, **kw: calls.append("s02"))
    s01 = _pipeline_yaml(
        tmp_path / "a.yaml", symbols=["AAPL"], timeframes=["1D"], stages=["s01_edge"]
    )
    s02 = _pipeline_yaml(
        tmp_path / "b.yaml",
        symbol_scope="stage_inputs",
        stage_inputs={"s01_edge": "r"},
        timeframes=["1D"],
        stages=["s02_screen"],
    )
    stage_run.run_config(s01)
    stage_run.run_config(s02)
    assert calls == ["s01", "s02"]


def test_F_2_7_run_stage2_refusals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from strategy_factory.pipeline import stage_run

    no_input = _pipeline_yaml(
        tmp_path / "a.yaml", symbols=["AAPL"], timeframes=["1D"], stages=["s02_screen"]
    )
    with pytest.raises(ConfigError, match="stage_inputs"):
        stage_run.run_stage2(no_input)
    series = planted_series(SYMBOLS)
    stage1_run(tmp_path, series, SYMBOLS)
    monkeypatch.setattr(stage_run, "artifacts_root", lambda: tmp_path)
    no_pass = _pipeline_yaml(
        tmp_path / "b.yaml",
        symbol_scope="stage_inputs",
        stage_inputs={"s01_edge": "dry-run"},
        timeframes=["1H"],
        stages=["s02_screen"],
    )
    with pytest.raises(ConfigError, match="has no pass"):
        stage_run.run_stage2(no_pass)


# ------------------------------------------------------------------ stage inputs in the config
def test_F_0_8_2_stage_inputs_keep_old_hashes_and_enter_new_ones() -> None:
    """``stage_inputs`` is left out of the canonical JSON when empty (every hash written before
    T13 stays valid) and is part of the hash when set (rule 8)."""
    base = PipelineConfig(symbols=("AAPL",), timeframes=("1D",), stages=("s01_edge",))
    assert "stage_inputs" not in base.canonical()
    staged = base.model_copy(update={"stage_inputs": {"s01_edge": "run-1"}})
    other = base.model_copy(update={"stage_inputs": {"s01_edge": "run-2"}})
    assert len({config_hash(base), config_hash(staged), config_hash(other)}) == 3
    with pytest.raises(ValueError, match="stage_inputs"):
        PipelineConfig(timeframes=("1D",), stages=("s02_screen",), symbol_scope="stage_inputs")


def test_F_2_7_positions_feed_the_overlap(screened: Any) -> None:
    _, _, arts = screened
    walked = [a for a in arts if a.overlap_with_selected is not None]
    assert walked and all(0.0 <= a.overlap_with_selected <= 1.0 for a in walked)  # type: ignore[operator]
    assert overlap(np.ones(3, bool), np.ones(3, bool)) == 1.0
