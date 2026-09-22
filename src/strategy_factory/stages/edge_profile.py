"""The stage-1 artifact: one :class:`EdgeProfile` per (symbol, timeframe, edge type, direction).

F-1.9 / T12 §8 / D-604 / D-610 / D-617. Written as ``summary.json`` under
``artifacts/<run_id>/s01_edge/<candidate_id>/`` and validated by this model on write and on
read (``schema_version`` guards a later change). It is the direct input of stage 2.

Missing statistics (a probe without trades) are ``None`` in JSON: never ``NaN``, never 0.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1"

Number = float | None


def clean(value: float | None) -> float | None:
    """``NaN`` / ``inf`` -> ``None`` (JSON has neither); other floats unchanged."""
    if value is None:
        return None
    v = float(value)
    return v if math.isfinite(v) else None


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SnapshotId(_Frozen):
    source: str
    snapshot_hash: str


class Identity(_Frozen):
    candidate_id: str
    run_id: str | None
    symbol: str
    timeframe: str
    edge_type: str
    direction: Literal["long", "short"]
    asset_class: str
    snapshot: SnapshotId
    config_hash: str  # the pipeline run config (D-606: which constants produced the score)
    stage_config_hash: str  # configs/stages/s01_edge.yaml
    code_version: str
    control: Literal["none", "random_walk"] = "none"
    dev_start: str
    dev_end: str
    dev_bars: int


class Caveat(_Frozen):
    """D-610: what a reader must know about the series without consulting the catalog."""

    quality_status: str
    warning_checks: tuple[str, ...] = ()
    splices: tuple[dict[str, str], ...] = ()  # role, boundary, reason (T04l, D-709)
    research_window: bool = False  # starts at an unsettled boundary (D-713)
    derived: bool = False  # a derived snapshot (T04k clean, T04l trim)
    trimmed: bool = False  # T04l: history cut at a proven re-use boundary (D-709)
    notes: str = ""


class ProbeResult(_Frozen):
    name: str
    group: str
    trigger: str
    params: dict[str, Any]
    n_closed_trades: int
    mean_atr: Number  # D-601: the percentile statistic (zero costs)
    median_atr: Number
    baseline_mean_atr: Number  # the mean over every baseline trade
    excess_atr: Number  # D-613: mean_atr - baseline_mean_atr
    percentile: Number
    p_value: Number
    q_value: Number
    profit_factor: Number  # D-602: full Moneta costs, same signals
    pf_n_trades: int
    pf_skipped_min_volume: int
    positive_year_share: Number
    years_counted: int
    years_excluded: int
    disaster_share: Number  # D-130: > 2 % is a warning
    baseline_infeasible: int
    clamped_holdings: int
    accepted: bool
    failed_criteria: tuple[str, ...]

    @field_validator(
        "mean_atr",
        "median_atr",
        "baseline_mean_atr",
        "excess_atr",
        "percentile",
        "p_value",
        "q_value",
        "profit_factor",
        "positive_year_share",
        "disaster_share",
        mode="before",
    )
    @classmethod
    def _finite(cls, value: Any) -> Any:
        return clean(value) if isinstance(value, float) else value


class GateLine(_Frozen):
    metric: str
    op: str
    threshold: float
    value: Number
    passed: bool
    reason: str


class ProfileVerdict(_Frozen):
    ess: dict[str, Any]  # raw / share / points / total (metrics.ess.as_json)
    accepted_groups: tuple[str, ...]
    applicable_groups: tuple[str, ...]
    gate: tuple[GateLine, ...]
    passed: bool


class ComplementaryStats(_Frozen):
    """F-1.7 (P1): reserved and empty (D-617); nothing computes them yet."""

    variance_ratio: None = None
    hurst: None = None
    autocorrelation: None = None
    half_life: None = None


class EdgeProfile(_Frozen):
    schema_version: Literal["1"] = "1"  # SCHEMA_VERSION
    identity: Identity
    probes: tuple[ProbeResult, ...] = Field(min_length=1)
    profile: ProfileVerdict
    probes_run: int = Field(ge=1)  # D-605: the count for D-160
    caveats: Caveat
    complementary_stats: ComplementaryStats = Field(default_factory=ComplementaryStats)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _probes_run_matches(self) -> EdgeProfile:
        if self.probes_run != len(self.probes):
            raise ValueError(f"probes_run {self.probes_run} != {len(self.probes)} probe results")
        return self


def json_schema() -> dict[str, Any]:
    """The JSON schema of ``summary.json``."""
    return EdgeProfile.model_json_schema()
