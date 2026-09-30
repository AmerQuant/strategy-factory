"""F-7.1: t-tests of "mean return = 0" (T16, D-660, D-723).

* :func:`hac_t_test` -- daily returns are serially dependent, so the mean's standard error uses the
  Newey-West long-run variance with the Bartlett kernel ``w_j = 1 - j / (L + 1)`` and **the
  Newey-West (1994) lag rule** ``L = floor(4 (T / 100)^(2/9))`` (D-723). The p-value is two-sided
  from the standard normal (the HAC statistic's asymptotic distribution). Measured: on AR(1)
  returns with phi 0.3 the plain t-test rejects a true null 13-16 % of the time; with this rule
  about 6 % (``docs/tasks/T16_plan.md`` §3). It equals ``statsmodels``' HAC at the same lag.

A NaN in the returns gives NaN results (D-651 (1)): the caller drops what it means to drop.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import numpy.typing as npt

from strategy_factory.stats.results import TTestResult

_N = NormalDist()


def newey_west_lags(n_obs: int) -> int:
    """The Newey-West (1994) lag rule: ``floor(4 (T / 100)^(2/9))`` (D-723)."""
    return math.floor(4 * (n_obs / 100) ** (2 / 9))


def long_run_variance(x: npt.NDArray[np.float64], lags: int) -> float:
    """The Newey-West (Bartlett) long-run variance of ``x``, divided by T (not T - 1)."""
    t = len(x)
    u = x - x.mean()
    s = float(u @ u) / t
    for j in range(1, lags + 1):
        s += 2 * (1 - j / (lags + 1)) * float(u[j:] @ u[:-j]) / t
    return s


def hac_t_test(returns: npt.ArrayLike, lags: int | None = None) -> TTestResult:
    """F-7.1: the HAC t-test of a daily return series; ``lags`` default: Newey-West 1994."""
    x = np.asarray(returns, dtype=np.float64).ravel()
    n = int(x.size)
    lag = newey_west_lags(n) if lags is None else lags
    if lag < 0 or (n and lag >= n):
        raise ValueError(f"lags must be in [0, {n}), got {lag}")
    if n < 2 or np.isnan(x).any():
        return TTestResult(
            method="hac_newey_west", statistic=math.nan, p_value=math.nan,
            mean=math.nan, n=n, lags=lag,
        )  # fmt: skip
    var = long_run_variance(x, lag)
    mean = float(x.mean())
    stat = mean / math.sqrt(var / n) if var > 0 else math.nan
    p = math.nan if math.isnan(stat) else 2 * (1 - _N.cdf(abs(stat)))
    return TTestResult(method="hac_newey_west", statistic=stat, p_value=p, mean=mean, n=n, lags=lag)
