"""Volatility indicators and bands."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from strategy_factory.components.indicators._core import (
    as_f64,
    check_length,
    same_length,
    sma_kernel,
    smoothed_kernel,
    stdev_kernel,
    true_range_kernel,
)


class Bands(NamedTuple):
    mid: np.ndarray
    upper: np.ndarray
    lower: np.ndarray


def _hlc(high: np.ndarray, low: np.ndarray, close: np.ndarray):
    h, lo, c = as_f64(high, "high"), as_f64(low, "low"), as_f64(close, "close")
    same_length(h, lo, c)
    return h, lo, c


def true_range(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, handle_na: bool = True
) -> np.ndarray:
    """True range (``ta.tr(handle_na)``): ``max(high-low, |high-close[1]|, |low-close[1]|)``.

    Bar 0 has no previous close: it is ``high - low`` when ``handle_na`` is true (the form
    used inside ``ta.atr`` and ``ta.supertrend``) and NaN otherwise (the bare ``ta.tr``
    used inside ``ta.kc`` and ``ta.dmi``).
    """
    h, lo, c = _hlc(high, low, close)
    return true_range_kernel(h, lo, c, bool(handle_na))


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    """Average true range (``ta.atr``): ``rma(true_range(handle_na=True), length)``.

    Warm-up/seed: bar 0 uses ``high - low``, so the SMA seed covers bars ``0..length-1`` and
    the first value is at bar ``length - 1`` (golden: ATR_14 first at bar 13).
    """
    length = check_length(length)
    h, lo, c = _hlc(high, low, close)
    tr = true_range_kernel(h, lo, c, True)
    return smoothed_kernel(tr, length, 1.0 / length)


def stdev(src: np.ndarray, length: int) -> np.ndarray:
    """Population standard deviation (``ta.stdev(biased=true)``).

    Two-pass (mean, then squared deviations). As in TradingView's reference implementation a
    deviation with ``|d| <= 1e-10`` counts as exactly zero, so a constant window gives 0.
    """
    length = check_length(length)
    return stdev_kernel(as_f64(src, "src"), length)


def bollinger(src: np.ndarray, length: int = 20, mult: float = 2.0) -> Bands:
    """Bollinger bands (``ta.bb``): ``sma ± mult * population stdev``."""
    length = check_length(length)
    x = as_f64(src, "src")
    mid = sma_kernel(x, length)
    dev = float(mult) * stdev_kernel(x, length)
    return Bands(mid, mid + dev, mid - dev)


def keltner(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    length: int = 20,
    mult: float = 2.0,
    use_true_range: bool = True,
) -> Bands:
    """Keltner channels (``ta.kc(close, length, mult)``).

    ``mid = ema(close, length)``; the band width is ``mult * ema(range, length)`` where
    ``range`` is the bare true range (NaN on bar 0, TradingView ``ta.tr``) or ``high - low``.
    Consequence (golden): the bands start one bar after the middle line (bar ``length``).
    """
    length = check_length(length)
    h, lo, c = _hlc(high, low, close)
    alpha = 2.0 / (length + 1)
    mid = smoothed_kernel(c, length, alpha)
    rng = true_range_kernel(h, lo, c, False) if use_true_range else h - lo
    width = float(mult) * smoothed_kernel(rng, length, alpha)
    return Bands(mid, mid + width, mid - width)
