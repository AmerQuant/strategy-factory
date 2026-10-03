"""F-7.3: the effective number of trials by ONC (T16, D-722). The default between ONC and
hierarchical clustering is the supervisor's (D-722); these tests hold for ONC as implemented."""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.hypothesis_budget import examples
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.stats.neff import (
    _silhouette,
    correlation,
    hierarchical,
    hierarchical_labels,
    identical_guard_fires,
    onc,
)


def _blocks(sizes: list[int], rho: float, t: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    f = rng.standard_normal((len(sizes), t))
    g = np.repeat(np.arange(len(sizes)), sizes)
    return np.sqrt(rho) * f[g] + np.sqrt(1 - rho) * rng.standard_normal((sum(sizes), t))


def test_F_7_3_finds_planted_groups() -> None:
    r = onc(_blocks([10, 10, 10, 10], 0.9, 500, seed=1), seed=0)
    assert (r.n_raw, r.n_effective) == (40, 4)
    labels = np.array(r.labels)
    assert all(len(set(labels[i : i + 10])) == 1 for i in range(0, 40, 10))  # each group whole


def test_F_7_3_identical_trials_are_one_cluster() -> None:
    x = np.tile(np.random.default_rng(2).standard_normal(300), (25, 1))
    assert onc(x, seed=0).n_effective == 1


def test_F_7_3_is_deterministic_with_a_seed() -> None:
    x = _blocks([8, 8, 8], 0.6, 300, seed=3)
    assert onc(x, seed=5) == onc(x, seed=5)


@settings(max_examples=examples(15), deadline=None)
@given(st.integers(3, 25), st.floats(0.0, 0.95), st.integers(0, 10_000))
def test_F_7_3_n_effective_never_exceeds_n_raw(n: int, rho: float, seed: int) -> None:
    x = _blocks([n], rho, 120, seed) + np.random.default_rng(seed).standard_normal((n, 120))
    r = onc(x, seed=seed, n_init=2)
    assert 1 <= r.n_effective <= r.n_raw == n


def test_F_7_3_silhouette_by_hand() -> None:
    """Points 0, 1 at distance 1; point 2 at distance 4 from both: labels {0, 1} and {2}."""
    pair = np.array([[0.0, 1.0, 4.0], [1.0, 0.0, 4.0], [4.0, 4.0, 0.0]])
    s = _silhouette(pair, np.array([0, 0, 1]))
    assert s[0] == pytest.approx((4 - 1) / 4) and s[1] == pytest.approx(0.75)
    assert s[2] == 0.0  # a singleton


def test_F_7_3_input_checks_and_a_constant_trial() -> None:
    with pytest.raises(ValueError):
        onc(np.full((5, 50), np.nan), seed=0)
    x = _blocks([6, 6], 0.9, 200, seed=4)
    x[0] = 1.0  # constant: correlates 0 with everything, no NaN
    c = correlation(x)
    assert np.isfinite(c).all() and c[0, 1] == 0.0
    assert onc(x, seed=0).n_raw == 12


def test_F_7_3_the_identical_trials_guard_is_a_switch() -> None:
    """D-722: the guard is a design choice under comparison. On **exactly** identical trials every
    distance is 0, k-means puts every trial on its first centre, and the published method returns
    one cluster anyway -- with or without the guard (measured; the guard decides nothing here)."""
    x = np.tile(np.random.default_rng(2).standard_normal(300), (25, 1))
    assert identical_guard_fires(correlation(x))
    assert onc(x, seed=0).n_effective == 1
    assert onc(x, seed=0, identical_guard=False).n_effective == 1


# -- hierarchical clustering with a correlation cut (D-722) -------------------------------------

# rho(0, 1) = 0.9, rho(2, 3) = 0.8, every cross pair 0.1. Distances sqrt((1 - rho) / 2): 0.2236,
# 0.3162 and 0.6708; average linkage merges {0, 1} at 0.2236, {2, 3} at 0.3162, then both at
# 0.6708 (every cross pair is equal, so the average is too).
HAND = np.array(
    [[1.0, 0.9, 0.1, 0.1], [0.9, 1.0, 0.1, 0.1], [0.1, 0.1, 1.0, 0.8], [0.1, 0.1, 0.8, 1.0]]
)


@pytest.mark.parametrize(
    ("rho_cut", "labels"),
    [
        (0.95, (0, 1, 2, 3)),  # d 0.158: nothing merges
        (0.85, (0, 0, 1, 2)),  # d 0.274: only {0, 1}
        (0.5, (0, 0, 1, 1)),  # d 0.5: both pairs
        (0.05, (0, 0, 0, 0)),  # d 0.689: everything
    ],
)
def test_F_7_3_hierarchical_by_hand(rho_cut: float, labels: tuple[int, ...]) -> None:
    assert tuple(hierarchical_labels(HAND, rho_cut)) == labels


def test_F_7_3_hierarchical_finds_planted_groups_identical_and_independent() -> None:
    r = hierarchical(_blocks([10, 10, 10, 10], 0.6, 500, seed=1), rho_cut=0.3)
    assert (r.method, r.n_raw, r.n_effective, r.rho_cut) == ("hierarchical", 40, 4, 0.3)
    labels = np.array(r.labels)
    assert all(len(set(labels[i : i + 10])) == 1 for i in range(0, 40, 10))
    same = np.tile(np.random.default_rng(2).standard_normal(300), (25, 1))
    assert hierarchical(same, rho_cut=0.3).n_effective == 1
    indep = np.random.default_rng(3).standard_normal((30, 2000))
    assert hierarchical(indep, rho_cut=0.3).n_effective == 30


@settings(max_examples=examples(25), deadline=None)
@given(st.integers(1, 30), st.floats(0.0, 0.95), st.floats(-0.5, 0.9), st.integers(0, 10_000))
def test_F_7_3_hierarchical_n_effective_never_exceeds_n_raw(
    n: int, rho: float, cut: float, seed: int
) -> None:
    x = _blocks([n], rho, 120, seed) + np.random.default_rng(seed).standard_normal((n, 120))
    r = hierarchical(x, rho_cut=cut)
    assert 1 <= r.n_effective <= r.n_raw == n


def test_F_7_3_hierarchical_refuses_a_cut_outside_minus_one_one() -> None:
    for cut in (-1.0, 1.0, 2.0):
        with pytest.raises(ValueError):
            hierarchical(np.random.default_rng(0).standard_normal((4, 50)), rho_cut=cut)
