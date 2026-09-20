"""F-0.8.1: declarative gate engine (operators, overrides, missing metrics, borderline)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, select

from strategy_factory.core.errors import ConfigError
from strategy_factory.gates.engine import GateConfig, GateEngine, load_gate_config, record

REPO_GATES = Path(__file__).resolve().parents[2] / "configs" / "gates" / "default.yaml"
FX_1D = {"asset_class": "fx", "timeframe": "1D"}


def engine(stages: dict[str, Any], **extra: Any) -> GateEngine:
    return GateEngine(GateConfig.model_validate({"stages": stages, **extra}))


@pytest.mark.parametrize(
    ("op", "value", "threshold", "passed"),
    [
        (">=", 2.0, 2.0, True),
        (">=", 1.99, 2.0, False),
        ("<=", 0.25, 0.25, True),
        ("<=", 0.26, 0.25, False),
        (">", 0.01, 0.0, True),
        (">", 0.0, 0.0, False),
        ("<", 0.04, 0.05, True),
        ("<", 0.05, 0.05, False),
        ("==", 1, 1, True),
        ("==", 0, 1, False),
        ("==", True, 1, True),
    ],
)
def test_F_0_8_1_each_operator(op: str, value: Any, threshold: float, passed: bool) -> None:
    e = engine({"s": [{"metric": "m", "op": op, "threshold": threshold}]})
    res = e.evaluate("s", "C1", {"m": value}, FX_1D)
    assert res.passed is passed and res.items[0].passed is passed
    assert res.items[0].reason.startswith("ok" if passed else "failed")


def test_F_0_8_1_missing_and_nan_metrics_fail() -> None:
    e = engine(
        {
            "s": [
                {"metric": "a", "op": ">=", "threshold": 1},
                {"metric": "b", "op": ">=", "threshold": 1},
            ]
        }
    )
    res = e.evaluate("s", "C1", {"b": math.nan}, FX_1D)
    assert not res.passed
    reasons = {i.metric: i.reason for i in res.items}
    assert reasons == {"a": "metric_missing", "b": "metric_nan"}


def test_F_0_8_1_overrides_by_asset_class_timeframe_and_combined() -> None:
    e = engine(
        {"s": [{"metric": "trades", "op": ">=", "threshold": 30}]},
        overrides={
            "asset_class": {"fx": {"s": [{"metric": "pf", "op": ">=", "threshold": 1.2}]}},
            "timeframe": {"1H": {"s": [{"metric": "trades", "op": ">=", "threshold": 100}]}},
            "combined": {"fx/1H": {"s": [{"metric": "trades", "op": ">=", "threshold": 150}]}},
        },
    )

    def crit(ctx: dict[str, str]) -> dict[str, float]:
        return {c.metric: c.threshold for c in e.criteria("s", ctx)}

    assert crit({"asset_class": "us_equity", "timeframe": "1D"}) == {"trades": 30}
    assert crit({"asset_class": "fx", "timeframe": "1D"}) == {"trades": 30, "pf": 1.2}  # added
    assert crit({"asset_class": "us_equity", "timeframe": "1H"}) == {"trades": 100}  # replaced
    assert crit({"asset_class": "fx", "timeframe": "1H"}) == {"trades": 150, "pf": 1.2}
    res = e.evaluate(
        "s", "C1", {"trades": 120, "pf": 1.3}, {"asset_class": "fx", "timeframe": "1H"}
    )
    assert not res.passed


@pytest.mark.parametrize(
    ("metrics", "borderline"),
    [
        ({"a": 1.0, "b": 0.95, "c": 1.0}, True),  # one non-critical failure within 10 %
        ({"a": 1.0, "b": 0.89, "c": 1.0}, False),  # beyond 10 %
        ({"a": 0.95, "b": 0.95, "c": 1.0}, False),  # two failures
        ({"a": 1.0, "b": 1.0, "c": 0.97}, False),  # the failure is critical
        ({"a": 1.0, "b": 0.95, "c": 0.97}, False),  # any critical failure
        ({"a": 1.0, "b": 1.0, "c": 1.0}, False),  # passed -> not borderline
    ],
)
def test_F_0_8_1_borderline_rule(metrics: dict[str, float], borderline: bool) -> None:
    e = engine(
        {
            "s": [
                {"metric": "a", "op": ">=", "threshold": 1.0},
                {"metric": "b", "op": ">=", "threshold": 1.0},
                {"metric": "c", "op": ">=", "threshold": 1.0, "critical": True},
            ]
        }
    )
    assert e.evaluate("s", "C1", metrics, FX_1D).borderline is borderline


def test_F_0_8_1_borderline_tolerance_from_config_and_zero_threshold() -> None:
    stages = {"s": [{"metric": "a", "op": ">=", "threshold": 1.0}]}
    assert (
        not engine(stages, borderline_tolerance=0.02)
        .evaluate("s", "C", {"a": 0.95}, FX_1D)
        .borderline
    )
    assert (
        engine(stages, borderline_tolerance=0.06).evaluate("s", "C", {"a": 0.95}, FX_1D).borderline
    )
    zero = engine({"s": [{"metric": "p", "op": ">", "threshold": 0}]})
    assert not zero.evaluate("s", "C", {"p": -0.001}, FX_1D).borderline  # no relative distance


def test_F_0_8_1_changing_threshold_in_config_changes_result(tmp_path: Path) -> None:
    data = yaml.safe_load(REPO_GATES.read_text(encoding="utf-8"))
    metrics = {"accepted_probe_groups": 3, "ess": 55}
    assert GateEngine(load_gate_config(REPO_GATES)).evaluate("s01_edge", "C", metrics, FX_1D).passed
    data["stages"]["s01_edge"][1]["threshold"] = 60
    stricter = tmp_path / "gates.yaml"
    stricter.write_text(yaml.safe_dump(data), encoding="utf-8")
    res = GateEngine.from_file(stricter).evaluate("s01_edge", "C", metrics, FX_1D)
    assert not res.passed and res.failed()[0].metric == "ess"


def test_F_0_8_1_default_gates_as_specified() -> None:
    cfg = load_gate_config(REPO_GATES)
    assert cfg.borderline_tolerance == 0.10
    table = {
        s: {c.metric: (c.op, c.threshold, c.critical) for c in cs} for s, cs in cfg.stages.items()
    }
    assert table["s01_probe"] == {
        "n_trades": (">=", 30, False),  # D-301/D-333: closed trades
        "probe_percentile": (">=", 90, False),
        "profit_factor": (">=", 1.1, False),
    }
    assert table["s01_edge"] == {
        "accepted_probe_groups": (">=", 3, False),
        "ess": (">=", 50, False),
    }
    assert table["s03_entry"]["stability_ratio"] == (">=", 0.8, False)
    assert table["s03_entry"]["plateau_area"] == (">=", 0.10, False)
    assert table["s02_screen"]["profitable_cell_share"] == (">=", 0.60, False)
    assert table["s02_screen"]["overlap_with_selected"] == ("<=", 0.60, False)
    crit6 = {m for m, (_, _, c) in table["s06_robust"].items() if c}
    assert crit6 == {
        "wf_efficiency",
        "wf_oos_profitable_share",
        "wf_matrix_success_share",
        "profit_cost_x2",
        "holdout_band_percentile",
    }
    assert table["s07_stats"]["dsr"] == (">=", 0.95, False)
    assert table["s07_stats"]["pbo"] == ("<=", 0.25, False)
    e = GateEngine(cfg)
    one_h = {c.metric: c.threshold for c in e.criteria("s01_probe", {"timeframe": "1H"})}
    assert one_h["n_trades"] == 100


def test_F_0_8_1_unknown_stage_and_bad_config() -> None:
    with pytest.raises(ConfigError, match="no gates configured"):
        engine({"s": []}).criteria("nope", FX_1D)
    with pytest.raises(ValueError, match="lists a metric twice"):
        GateConfig.model_validate(
            {
                "stages": {
                    "s": [
                        {"metric": "a", "op": ">", "threshold": 0},
                        {"metric": "a", "op": "<", "threshold": 1},
                    ]
                }
            }
        )
    with pytest.raises(ValueError):
        GateConfig.model_validate({"stages": {"s": [{"metric": "a", "op": "!=", "threshold": 0}]}})


@pytest.mark.db
def test_F_0_8_1_results_written_to_registry(registry_engine: Engine) -> None:
    from fixtures.registry_db import RUN_CONFIG

    from strategy_factory.registry.tables import gate_results
    from strategy_factory.registry.writer import CandidateRecord, RegistryWriter

    w = RegistryWriter(registry_engine)
    run_id = w.start_run(RUN_CONFIG, seed=1, code_version="c" * 40)
    w.upsert_candidate(
        CandidateRecord(
            id="C1",
            run_id=run_id,
            symbol="EURUSD",
            timeframe="1H",
            direction="long",
            edge_type="MR",
            spec={},
            spec_hash="h",
            current_stage="s01_edge",
        )
    )
    e = GateEngine(load_gate_config(REPO_GATES))
    res = e.evaluate("s01_edge", "C1", {"ess": 48}, {"asset_class": "fx", "timeframe": "1H"})
    record(res, run_id, w)
    with registry_engine.connect() as conn:
        rows = {r.criterion: r for r in conn.execute(select(gate_results))}
    assert set(rows) == {"accepted_probe_groups", "ess"}
    assert rows["ess"].metric_value == 48 and rows["ess"].passed is False
    assert rows["ess"].reason == "failed: 48 >= 50"
    assert rows["accepted_probe_groups"].metric_value is None
    assert rows["accepted_probe_groups"].reason == "metric_missing"
