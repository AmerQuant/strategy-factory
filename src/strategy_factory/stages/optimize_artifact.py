"""The stage-3 artifact: one ``summary.json`` per candidate (T14 §6, F-3.7).

Identity and parent (the stage-2 candidate, D-805's hash scheme), the fixed choice parameters,
the fine grid and its effective size (D-640, D-649), the **surfaces as data** (T15 draws them):
per cell the trades and the target on the whole window and both halves, zero cost and after
costs, and the smoothed surfaces; the selected centre, the plateau's extent per parameter, the
stability ratio, plateau area and cells, edge slope, SPP, half 2 at the selected point (D-641),
the zero-cost plateau and its shift (D-642), the overlaps after optimisation (D-643), the
``unconfirmed`` flag (D-645), the caveats (D-610) and the gate per criterion. A JSON number
cannot be infinite: an infinite value is stored as ``None``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from strategy_factory.stages.edge_profile import Caveat, GateLine, Number, SnapshotId

SCHEMA_VERSION = "1"
SEGMENTS = ("whole", "h1", "h2")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EntryIdentity(_Frozen):
    candidate_id: str
    parent_id: str  # the stage-2 candidate id
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
    unconfirmed: bool = False  # D-621, D-628, carried unchanged (D-645)


class Axis(_Frozen):
    name: str
    values: list[float | int]
    multiplier: int  # the fine-step multiplier (1 unless the grid was coarsened, D-649)


class GridInfo(_Frozen):
    #: the numeric axes **in lattice order** (a list: ``summary.json`` sorts object keys, so a
    #: dict would lose the order the surface is laid out in); ``surface`` is in C order over them
    axes: list[Axis]
    fixed: dict[str, Any]  # choice parameters at the stage-2 median cell's values (D-640)
    stage2_median_cell: dict[str, Any]
    size: int  # effective cells
    size_d639: int  # before coarsening (D-649)
    small_grid: bool  # fewer cells than the configured small-grid size (D-648)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(a.values) for a in self.axes)


class Segment(_Frozen):
    start: int
    end: int  # exclusive
    first_ts_us: int
    last_ts_us: int
    min_trades: int


class Leg(_Frozen):
    n_trades: list[int]  # whole, h1, h2
    target: list[Number]  # whole, h1, h2


class SurfaceCell(_Frozen):
    params: dict[str, Any]
    cost: Leg
    zero: Leg
    avg_annual_profit_pct_cost: Number  # the whole window
    smoothed_h1_cost: Number
    smoothed_h2_cost: Number
    smoothed_h1_zero: Number
    in_plateau: bool = False


class Selection(_Frozen):
    params: dict[str, Any] | None
    h1_raw: Number
    h1_smoothed: Number
    stability_ratio: Number
    plateau_area: float
    plateau_cells: int
    plateau_extent: dict[str, list[Number]]  # per axis [lowest, highest] value in the plateau
    edge_slope: Number
    failed_cells: dict[str, int]  # per segment
    inf_targets: dict[str, int]  # +inf targets replaced before smoothing, per half (D-650 (h))


class HalfTwo(_Frozen):
    """D-641: the selected parameters on half 2 -- the only out-of-sample test before stage 6."""

    valid: bool
    n_trades: int
    raw: Number
    smoothed: Number
    stability_ratio: Number
    accepted: bool


class WholeAtSelected(_Frozen):
    n_trades_cost: int
    target_cost: Number
    avg_annual_profit_pct_cost: Number
    n_trades_zero: int
    target_zero: Number


class SppReport(_Frozen):
    median: Number
    p_low: Number
    p_high: Number
    low_pct: float
    high_pct: float
    median_valid: Number
    cells: int
    failed: int


class ZeroCost(_Frozen):
    """D-642: the plateau chosen on the zero-cost half-1 surface, and how far costs moved it."""

    params: dict[str, Any] | None
    shift_steps: int | None


class OverlapLine(_Frozen):
    candidate_id: str
    method: str
    overlap: Number
    gate_passed: bool


class EntryOptimisation(_Frozen):
    schema_version: Literal["1"] = "1"
    identity: EntryIdentity
    grid: GridInfo
    segments: dict[str, Segment]
    surface: tuple[SurfaceCell, ...]
    cells_run: int  # D-160: every cell on every segment is a trial (3 per cell)
    selection: Selection
    half2: HalfTwo
    whole: WholeAtSelected | None
    spp: SppReport
    zero_cost: ZeroCost
    overlaps: tuple[OverlapLine, ...]  # D-643: reported, not gated
    gate_values: dict[str, Number]
    gate: tuple[GateLine, ...]
    gate_passed: bool
    caveats: Caveat
    warnings: tuple[str, ...] = ()


def json_schema() -> dict[str, Any]:
    return EntryOptimisation.model_json_schema()
