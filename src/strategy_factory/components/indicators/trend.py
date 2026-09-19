"""Trend indicators: DMI/ADX, Supertrend, Parabolic SAR, Aroon, Ichimoku."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numba import njit

from strategy_factory.components.indicators._core import (
    TV_EPS,
    as_f64,
    check_length,
    extreme_offset_kernel,
    fixnan_kernel,
    highest_kernel,
    lowest_kernel,
    same_length,
    smoothed_kernel,
    true_range_kernel,
)


class DMI(NamedTuple):
    plus: np.ndarray
    minus: np.ndarray
    adx: np.ndarray


class Supertrend(NamedTuple):
    value: np.ndarray
    direction: np.ndarray


class Aroon(NamedTuple):
    up: np.ndarray
    down: np.ndarray


class Ichimoku(NamedTuple):
    tenkan: np.ndarray
    kijun: np.ndarray
    span_a_raw: np.ndarray
    span_b_raw: np.ndarray


def _hlc(high, low, close):
    h, lo, c = as_f64(high, "high"), as_f64(low, "low"), as_f64(close, "close")
    same_length(h, lo, c)
    return h, lo, c


@njit(cache=True)
def _directional_movement(high, low):
    n = high.shape[0]
    plus = np.full(n, np.nan)
    minus = np.full(n, np.nan)
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus[i] = up if (up - down > TV_EPS and up > 0.0) else 0.0
        minus[i] = down if (down - up > TV_EPS and down > 0.0) else 0.0
    return plus, minus


@njit(cache=True)
def _dmi_kernel(high, low, close, di_length, adx_length):
    n = high.shape[0]
    pdm, mdm = _directional_movement(high, low)
    a = 1.0 / di_length
    trur = smoothed_kernel(true_range_kernel(high, low, close, False), di_length, a)
    rp = smoothed_kernel(pdm, di_length, a)
    rm = smoothed_kernel(mdm, di_length, a)
    plus_raw = np.full(n, np.nan)
    minus_raw = np.full(n, np.nan)
    for i in range(n):
        if trur[i] != 0.0:  # Pine: x / 0 is na, later filled by fixnan
            plus_raw[i] = 100.0 * rp[i] / trur[i]
            minus_raw[i] = 100.0 * rm[i] / trur[i]
    plus = fixnan_kernel(plus_raw)
    minus = fixnan_kernel(minus_raw)
    dx = np.full(n, np.nan)
    for i in range(n):
        s = plus[i] + minus[i]
        dx[i] = abs(plus[i] - minus[i]) / (1.0 if s == 0.0 else s)
    adx = 100.0 * smoothed_kernel(dx, adx_length, 1.0 / adx_length)
    return plus, minus, adx


def dmi(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    di_length: int = 14,
    adx_length: int = 14,
) -> DMI:
    """Directional movement index (``ta.dmi``): DI+, DI- and ADX.

    * ``+DM = up if up > down and up > 0 else 0`` (``up = high - high[1]``,
      ``down = low[1] - low``); NaN on bar 0. ``up`` and ``down`` that differ by no more than
      ``1e-10`` (float rounding of equal price moves) are a tie, so both DM are 0 — this is
      what TradingView does (golden files); a strict float ``>`` gives DI errors of up to 10
      points on EURUSD 1H;
    * DI = ``100 * rma(DM) / rma(tr)`` with the bare true range (NaN on bar 0), then
      ``fixnan`` (a zero true-range average carries the previous DI forward);
    * ``ADX = 100 * rma(|DI+ - DI-| / (DI+ + DI-, or 1 if 0), adx_length)``.
    Warm-up: DI from bar ``di_length``, ADX from bar ``di_length + adx_length - 1``.
    """
    di_length = check_length(di_length, "di_length")
    adx_length = check_length(adx_length, "adx_length")
    h, lo, c = _hlc(high, low, close)
    return DMI(*_dmi_kernel(h, lo, c, di_length, adx_length))


@njit(cache=True)
def _supertrend_kernel(high, low, close, factor, atr_period):
    n = high.shape[0]
    atr = smoothed_kernel(true_range_kernel(high, low, close, True), atr_period, 1.0 / atr_period)
    value = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    prev_lower = np.nan  # lowerBand[1] after the ratchet
    prev_upper = np.nan
    prev_st = np.nan
    for i in range(n):
        src = (high[i] + low[i]) / 2.0
        upper = src + factor * atr[i]
        lower = src - factor * atr[i]
        p_lower = 0.0 if np.isnan(prev_lower) else prev_lower  # nz(lowerBand[1])
        p_upper = 0.0 if np.isnan(prev_upper) else prev_upper
        c1 = close[i - 1] if i > 0 else np.nan
        if not (lower > p_lower or c1 < p_lower):
            lower = p_lower
        if not (upper < p_upper or c1 > p_upper):
            upper = p_upper
        if i == 0 or np.isnan(atr[i - 1]):
            d = 1.0
        elif prev_st == p_upper:
            d = -1.0 if close[i] > upper else 1.0
        else:
            d = 1.0 if close[i] < lower else -1.0
        st = lower if d == -1.0 else upper
        value[i] = st
        direction[i] = d
        prev_lower = lower
        prev_upper = upper
        prev_st = st
    return value, direction


def supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    factor: float = 3.0,
    atr_period: int = 10,
) -> Supertrend:
    """Supertrend (``ta.supertrend(factor, atr_period)``), a line-by-line port of
    TradingView's reference implementation, including its ``na`` quirks:

    * bands ``hl2 ± factor * atr(atr_period)``; the lower band only rises and the upper band
      only falls unless the previous close crossed them; the previous bands enter through
      ``nz()`` (NaN → 0);
    * ``direction`` uses TradingView's convention: **-1 = up-trend** (line is the lower band),
      **+1 = down-trend**. It is +1 while ``atr[1]`` is NaN;
    * warm-up (golden files): bar 0 has ``value == 0.0`` (the ``nz`` of the missing previous
      upper band, *not* NaN), bars ``1 .. atr_period-2`` are NaN, values start at bar
      ``atr_period - 1``. ``direction`` is never NaN (+1 through the warm-up).
    """
    atr_period = check_length(atr_period, "atr_period")
    h, lo, c = _hlc(high, low, close)
    return Supertrend(*_supertrend_kernel(h, lo, c, float(factor), atr_period))


@njit(cache=True)
def _psar_kernel(high, low, close, start, inc, maximum):
    n = high.shape[0]
    out = np.full(n, np.nan)
    result = np.nan
    max_min = np.nan
    accel = np.nan
    is_below = False
    for i in range(1, n):
        first_trend_bar = False
        if i == 1:
            if close[1] > close[0]:
                is_below = True
                max_min = high[1]
                result = low[0]
            else:
                is_below = False
                max_min = low[1]
                result = high[0]
            first_trend_bar = True
            accel = start
        result = result + accel * (max_min - result)
        if is_below:
            if result > low[i]:
                first_trend_bar = True
                is_below = False
                result = max(high[i], max_min)
                max_min = low[i]
                accel = start
        else:
            if result < high[i]:
                first_trend_bar = True
                is_below = True
                result = min(low[i], max_min)
                max_min = high[i]
                accel = start
        if not first_trend_bar:
            if is_below:
                if high[i] > max_min:
                    max_min = high[i]
                    accel = min(accel + inc, maximum)
            else:
                if low[i] < max_min:
                    max_min = low[i]
                    accel = min(accel + inc, maximum)
        if is_below:
            result = min(result, low[i - 1])
            if i > 1:
                result = min(result, low[i - 2])
        else:
            result = max(result, high[i - 1])
            if i > 1:
                result = max(result, high[i - 2])
        out[i] = result
    return out


def psar(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    start: float = 0.02,
    increment: float = 0.02,
    maximum: float = 0.2,
) -> np.ndarray:
    """Parabolic SAR (``ta.sar``), port of TradingView's reference implementation.

    Seeding: NaN on bar 0. On bar 1 the trend is long if ``close[1] > close[0]`` (SAR starts
    at ``low[0]``, extreme point ``high[1]``), otherwise short (SAR ``high[0]``, EP
    ``low[1]``); acceleration starts at ``start``. On a reversal the SAR jumps to
    ``max(high, EP)`` / ``min(low, EP)``. The SAR is clamped by the previous two bars' lows
    (long) or highs (short). Textbook Wilder seeding (first extreme of a trend) differs.
    """
    h, lo, c = _hlc(high, low, close)
    return _psar_kernel(h, lo, c, float(start), float(increment), float(maximum))


def aroon(high: np.ndarray, low: np.ndarray, length: int = 25) -> Aroon:
    """Aroon up/down as plotted by TradingView's built-in:
    ``100 * (highestbars(high, length + 1) + length) / length`` (and ``lowestbars`` on low).

    The window is ``length + 1`` bars (current included), so values start at bar ``length``.
    Ties resolve to the oldest bar (golden files).
    """
    length = check_length(length)
    h, lo = as_f64(high, "high"), as_f64(low, "low")
    same_length(h, lo)
    up = 100.0 * (extreme_offset_kernel(h, length + 1, True) + length) / length
    down = 100.0 * (extreme_offset_kernel(lo, length + 1, False) + length) / length
    return Aroon(up, down)


def ichimoku(
    high: np.ndarray,
    low: np.ndarray,
    conversion: int = 9,
    base: int = 26,
    span_b: int = 52,
) -> Ichimoku:
    """Ichimoku lines, **unshifted** (value computed on the current bar).

    ``tenkan = mid(conversion)``, ``kijun = mid(base)``, ``span_a_raw = (tenkan + kijun)/2``,
    ``span_b_raw = mid(span_b)`` where ``mid(n) = (lowest(low, n) + highest(high, n)) / 2``.
    The forward displacement of the cloud belongs to the strategy, not the indicator.
    """
    conversion = check_length(conversion, "conversion")
    base = check_length(base, "base")
    span_b = check_length(span_b, "span_b")
    h, lo = as_f64(high, "high"), as_f64(low, "low")
    same_length(h, lo)

    def mid(n: int) -> np.ndarray:
        return (lowest_kernel(lo, n) + highest_kernel(h, n)) / 2.0

    tenkan = mid(conversion)
    kijun = mid(base)
    return Ichimoku(tenkan, kijun, (tenkan + kijun) / 2.0, mid(span_b))
