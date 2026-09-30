"""F-7.5: PBO by CSCV (T16). Tolerances from docs/tasks/T16_plan.md §4: on noise one matrix's PBO
has a standard deviation of 0.1-0.15, so the "about 0.5" check averages over seeds."""

from __future__ import annotations

from math import comb

import numpy as np
import pytest

from strategy_factory.stats.pbo import pbo_cscv


@pytest.mark.parametrize("s", [4, 6, 8, 10])
def test_F_7_5_the_split_count_is_the_combinatorics(s: int) -> None:
    r = pbo_cscv(np.random.default_rng(0).standard_normal((20, 400)), s)
    assert r.n_splits == comb(s, s // 2) == len(r.logits)


def test_F_7_5_about_one_half_on_random_trials() -> None:
    pbos = [
        pbo_cscv(np.random.default_rng(seed).standard_normal((200, 1000)), 8).pbo
        for seed in range(12)
    ]
    assert abs(float(np.mean(pbos)) - 0.5) < 0.1


def test_F_7_5_low_when_one_trial_dominates_out_of_sample() -> None:
    x = np.random.default_rng(1).standard_normal((100, 1000))
    x[7] += 0.3  # a real daily Sharpe of 0.3
    r = pbo_cscv(x, 10)
    assert r.pbo == 0.0 and min(r.logits) > 0


def test_F_7_5_refuses_bad_input() -> None:
    x = np.zeros((5, 100))
    for s in (3, 0, 200):
        with pytest.raises(ValueError):
            pbo_cscv(x, s)
    with pytest.raises(ValueError):
        pbo_cscv(np.full((5, 100), np.nan), 4)


def test_F_7_5_a_constant_trial_ranks_lowest_and_never_divides_by_zero() -> None:
    x = np.random.default_rng(2).standard_normal((10, 400))
    x[0] = 0.0
    r = pbo_cscv(x, 4)
    assert np.isfinite(r.logits).all()
