"""F-3.3 / F-3.4 on hand-built surfaces (T14 §4, §7; D-646, D-648, D-650).

Smoothing, selection of the plateau's centre rather than the peak, the stability ratio at the
edges, the connected plateau (two disjoint islands: only the selected one counts), the edge
slope, and the failed-cell treatment -- including the lone-survivor surface the plan measured
(TMUS long ``mr_n_day_low``: 20 of 21 cells failed).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from strategy_factory.metrics.plateau import (
    edge_slope,
    extent,
    fill_failed,
    neighbours,
    offsets,
    plateau,
    select,
    smooth,
    stability_ratio,
    step_distance,
)

RATIO = 0.8  # the s03_entry gate's stability_ratio threshold


def keys_for(shape: tuple[int, ...]) -> np.ndarray:
    k = np.empty(shape, dtype=object)
    for idx in np.ndindex(shape):
        k[idx] = "|".join(f"{i:03d}" for i in idx)
    return k


def all_valid(x: np.ndarray) -> np.ndarray:
    return np.ones(x.shape, dtype=np.bool_)


# ------------------------------------------------------------------ neighbourhood
def test_F_3_3_neighbourhood_is_one_step_in_every_dimension() -> None:
    assert len(offsets(1)) == 2 and len(offsets(2)) == 8 and len(offsets(3)) == 26
    assert sorted(neighbours((0,), (3,))) == [(1,)]
    assert len(neighbours((1, 1), (3, 3))) == 8
    assert len(neighbours((0, 0), (3, 3))) == 3  # a corner: only what exists
    assert len(neighbours((1, 1, 1), (3, 3, 3))) == 26


def test_F_3_3_smoothing_is_the_mean_of_the_cell_and_its_existing_neighbours() -> None:
    x = np.array([1.0, 2.0, 6.0, 3.0])
    assert np.allclose(smooth(x), [1.5, 3.0, 11 / 3, 4.5])
    g = np.arange(9, dtype=float).reshape(3, 3)
    s = smooth(g)
    assert s[1, 1] == pytest.approx(g.mean())
    assert s[0, 0] == pytest.approx(np.mean([0, 1, 3, 4]))


# ------------------------------------------------------------ F-3.3: the plateau, not the peak
def _peak_and_plateau_2d() -> np.ndarray:
    """A sharp peak (one cell of 5.0 among zeros) and a broad plateau of 2.0."""
    x = np.zeros((9, 9))
    x[1, 1] = 5.0  # the sharp peak
    x[4:9, 4:9] = 2.0  # the broad plateau (5 x 5)
    return x


def test_F_3_3_the_plateau_centre_is_chosen_not_the_peak() -> None:
    x = _peak_and_plateau_2d()
    assert np.unravel_index(np.argmax(x), x.shape) == (1, 1)  # the raw maximum is the peak
    sel = select(smooth(x), all_valid(x), keys_for(x.shape))
    assert sel is not None
    assert 5 <= sel[0] <= 7 and 5 <= sel[1] <= 7  # inside the plateau, away from its edge
    assert sel != (1, 1)


def test_F_3_3_the_plateau_centre_is_chosen_in_3d() -> None:
    x = np.zeros((7, 7, 7))
    x[1, 1, 1] = 3.0  # the raw maximum; smoothed it is at most 3/8 (the corner next to it)
    x[2:7, 2:7, 2:7] = 1.0
    sel = select(smooth(x), all_valid(x), keys_for(x.shape))
    assert sel is not None and all(3 <= i <= 5 for i in sel)


def test_F_3_3_a_failed_cell_is_never_selected_and_ties_break_by_key() -> None:
    x = np.array([1.0, 1.0, 1.0])
    valid = np.array([True, False, True])
    s = np.array([2.0, 3.0, 2.0])
    assert select(s, valid, keys_for(x.shape)) == (0,)  # (1,) is failed; (0,) wins the tie by key


# ------------------------------------------------------------------ F-3.4: stability ratio
def test_F_3_4_stability_ratio_is_neighbour_mean_over_the_raw_value() -> None:
    x = np.array([[1.0, 1.0, 1.0], [1.0, 2.0, 1.0], [1.0, 1.0, 1.0]])
    assert stability_ratio(x, (1, 1)) == pytest.approx(0.5)
    assert stability_ratio(x, (0, 0)) == pytest.approx((1 + 1 + 2) / 3 / 1.0)  # the corner


def test_F_3_4_stability_ratio_fails_on_a_loss_or_a_lone_cell() -> None:
    assert math.isnan(stability_ratio(np.array([-1.0, 2.0, 2.0]), (0,)))
    assert math.isnan(stability_ratio(np.array([0.0, 2.0]), (0,)))
    assert math.isnan(stability_ratio(np.array([3.0]), (0,)))  # no neighbour at all


# ------------------------------------------------------------------ F-3.4: plateau, islands, slope
def test_F_3_4_two_disjoint_islands_only_the_selected_one_counts() -> None:
    s = np.zeros((10, 10))
    s[1:4, 1:4] = 1.0  # island A: 9 cells
    s[6:10, 6:10] = 1.0  # island B: 16 cells, not connected to A
    mask = plateau(s, (2, 2), RATIO)
    assert int(mask.sum()) == 9 and mask[1:4, 1:4].all() and not mask[6:, 6:].any()
    assert int(plateau(s, (7, 7), RATIO).sum()) == 16


def test_F_3_4_the_plateau_connects_diagonally_and_cuts_at_the_ratio() -> None:
    s = np.array([[1.0, 0.0], [0.0, 0.85]])
    assert int(plateau(s, (0, 0), RATIO).sum()) == 2  # diagonal neighbour, 0.85 >= 0.8
    assert int(plateau(s, (0, 0), 0.9).sum()) == 1


def test_F_3_4_no_plateau_on_a_loss() -> None:
    assert not plateau(np.array([-1.0, -0.5]), (1,), RATIO).any()


def test_F_3_4_edge_slope_and_extent() -> None:
    s = np.array([0.2, 1.0, 1.0, 1.0, 0.2])
    mask = plateau(s, (2,), RATIO)
    assert mask.tolist() == [False, True, True, True, False]
    assert edge_slope(s, mask, (2,)) == pytest.approx(0.8)  # boundary cells drop 0.8 of 1.0
    assert edge_slope(np.ones(3), np.ones(3, bool), (1,)) == 0.0  # fills the grid
    assert extent(mask, [[10, 20, 30, 40, 50]]) == [(20.0, 40.0)]
    assert step_distance((1, 4), (3, 3)) == 2


# ------------------------------------------------------------------ D-646: failed cells
def test_F_3_4_d646_failed_cells_enter_as_min_of_worst_and_zero() -> None:
    t = np.array([2.0, 3.0, 9.0, 4.0])
    valid = np.array([True, True, False, True])
    x, n_inf = fill_failed(t, valid, "worst0")
    assert x.tolist() == [2.0, 3.0, 0.0, 4.0] and n_inf == 0  # worst is 2 > 0: capped at 0
    x, _ = fill_failed(np.array([-1.0, 3.0, 9.0]), np.array([True, True, False]), "worst0")
    assert x[2] == -1.0  # worst is -1 < 0: the worst
    assert fill_failed(t, valid, "zero")[0][2] == 0.0
    assert fill_failed(t, valid, "worst")[0][2] == 2.0
    assert fill_failed(t, valid, "neginf")[0][2] == -math.inf


def test_F_3_4_d646_the_lone_survivor_does_not_pass() -> None:
    """The plan's measured case: one valid cell among 20 failed ones on a 21-cell line. With
    the grid's "worst" value the failed neighbours inherit the survivor's own positive value,
    so it scores stability 1.0 and a plateau of the whole grid; with D-646 it has neither."""
    t = np.full(21, np.nan)
    t[10] = 0.95
    valid = np.zeros(21, dtype=np.bool_)
    valid[10] = True
    keys = keys_for((21,))

    x, _ = fill_failed(t, valid, "worst")
    s = smooth(x)
    sel = select(s, valid, keys)
    assert sel == (10,)
    assert stability_ratio(x, sel) == pytest.approx(1.0)  # the pathology D-646 closes
    assert plateau(s, sel, RATIO).sum() == 21

    x, _ = fill_failed(t, valid, "worst0")
    s = smooth(x)
    sel = select(s, valid, keys)
    assert sel == (10,)
    assert stability_ratio(x, sel) == pytest.approx(0.0)  # neighbours count as 0: below 0.8
    assert int(plateau(s, sel, RATIO).sum()) == 3  # smoothing spreads it to its two neighbours only


def test_F_3_4_d650h_infinite_targets_are_capped_and_counted() -> None:
    x, n_inf = fill_failed(np.array([1.0, np.inf, 2.0]), np.ones(3, bool), "worst0")
    assert n_inf == 1 and x.tolist() == [1.0, 2.0, 2.0]
    assert np.isfinite(smooth(x)).all()
