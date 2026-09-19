"""Oscillators and normalised price measures."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numba import njit

from strategy_factory.components.indicators._core import (
    as_f64,
    check_length,
    highest_kernel,
    lowest_kernel,
    same_length,
    shift_kernel,
    sma_kernel,
    smoothed_kernel,
    stdev_kernel,
)


class MACD(NamedTuple):
    line: np.ndarray
    signal: np.ndarray
    hist: np.ndarray


class Stochastic(NamedTuple):
    k: np.ndarray
    d: np.ndarray


@njit(cache=True)
def _rsi_from_changes(up, down):
    n = up.shape[0]
    out = np.full(n, np.nan)
    for i in range(n):
        u = up[i]
        d = down[i]
        if np.isnan(u) or np.isnan(d):
            continue
        if d == 0.0:
            out[i] = 100.0
        elif u == 0.0:
            out[i] = 0.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + u / d)
    return out


@njit(cache=True)
def _rsi_kernel(src, length):
    n = src.shape[0]
    gain = np.full(n, np.nan)
    loss = np.full(n, np.nan)
    for i in range(1, n):
        ch = src[i] - src[i - 1]
        if np.isnan(ch):
            continue
        gain[i] = max(ch, 0.0)
        loss[i] = max(-ch, 0.0)
    alpha = 1.0 / length
    return _rsi_from_changes(
        smoothed_kernel(gain, length, alpha), smoothed_kernel(loss, length, alpha)
    )


def rsi(src: np.ndarray, length: int = 14) -> np.ndarray:
    """Relative strength index (``ta.rsi``), Wilder smoothing.

    * gains/losses from ``src - src[1]`` (NaN on bar 0), each smoothed with :func:`rma`
      (SMA seed of the first ``length`` changes), so the first value is at bar ``length``;
    * ``down == 0 → 100``, else ``up == 0 → 0``, else ``100 - 100 / (1 + up/down)``
      (TradingView's rule; a flat window therefore gives 100, not NaN or 50).
    """
    length = check_length(length)
    return _rsi_kernel(as_f64(src, "src"), length)


def ibs(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Internal bar strength ``(close - low) / (high - low)``; NaN when ``high == low``."""
    h, lo, c = as_f64(high, "high"), as_f64(low, "low"), as_f64(close, "close")
    same_length(h, lo, c)
    rng = h - lo
    out = np.full(h.shape[0], np.nan)
    ok = rng != 0.0
    out[ok] = (c[ok] - lo[ok]) / rng[ok]
    return out


def zscore(src: np.ndarray, length: int = 20) -> np.ndarray:
    """``(src - sma) / stdev`` with population stdev; NaN when stdev is 0 (Pine script rule)."""
    length = check_length(length)
    x = as_f64(src, "src")
    m = sma_kernel(x, length)
    s = stdev_kernel(x, length)
    out = np.full(x.shape[0], np.nan)
    ok = s != 0.0  # NaN != 0 is True; NaN then propagates through the division
    out[ok] = (x[ok] - m[ok]) / s[ok]
    return out


def macd(src: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> MACD:
    """MACD (``ta.macd``): ``ema(fast) - ema(slow)``, signal ``ema(line, signal)``, hist.

    Each EMA is SMA-seeded (see :func:`ema`), so the line starts at bar ``slow - 1`` and the
    signal at bar ``slow + signal - 2`` (seeded by the SMA of the first ``signal`` line values).
    """
    fast = check_length(fast, "fast")
    slow = check_length(slow, "slow")
    signal = check_length(signal, "signal")
    x = as_f64(src, "src")
    line = smoothed_kernel(x, fast, 2.0 / (fast + 1)) - smoothed_kernel(x, slow, 2.0 / (slow + 1))
    sig = smoothed_kernel(line, signal, 2.0 / (signal + 1))
    return MACD(line, sig, line - sig)


def roc(src: np.ndarray, length: int = 20) -> np.ndarray:
    """Rate of change in percent (``ta.roc``): ``100 * (src - src[length]) / src[length]``."""
    length = check_length(length)
    x = as_f64(src, "src")
    prev = shift_kernel(x, length)
    return 100.0 * (x - prev) / prev


def momentum(src: np.ndarray, length: int) -> np.ndarray:
    """``src - src[length]`` (``ta.mom``); same sign as :func:`roc` for positive prices."""
    length = check_length(length)
    x = as_f64(src, "src")
    return x - shift_kernel(x, length)


def _range_position(high, low, close, length, offset):
    h, lo, c = as_f64(high, "high"), as_f64(low, "low"), as_f64(close, "close")
    same_length(h, lo, c)
    hh = highest_kernel(h, length)
    ll = lowest_kernel(lo, length)
    rng = hh - ll
    out = np.full(h.shape[0], np.nan)
    ok = rng != 0.0
    out[ok] = 100.0 * (c[ok] - offset(hh, ll)[ok]) / rng[ok]
    return out


def williams_r(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14
) -> np.ndarray:
    """Williams %R (``ta.wpr``): ``100 * (close - hh) / (hh - ll)`` in [-100, 0].

    NaN during the ``length - 1`` warm-up bars and when ``hh == ll``.
    """
    length = check_length(length)
    return _range_position(high, low, close, length, lambda hh, ll: hh)


def stochastic(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    length: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> Stochastic:
    """Stochastic oscillator: ``K = sma(ta.stoch(close, high, low, length), k_smooth)``,
    ``D = sma(K, d_smooth)``. Raw stoch is NaN when ``hh == ll``."""
    length = check_length(length)
    k_smooth = check_length(k_smooth, "k_smooth")
    d_smooth = check_length(d_smooth, "d_smooth")
    raw = _range_position(high, low, close, length, lambda hh, ll: ll)
    k = sma_kernel(raw, k_smooth)
    return Stochastic(k, sma_kernel(k, d_smooth))


@njit(cache=True)
def _percent_rank_kernel(src, length):
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(length, n):
        cur = src[i]
        if np.isnan(cur):
            continue
        cnt = 0
        for k in range(i - length, i):
            if src[k] <= cur:  # a NaN in the history counts as "not <="
                cnt += 1
        out[i] = 100.0 * cnt / length
    return out


def percent_rank(src: np.ndarray, length: int) -> np.ndarray:
    """Percent of the previous ``length`` values (current bar excluded) that are ``<=`` the
    current value (``ta.percentrank``).

    NaN on bars ``0 .. length-1`` and where the current value is NaN. A NaN inside the
    history window is counted as "not <=" but the divisor stays ``length`` (golden: Connors
    RSI starts at bar 100 although ``roc(close, 1)`` is NaN on bar 0).
    """
    length = check_length(length)
    return _percent_rank_kernel(as_f64(src, "src"), length)


@njit(cache=True)
def _streak_kernel(src):
    n = src.shape[0]
    out = np.full(n, np.nan)
    prev = np.nan  # ud[1]; Pine's history of a `var` on bar 0 is na
    for i in range(n):
        if i > 0 and src[i] == src[i - 1]:
            ud = 0.0
        elif i > 0 and src[i] > src[i - 1]:
            ud = 1.0 if prev <= 0.0 else prev + 1.0
        else:
            ud = -1.0 if prev >= 0.0 else prev - 1.0
        out[i] = ud
        prev = ud
    return out


def updown_streak(src: np.ndarray) -> np.ndarray:
    """Consecutive up (+n) / down (-n) streak of ``src``; 0 on an unchanged value.

    Golden-file convention (the ``updown`` helper in ``sf_golden_indicators.pine``): the
    previous streak ``ud[1]`` is ``na`` on bar 0, and ``na ± 1`` stays ``na``, so the streak
    is NaN from bar 0 until the first unchanged value resets it to 0. Textbook Connors RSI
    starts the streak at 0 on the first bar. See the T07 review (open question).
    """
    return _streak_kernel(as_f64(src, "src"))


def connors_rsi(
    close: np.ndarray, rsi_length: int = 3, streak_length: int = 2, rank_length: int = 100
) -> np.ndarray:
    """Connors RSI: mean of ``rsi(close, rsi_length)``, ``rsi(streak, streak_length)`` and
    ``percent_rank(roc(close, 1), rank_length)``. NaN if any part is NaN; inherits the
    streak convention of :func:`updown_streak`."""
    rsi_length = check_length(rsi_length, "rsi_length")
    streak_length = check_length(streak_length, "streak_length")
    rank_length = check_length(rank_length, "rank_length")
    c = as_f64(close, "close")
    a = _rsi_kernel(c, rsi_length)
    b = _rsi_kernel(_streak_kernel(c), streak_length)
    prev = shift_kernel(c, 1)
    r = _percent_rank_kernel(100.0 * (c - prev) / prev, rank_length)
    return (a + b + r) / 3.0
