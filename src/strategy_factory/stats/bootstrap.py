"""F-7.1: bootstrap confidence intervals for the Sharpe ratio and the expectancy (T16, D-723).

A **block bootstrap with automatic block-length selection** (D-723): the block length is Politis &
White (2004) with the Patton, Politis & White (2009) correction, ``arch``'s
``optimal_block_length``, for the chosen scheme. The resampling and the interval are ``arch``'s
(D-659). Measured: the block bootstraps cover 92.5-94.5 % where i.i.d. resampling covers 88 % on
AR(1) phi 0.2 returns (``docs/tasks/T16_plan.md`` §3).

The **scheme** (stationary or circular block) and the **interval method** are explicit arguments:
D-723 fixes the automatic block length, not these two. A circular block bootstrap needs an integer
block, so its automatic length is rounded up. The Sharpe ratio is per observation (the mean over the
sample standard deviation, ddof 1). Randomness only through ``seed`` (D-660).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal

import numpy as np
import numpy.typing as npt
from arch.bootstrap import CircularBlockBootstrap, StationaryBootstrap, optimal_block_length

from strategy_factory.stats.results import IntervalResult

Scheme = Literal["stationary", "circular"]
Method = Literal["percentile", "basic", "bca", "studentized"]
Statistic = Literal["sharpe", "expectancy"]


def _sharpe(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return np.array([x.mean() / x.std(ddof=1)])


def _expectancy(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return np.array([x.mean()])


_FUNCS: dict[str, Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]]] = {
    "sharpe": _sharpe,
    "expectancy": _expectancy,
}


def automatic_block_length(returns: npt.ArrayLike, scheme: Scheme) -> float:
    """Politis-White (with the 2009 correction) for ``scheme``, at least 1 (D-723)."""
    x = np.asarray(returns, dtype=np.float64).ravel()
    length = float(optimal_block_length(x)[scheme].iloc[0])
    length = max(1.0, length)
    return float(math.ceil(length)) if scheme == "circular" else length


def bootstrap_interval(
    returns: npt.ArrayLike,
    statistic: Statistic,
    *,
    scheme: Scheme,
    method: Method,
    level: float,
    reps: int,
    seed: int,
    block_length: float | None = None,
) -> IntervalResult:
    """F-7.1: a ``level`` interval for ``statistic`` of ``returns``; the block length is automatic
    unless given."""
    x = np.asarray(returns, dtype=np.float64).ravel()
    if x.size < 10 or np.isnan(x).any():
        raise ValueError(f"returns must hold at least 10 values and no NaN, got {x.size}")
    if not 0 < level < 1 or reps < 1:
        raise ValueError(f"level must be in (0, 1) and reps >= 1, got {level}, {reps}")
    block = automatic_block_length(x, scheme) if block_length is None else block_length
    func = _FUNCS[statistic]
    if scheme == "stationary":
        # a mean block length: arch hints int but takes the fractional Politis-White length
        bs: StationaryBootstrap | CircularBlockBootstrap = StationaryBootstrap(
            block,  # type: ignore[arg-type]
            x,
            seed=seed,
        )
    else:
        bs = CircularBlockBootstrap(int(block), x, seed=seed)
    lower, upper = bs.conf_int(func, reps=reps, method=method, size=level).ravel()
    return IntervalResult(
        statistic_name=statistic,
        estimate=float(func(x)[0]),
        lower=float(lower),
        upper=float(upper),
        level=level,
        n=int(x.size),
        scheme=scheme,
        method=method,
        block_length=float(block),
        reps=reps,
        seed=seed,
    )
