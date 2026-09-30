"""F-7.1: the HAC t-test against statsmodels (the oracle, tests only) and the block bootstrap's
coverage on series whose mean and Sharpe are known (T16, D-723; tolerances from
docs/tasks/T16_plan.md §3: 92.5-94.5 % measured at a nominal 95 %)."""

from __future__ import annotations

import math

import numpy as np
import pytest
import statsmodels.api as sm

from strategy_factory.stats.bootstrap import automatic_block_length, bootstrap_interval
from strategy_factory.stats.ttest import hac_t_test, newey_west_lags


def _ar1(t: int, phi: float, rng: np.random.Generator, mu: float = 0.0) -> np.ndarray:
    e = rng.standard_normal(t + 200) * math.sqrt(1 - phi**2)
    x = np.empty_like(e)
    x[0] = e[0]
    for i in range(1, len(e)):
        x[i] = phi * x[i - 1] + e[i]
    return mu + x[200:]


@pytest.mark.parametrize(("t", "lags"), [(250, 4), (1000, 6), (2500, 8), (100, 4), (99, 3)])
def test_F_7_1_the_newey_west_1994_lag_rule(t: int, lags: int) -> None:
    assert newey_west_lags(t) == lags == math.floor(4 * (t / 100) ** (2 / 9))


@pytest.mark.parametrize("phi", [0.0, 0.3])
def test_F_7_1_hac_t_equals_statsmodels(phi: float) -> None:
    x = _ar1(1000, phi, np.random.default_rng(5), mu=0.05)
    ours = hac_t_test(x)
    oracle = sm.OLS(x, np.ones_like(x)).fit(
        cov_type="HAC", cov_kwds={"maxlags": ours.lags, "use_correction": False}
    )
    assert ours.lags == 6
    assert ours.statistic == pytest.approx(float(oracle.tvalues[0]), rel=1e-10)
    assert ours.p_value == pytest.approx(float(oracle.pvalues[0]), rel=1e-8)


def test_F_7_1_hac_nan_in_nan_out() -> None:
    r = hac_t_test([1.0, math.nan, 2.0], lags=1)
    assert math.isnan(r.statistic) and math.isnan(r.p_value)


def _coverage(series: int, t: int, reps: int, phi: float) -> tuple[float, float]:
    rng = np.random.default_rng(11)
    mu, hit_m, hit_s = 0.05, 0, 0  # unit unconditional sd: the true Sharpe is mu
    for k in range(series):
        x = _ar1(t, phi, rng, mu)
        common = {"scheme": "stationary", "method": "percentile", "level": 0.95, "reps": reps}
        m = bootstrap_interval(x, "expectancy", seed=k, **common)  # type: ignore[arg-type]
        s = bootstrap_interval(x, "sharpe", seed=k, **common)  # type: ignore[arg-type]
        hit_m += m.lower <= mu <= m.upper
        hit_s += s.lower <= mu <= s.upper
    return hit_m / series, hit_s / series


def test_F_7_1_block_bootstrap_covers_on_dependent_returns() -> None:
    cov_m, cov_s = _coverage(series=80, t=500, reps=199, phi=0.2)
    assert cov_m >= 0.85 and cov_s >= 0.85  # 80 series: about +-5 points at two sd


@pytest.mark.slow
def test_F_7_1_block_bootstrap_coverage_near_nominal() -> None:
    cov_m, cov_s = _coverage(series=400, t=1000, reps=499, phi=0.2)
    assert 0.91 <= cov_m <= 0.98 and 0.91 <= cov_s <= 0.98


def test_F_7_1_block_length_adapts_and_the_interval_is_deterministic() -> None:
    rng = np.random.default_rng(6)
    assert automatic_block_length(rng.standard_normal(1000), "stationary") < 3
    assert automatic_block_length(_ar1(1000, 0.5, rng), "stationary") > 3
    assert float(automatic_block_length(_ar1(1000, 0.5, rng), "circular")).is_integer()
    x = _ar1(500, 0.2, rng, 0.05)
    kw = {"scheme": "circular", "method": "percentile", "level": 0.9, "reps": 99, "seed": 3}
    a = bootstrap_interval(x, "sharpe", **kw)  # type: ignore[arg-type]
    assert a == bootstrap_interval(x, "sharpe", **kw)  # type: ignore[arg-type]
    assert a.lower < a.estimate < a.upper and a.block_length >= 1
    with pytest.raises(ValueError):
        bootstrap_interval([1.0] * 5, "sharpe", **kw)  # type: ignore[arg-type]


def test_F_7_1_D725_defaults_are_the_stationary_percentile_pair() -> None:
    x = _ar1(300, 0.2, np.random.default_rng(12), 0.05)
    r = bootstrap_interval(x, "expectancy", level=0.9, reps=99, seed=1)
    assert (r.scheme, r.method) == ("stationary", "percentile")
