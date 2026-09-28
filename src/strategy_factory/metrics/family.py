"""Stage-2 family score, good region, rank-sum and overlap (F-2.4 ... F-2.6; D-624, D-629, D-636).

A method is scored by its **whole grid**, never by its best cell (spec §2.2): a method good in
one cell and poor around it is luck.

==================  ============================================================  ===========
component           raw value (zero-cost leg, D-623)                              share
==================  ============================================================  ===========
grid_median         median target metric over **all** cells; a cell below the     raw / target,
                    trade minimum is **-inf** (T13 §5: failed, not missing)        clipped 0..1
profitable_share    share of cells at the minimum with a positive target          raw
excess              the good-region median cell's mean ATR return minus its own    raw / target,
                    matched baseline's mean (D-624, D-613)                          clipped 0..1
consistency         median over the good-region cells of the share of calendar     (raw-0.5)/0.5,
                    years with a positive profit (years with too few trades         clipped 0..1
                    excluded, D-613's minimum)
==================  ============================================================  ===========

``points = 100 * weight / sum(weights) * share``: the score is on 0..100 and F-2.4's weights
40 / 25 / 20 / 15 give each component its points directly. An infinite target (a zero
drawdown) ranks top and counts as profitable (D-636); the caller flags it.

**Ranking is a weighted rank-sum** over the four raw components (F-2.5, D-636): per component
the methods of a profile are ranked (average ranks for ties, a missing value lowest), and the
rank-sum is ``sum(weight * rank)``. Ranks are invariant to any monotone rescaling of a component,
so the points constants never change the order.

Every constant comes from ``configs/stages/s02_screen.yaml`` (rule 1); provisional until T15.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

FAMILY_COMPONENTS = ("grid_median", "profitable_share", "excess", "consistency")


class FamilyScoreConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: dict[str, float]
    grid_median_target: float = Field(gt=0)
    excess_target_atr: float = Field(gt=0)
    consistency_min_trades_per_year: int = Field(ge=1)

    @field_validator("weights")
    @classmethod
    def _weights(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != set(FAMILY_COMPONENTS):
            raise ValueError(f"weights must name exactly {list(FAMILY_COMPONENTS)}")
        if any(w < 0 for w in value.values()) or sum(value.values()) <= 0:
            raise ValueError("weights must be non-negative with a positive sum")
        return value


@dataclass(frozen=True)
class FamilyRaw:
    grid_median: float
    profitable_share: float
    excess: float
    consistency: float

    def as_dict(self) -> dict[str, float]:
        return {c: float(getattr(self, c)) for c in FAMILY_COMPONENTS}


@dataclass(frozen=True)
class FamilyScore:
    raw: dict[str, float]
    share: dict[str, float]
    points: dict[str, float]
    total: float


def _is_failed(target: float, n_trades: int, min_trades: int) -> bool:
    return n_trades < min_trades or math.isnan(target)


def grid_values(targets: Sequence[float], n_trades: Sequence[int], min_trades: int) -> np.ndarray:
    """The targets with every failed cell (below the minimum, or no number) set to -inf."""
    return np.array(
        [
            -math.inf if _is_failed(t, n, min_trades) else float(t)
            for t, n in zip(targets, n_trades, strict=True)
        ],
        dtype=np.float64,
    )


def grid_median(targets: Sequence[float], n_trades: Sequence[int], min_trades: int) -> float:
    """Median target over all cells; failed cells count as -inf (they cannot be skipped)."""
    return float(np.median(grid_values(targets, n_trades, min_trades)))


def profitable_share(targets: Sequence[float], n_trades: Sequence[int], min_trades: int) -> float:
    """Share of **all** cells that reach the minimum and have a positive target."""
    v = grid_values(targets, n_trades, min_trades)
    return float(np.mean(v > 0.0)) if v.size else math.nan


def good_region(
    targets: Sequence[float],
    n_trades: Sequence[int],
    min_trades: int,
    share: float,
    tie_keys: Sequence[str],
) -> list[int]:
    """D-624, D-636 (g): the top ``ceil(share * cells)`` cells by target among the cells at the
    minimum (a failed cell never enters), in order; ties broken by ``tie_keys`` (the canonical
    JSON of the parameters). Empty when no cell reaches the minimum."""
    eligible = [
        i for i, (t, n) in enumerate(zip(targets, n_trades, strict=True))
        if not _is_failed(t, n, min_trades)
    ]  # fmt: skip
    size = max(1, math.ceil(share * len(targets)))
    ordered = sorted(eligible, key=lambda i: (-float(targets[i]), tie_keys[i]))
    return ordered[:size]


def median_cell(region: Sequence[int]) -> int | None:
    """The good region's median cell: the element at index ``len // 2`` (D-636 (g))."""
    return region[len(region) // 2] if region else None


def year_share(
    profit_by_year: dict[int, float], trades_by_year: dict[int, int], min_trades: int
) -> float:
    """Share of counted years with a positive profit; a year below ``min_trades`` is excluded.
    NaN when no year counts."""
    counted = [y for y, n in trades_by_year.items() if n >= min_trades]
    if not counted:
        return math.nan
    return sum(1 for y in counted if profit_by_year.get(y, 0.0) > 0.0) / len(counted)


def median_ignoring_nan(values: Sequence[float]) -> float:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[~np.isnan(arr)]
    return float(np.median(arr)) if arr.size else math.nan


def _clip01(x: float) -> float:
    if math.isnan(x):
        return 0.0
    return min(1.0, max(0.0, x))


def score_family(raw: FamilyRaw, cfg: FamilyScoreConfig) -> FamilyScore:
    values = raw.as_dict()
    share = {
        "grid_median": _clip01(values["grid_median"] / cfg.grid_median_target),
        "profitable_share": _clip01(values["profitable_share"]),
        "excess": _clip01(values["excess"] / cfg.excess_target_atr),
        "consistency": _clip01((values["consistency"] - 0.5) / 0.5),
    }
    total_w = sum(cfg.weights.values())
    points = {c: 100.0 * cfg.weights[c] / total_w * share[c] for c in FAMILY_COMPONENTS}
    return FamilyScore(raw=values, share=share, points=points, total=float(sum(points.values())))


def average_ranks(values: Sequence[float]) -> np.ndarray:
    """Ranks 1..n (higher value = higher rank), ties averaged, NaN ranked lowest (tied)."""
    arr = np.asarray(values, dtype=np.float64)
    n = arr.size
    key = np.where(np.isnan(arr), -np.inf, arr)
    order = np.argsort(key, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and key[order[j + 1]] == key[order[i]]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def rank_sum(raws: Sequence[FamilyRaw], weights: dict[str, float]) -> np.ndarray:
    """F-2.5, D-636 (h): ``sum(weight_k * rank_k)`` over the four components, per method."""
    if not raws:
        return np.zeros(0)
    total = np.zeros(len(raws))
    for c in FAMILY_COMPONENTS:
        total += weights[c] * average_ranks([getattr(r, c) for r in raws])
    return total


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    """F-2.6: the share of the **smaller** candidate's in-position bars that the other is also
    in position on (a method nested inside another overlaps 100 %). 0 when either is never in
    position."""
    na, nb = int(np.count_nonzero(a)), int(np.count_nonzero(b))
    if na == 0 or nb == 0:
        return 0.0
    return int(np.count_nonzero(a & b)) / min(na, nb)


def select_diverse(
    order: Sequence[int],
    positions: Sequence[np.ndarray],
    accept: Callable[[int, float], bool],
    max_selected: int,
) -> tuple[list[int], dict[int, float]]:
    """F-2.6: walk ``order`` (best first); for each method, its largest overlap with the already
    selected ones is computed and ``accept(index, overlap)`` decides (the gate, which holds the
    60 % threshold). ``accept`` is called for **every** method, so each has a verdict; one that
    passes after ``max_selected`` are taken is not selected. Returns the selected indices and
    every method's overlap."""
    selected: list[int] = []
    overlaps: dict[int, float] = {}
    for i in order:
        ov = max((overlap(positions[i], positions[j]) for j in selected), default=0.0)
        overlaps[i] = ov
        if accept(i, ov) and len(selected) < max_selected:
            selected.append(i)
    return selected, overlaps
