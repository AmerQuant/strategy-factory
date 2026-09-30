"""F-7.6: Hansen's SPA against not trading (T16, D-723). Size and power on cases with a known
answer; the plan measured 5.0 % size at 10 models (docs/tasks/T16_plan.md §5)."""

from __future__ import annotations

import numpy as np
import pytest

from strategy_factory.stats.spa import spa_test


def test_F_7_6_rejects_a_planted_superior_candidate() -> None:
    x = np.random.default_rng(3).standard_normal((1000, 10))
    x[:, 4] += 0.2  # a real daily Sharpe of 0.2
    r = spa_test(x, block_size=10, reps=500, seed=1)
    assert r.p_consistent < 0.05
    assert r.p_lower <= r.p_consistent <= r.p_upper
    assert (r.n_models, r.n_obs) == (10, 1000)


@pytest.mark.slow
def test_F_7_6_near_nominal_size_on_the_null() -> None:
    sims, rejected = 200, 0
    for seed in range(sims):
        x = np.random.default_rng(seed).standard_normal((500, 10))
        rejected += spa_test(x, block_size=10, reps=300, seed=seed).p_consistent < 0.05
    # nominal 5 % (measured 5.5 % with these seeds); 200 simulations: about +-3 points at two sd
    assert 0.02 <= rejected / sims <= 0.09


def test_F_7_6_is_deterministic_with_a_seed_and_refuses_bad_input() -> None:
    x = np.random.default_rng(4).standard_normal((300, 5))
    assert spa_test(x, block_size=5, reps=200, seed=9) == spa_test(
        x, block_size=5, reps=200, seed=9
    )
    with pytest.raises(ValueError):
        spa_test(np.full((10, 2), np.nan), block_size=2, reps=10, seed=0)
    with pytest.raises(ValueError):
        spa_test(x, block_size=0, reps=10, seed=0)
