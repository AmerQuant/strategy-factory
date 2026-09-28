"""F-1.6 (D-606, D-613): the edge strength score -- components at their boundaries, 0-100, and
a weight change in config takes effect."""

from __future__ import annotations

import math

import pytest

from strategy_factory.metrics.ess import EssConfig, EssRaw, raw_components, score_ess

CFG = EssConfig(
    weights={"breadth": 30, "magnitude": 30, "significance": 20, "consistency": 20},
    magnitude_target_atr=0.10,
    significance_full_log10p=2.0,
    consistency_min_trades_per_year=5,
)


def raw(**kw: float) -> EssRaw:
    base = {"breadth": 0.5, "magnitude": 0.05, "significance": 1.0, "consistency": 0.75}
    base.update(kw)
    return EssRaw(**base)


def test_F_1_6_a_hand_case_matches_d606() -> None:
    """breadth 2/4 -> 15; magnitude 0.05/0.10 -> 15; significance 1/2 -> 10;
    consistency (0.75 - 0.5)/0.5 -> 10: total 50."""
    res = score_ess(raw(), CFG)
    assert res.points == pytest.approx(
        {"breadth": 15.0, "magnitude": 15.0, "significance": 10.0, "consistency": 10.0}
    )
    assert res.total == pytest.approx(50.0)


@pytest.mark.parametrize(
    ("field", "value", "points"),
    [
        ("breadth", 0.0, 0.0),  # 0 accepted groups
        ("breadth", 1.0, 30.0),
        ("magnitude", 0.10, 30.0),  # at the target
        ("magnitude", 0.50, 30.0),  # capped at full
        ("magnitude", -0.20, 0.0),  # a negative excess scores 0, never below
        ("significance", 2.0, 20.0),  # p = 0.01
        ("significance", 3.0, 20.0),  # p at the 1/1001 floor: capped
        ("significance", 0.0, 0.0),
        ("consistency", 0.5, 0.0),  # exactly half the years positive
        ("consistency", 0.25, 0.0),  # below half: 0, not negative
        ("consistency", 1.0, 20.0),
    ],
)
def test_F_1_6_component_boundaries(field: str, value: float, points: float) -> None:
    assert score_ess(raw(**{field: value}), CFG).points[field] == pytest.approx(points)


def test_F_1_6_a_missing_component_scores_zero() -> None:
    """No probe with trades means no median: the component contributes nothing."""
    res = score_ess(raw(magnitude=float("nan"), consistency=float("nan")), CFG)
    assert res.points["magnitude"] == 0.0 and res.points["consistency"] == 0.0
    assert math.isnan(res.raw["magnitude"])  # the raw value stays visibly missing


def test_F_1_6_score_stays_within_0_and_100() -> None:
    low = score_ess(EssRaw(breadth=0, magnitude=-9, significance=0, consistency=0), CFG)
    high = score_ess(EssRaw(breadth=1, magnitude=9, significance=9, consistency=1), CFG)
    assert low.total == 0.0 and high.total == pytest.approx(100.0)


def test_F_1_6_a_weight_change_in_config_takes_effect() -> None:
    heavier = CFG.model_copy(
        update={"weights": {"breadth": 70, "magnitude": 10, "significance": 10, "consistency": 10}}
    )
    base, moved = score_ess(raw(breadth=1.0), CFG), score_ess(raw(breadth=1.0), heavier)
    assert moved.total != pytest.approx(base.total)
    assert moved.points["breadth"] == pytest.approx(70.0)
    # weights that do not sum to 100 are normalised: the score stays on 0..100
    doubled = CFG.model_copy(
        update={"weights": {"breadth": 60, "magnitude": 60, "significance": 40, "consistency": 40}}
    )
    assert score_ess(raw(), doubled).total == pytest.approx(score_ess(raw(), CFG).total)


def test_F_1_6_config_refuses_bad_weights() -> None:
    with pytest.raises(ValueError, match="weights"):
        EssConfig(**{**CFG.model_dump(), "weights": {"breadth": 30}})
    with pytest.raises(ValueError):
        EssConfig(**{**CFG.model_dump(), "magnitude_target_atr": 0.0})


# -- raw components from probe statistics (D-613: medians over every probe run) --------------
def test_F_1_6_raw_components_use_medians_over_all_probes_run() -> None:
    r = raw_components(
        accepted_groups=1,
        applicable_groups=4,
        excess=[0.3, -0.1, 0.0, float("nan")],  # the NaN probe had no trades
        p_values=[0.01, 0.5, 1.0, float("nan")],
        positive_year_share=[1.0, 0.0, 0.5, float("nan")],
    )
    assert r.breadth == pytest.approx(0.25)
    assert r.magnitude == pytest.approx(0.0)  # median of 0.3, -0.1, 0.0
    assert r.significance == pytest.approx(-math.log10(0.5))  # median of 2, 0.301, 0
    assert r.consistency == pytest.approx(0.5)


def test_F_1_6_raw_components_without_any_trades_are_missing() -> None:
    r = raw_components(
        accepted_groups=0,
        applicable_groups=5,
        excess=[float("nan")] * 3,
        p_values=[float("nan")] * 3,
        positive_year_share=[float("nan")] * 3,
    )
    assert r.breadth == 0.0
    assert math.isnan(r.magnitude) and math.isnan(r.significance) and math.isnan(r.consistency)
