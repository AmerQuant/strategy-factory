"""Moving averages (TradingView conventions, verified against the golden exports)."""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from strategy_factory.components.indicators._core import (
    as_f64,
    check_length,
    shift_kernel,
    sma_kernel,
    smoothed_kernel,
    wma_kernel,
)


def sma(src: np.ndarray, length: int) -> np.ndarray:
    """Simple moving average (``ta.sma``).

    Warm-up: NaN for the first ``length - 1`` bars and wherever the window contains NaN.
    """
    length = check_length(length)
    return sma_kernel(as_f64(src, "src"), length)


def ema(src: np.ndarray, length: int) -> np.ndarray:
    """Exponential moving average (``ta.ema``), ``alpha = 2 / (length + 1)``.

    Seeding (TradingView, confirmed by the golden files): the first value is the SMA of the
    first ``length`` values (bar ``length - 1``); earlier bars are NaN. Textbook variants that
    seed with the first price, or start at bar 0, differ from TradingView for many bars.
    The seed is re-taken whenever the previous output is NaN (Pine ``na(sum[1])`` rule).
    """
    length = check_length(length)
    return smoothed_kernel(as_f64(src, "src"), length, 2.0 / (length + 1))


def rma(src: np.ndarray, length: int) -> np.ndarray:
    """Wilder's moving average (``ta.rma``), ``alpha = 1 / length``.

    Seeding identical to :func:`ema`: SMA of the first ``length`` values, NaN before.
    """
    length = check_length(length)
    return smoothed_kernel(as_f64(src, "src"), length, 1.0 / length)


def wma(src: np.ndarray, length: int) -> np.ndarray:
    """Linearly weighted moving average (``ta.wma``): weight ``length`` on the current bar."""
    length = check_length(length)
    return wma_kernel(as_f64(src, "src"), length)


def hma(src: np.ndarray, length: int) -> np.ndarray:
    """Hull moving average (``ta.hma``).

    ``wma(2 * wma(src, length // 2) - wma(src, length), floor(sqrt(length)))``.
    Convention: the half length is ``length // 2`` (integer division; identical to Pine for
    even lengths, which is all the golden file covers). Requires ``length >= 2``.
    First value at bar ``length - 1 + floor(sqrt(length)) - 1``.
    """
    length = check_length(length, minimum=2)
    x = as_f64(src, "src")
    half = wma_kernel(x, length // 2)
    full = wma_kernel(x, length)
    return wma_kernel(2.0 * half - full, max(1, math.isqrt(length)))


def sma_slope(src: np.ndarray, length: int) -> np.ndarray:
    """One-bar change of the SMA: ``sma[i] - sma[i-1]`` (first value at bar ``length``)."""
    s = sma(src, length)
    return s - shift_kernel(s, 1)


@njit(cache=True)
def _kama_kernel(src, length, fast_sc, slow_sc):
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(n):
        if i < length:
            out[i] = src[i]
            continue
        change = abs(src[i] - src[i - length])
        vol = 0.0
        for k in range(i - length + 1, i + 1):
            vol += abs(src[k] - src[k - 1])
        er = change / vol if vol != 0.0 else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        prev = out[i - 1]
        out[i] = prev + sc * (src[i] - prev)
    return out


def kama(src: np.ndarray, length: int = 10, fast: int = 2, slow: int = 30) -> np.ndarray:
    """Kaufman adaptive moving average, as defined in ``sf_golden_indicators.pine``.

    * efficiency ratio ``er = |src - src[length]| / sum(|src - src[1]|, length)``, and
      ``er = 0`` when the volatility sum is 0;
    * ``sc = (er * (2/(fast+1) - 2/(slow+1)) + 2/(slow+1)) ** 2``;
    * seeding (our convention, fixed in the Pine script): ``kama = src`` for bars
      ``0 .. length-1``, then ``kama = kama[1] + sc * (src - kama[1])``. There is no NaN
      warm-up. Textbook KAMA usually seeds once with the first close or an SMA.
    """
    length = check_length(length)
    fast = check_length(fast, "fast")
    slow = check_length(slow, "slow")
    return _kama_kernel(as_f64(src, "src"), length, 2.0 / (fast + 1), 2.0 / (slow + 1))
