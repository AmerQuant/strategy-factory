"""Edge strength score, ESS (F-1.6; D-103, D-606, amended by D-613).

Four components, each first reduced to a **raw** value and then to a share in ``[0, 1]``:

==============  =========================================================  =================
component       raw value (medians over **every probe run**, D-613)          share
==============  =========================================================  =================
breadth         accepted groups / applicable groups                         raw
magnitude       median excess ATR return per trade (probe mean minus its    raw / target,
                own baseline mean, D-613)                                   clipped to 0..1
significance    median of ``-log10(p)``, p floored at ``1/(n+1)``            raw / full,
                                                                            capped at 1
consistency     median share of years with a positive excess (years with     (raw - 0.5)/0.5,
                too few probe trades excluded, D-613)                       clipped to 0..1
==============  =========================================================  =================

``points = 100 * weight / sum(weights) * share`` and ``total = sum(points)``, so the score is
always on 0..100 and a weight change in config takes effect (F-1.6). A missing raw value (no
probe with trades) contributes 0 points and stays ``NaN`` in :attr:`EssResult.raw`.

D-606 writes magnitude as ``30 * min(1, median / target)``; a negative excess would give
negative points there, which F-1.6's "score within 0 to 100" rules out, so the share is also
clipped at 0 -- the same floor D-606 writes for consistency.

Every constant comes from :class:`EssConfig` (``configs/stages/s01_edge.yaml``, rule 1).
They are provisional until T15 calibrates them (D-606).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPONENTS = ("breadth", "magnitude", "significance", "consistency")


class EssConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: dict[str, float]
    magnitude_target_atr: float = Field(gt=0)
    significance_full_log10p: float = Field(gt=0)
    consistency_min_trades_per_year: int = Field(ge=1)

    @field_validator("weights")
    @classmethod
    def _weights(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != set(COMPONENTS):
            raise ValueError(
                f"ESS weights must name exactly {list(COMPONENTS)}, got {sorted(value)}"
            )
        if any(w < 0 for w in value.values()) or sum(value.values()) <= 0:
            raise ValueError("ESS weights must be non-negative with a positive sum")
        return value


class EssRaw(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    breadth: float
    magnitude: float
    significance: float
    consistency: float


class EssResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw: dict[str, float]
    share: dict[str, float]
    points: dict[str, float]
    total: float


def _median(values: Sequence[float]) -> float:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[~np.isnan(arr)]
    return float(np.median(arr)) if arr.size else float("nan")


def raw_components(
    *,
    accepted_groups: int,
    applicable_groups: int,
    excess: Sequence[float],
    p_values: Sequence[float],
    positive_year_share: Sequence[float],
) -> EssRaw:
    """Raw ESS values from per-probe statistics; ``NaN`` entries (no trades) are skipped."""
    if applicable_groups <= 0:
        raise ValueError("applicable_groups must be positive")
    log_p = [-math.log10(p) if not math.isnan(p) else float("nan") for p in p_values]
    return EssRaw(
        breadth=accepted_groups / applicable_groups,
        magnitude=_median(excess),
        significance=_median(log_p),
        consistency=_median(positive_year_share),
    )


def _clip01(x: float) -> float:
    return 0.0 if math.isnan(x) else min(1.0, max(0.0, x))


def score_ess(raw: EssRaw, cfg: EssConfig) -> EssResult:
    values: dict[str, float] = raw.model_dump()
    share = {
        "breadth": _clip01(values["breadth"]),
        "magnitude": _clip01(values["magnitude"] / cfg.magnitude_target_atr),
        "significance": _clip01(values["significance"] / cfg.significance_full_log10p),
        "consistency": _clip01((values["consistency"] - 0.5) / 0.5),
    }
    total_w = sum(cfg.weights.values())
    points = {c: 100.0 * cfg.weights[c] / total_w * share[c] for c in COMPONENTS}
    return EssResult(raw=values, share=share, points=points, total=float(sum(points.values())))


def as_json(result: EssResult) -> dict[str, Any]:
    """JSON-safe dict (``NaN`` -> ``None``)."""

    def clean(d: dict[str, float]) -> dict[str, float | None]:
        return {k: (None if math.isnan(v) else v) for k, v in d.items()}

    return {
        "raw": clean(result.raw),
        "share": result.share,
        "points": result.points,
        "total": result.total,
    }
