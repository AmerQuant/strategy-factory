"""F-0.8.1 / D-309: one registry of metric names, and the gate YAML validated against it.

Also covers the D-333 gate-YAML renames (``min_trades`` -> ``n_trades``,
``mc_dd95_within_tolerance == 1`` -> ``mc_max_dd_p95_pct <= 25``, D-308) and the five T08
run-meta names (D-345).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from fixtures.metrics_runs import hand_run

from strategy_factory.core.errors import ConfigError
from strategy_factory.gates.engine import (
    GateConfig,
    GateEngine,
    load_gate_config,
    metrics_used,
    validate_metric_names,
)
from strategy_factory.metrics import names as metric_names
from strategy_factory.metrics.batch import core_metrics_batch
from strategy_factory.metrics.standard import MetricsReport, compute_metrics

REPO = Path(__file__).resolve().parents[2]
REPO_GATES = REPO / "configs" / "gates" / "default.yaml"
FX_1D = {"asset_class": "fx", "timeframe": "1D"}
T08_NAMES = (
    "n_skipped_min_volume",
    "min_volume_skip_flag",
    "volume_step_assumed",
    "contracts_fixed",
    "fx_peg",
)


# -- the registry itself --------------------------------------------------------------------
def test_F_0_8_1_registry_entries_are_complete_and_unique() -> None:
    reg = metric_names.registry()
    assert len(reg) == len(metric_names.names())
    for name, entry in reg.items():
        assert entry.name == name
        assert entry.unit in metric_names.UNITS
        assert entry.description.strip()
        assert entry.producers and entry.producer == entry.producers[0]
        assert len(set(entry.producers)) == len(entry.producers)
    assert metric_names.is_registered("profit_dd_ratio")
    assert not metric_names.is_registered("nope")
    with pytest.raises(KeyError):
        metric_names.get("nope")
    assert metric_names.unknown(["profit_dd_ratio", "nope", "also_nope"]) == ["also_nope", "nope"]


def test_F_0_8_1_core_producer_equals_as_gate_dict() -> None:
    """``metrics.core`` is exactly the ``as_gate_dict()`` key set -- no more, no less."""
    gate_dict = compute_metrics(hand_run(), calendar="us_equity").as_gate_dict()
    core = metric_names.by_producer(metric_names.CORE)
    assert set(gate_dict) == core
    assert set(MetricsReport.model_fields) == core  # a new field must be registered
    for name in T08_NAMES:  # D-345
        assert name in core and metric_names.get(name).producer == metric_names.CORE


def test_F_0_8_1_batch_producer_equals_the_batch_keys() -> None:
    n = 60
    ts = np.array([np.datetime64("2024-01-01", "ns")] * n) + np.arange(n) * np.timedelta64(1, "D")
    equity = np.tile(np.linspace(100_000.0, 101_000.0, n), (3, 1)).T
    in_pos = np.ones((n, 3), dtype=np.bool_)
    table = core_metrics_batch(equity, in_pos, np.array([5, 6, 7]), ts, 100_000.0)
    batch = metric_names.by_producer(metric_names.BATCH)
    assert set(table) == batch
    assert batch < metric_names.by_producer(metric_names.CORE)  # the grid path is a subset


def test_F_0_8_1_stage_metrics_have_their_producing_stage() -> None:
    for name, stage in (
        ("ess", "s01_edge"),
        ("probe_percentile", "s01_probe"),
        ("probe_q_value", "s01_probe"),  # D-605
        ("grid_median_target", "s02_screen"),
        ("plateau_area", "s03_entry"),
        ("q_value", "s01s_seasonal"),
        ("free_params_total", "s04_exit"),
        ("filter_count", "s05_filter"),
        ("mc_max_dd_p95_pct", "s06_robust"),
        ("dsr", "s07_stats"),
    ):
        assert metric_names.get(name).producers == (stage,)


# -- the gate YAML is validated against the registry (D-309) --------------------------------
def test_F_0_8_1_every_metric_of_the_repo_gates_is_registered() -> None:
    cfg = load_gate_config(REPO_GATES)
    used = metrics_used(cfg)
    assert metric_names.unknown(used) == []
    assert used["n_trades"] == ["s01_probe", "timeframe:1H/s01_probe"]
    assert used["mc_max_dd_p95_pct"] == ["s06_robust"]


@pytest.mark.parametrize(
    "patch",
    [
        {"stages": {"s01_edge": [{"metric": "typo_metric", "op": ">=", "threshold": 1}]}},
        {
            "overrides": {
                "timeframe": {
                    "1H": {"s01_probe": [{"metric": "typo_metric", "op": ">=", "threshold": 1}]}
                }
            }
        },
        {
            "overrides": {
                "asset_class": {
                    "fx": {"s01_edge": [{"metric": "typo_metric", "op": ">=", "threshold": 1}]}
                }
            }
        },
        {
            "overrides": {
                "combined": {
                    "fx/1H": {"s01_edge": [{"metric": "typo_metric", "op": ">=", "threshold": 1}]}
                }
            }
        },
    ],
)
def test_F_0_8_1_unknown_metric_in_base_or_override_fails_at_load(
    tmp_path: Path, patch: dict[str, object]
) -> None:
    data = yaml.safe_load(REPO_GATES.read_text(encoding="utf-8"))
    for key, value in patch.items():
        target = data.setdefault(key, {})
        for sub, stages in value.items():  # type: ignore[union-attr]
            if key == "stages":
                target[sub] = stages
            else:
                target.setdefault(sub, {}).update(stages)
    path = tmp_path / "gates.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match=r"unknown metric.*typo_metric"):
        load_gate_config(path)


def test_F_0_8_1_config_built_in_code_is_not_registry_checked() -> None:
    """Synthetic names stay usable in code; only *loading* a YAML validates (D-309)."""
    cfg = GateConfig.model_validate(
        {"stages": {"s": [{"metric": "a", "op": ">=", "threshold": 1}]}}
    )
    assert GateEngine(cfg).evaluate("s", "C", {"a": 2}, FX_1D).passed
    with pytest.raises(ConfigError, match="unknown metric"):
        validate_metric_names(cfg)


# -- the renames (D-333, D-301, D-308) -- CRITICAL -------------------------------------------
def test_F_0_8_1_d333_min_trades_renamed_to_n_trades() -> None:
    e = GateEngine(load_gate_config(REPO_GATES))
    base = {c.metric: (c.op, c.threshold) for c in e.criteria("s01_probe", FX_1D)}
    assert base["n_trades"] == (">=", 30)
    assert "min_trades" not in base
    one_h = {c.metric: c.threshold for c in e.criteria("s01_probe", {"timeframe": "1H"})}
    assert one_h["n_trades"] == 100 and "min_trades" not in one_h
    # the gate reads the closed-trade count of the metrics report (D-301)
    run = hand_run()
    report = compute_metrics(run, calendar="us_equity")
    assert report.as_gate_dict()["n_trades"] == float(len(run.trades))


@pytest.mark.parametrize(
    ("value", "passed"), [(0.0, True), (24.9, True), (25.0, True), (25.1, False), (99.0, False)]
)
def test_F_0_8_1_d308_monte_carlo_drawdown_criterion(value: float, passed: bool) -> None:
    e = GateEngine(load_gate_config(REPO_GATES))
    crit = {c.metric: c for c in e.criteria("s06_robust", FX_1D)}
    assert "mc_dd95_within_tolerance" not in crit
    mc = crit["mc_max_dd_p95_pct"]
    assert (mc.op, mc.threshold, mc.critical) == ("<=", 25, False)  # D-308, % of capital
    metrics = {
        "wf_efficiency": 0.9,
        "wf_oos_profitable_share": 0.9,
        "wf_matrix_success_share": 0.9,
        "profit_cost_x2": 10.0,
        "holdout_band_percentile": 50.0,
        "mc_max_dd_p95_pct": value,
    }
    assert (
        GateEngine(load_gate_config(REPO_GATES)).evaluate("s06_robust", "C", metrics, FX_1D).passed
        is passed
    )


def test_F_0_8_1_metrics_used_lists_every_place_a_metric_appears() -> None:
    cfg = GateConfig.model_validate(
        {
            "stages": {"s01_edge": [{"metric": "ess", "op": ">=", "threshold": 50}]},
            "overrides": {
                "timeframe": {"1H": {"s01_edge": [{"metric": "ess", "op": ">=", "threshold": 80}]}},
                "combined": {
                    "fx/1H": {"s01_edge": [{"metric": "ess", "op": ">=", "threshold": 90}]}
                },
            },
        }
    )
    assert metrics_used(cfg) == {
        "ess": ["combined:fx/1H/s01_edge", "s01_edge", "timeframe:1H/s01_edge"]
    }
    validate_metric_names(cfg)  # every name is registered


def test_F_0_8_1_registry_lookup_returns_a_copy() -> None:
    first = metric_names.registry()
    assert first is not metric_names.REGISTRY and first == metric_names.REGISTRY
