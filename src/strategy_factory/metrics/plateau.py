"""Stage-3 surface metrics (T14 §4; F-3.3, F-3.4; D-120, D-641, D-646, D-648, D-650).

Pure NumPy on a **lattice**: a surface is an ``ndarray`` whose axes are the numeric parameters of
the fine grid (at most 3, D-120), one value per cell. Neighbours are the cells at ±1 step in
every dimension (up to 26 in 3-D, T14 §4); at the grid's edge only the neighbours that exist.

* :func:`fill_failed` -- a cell below the trade minimum is a *failed* cell; it enters every mean
  as ``min(worst valid value, 0)`` (D-646), never skipped, so a lone survivor among failed
  neighbours cannot look stable. A ``+inf`` target (no drawdown) is replaced by the surface's
  largest finite value and counted (D-650 (h)).
* :func:`smooth` -- the mean over the cell and its existing neighbours (F-3.3).
* :func:`select` -- the maximum of the smoothed surface among the valid cells; ties by the
  cell's key (the canonical JSON of its parameters, D-636 (g)).
* :func:`stability_ratio` -- the mean of the cell's raw neighbours over its raw value; ``nan``
  (a failure) when the raw value is not positive (D-650 (e)).
* :func:`plateau` -- the connected set of cells, containing the selected one, whose smoothed
  value is at least ``ratio`` x the selected cell's smoothed value (F-3.4, D-650 (f)).
* :func:`edge_slope` -- the relative drop across the plateau's boundary (reported, D-650 (j)).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Literal

import numpy as np

FailedCell = Literal["worst0", "zero", "worst", "neginf"]
Index = tuple[int, ...]


def offsets(ndim: int) -> list[Index]:
    """Every neighbour offset at ±1 step in each dimension (3**ndim - 1 of them)."""
    return [o for o in itertools.product((-1, 0, 1), repeat=ndim) if any(o)]


def neighbours(idx: Index, shape: Sequence[int]) -> list[Index]:
    """The existing neighbours of ``idx`` on a lattice of ``shape``."""
    out: list[Index] = []
    for o in offsets(len(shape)):
        j = tuple(a + b for a, b in zip(idx, o, strict=True))
        if all(0 <= x < s for x, s in zip(j, shape, strict=True)):
            out.append(j)
    return out


def fill_failed(
    target: np.ndarray, valid: np.ndarray, how: FailedCell = "worst0"
) -> tuple[np.ndarray, int]:
    """``(surface, n_inf)``: ``target`` with failed cells replaced (D-646) and ``+inf`` targets
    of valid cells replaced by the largest finite valid value (D-650 (h)); ``n_inf`` counts them.

    ``how``: ``worst0`` = min(worst valid, 0) (D-646); ``zero``; ``worst`` (the grid's worst
    valid value -- measured to pass a lone survivor, kept for the guard test); ``neginf``.
    """
    x = np.array(target, dtype=np.float64, copy=True)
    valid = np.asarray(valid, dtype=np.bool_)
    if x.shape != valid.shape:
        raise ValueError("target and valid must have the same shape")
    pos_inf = valid & np.isposinf(x)
    finite = valid & np.isfinite(x)
    n_inf = int(np.count_nonzero(pos_inf))
    if n_inf:
        x[pos_inf] = float(np.max(x[finite])) if finite.any() else 0.0
    worst = float(np.min(x[valid])) if valid.any() else 0.0
    fill = {"worst0": min(worst, 0.0), "zero": 0.0, "worst": worst, "neginf": -math.inf}[how]
    x[~valid] = fill
    return x, n_inf


def smooth(x: np.ndarray) -> np.ndarray:
    """F-3.3: the mean over each cell and its existing neighbours (the edge uses fewer)."""
    x = np.asarray(x, dtype=np.float64)
    pad = np.pad(x, 1, mode="constant", constant_values=np.nan)
    total = np.zeros(x.shape)
    count = np.zeros(x.shape)
    for o in itertools.product((-1, 0, 1), repeat=x.ndim):
        sl = tuple(slice(1 + d, 1 + d + n) for d, n in zip(o, x.shape, strict=True))
        v = pad[sl]
        ok = ~np.isnan(v)
        total = total + np.where(ok, v, 0.0)
        count = count + ok
    with np.errstate(invalid="ignore"):
        return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def select(s: np.ndarray, valid: np.ndarray, keys: np.ndarray) -> Index | None:
    """F-3.3: the valid cell with the largest smoothed value; ties by ``keys`` (D-636 (g))."""
    best: tuple[float, str, Index] | None = None
    for idx in itertools.product(*(range(k) for k in s.shape)):
        v = float(s[idx])
        if not valid[idx] or math.isnan(v):
            continue
        cand = (-v, str(keys[idx]), idx)
        if best is None or cand[:2] < best[:2]:
            best = cand
    return None if best is None else best[2]


def neighbour_mean(x: np.ndarray, idx: Index) -> float:
    vals = [float(x[j]) for j in neighbours(idx, x.shape)]
    return float(np.mean(vals)) if vals else math.nan


def stability_ratio(x: np.ndarray, idx: Index) -> float:
    """F-3.4: mean of the raw neighbours ÷ the raw value; ``nan`` if the value is not positive
    or infinite, or the cell has no neighbour (a one-cell grid) -- all fail the gate."""
    own = float(x[idx])
    if not own > 0 or math.isinf(own):
        return math.nan
    nb = neighbour_mean(x, idx)
    return nb / own if not math.isnan(nb) else math.nan


def plateau(s: np.ndarray, idx: Index, ratio: float) -> np.ndarray:
    """F-3.4: the connected set (same neighbourhood as the smoothing, diagonals included) of
    cells whose smoothed value is ≥ ``ratio`` x the selected cell's, containing it. Empty when
    the selected smoothed value is not positive (D-650 (f))."""
    mask = np.zeros(s.shape, dtype=np.bool_)
    top = float(s[idx])
    if not top > 0:
        return mask
    ok = np.asarray(s >= ratio * top) & ~np.isnan(s)
    mask[idx] = True
    stack = [idx]
    while stack:
        c = stack.pop()
        for j in neighbours(c, s.shape):
            if ok[j] and not mask[j]:
                mask[j] = True
                stack.append(j)
    return mask


def accepted(x: np.ndarray, s: np.ndarray, valid: np.ndarray, idx: Index, ratio: float) -> bool:
    """D-641, D-650 (g): ``idx`` lies in a half's acceptance region -- the cell is at the trade
    minimum, its smoothed after-cost value is positive and its stability ratio meets ``ratio``.
    ``x`` is the half's raw surface after :func:`fill_failed`, ``s`` its smoothing."""
    return bool(valid[idx]) and float(s[idx]) > 0 and stability_ratio(x, idx) >= ratio


def edge_slope(s: np.ndarray, mask: np.ndarray, idx: Index) -> float:
    """D-650 (j): the mean over the plateau's boundary cells of (the cell's smoothed value - the
    mean smoothed value of its neighbours outside the plateau), ÷ the selected smoothed value;
    0 when the plateau has no outside neighbour (it fills the grid); ``nan`` without a plateau."""
    top = float(s[idx])
    if not mask.any() or not top > 0:
        return math.nan
    drops: list[float] = []
    for c in zip(*np.nonzero(mask), strict=True):
        cell = tuple(int(v) for v in c)
        out = [float(s[j]) for j in neighbours(cell, s.shape) if not mask[j]]
        if out:
            drops.append(float(s[cell]) - float(np.mean(out)))
    return float(np.mean(drops)) / top if drops else 0.0


def extent(mask: np.ndarray, axes: Sequence[Sequence[float | int]]) -> list[tuple[float, float]]:
    """Per axis, the smallest and largest parameter value inside the plateau."""
    out: list[tuple[float, float]] = []
    where = np.nonzero(mask)
    for d, values in enumerate(axes):
        if not mask.any():
            out.append((math.nan, math.nan))
            continue
        out.append((float(values[int(where[d].min())]), float(values[int(where[d].max())])))
    return out


def step_distance(a: Index, b: Index) -> int:
    """The largest per-axis distance in steps between two cells (D-650 (k))."""
    return max((abs(x - y) for x, y in zip(a, b, strict=True)), default=0)


__all__ = [
    "FailedCell",
    "Index",
    "accepted",
    "edge_slope",
    "extent",
    "fill_failed",
    "neighbour_mean",
    "neighbours",
    "offsets",
    "plateau",
    "select",
    "smooth",
    "stability_ratio",
    "step_distance",
]
