"""The stage-2 artifact: one ``summary.json`` per (profile, method) (T13 §8, F-2.7).

It is stage 3's direct input (F-2.7): the identity (parent stage-1 candidate, method, hashes,
code version, control), the **full grid** with both legs per cell (D-623) -- the heatmap is
written as data, T15 draws it --, the family score with raw values and points, the rank, the
overlaps, the gate per criterion, and the parent profile's caveats (D-610) and ``unconfirmed``
flag (D-628). A JSON number cannot be infinite: an infinite target is stored as ``None`` with
``inf_target`` set (D-636).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from strategy_factory.stages.edge_profile import Caveat, GateLine, Number, SnapshotId

SCHEMA_VERSION = "1"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScreenIdentity(_Frozen):
    candidate_id: str
    parent_id: str  # the stage-1 profile's candidate id
    run_id: str | None
    parent_run_id: str
    symbol: str
    timeframe: str
    edge_type: str
    direction: Literal["long", "short"]
    asset_class: str
    method: str
    snapshot: SnapshotId
    config_hash: str
    stage_config_hash: str
    code_version: str
    control: Literal["none", "random_walk"] = "none"
    source: str = "real"  # D-670: "real", or the synthetic source id (null:/planted:<hash12>)
    unconfirmed: bool = False  # D-621, D-628


class Cell(_Frozen):
    params: dict[str, Any]
    n_trades_zero: int
    target_zero: Number
    n_trades_cost: int
    target_cost: Number
    avg_annual_profit_pct_cost: Number
    inf_target: bool = False  # a zero drawdown: the target is +inf on some leg (D-636)
    good_region: bool = False


class BaselineTest(_Frozen):
    """D-624 / D-629: the good-region median cell against its matched random entries."""

    cell: dict[str, Any] | None
    n_trades: int
    mean_atr: Number
    baseline_mean_atr: Number
    excess_atr: Number
    percentile: Number
    p_value: Number
    q_value: Number
    warmup_bars: int | None
    baseline_infeasible: int


class Family(_Frozen):
    raw: dict[str, Number]
    share: dict[str, float]
    points: dict[str, float]
    total: float
    rank_sum: float
    rank: int  # 1 = best within the profile


class MethodScreen(_Frozen):
    schema_version: Literal["1"] = "1"
    identity: ScreenIdentity
    grid: tuple[Cell, ...]
    cells_run: int  # D-160: every cell is a trial
    baseline: BaselineTest
    family: Family
    gate_values: dict[str, Number]
    gate: tuple[GateLine, ...]
    gate_passed: bool
    overlap_with_selected: Number
    overlaps: dict[str, Number]  # with every selected method of the profile
    selected: bool
    selection_note: str
    caveats: Caveat
    warnings: tuple[str, ...] = ()


def json_schema() -> dict[str, Any]:
    return MethodScreen.model_json_schema()
