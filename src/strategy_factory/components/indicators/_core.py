"""Shared Numba kernels with TradingView (Pine) ``na`` semantics.

Conventions used by every kernel in this package:

* inputs are 1-D contiguous float64 arrays; ``NaN`` plays the role of Pine's ``na``;
* a window statistic is ``NaN`` until ``length`` bars exist and whenever any value in the
  window is ``NaN`` (Pine's ``ta.sma``/``ta.highest``/``math.sum`` behaviour);
* comparisons with ``NaN`` are false, as in Pine;
* output ``i`` depends only on inputs ``0..i`` (no look-ahead).

The kernels are private; the public, documented wrappers live in the sibling modules.
"""

from __future__ import annotations

import numpy as np
from numba import njit

# TradingView's float-noise threshold. Its reference ``ta.stdev`` sets a deviation with
# ``|d| <= TV_EPS`` to exactly zero, and ``ta.dmi`` treats +DM/-DM moves that differ by no
# more than this as a tie (verified on the golden files). Numerical constant of
# TradingView's algorithms, not a research decision.
TV_EPS = 1e-10


def as_f64(x: object, name: str = "x") -> np.ndarray:
    """1-D contiguous float64 copy-free view of ``x`` (raises on other shapes)."""
    arr = np.ascontiguousarray(x, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    return arr


def check_length(length: int, name: str = "length", minimum: int = 1) -> int:
    """Validate an integer window length."""
    if isinstance(length, bool) or int(length) != length or length < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {length!r}")
    return int(length)


def same_length(*arrays: np.ndarray) -> None:
    n = arrays[0].shape[0]
    if any(a.shape[0] != n for a in arrays):
        raise ValueError("input arrays must have the same length")


@njit(cache=True)
def sma_kernel(src, length):
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(length - 1, n):
        s = 0.0
        ok = True
        for k in range(i - length + 1, i + 1):
            v = src[k]
            if np.isnan(v):
                ok = False
                break
            s += v
        if ok:
            out[i] = s / length
    return out


@njit(cache=True)
def smoothed_kernel(src, length, alpha):
    """Pine ``ta.ema``/``ta.rma`` recursion.

    ``out[i] = sma(src, length)[i]`` while ``out[i-1]`` is na (SMA seed), else
    ``alpha * src[i] + (1 - alpha) * out[i-1]``.
    """
    n = src.shape[0]
    out = np.full(n, np.nan)
    prev = np.nan
    for i in range(n):
        if np.isnan(prev):
            val = np.nan
            if i >= length - 1:
                s = 0.0
                ok = True
                for k in range(i - length + 1, i + 1):
                    v = src[k]
                    if np.isnan(v):
                        ok = False
                        break
                    s += v
                if ok:
                    val = s / length
        else:
            val = alpha * src[i] + (1.0 - alpha) * prev
        out[i] = val
        prev = val
    return out


@njit(cache=True)
def wma_kernel(src, length):
    """Pine ``ta.wma``: weights ``length`` (current bar) down to 1 (oldest bar)."""
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(length - 1, n):
        norm = 0.0
        s = 0.0
        ok = True
        for j in range(length):
            v = src[i - j]
            if np.isnan(v):
                ok = False
                break
            w = float((length - j) * length)
            norm += w
            s += v * w
        if ok:
            out[i] = s / norm
    return out


@njit(cache=True)
def stdev_kernel(src, length):
    """Pine ``ta.stdev(src, length, biased=true)`` (population), two-pass with the EPS rule."""
    n = src.shape[0]
    out = np.full(n, np.nan)
    avg = sma_kernel(src, length)
    for i in range(length - 1, n):
        m = avg[i]
        if np.isnan(m):
            continue
        ss = 0.0
        for k in range(i - length + 1, i + 1):
            d = src[k] - m
            if abs(d) <= TV_EPS:
                d = 0.0
            ss += d * d
        out[i] = np.sqrt(ss / length)
    return out


@njit(cache=True)
def highest_kernel(src, length):
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(length - 1, n):
        best = src[i - length + 1]
        ok = not np.isnan(best)
        for k in range(i - length + 2, i + 1):
            v = src[k]
            if np.isnan(v):
                ok = False
                break
            if v > best:
                best = v
        if ok:
            out[i] = best
    return out


@njit(cache=True)
def lowest_kernel(src, length):
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(length - 1, n):
        best = src[i - length + 1]
        ok = not np.isnan(best)
        for k in range(i - length + 2, i + 1):
            v = src[k]
            if np.isnan(v):
                ok = False
                break
            if v < best:
                best = v
        if ok:
            out[i] = best
    return out


@njit(cache=True)
def extreme_offset_kernel(src, length, find_max):
    """Pine ``ta.highestbars``/``ta.lowestbars``: offset (<= 0) of the extreme in the window.

    Ties resolve to the oldest bar holding the extreme value (golden Aroon columns).
    """
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(length - 1, n):
        best = src[i - length + 1]
        pos = i - length + 1
        ok = not np.isnan(best)
        for k in range(i - length + 2, i + 1):
            v = src[k]
            if np.isnan(v):
                ok = False
                break
            if (find_max and v > best) or ((not find_max) and v < best):
                best = v
                pos = k
        if ok:
            out[i] = float(pos - i)
    return out


@njit(cache=True)
def shift_kernel(src, periods):
    """``src[periods]`` in Pine notation: the value ``periods`` bars ago (NaN before start)."""
    n = src.shape[0]
    out = np.full(n, np.nan)
    for i in range(periods, n):
        out[i] = src[i - periods]
    return out


@njit(cache=True)
def true_range_kernel(high, low, close, handle_na):
    n = high.shape[0]
    out = np.full(n, np.nan)
    if n == 0:
        return out
    if handle_na:
        out[0] = high[0] - low[0]
    for i in range(1, n):
        pc = close[i - 1]
        out[i] = max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc))
    return out


@njit(cache=True)
def fixnan_kernel(src):
    """Pine ``fixnan``: replace NaN with the last non-NaN value (leading NaN stays NaN)."""
    n = src.shape[0]
    out = np.full(n, np.nan)
    last = np.nan
    for i in range(n):
        if not np.isnan(src[i]):
            last = src[i]
        out[i] = last
    return out
