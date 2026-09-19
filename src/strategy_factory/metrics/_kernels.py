"""Numba kernels for the core metrics.

The single-run path (:mod:`strategy_factory.metrics.standard`) and the grid path
(:mod:`strategy_factory.metrics.batch`) both call :func:`core_one`, so they give bit-identical
results. Kernels are pure: arrays in, arrays/scalars out. No fastmath, so floating-point
operation order is fixed.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange


@njit(cache=True)
def yearly_drawdowns(equity, year_id, n_years, capital):
    """Per-year maximum drawdown in money, both versions.

    * ``dd_ystart[y]``: running peak starts at the equity at the end of the previous year
      (``capital`` for the first year);
    * ``dd_peak[y]``: running peak is the all-time peak (starting from ``capital``).
    """
    dd_ystart = np.zeros(n_years)
    dd_peak = np.zeros(n_years)
    peak_all = capital
    peak_year = capital
    prev = capital
    cur = -1
    for t in range(equity.shape[0]):
        y = year_id[t]
        if y != cur:
            cur = y
            peak_year = prev
        e = equity[t]
        if e > peak_year:
            peak_year = e
        if e > peak_all:
            peak_all = e
        d = peak_year - e
        if d > dd_ystart[y]:
            dd_ystart[y] = d
        d = peak_all - e
        if d > dd_peak[y]:
            dd_peak[y] = d
        prev = e
    return dd_ystart, dd_peak


@njit(cache=True)
def weighted_mean(values, weights):
    acc = 0.0
    wsum = 0.0
    for i in range(values.shape[0]):
        acc += weights[i] * values[i]
        wsum += weights[i]
    return acc / wsum


@njit(cache=True)
def position_entries(in_position):
    """Number of flat -> in-position transitions (a position held at bar 0 counts)."""
    count = 0
    prev = False
    for t in range(in_position.shape[0]):
        cur = in_position[t]
        if cur and not prev:
            count += 1
        prev = cur
    return count


@njit(cache=True)
def core_one(equity, in_position, year_id, weights, capital, years):
    """Core metrics of one equity curve.

    Returns ``(avg_annual_profit_usd, avg_annual_profit_pct, avg_annual_dd_ystart_usd,
    avg_annual_dd_ystart_pct, profit_dd_ratio, exposure, n_position_entries)``.
    ``profit_dd_ratio`` is ``inf`` when the drawdown denominator is 0.
    """
    n = equity.shape[0]
    dd_ystart, _ = yearly_drawdowns(equity, year_id, weights.shape[0], capital)
    profit_usd = (equity[n - 1] - capital) / years
    profit_pct = profit_usd / capital * 100.0
    dd_usd = weighted_mean(dd_ystart, weights)
    dd_pct = dd_usd / capital * 100.0
    ratio = profit_pct / dd_pct if dd_pct > 0.0 else np.inf
    held = 0
    for t in range(n):
        if in_position[t]:
            held += 1
    exposure = held / n
    return (
        profit_usd,
        profit_pct,
        dd_usd,
        dd_pct,
        ratio,
        exposure,
        position_entries(in_position),
    )


@njit(cache=True, parallel=True)
def core_batch(equity, in_position, year_id, weights, capital, years):
    """:func:`core_one` for every column of ``equity[n_bars, n_configs]``."""
    m = equity.shape[1]
    profit_usd = np.empty(m)
    profit_pct = np.empty(m)
    dd_usd = np.empty(m)
    dd_pct = np.empty(m)
    ratio = np.empty(m)
    exposure = np.empty(m)
    n_entries = np.empty(m, dtype=np.int64)
    for j in prange(m):  # type: ignore[attr-defined]
        r = core_one(equity[:, j], in_position[:, j], year_id, weights, capital, years)
        profit_usd[j] = r[0]
        profit_pct[j] = r[1]
        dd_usd[j] = r[2]
        dd_pct[j] = r[3]
        ratio[j] = r[4]
        exposure[j] = r[5]
        n_entries[j] = r[6]
    return profit_usd, profit_pct, dd_usd, dd_pct, ratio, exposure, n_entries
