"""The stage's wiring of the decisions, each by a test that fails if the wiring breaks.

The acceptance reviewer broke each of these in memory and every earlier test still passed:
* D-613 (3): consistency subtracts the baseline **per year** and excludes thin years;
* D-602: the profit factor comes from the **full-cost** run, not the zero-cost one;
* D-614 (1): the 3-ATR disaster stop is **on** for every probe;
* D-615: a ``random_walk`` control really runs on permuted data.
Plus D-354 (1) (a parity setting is refused, not ignored), the non-USD skip (P-105), and
``sfac run`` refusing anything but stage 1 (D-616).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fixtures.edge_stage import (
    GATES,
    FakeData,
    FakeReferences,
    flat_costs,
    make_task,
    resolved_config,
    stage_config,
    synthetic_bars,
)

from strategy_factory.core.config import EngineConfig
from strategy_factory.core.errors import ConfigError
from strategy_factory.gates.engine import GateEngine
from strategy_factory.metrics.standard import profit_factor
from strategy_factory.pipeline.executor import SerialExecutor
from strategy_factory.stages.base import RunContext
from strategy_factory.stages.edge import EdgeStage, _consistency, compute_profile, probe_run

PLANTED = synthetic_bars(2000, 1, phi=-0.35)


# -- D-613 (3): consistency, by hand ------------------------------------------------------------
def test_F_1_5_d613_consistency_subtracts_the_baseline_per_year_and_drops_thin_years() -> None:
    years = np.array([2020] * 6 + [2021] * 6 + [2022] * 2 + [2023] * 6)
    probe = np.array([1.0] * 6 + [0.5] * 6 + [9.0] * 2 + [0.2] * 6)
    base_years = np.array([2020] * 3 + [2021] * 3 + [2022] * 3)  # no baseline trade in 2023
    base = np.array([0.5] * 3 + [0.8] * 3 + [0.0] * 3)
    share, counted, excluded = _consistency(probe, years, base, base_years, range(2019, 2024), 5)
    # 2020: 1.0 - 0.5 > 0 (positive); 2021: 0.5 - 0.8 < 0 (not);
    # 2022: 2 probe trades < 5 (excluded, however large); 2023: no baseline trades (excluded);
    # 2019: no probe trades (excluded). Without the per-year baseline 2021 would be positive.
    assert (counted, excluded) == (2, 3)
    assert share == pytest.approx(0.5)


def test_F_1_5_d613_consistency_without_a_countable_year_is_missing() -> None:
    share, counted, excluded = _consistency(
        np.array([1.0]), np.array([2020]), np.array([0.0]), np.array([2020]), range(2020, 2021), 5
    )
    assert np.isnan(share) and (counted, excluded) == (0, 1)


# -- D-602: the profit factor is after costs ------------------------------------------------------
def test_F_1_5_d602_profit_factor_comes_from_the_full_cost_run() -> None:
    task = make_task(PLANTED, cfg=stage_config(simulations=50))
    task = task.__class__(**{**task.__dict__, "costs": flat_costs(len(PLANTED["close"]), 0.2)})
    prof = compute_profile(task).profile
    spec = task.stage.edge_types["MR"]
    for p in prof.probes[:3]:
        costly = probe_run(PLANTED, p.name, p.params, spec, "long", task.engine, task.costs)
        free = probe_run(PLANTED, p.name, p.params, spec, "long", task.engine)
        assert p.profit_factor == pytest.approx(profit_factor(costly.pnl_net))
        assert profit_factor(costly.pnl_net) < profit_factor(free.pnl_net)  # costs bite


# -- D-614 (1): the disaster stop is on for every probe ------------------------------------------
def violent(n: int = 1500) -> dict:
    """Ordinary bars with rare overnight gaps of +-12 % (far beyond 3 ATR of a ~1 % ATR), so
    some probe trades are stopped out -- widening every bar would only widen the ATR too."""
    bars = synthetic_bars(n, 5, phi=-0.3)
    rng = np.random.default_rng(9)
    gaps = np.zeros(n)
    at = rng.choice(np.arange(50, n), size=n // 40, replace=False)
    gaps[at] = rng.choice([-0.12, 0.12], size=at.size)
    scale = np.exp(np.cumsum(gaps))
    for col in ("open", "high", "low", "close"):
        bars[col] = bars[col] * scale  # each bar keeps its shape; the gap opens the bar
    return bars


def test_F_1_5_d614_the_disaster_stop_fires_on_probes() -> None:
    cfg = stage_config(simulations=20)
    shares = [
        p.disaster_share for p in compute_profile(make_task(violent(), cfg=cfg)).profile.probes
    ]
    assert max(s for s in shares if s is not None) > 0.0
    far = make_task(violent(), cfg=cfg)
    far = far.__class__(**{**far.__dict__, "engine": EngineConfig(disaster_stop_atr=1e6)})
    assert all(not s for s in (p.disaster_share for p in compute_profile(far).profile.probes))


# -- the stage end to end: the control, D-354 (1), the non-USD skip ------------------------------
def context(
    tmp_path: Path, symbols: tuple[str, ...], control: str = "none", **cfg_update: object
) -> RunContext:
    cfg = resolved_config(symbols, control=control).model_copy(update=cfg_update)
    return RunContext(
        config=cfg,
        data=FakeData({(s, "1D"): synthetic_bars(900, i, phi=-0.3) for i, s in enumerate(symbols)}),  # type: ignore[arg-type]
        references=FakeReferences(  # type: ignore[arg-type]
            {(s, "1D"): cfg.data_snapshots[s]["1D"].snapshot_hash for s in symbols}
        ),
        executor=SerialExecutor(),
        gates=GateEngine.from_file(GATES),
        artifacts_root=tmp_path,
        code_version="test",
    )


def summaries(root: Path) -> dict[str, dict]:
    import json

    return {
        f.parent.name: json.loads(f.read_text(encoding="utf-8"))
        for f in (root / "dry-run" / "s01_edge").glob("*/summary.json")
    }


def stage_file(tmp_path: Path) -> Path:
    import yaml

    path = tmp_path / "s01.yaml"
    path.write_text(
        yaml.safe_dump(stage_config(simulations=30).model_dump(mode="json")), encoding="utf-8"
    )
    return path


def test_F_1_5_d615_the_random_walk_control_runs_on_permuted_data(tmp_path: Path) -> None:
    sfile = stage_file(tmp_path)
    EdgeStage(stage_config_path=sfile).run([("AAPL", "1D")], context(tmp_path / "real", ("AAPL",)))
    EdgeStage(stage_config_path=sfile).run(
        [("AAPL", "1D")], context(tmp_path / "ctrl", ("AAPL",), control="random_walk")
    )
    real, ctrl = summaries(tmp_path / "real"), summaries(tmp_path / "ctrl")
    assert len(real) == len(ctrl) == 4 and not set(real) & set(ctrl)  # distinct candidate ids
    means = lambda s: sorted(p["mean_atr"] or 0.0 for d in s.values() for p in d["probes"])  # noqa: E731
    assert means(real) != means(ctrl)
    assert {d["identity"]["control"] for d in ctrl.values()} == {"random_walk"}


@pytest.mark.parametrize(
    "update",
    [
        {"intrabar_mode": "tradingview"},
        {"engine": EngineConfig(entry_requires_flat_at_signal=True)},
    ],
)
def test_F_1_5_d354_a_parity_setting_is_refused_not_ignored(tmp_path: Path, update: dict) -> None:
    with pytest.raises(ConfigError, match="research settings only"):
        EdgeStage().run([("AAPL", "1D")], context(tmp_path, ("AAPL",), **update))


def test_F_1_9_a_non_usd_symbol_is_listed_as_skipped_not_fatal(tmp_path: Path) -> None:
    """USDJPY is quoted in JPY: stage 1 has no conversion arrays wired in yet (P-105)."""
    res = EdgeStage(stage_config_path=stage_file(tmp_path)).run(
        [("USDJPY", "1D"), ("AAPL", "1D")], context(tmp_path, ("USDJPY", "AAPL"))
    )
    rows = (
        (tmp_path / "dry-run" / "s01_edge" / "index.csv").read_text(encoding="utf-8").splitlines()
    )
    skipped = [r for r in rows if r.startswith("USDJPY")]
    assert len(skipped) == 1 and "quote currency JPY" in skipped[0]
    assert res.summary["1D"]["profiles"] == 4 and res.summary["1D"]["skipped"] == 1  # AAPL ran


def test_F_1_9_d616_sfac_run_refuses_anything_but_stage_1(tmp_path: Path) -> None:
    from strategy_factory.pipeline.stage_run import run_stage1

    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        "symbols: [AAPL]\ntimeframes: [1D]\nstages: [s01_edge, s02_screen]\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="stage 1 only"):
        run_stage1(cfg)
