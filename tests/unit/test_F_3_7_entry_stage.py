"""F-3.1 ... F-3.7 and the stage wiring of ``s03_entry`` (T14 §4-§7; D-639 ... D-651).

A real stage-1 and stage-2 run on planted mean-reversion series, then stage 3 on the stage-2
selections. The cell cap is lowered (``max_cells``) so the tests stay fast; that also exercises
the coarsening of D-649.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from fixtures.edge_stage import GATES, flat_costs, synthetic_bars
from fixtures.entry_stage import entry_config_file, entry_context, stage2_run
from fixtures.screen_stage import planted_series

from strategy_factory.core.config import EngineConfig, canonical_json
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.gates.engine import GateEngine
from strategy_factory.metrics.plateau import accepted, fill_failed, select, smooth
from strategy_factory.pipeline.executor import ExecutorConfig, LocalExecutor
from strategy_factory.stages import optimize as opt
from strategy_factory.stages.optimize import (
    EntryStage,
    EntryTask,
    candidate_id,
    compute_entry,
    halves,
    stage2_selection_symbols,
)
from strategy_factory.stages.optimize_artifact import EntryOptimisation
from strategy_factory.stages.optimize_config import load_s03_config, stage_config_hash
from strategy_factory.stages.optimize_grid import fine_grid
from strategy_factory.stages.screen_artifact import MethodScreen

SYMBOLS = ("AAPL",)
FAST = {"fine_grid": {"max_cells": 300}}


def run(root: Path, *, screen: dict[str, Any] | None = None, config: dict[str, Any] | None = None,
        **kw: Any) -> tuple[Path, Any]:  # fmt: skip
    series = planted_series(SYMBOLS)
    stage2_run(root, series, SYMBOLS, **(screen or {}))
    ctx = entry_context(root, series, SYMBOLS, **kw)
    cfg = entry_config_file(root, **{**FAST, **(config or {})})
    result = EntryStage(stage_config_path=cfg).run([(s, "1D") for s in SYMBOLS], ctx)
    return root / "dry-run" / "s03_entry", result


def summaries(out: Path) -> list[EntryOptimisation]:
    return [
        EntryOptimisation.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(out.glob("*/summary.json"))
    ]


def selections(root: Path) -> list[MethodScreen]:
    out = root / "dry-run" / "s02_screen"
    rows = list(csv.DictReader((out / "index.csv").open(encoding="utf-8")))
    return [
        MethodScreen.model_validate_json(
            (out / r["candidate_id"] / "summary.json").read_text(encoding="utf-8")
        )
        for r in rows
        if r.get("selected") == "True"
    ]


@pytest.fixture(scope="module")
def entered(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any, list[EntryOptimisation]]:
    root = tmp_path_factory.mktemp("s03")
    out, result = run(root)
    return out, result, summaries(out)


# ------------------------------------------------------------------ artifacts (F-3.7, T14 §6)
def test_F_3_7_every_stage2_selection_has_a_valid_artifact(entered: Any) -> None:
    out, result, arts = entered
    root = out.parents[1]
    sel = selections(root)
    assert sel, "the planted edge must give stage-2 selections"
    assert sorted(a.identity.parent_id for a in arts) == sorted(
        s.identity.candidate_id for s in sel
    )
    cfg = load_s03_config(root / "s03.yaml")
    for a in arts:
        assert a.cells_run == 3 * a.grid.size == 3 * len(a.surface)  # D-160: 3 segments per cell
        assert a.grid.size <= 300 and a.identity.stage_config_hash == stage_config_hash(cfg)
        assert a.identity.unconfirmed is False and a.identity.control == "none"
        assert a.grid.small_grid == (a.grid.size < cfg.small_grid_cells)
        assert {s for s in a.segments} == {"whole", "h1", "h2"}
        assert a.segments["h1"].end == a.segments["h2"].start
    assert (out / "entry_optimisation.schema.json").is_file()
    rows = list(csv.DictReader((out / "index.csv").open(encoding="utf-8")))
    assert len(rows) == len(arts)
    assert sum(r["gate_passed"] == "True" for r in rows) == len(result.passed)


def test_F_3_7_the_surface_is_laid_out_in_the_declared_axis_order(entered: Any) -> None:
    """``summary.json`` sorts object keys, so the axes are a list: their order is the method's
    declaration order and the surface is in C order over them (T15 draws it from this)."""
    from strategy_factory.components.registry import default_registry

    out, _, _ = entered
    for p in out.glob("*/summary.json"):
        a = EntryOptimisation.model_validate_json(p.read_text(encoding="utf-8"))
        comp = default_registry().get(a.identity.method)
        assert [x.name for x in a.grid.axes] == [q.name for q in comp.params if q.kind != "choice"]
        cells = list(np.ndindex(a.grid.shape))
        for flat, cell in enumerate(a.surface):
            idx = cells[flat]
            for d, axis in enumerate(a.grid.axes):
                assert cell.params[axis.name] == axis.values[idx[d]]


def test_F_3_7_trades_only_for_passing_candidates(entered: Any) -> None:
    out, _, arts = entered
    for a in arts:
        assert (out / a.identity.candidate_id / "trades").exists() == a.gate_passed


def test_F_3_7_the_artifact_reports_centre_extent_and_spp(entered: Any) -> None:
    _, _, arts = entered
    for a in arts:
        if a.selection.params is None:
            continue
        centre = a.selection.params
        for name, (lo, hi) in a.selection.plateau_extent.items():
            if a.selection.plateau_cells:
                assert lo is not None and hi is not None and lo <= centre[name] <= hi
        assert a.spp.cells == a.grid.size and a.spp.low_pct == 5 and a.spp.high_pct == 95
        assert sum(c.in_plateau for c in a.surface) == a.selection.plateau_cells
        for k in a.grid.fixed:
            assert centre[k] == a.grid.stage2_median_cell[k]  # D-640


def test_F_3_7_gate_values_are_the_artifacts_numbers(entered: Any) -> None:
    _, _, arts = entered
    for a in arts:
        g = a.gate_values
        assert g["plateau_cells"] == a.selection.plateau_cells
        assert g["plateau_area"] == pytest.approx(a.selection.plateau_cells / a.grid.size)
        assert g["selected_in_both_halves"] == (1.0 if a.half2.accepted else 0.0)
        assert g["spp_median_target"] == a.spp.median
        assert g["stability_ratio"] == a.selection.stability_ratio
        assert {x.metric for x in a.gate} == set(g)


def test_F_3_3_the_selection_is_the_smoothed_half1_after_cost_maximum(entered: Any) -> None:
    """Recomputed from the artifact's own surface: fill (D-646), smooth, select (D-642)."""
    _, _, arts = entered
    for a in arts:
        shape = a.grid.shape
        t = np.array([c.cost.target[1] if c.cost.target[1] is not None else np.nan
                      for c in a.surface]).reshape(shape)  # fmt: skip
        n = np.array([c.cost.n_trades[1] for c in a.surface]).reshape(shape)
        keys = np.array([canonical_json(c.params) for c in a.surface], dtype=object).reshape(shape)
        valid = n >= a.segments["h1"].min_trades
        x, _ = fill_failed(np.where(np.isnan(t), np.inf, t), valid, "worst0")
        sel = select(smooth(x), valid, keys)
        want = None if sel is None else a.surface[int(np.ravel_multi_index(sel, shape))].params
        assert want == a.selection.params


# ------------------------------------------------------------------ the gate (F-3.7)
GOOD = {
    "spp_median_target": 0.5,
    "stability_ratio": 0.9,
    "plateau_area": 0.2,
    "plateau_cells": 12,
    "selected_in_both_halves": 1,
}


@pytest.mark.parametrize(
    ("metric", "bad"),
    [
        ("spp_median_target", -0.1),
        ("stability_ratio", 0.79),
        ("plateau_area", 0.09),
        ("plateau_cells", 2),  # D-648
        ("selected_in_both_halves", 0),
    ],
)
def test_F_3_7_each_criterion_fails_by_name_from_the_config(metric: str, bad: float) -> None:
    gates = GateEngine.from_file(GATES)
    assert gates.evaluate("s03_entry", "c", GOOD, {"timeframe": "1D"}).passed
    res = gates.evaluate("s03_entry", "c", {**GOOD, metric: bad}, {"timeframe": "1D"})
    assert [i.metric for i in res.failed()] == [metric]


def test_F_3_7_the_trade_minimum_is_stage_2s_and_the_cut_is_the_gates() -> None:
    gates = GateEngine.from_file(GATES)
    assert opt._threshold(gates, "s02_screen", opt.MIN_TRADES_METRIC, {"timeframe": "1D"}) == 30
    assert opt._threshold(gates, "s02_screen", opt.MIN_TRADES_METRIC, {"timeframe": "1H"}) == 100
    assert opt._threshold(gates, "s03_entry", opt.STABILITY_METRIC, {"timeframe": "1D"}) == 0.8


# ------------------------------------------------------------------ D-642 wiring
def test_F_3_7_d642_the_plateau_is_selected_after_costs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With heavy costs the after-cost and zero-cost surfaces disagree; the selection must follow
    the after-cost one. Swapping the surfaces in :func:`compute_entry` fails this test."""
    monkeypatch.setattr(
        opt, "_cost_arrays", lambda sym, ac, tf, bars, *a: flat_costs(bars["close"].shape[0], 0.6)
    )
    out, _ = run(tmp_path)
    arts = [a for a in summaries(out) if a.selection.params is not None]
    moved = [a for a in arts if a.zero_cost.params != a.selection.params]
    assert moved, "heavy costs must move at least one plateau"
    for a in moved:
        m = a.segments["h1"].min_trades
        best_cost = max(
            c.smoothed_h1_cost
            for c in a.surface
            if c.cost.n_trades[1] >= m and c.smoothed_h1_cost is not None
        )
        best_zero = max(
            c.smoothed_h1_zero
            for c in a.surface
            if c.zero.n_trades[1] >= m and c.smoothed_h1_zero is not None
        )
        chosen = next(c for c in a.surface if c.params == a.selection.params)
        zero = next(c for c in a.surface if c.params == a.zero_cost.params)
        assert chosen.smoothed_h1_cost == pytest.approx(best_cost)  # the after-cost maximum
        assert zero.smoothed_h1_zero == pytest.approx(best_zero)  # reported beside it
        assert chosen.smoothed_h1_zero != pytest.approx(best_zero)  # which is another cell
        assert a.zero_cost.shift_steps is not None and a.zero_cost.shift_steps > 0


# ------------------------------------------------------------------ F-3.6 / D-641: the halves
def _task(bars: dict[str, Any], method: str = "mr_n_day_low") -> EntryTask:
    good = [{"n": 5, "source": "low"}, {"n": 10, "source": "low"}]  # the fine grid: n 3 ... 20
    return EntryTask(
        candidate_id="c",
        parent_id="p",
        method=method,
        symbol="SYN",
        timeframe="1D",
        direction="long",
        grid=fine_grid(method, good, good[0]),
        bars=bars,
        costs=flat_costs(int(bars["close"].shape[0]), 0.0),
        engine=EngineConfig(),
        exits=load_s03_config().exits["MR"],
        min_trades=30,
        min_trades_half=30,
        ratio=0.8,
        failed_cell="worst0",
        spp_low=5,
        spp_high=95,
    )


def _joined(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """``a`` then ``b``'s returns continued from ``a``'s last close."""
    scale = a["close"][-1] / b["open"][0]
    out = {k: np.concatenate([a[k], b[k] * scale]) for k in ("open", "high", "low", "close")}
    out["ts"] = np.concatenate(
        [a["ts"], a["ts"][-1] + (b["ts"] - b["ts"][0]) + (b["ts"][1] - b["ts"][0])]
    )
    return out


def test_F_3_6_a_parameter_good_on_half_1_and_bad_on_half_2_fails() -> None:
    """Mean reversion in half 1, trend in half 2: the plateau found on half 1 is not in half 2's
    acceptance region."""
    mr = synthetic_bars(1400, 3, phi=-0.45)
    trend = synthetic_bars(1400, 4, phi=0.45)
    o = compute_entry(_task(_joined(mr, trend)))
    assert o.task.grid.size == 18 and o.selected is not None
    assert o.smoothed["h1_cost"][o.selected] > 0
    assert not o.half2.accepted


def test_F_3_6_half2_acceptance_on_hand_built_surfaces() -> None:
    """A parameter good on half 1 and bad on half 2 fails; one good on both passes (D-641)."""
    h1 = np.array([0.2, 1.0, 1.1, 1.0, 0.3])
    valid = np.ones(5, bool)
    x1, _ = fill_failed(h1, valid)
    sel = select(smooth(x1), valid, np.array(["a", "b", "c", "d", "e"], dtype=object))
    assert sel == (2,)
    good_h2 = np.array([0.1, 0.9, 1.0, 0.95, 0.2])
    bad_h2 = np.array([0.5, -0.2, -0.4, -0.1, 0.6])
    thin_h2 = np.array([0.0, 0.1, 1.0, 0.1, 0.0])  # positive but unstable at the cell
    for surf, want in ((good_h2, True), (bad_h2, False), (thin_h2, False)):
        x2, _ = fill_failed(surf, valid)
        assert accepted(x2, smooth(x2), valid, sel, 0.8) is want
    failed = valid.copy()
    failed[2] = False  # below the trade minimum in half 2
    x2, _ = fill_failed(good_h2, failed)
    assert accepted(x2, smooth(x2), failed, sel, 0.8) is False


def test_F_3_6_the_stage_applies_the_half2_rule(entered: Any) -> None:
    """Every artifact's half-2 verdict is D-641's rule recomputed from its own half-2 surface;
    the planted edge has candidates on both sides of it."""
    _, _, arts = entered
    verdicts = set()
    for a in arts:
        if a.selection.params is None:
            continue
        shape = a.grid.shape
        t = np.array([np.inf if c.cost.target[2] is None else c.cost.target[2] for c in a.surface])
        n = np.array([c.cost.n_trades[2] for c in a.surface])
        valid = (n >= a.segments["h2"].min_trades).reshape(shape)
        x2, _ = fill_failed(t.reshape(shape), valid)
        idx = next(np.unravel_index(i, shape) for i, c in enumerate(a.surface)
                   if c.params == a.selection.params)  # fmt: skip
        assert a.half2.accepted == accepted(x2, smooth(x2), valid, idx, 0.8)
        verdicts.add(a.half2.accepted)
    assert verdicts == {True, False}


def test_F_3_6_d641_halves_have_equal_bar_counts() -> None:
    assert halves(10) == {"whole": (0, 10), "h1": (0, 5), "h2": (5, 10)}
    assert halves(11) == {"whole": (0, 11), "h1": (0, 5), "h2": (5, 11)}


# ------------------------------------------------------------------ D-607, control, refusals
def test_F_3_7_d607_serial_and_parallel_runs_are_bit_identical(tmp_path: Path) -> None:
    serial, _ = run(tmp_path / "serial")
    parallel, _ = run(
        tmp_path / "parallel", executor=LocalExecutor(ExecutorConfig(workers=2, numba_threads=1))
    )
    a = {p.parent.name: p.read_text(encoding="utf-8") for p in serial.glob("*/summary.json")}
    b = {p.parent.name: p.read_text(encoding="utf-8") for p in parallel.glob("*/summary.json")}
    assert a and a == b
    assert (serial / "index.csv").read_text(encoding="utf-8") == (parallel / "index.csv").read_text(
        encoding="utf-8"
    )


def test_F_3_7_d651_the_control_reruns_the_real_selections_on_reshuffled_bars(
    entered: Any, tmp_path: Path
) -> None:
    _, _, real = entered
    out, _ = run(tmp_path, control="random_walk")
    ctrl = summaries(out)
    assert {a.identity.control for a in ctrl} == {"random_walk"}
    assert sorted(a.identity.parent_id for a in ctrl) == sorted(a.identity.parent_id for a in real)
    assert not {a.identity.candidate_id for a in ctrl} & {a.identity.candidate_id for a in real}
    r = {a.identity.parent_id: a for a in real}
    for a in ctrl:
        assert a.grid.axes == r[a.identity.parent_id].grid.axes  # the same fine grid
    assert any(a.surface != r[a.identity.parent_id].surface for a in ctrl)  # other bars


def test_F_3_7_a_control_stage2_run_is_refused_as_input(tmp_path: Path) -> None:
    series = planted_series(SYMBOLS)
    s02 = stage2_run(tmp_path, series, SYMBOLS)
    for p in s02.glob("*/summary.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        data["identity"]["control"] = "random_walk"
        p.write_text(json.dumps(data), encoding="utf-8")
    ctx = entry_context(tmp_path, series, SYMBOLS)
    with pytest.raises(ConfigError, match="control run"):
        EntryStage(stage_config_path=entry_config_file(tmp_path)).run([("AAPL", "1D")], ctx)


def test_F_3_7_a_moved_reference_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="moved since stage 2"):
        run(tmp_path, hashes={("AAPL", "1D"): "f" * 64})


def test_F_3_7_d645_unconfirmed_is_carried_from_stage_2(tmp_path: Path) -> None:
    out, _ = run(tmp_path, screen={"unconfirmed_timeframes": ["1D"]})
    assert {a.identity.unconfirmed for a in summaries(out)} == {True}


def test_F_3_7_d622_the_exits_are_stage_1s_and_cannot_be_restated(tmp_path: Path) -> None:
    path = entry_config_file(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["exits"] = {
        "MR": {"applicable_groups": ["x"], "exit_signal": "reverse", "time_exit_bars": 9}
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="D-622"):
        load_s03_config(path)


def test_F_3_7_d651_candidate_id_carries_parent_control_and_config() -> None:
    base = {"parent_id": "p", "control": "none", "stage_config_hash": "h"}
    ids = {candidate_id(**base)}
    for k, v in [("parent_id", "q"), ("control", "random_walk"), ("stage_config_hash", "g")]:
        ids.add(candidate_id(**{**base, k: v}))
    assert len(ids) == 4


def test_F_3_7_operational_settings_change_no_id() -> None:
    cfg = load_s03_config()
    assert stage_config_hash(cfg) == stage_config_hash(cfg.model_copy(update={"batch_units": 3}))
    assert stage_config_hash(cfg) != stage_config_hash(
        cfg.model_copy(update={"failed_cell": "zero"})
    )


# ------------------------------------------------------------------ inputs and the run command
def test_F_3_7_stage_inputs_expand_to_the_stage2_selections(entered: Any) -> None:
    out, _, _ = entered
    root = out.parents[1]
    assert stage2_selection_symbols(root, "dry-run", ["1D"]) == ("AAPL",)
    assert stage2_selection_symbols(root, "dry-run", ["1H"]) == ()


def _pipeline_yaml(path: Path, **data: Any) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_F_3_7_sfac_run_dispatches_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from strategy_factory.pipeline import stage_run

    calls: list[str] = []
    monkeypatch.setattr(stage_run, "run_stage3", lambda p, **kw: calls.append("s03"))
    s03 = _pipeline_yaml(
        tmp_path / "c.yaml",
        symbol_scope="stage_inputs",
        stage_inputs={"s02_screen": "r"},
        timeframes=["1D"],
        stages=["s03_entry"],
    )
    stage_run.run_config(s03)
    assert calls == ["s03"]


def test_F_3_7_run_stage3_refusals(
    entered: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from strategy_factory.pipeline import stage_run

    no_input = _pipeline_yaml(
        tmp_path / "a.yaml", symbols=["AAPL"], timeframes=["1D"], stages=["s03_entry"]
    )
    with pytest.raises(ConfigError, match="stage_inputs"):
        stage_run.run_stage3(no_input)
    out, _, _ = entered
    monkeypatch.setattr(stage_run, "artifacts_root", lambda: out.parents[1])
    no_sel = _pipeline_yaml(
        tmp_path / "b.yaml",
        symbol_scope="stage_inputs",
        stage_inputs={"s02_screen": "dry-run"},
        timeframes=["1H"],
        stages=["s03_entry"],
    )
    with pytest.raises(ConfigError, match="has no selection"):
        stage_run.run_stage3(no_sel)
