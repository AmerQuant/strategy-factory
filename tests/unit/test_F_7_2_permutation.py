"""F-7.2: the permutation p-value is exact by hand and uniform on the null (T16)."""

from __future__ import annotations

import math

import numpy as np

from strategy_factory.stats.permutation import permutation_p_value


def test_F_7_2_the_count_by_hand() -> None:
    r = permutation_p_value(2.0, [1.0, 2.0, 3.0, math.nan])
    assert (r.p_value, r.n_null) == ((1 + 2) / (1 + 3), 3)  # 2.0 and 3.0 are >= 2.0; NaN dropped
    assert permutation_p_value(10.0, [1.0, 2.0]).p_value == 1 / 3  # never 0
    assert math.isnan(permutation_p_value(math.nan, [1.0]).p_value)


def test_F_7_2_p_is_uniform_on_the_null() -> None:
    """The observation drawn from the same distribution as the null: p ~ U(0, 1). A KS check
    against the discrete uniform on {1/(n+1), ..., 1}, at the 1 % critical value 1.63 / sqrt(m)."""
    rng = np.random.default_rng(20260930)
    m, n = 2000, 199
    ps = np.array(
        [
            permutation_p_value(float(rng.standard_normal()), rng.standard_normal(n)).p_value
            for _ in range(m)
        ]
    )
    grid = np.arange(1, n + 2) / (n + 1)
    empirical = np.searchsorted(np.sort(ps), grid, side="right") / m
    ks = float(np.max(np.abs(empirical - grid)))
    assert ks < 1.63 / math.sqrt(m)
    assert abs(ps.mean() - 0.5) < 0.02
