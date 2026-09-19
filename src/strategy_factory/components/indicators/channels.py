"""Rolling extremes and price channels."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from strategy_factory.components.indicators._core import (
    as_f64,
    check_length,
    extreme_offset_kernel,
    highest_kernel,
    lowest_kernel,
    same_length,
)


class Channel(NamedTuple):
    upper: np.ndarray
    lower: np.ndarray
    mid: np.ndarray


def highest(src: np.ndarray, length: int) -> np.ndarray:
    """Highest value of the last ``length`` bars including the current one (``ta.highest``).

    NaN for the first ``length - 1`` bars.
    """
    length = check_length(length)
    return highest_kernel(as_f64(src, "src"), length)


def lowest(src: np.ndarray, length: int) -> np.ndarray:
    """Lowest value of the last ``length`` bars including the current one (``ta.lowest``).

    ``lowest(close, 7)`` is the "lowest close" plot (LOWEST_CLOSE_7).
    """
    length = check_length(length)
    return lowest_kernel(as_f64(src, "src"), length)


def highest_bars(src: np.ndarray, length: int) -> np.ndarray:
    """Offset (0 = current bar, negative = bars ago) of the highest value (``ta.highestbars``).

    Ties resolve to the oldest bar in the window (verified on the golden Aroon columns).
    """
    length = check_length(length)
    return extreme_offset_kernel(as_f64(src, "src"), length, True)


def lowest_bars(src: np.ndarray, length: int) -> np.ndarray:
    """Offset of the lowest value (``ta.lowestbars``); ties resolve to the oldest bar."""
    length = check_length(length)
    return extreme_offset_kernel(as_f64(src, "src"), length, False)


def donchian(high: np.ndarray, low: np.ndarray, length: int) -> Channel:
    """Donchian channel: ``highest(high)``, ``lowest(low)`` and their average.

    Includes the current bar. A breakout rule "close beyond the channel" must compare with the
    previous bar's channel (``upper[i-1]``) — that shift belongs to the strategy.
    """
    length = check_length(length)
    h, lo = as_f64(high, "high"), as_f64(low, "low")
    same_length(h, lo)
    up = highest_kernel(h, length)
    dn = lowest_kernel(lo, length)
    return Channel(up, dn, (up + dn) / 2.0)
