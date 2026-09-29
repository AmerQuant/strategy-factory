"""F-3.5: SPP median, p5 and p95 against a hand-computed distribution (T14 §4, D-650 (i))."""

from __future__ import annotations

import math

import numpy as np
import pytest

from strategy_factory.robustness.spp import nearest_rank, spp


def test_F_3_5_spp_on_a_hand_computed_distribution() -> None:
    t = np.arange(1, 22, dtype=float)  # 1 ... 21: nearest ranks 0, 10, 20 of 20
    r = spp(t, np.ones(21, bool), 5, 95)
    assert r.median == 11.0
    assert r.p_low == 2.0  # round(0.05 * 20) = 1 -> the 2nd value
    assert r.p_high == 20.0  # round(0.95 * 20) = 19
    assert r.cells == 21 and r.failed == 0 and r.median_valid == 11.0


def test_F_3_5_failed_cells_rank_below_every_valid_cell() -> None:
    t = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
    valid = np.array([True, True, False, False, False])
    r = spp(t, valid, 5, 95)
    assert r.median == -math.inf  # three of five failed: the median is a failed cell
    assert r.median_valid == pytest.approx(4.5)
    assert r.failed == 3
    assert spp(t, np.array([True] * 3 + [False] * 2), 5, 95).median == 3.0


def test_F_3_5_spp_accepts_any_shape_and_empty() -> None:
    grid = np.arange(12, dtype=float).reshape(3, 4)
    assert spp(grid, np.ones((3, 4), bool), 5, 95).median == nearest_rank(np.arange(12.0), 50)
    assert math.isnan(nearest_rank(np.array([]), 50))
