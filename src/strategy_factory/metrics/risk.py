"""Risk and distribution metrics (F-0.5.2).

Definitions (all percentages are of initial capital):

* **Daily P&L**: the equity of a UTC date is the last ``equity_mtm`` of that date; daily
  P&L is its change from the previous date (the first date is compared with initial
  capital); daily return = daily P&L / initial capital.
* **Sharpe** = mean(daily return) / std(daily return, ddof=1) * sqrt(periods_per_year).
  NaN with fewer than 2 days or zero dispersion.
* **Sortino** = mean(daily return) / downside deviation * sqrt(periods_per_year), with
  downside deviation = sqrt(mean(min(r, 0)^2)) over all days (target 0). With no losing day
  it is ``inf`` when the mean is positive, NaN otherwise.
* **Drawdown series** ``dd[t] = max(initial_capital, max(equity[:t+1])) - equity[t]``.
  Max drawdown is its maximum, in % of initial capital.
* **Ulcer index** = sqrt(mean((dd[t] / initial_capital * 100)^2)) over all bars.
* **Time under water**: a stretch is a maximal run of bars with ``dd > 0``. Its length in
  bars is the number of bars in the run; its length in calendar days runs from the peak
  (the bar before the run, or the first bar when the run starts at bar 0) to the recovery
  bar (the bar after the run) or, if not recovered, to the last bar. The longest stretch is
  reported separately in bars and in days.
* **Skewness / excess kurtosis** of per-trade returns ``pnl_net / notional``: population
  (biased) moments ``m3 / m2^1.5`` and ``m4 / m2^2 - 3``. NaN with fewer than 2 trades or
  zero variance.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from strategy_factory.metrics._calendar import NS_PER_DAY, as_ns, day_keys
from strategy_factory.metrics.containers import EquityCurve

FloatArray = NDArray[np.float64]


def daily_returns(curve: EquityCurve) -> FloatArray:
    days = day_keys(curve.ts)
    last_of_day = np.flatnonzero(np.append(days[1:] != days[:-1], True))
    daily_equity = curve.equity_mtm[last_of_day]
    pnl = np.diff(daily_equity, prepend=curve.initial_capital)
    return pnl / curve.initial_capital


def sharpe(returns: FloatArray, periods_per_year: int) -> float:
    if returns.size < 2:
        return math.nan
    sd = float(np.std(returns, ddof=1))
    if sd == 0.0:
        return math.nan
    return float(np.mean(returns)) / sd * math.sqrt(periods_per_year)


def sortino(returns: FloatArray, periods_per_year: int) -> float:
    if returns.size == 0:
        return math.nan
    mean = float(np.mean(returns))
    downside = math.sqrt(float(np.mean(np.minimum(returns, 0.0) ** 2)))
    if downside == 0.0:
        return math.inf if mean > 0.0 else math.nan
    return mean / downside * math.sqrt(periods_per_year)


def drawdown_series(curve: EquityCurve) -> FloatArray:
    """Money drawdown below the all-time running peak (which starts at initial capital)."""
    peak = np.maximum.accumulate(np.maximum(curve.equity_mtm, curve.initial_capital))
    return peak - curve.equity_mtm


def max_drawdown_pct(curve: EquityCurve) -> float:
    return float(drawdown_series(curve).max()) / curve.initial_capital * 100.0


def ulcer_index(curve: EquityCurve) -> float:
    dd_pct = drawdown_series(curve) / curve.initial_capital * 100.0
    return math.sqrt(float(np.mean(dd_pct**2)))


def longest_underwater(curve: EquityCurve) -> tuple[int, float]:
    """Longest time under water as ``(bars, calendar days)``, each maximised separately."""
    under = drawdown_series(curve) > 0.0
    ts = as_ns(curve.ts)
    n = under.size
    best_bars, best_days = 0, 0.0
    t = 0
    while t < n:
        if not under[t]:
            t += 1
            continue
        start = t
        while t < n and under[t]:
            t += 1
        end = t - 1
        peak_idx = start - 1 if start > 0 else start
        stop_idx = end + 1 if end + 1 < n else end
        best_bars = max(best_bars, end - start + 1)
        best_days = max(best_days, float(ts[stop_idx] - ts[peak_idx]) / NS_PER_DAY)
    return best_bars, best_days


def trade_return_moments(pnl_net: FloatArray, notional: float) -> tuple[float, float]:
    """Skewness and excess kurtosis of per-trade returns ``pnl_net / notional``."""
    if pnl_net.size < 2:
        return math.nan, math.nan
    r = pnl_net / notional
    dev = r - r.mean()
    m2 = float(np.mean(dev**2))
    if m2 == 0.0:
        return math.nan, math.nan
    m3 = float(np.mean(dev**3))
    m4 = float(np.mean(dev**4))
    return m3 / m2**1.5, m4 / m2**2 - 3.0
