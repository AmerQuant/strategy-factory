"""F-2.4 family score, F-2.5 rank-sum, F-2.6 diversity (T13 §5, §6; D-624, D-636)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fixtures.edge_stage import GATES
from fixtures.hypothesis_budget import examples
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.gates.engine import GateEngine
from strategy_factory.metrics.family import (
    FamilyRaw,
    average_ranks,
    good_region,
    grid_median,
    median_cell,
    overlap,
    profitable_share,
    rank_sum,
    score_family,
    select_diverse,
    year_share,
)
from strategy_factory.stages.screen_config import load_s02_config

CFG = load_s02_config().family_score
MAX_SELECTED = load_s02_config().selection.max_candidates
OVERLAP_MAX = next(
    c.threshold
    for c in GateEngine.from_file(GATES).criteria("s02_screen", {"timeframe": "1D"})
    if c.metric == "overlap_with_selected"
)
MIN = 30


def family(targets: list[float], n_trades: list[int], excess: float, consistency: float) -> float:
    raw = FamilyRaw(
        grid_median=grid_median(targets, n_trades, MIN),
        profitable_share=profitable_share(targets, n_trades, MIN),
        excess=excess,
        consistency=consistency,
    )
    return score_family(raw, CFG).total


# ------------------------------------------------------------------ F-2.4
def test_F_2_4_one_good_cell_scores_below_a_uniformly_good_method() -> None:
    """The acceptance test: a method excellent in one cell and poor elsewhere is luck."""
    spike = [5.0] + [-0.5] * 15
    uniform = [0.8] * 16
    trades = [100] * 16
    # even with the spike's better excess and consistency (they come from its good region)
    assert family(spike, trades, excess=0.2, consistency=1.0) < family(
        uniform, trades, excess=0.05, consistency=0.6
    )


def test_F_2_4_failed_cells_are_minus_infinity_not_missing() -> None:
    """T13 §5: a method cannot raise its median by being silent."""
    targets = [1.0, 1.0, 1.0, 2.0, 2.0]
    assert grid_median(targets, [100] * 5, MIN) == 1.0
    silent = grid_median(targets, [100, 100, 5, 5, 5], MIN)  # three cells below the minimum
    assert silent == -math.inf
    assert profitable_share(targets, [100, 100, 5, 5, 5], MIN) == pytest.approx(0.4)
    assert grid_median([math.nan, 1.0, 1.0], [100] * 3, MIN) == 1.0  # NaN is failed too


def test_F_2_4_components_at_their_boundaries() -> None:
    def pts(**raw: float) -> dict[str, float]:
        base = {"grid_median": 0.0, "profitable_share": 0.0, "excess": 0.0, "consistency": 0.5}
        return score_family(FamilyRaw(**{**base, **raw}), CFG).points

    assert pts(grid_median=CFG.grid_median_target)["grid_median"] == pytest.approx(40)
    assert pts(grid_median=10 * CFG.grid_median_target)["grid_median"] == pytest.approx(40)
    assert pts(grid_median=-math.inf)["grid_median"] == 0
    assert pts(grid_median=math.inf)["grid_median"] == pytest.approx(40)  # D-636: ranks top
    assert pts(profitable_share=1.0)["profitable_share"] == pytest.approx(25)
    assert pts(excess=CFG.excess_target_atr)["excess"] == pytest.approx(20)
    assert pts(excess=-1.0)["excess"] == 0
    assert pts(consistency=1.0)["consistency"] == pytest.approx(15)
    assert pts(consistency=0.5)["consistency"] == 0
    assert pts(excess=math.nan)["excess"] == 0


def test_F_2_4_a_weight_change_takes_effect() -> None:
    raw = FamilyRaw(grid_median=0.5, profitable_share=0.5, excess=0.05, consistency=0.75)
    before = score_family(raw, CFG)
    heavier = CFG.model_copy(update={"weights": {**CFG.weights, "excess": 60.0}})
    after = score_family(raw, heavier)
    assert after.points["excess"] > before.points["excess"]
    assert 0 <= after.total <= 100


def test_F_2_4_good_region_and_its_median_cell() -> None:
    """D-624, D-636 (g): top quartile by target among cells at the minimum; median = len // 2;
    ties by the parameter key."""
    targets = [0.1, 0.9, 0.5, 0.9, 3.0, -1.0, 0.7, 0.2]
    trades = [100, 100, 100, 100, 10, 100, 100, 100]  # the 3.0 cell is failed
    keys = [f"k{i}" for i in range(8)]
    region = good_region(targets, trades, MIN, 0.25, keys)
    assert region == [1, 3]  # the two 0.9 cells, the failed 3.0 cell never enters
    assert median_cell(region) == 3
    assert good_region(targets, [1] * 8, MIN, 0.25, keys) == []
    assert median_cell([]) is None


def test_F_2_4_consistency_years_below_the_minimum_are_excluded() -> None:
    assert year_share({2019: 1.0, 2020: -1.0, 2021: 2.0}, {2019: 10, 2020: 10, 2021: 3}, 5) == 0.5
    assert math.isnan(year_share({2019: 1.0}, {2019: 2}, 5))


# ------------------------------------------------------------------ F-2.5
RAWS = [
    FamilyRaw(0.4, 0.7, 0.03, 0.6),
    FamilyRaw(1.2, 0.9, 0.01, 0.8),
    FamilyRaw(-0.1, 0.4, 0.09, 0.5),
    FamilyRaw(0.8, 0.8, math.nan, 0.7),
]


def order(raws: list[FamilyRaw]) -> list[int]:
    s = rank_sum(raws, CFG.weights)
    return sorted(range(len(raws)), key=lambda i: -s[i])


@pytest.mark.parametrize(
    "transform",
    [lambda x: 3 * x + 7, lambda x: x**3, lambda x: math.exp(x), lambda x: math.atan(x)],
)
def test_F_2_5_rank_sum_is_invariant_to_monotone_rescaling(transform: object) -> None:
    f = transform  # type: ignore[assignment]
    scaled = [
        FamilyRaw(
            *(
                v if math.isnan(v) else f(v)
                for v in (r.grid_median, r.profitable_share, r.excess, r.consistency)
            )  # type: ignore[operator]
        )
        for r in RAWS
    ]
    assert order(scaled) == order(RAWS)


def test_F_2_5_ranks_average_ties_and_put_missing_last() -> None:
    assert list(average_ranks([1.0, 2.0, 2.0, math.nan])) == [2.0, 3.5, 3.5, 1.0]


def test_F_2_5_the_weights_decide_between_components() -> None:
    a = FamilyRaw(1.0, 0.0, 0.0, 0.0)  # best median only
    b = FamilyRaw(0.0, 1.0, 1.0, 1.0)  # best everything else
    heavy_median = {
        "grid_median": 100.0,
        "profitable_share": 1.0,
        "excess": 1.0,
        "consistency": 1.0,
    }
    assert rank_sum([a, b], heavy_median)[0] > rank_sum([a, b], heavy_median)[1]
    assert rank_sum([a, b], CFG.weights)[1] > rank_sum([a, b], CFG.weights)[0]


# ------------------------------------------------------------------ F-2.6
def mask(n: int, *ranges: tuple[int, int]) -> np.ndarray:
    m = np.zeros(n, dtype=bool)
    for a, b in ranges:
        m[a:b] = True
    return m


def test_F_2_6_overlap_is_the_share_of_the_smaller_candidate() -> None:
    assert overlap(mask(100, (0, 50)), mask(100, (25, 75))) == pytest.approx(0.5)
    assert overlap(mask(100, (0, 50)), mask(100, (10, 20))) == 1.0  # nested
    assert overlap(mask(100, (0, 50)), mask(100)) == 0.0


def test_F_2_6_top_two_overlap_the_third_is_chosen() -> None:
    positions = [mask(100, (0, 50)), mask(100, (0, 45)), mask(100, (60, 90))]
    selected, ovs = select_diverse([0, 1, 2], positions, lambda i, ov: ov <= 0.6, 5)
    assert selected == [0, 2]
    assert ovs[1] == 1.0 and ovs[2] == 0.0


def test_F_2_6_the_cap_holds_and_every_method_gets_a_verdict() -> None:
    positions = [mask(100, (10 * i, 10 * i + 5)) for i in range(8)]
    called: list[int] = []

    def accept(i: int, ov: float) -> bool:
        called.append(i)
        return True

    selected, _ = select_diverse(list(range(8)), positions, accept, 5)
    assert selected == [0, 1, 2, 3, 4]
    assert called == list(range(8))


@settings(max_examples=examples(60), deadline=None)
@given(st.lists(st.lists(st.booleans(), min_size=40, max_size=40), min_size=2, max_size=9))
def test_F_2_6_no_two_selected_candidates_overlap_above_the_threshold(
    rows: list[list[bool]],
) -> None:
    positions = [np.array(r) for r in rows]
    selected, _ = select_diverse(
        list(range(len(rows))), positions, lambda i, ov: ov <= OVERLAP_MAX, MAX_SELECTED
    )
    thr = OVERLAP_MAX
    for a in selected:
        for b in selected:
            if a != b:
                assert overlap(positions[a], positions[b]) <= thr
