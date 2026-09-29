"""SPP -- System Parameter Permutation (spec §3.3, F-3.5; T14 §4; D-650 (i)).

The after-cost target metric of **every** fine-grid cell on the whole development window, seen
as one distribution: its median is the realistic expectation of the method (not the selected
cell's result), and its low and high percentiles show the range. A cell below the trade minimum
is ranked **below every valid cell** (stage 2's convention, D-636 (a)): it counts in the
distribution as ``-inf``, so a grid that mostly fails has a failing median. Percentiles are
nearest-rank. The median of the valid cells alone is reported beside it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SPP:
    median: float
    p_low: float
    p_high: float
    median_valid: float  # the valid cells only (reported, not gated)
    cells: int
    failed: int


def nearest_rank(sorted_values: np.ndarray, pct: float) -> float:
    """The value at rank ``round(pct/100 · (n - 1))`` of an ascending array."""
    n = int(sorted_values.size)
    if n == 0:
        return math.nan
    return float(sorted_values[min(n - 1, math.floor(pct / 100.0 * (n - 1) + 0.5))])


def spp(target: np.ndarray, valid: np.ndarray, low: float = 5.0, high: float = 95.0) -> SPP:
    """F-3.5 over ``target`` (any shape); ``valid`` marks the cells at the trade minimum."""
    t = np.asarray(target, dtype=np.float64).ravel()
    ok = np.asarray(valid, dtype=np.bool_).ravel()
    ranked = np.sort(np.where(ok, t, -np.inf))
    good = t[ok & ~np.isnan(t)]
    return SPP(
        median=nearest_rank(ranked, 50.0),
        p_low=nearest_rank(ranked, low),
        p_high=nearest_rank(ranked, high),
        median_valid=float(np.median(good)) if good.size else math.nan,
        cells=int(t.size),
        failed=int(np.count_nonzero(~ok)),
    )


__all__ = ["SPP", "nearest_rank", "spp"]
