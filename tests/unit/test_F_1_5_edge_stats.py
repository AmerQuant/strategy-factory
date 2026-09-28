"""F-1.5 / D-601 / D-605 / D-606 / D-617: the stage-1 statistics, against hand-computed cases."""

from __future__ import annotations

import math

import numpy as np
import pytest

from strategy_factory.stats.edge import (
    bh_qvalues,
    empirical_p,
    percentile_of,
    two_proportion_z,
)


# -- percentile: the share of baseline means strictly below the probe's mean, x100 -------------
def test_F_1_5_percentile_counts_strictly_below() -> None:
    dist = np.array([1.0, 2.0, 3.0, 4.0])
    assert percentile_of(2.5, dist) == 50.0
    assert percentile_of(3.0, dist) == 50.0  # a tie is not "below"
    assert percentile_of(0.0, dist) == 0.0
    assert percentile_of(9.0, dist) == 100.0


def test_F_1_5_percentile_of_an_empty_or_nan_input_is_nan() -> None:
    assert math.isnan(percentile_of(1.0, np.array([])))
    assert math.isnan(percentile_of(float("nan"), np.array([1.0, 2.0])))


# -- empirical p = (1 + #{baseline >= probe}) / (1 + n), floored (D-606) ----------------------
def test_F_1_5_empirical_p_hand_cases() -> None:
    dist = np.arange(1000, dtype=float)  # 0 … 999
    assert empirical_p(999.5, dist, floor=1 / 1001) == pytest.approx(1 / 1001)
    assert empirical_p(-1.0, dist, floor=1 / 1001) == pytest.approx(1001 / 1001)
    # ties count against the probe: #{>= 500} = 500
    assert empirical_p(500.0, dist, floor=1 / 1001) == pytest.approx(501 / 1001)


def test_F_1_5_empirical_p_is_floored() -> None:
    dist = np.zeros(9)  # n = 9: the raw minimum would be 1/10
    assert empirical_p(5.0, dist, floor=0.2) == pytest.approx(0.2)
    assert empirical_p(5.0, dist, floor=0.01) == pytest.approx(0.1)


def test_F_1_5_empirical_p_of_a_missing_statistic_is_nan() -> None:
    assert math.isnan(empirical_p(float("nan"), np.arange(10.0), floor=1 / 11))
    assert math.isnan(empirical_p(1.0, np.array([]), floor=0.5))


# -- Benjamini-Hochberg q-values (D-605) --------------------------------------------------------
def test_F_1_5_bh_worked_example() -> None:
    """Sorted p 0.005, 0.01, 0.03, 0.04 (m = 4): p*m/rank = 0.02, 0.02, 0.04, 0.04; the
    running minimum from the top leaves them as they are."""
    q = bh_qvalues(np.array([0.01, 0.04, 0.03, 0.005]))
    np.testing.assert_allclose(q, [0.02, 0.04, 0.04, 0.02])


def test_F_1_5_bh_is_monotone_and_capped_at_one() -> None:
    """The step-up takes the running minimum from the largest p down: 0.9*3/2 = 1.35 is
    lowered to the rank-3 value, and nothing exceeds 1."""
    q = bh_qvalues(np.array([0.9, 0.95, 0.5]))
    np.testing.assert_allclose(q, [0.95, 0.95, 0.95])
    assert (q <= 1.0).all()
    one = bh_qvalues(np.array([0.3]))
    np.testing.assert_allclose(one, [0.3])


def test_F_1_5_bh_skips_missing_p_values() -> None:
    """A probe with no trades has no p; it neither gets a q nor counts in m."""
    q = bh_qvalues(np.array([0.01, float("nan"), 0.04]))
    assert math.isnan(q[1])
    np.testing.assert_allclose(q[[0, 2]], [0.02, 0.04])  # m = 2
    assert bh_qvalues(np.array([])).shape == (0,)


# -- two-proportion z-test (D-617: the quality split, evidence only) ---------------------------
def test_F_1_5_two_proportion_z_hand_case() -> None:
    """40/100 vs 20/100: pooled 0.3, se = sqrt(0.3*0.7*(1/100+1/100)) = 0.0648; z = 3.086."""
    z, p = two_proportion_z(40, 100, 20, 100)
    assert z == pytest.approx(0.2 / math.sqrt(0.3 * 0.7 * 0.02))
    assert p == pytest.approx(math.erfc(abs(z) / math.sqrt(2)))
    assert p < 0.01


def test_F_1_5_two_proportion_z_equal_rates_and_degenerate_cases() -> None:
    z, p = two_proportion_z(10, 50, 20, 100)
    assert z == pytest.approx(0.0) and p == pytest.approx(1.0)
    for args in ((0, 0, 5, 10), (0, 10, 0, 10), (10, 10, 5, 5)):
        z, p = two_proportion_z(*args)
        assert math.isnan(z) and math.isnan(p), args
