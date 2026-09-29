"""Stage 3 -- entry optimisation (``s03_entry``; T14, F-3.1 ... F-3.7; D-639 ... D-651).

For every method stage 2 selected (T14 §3): **the parameters it is traded with**, chosen on a
fine grid at the centre of a stable plateau, never at the peak (D-120, F-3.3). Exits stay fixed
(D-622).

Per candidate -- one executor work unit, pure computation (:func:`compute_entry`):

1. the **fine grid** (:mod:`stages.optimize_grid`): stage 2's good region plus a coarse step of
   margin, choice parameters fixed, coarsened above the cap (D-639, D-640, D-649);
2. every cell on the **whole** development window and on its two **halves** of equal bar count
   (D-641), zero cost and after costs; a half is simulated on its own bars with signals and ATR
   computed on the bars up to its end (D-650 (c));
3. the half-1 after-cost surface (D-642) with failed cells as min(worst, 0) (D-646; the minimum
   applies in full in each half, D-647), smoothed; the selected cell, stability ratio, connected
   plateau, edge slope (:mod:`metrics.plateau`); the same on the zero-cost surface for the shift;
4. half 2's acceptance at the selected cell (D-641); SPP on the whole window (F-3.5).

The parent (:class:`EntryStage`) then evaluates the gate, measures the overlaps between a
profile's candidates at their selected cells (D-643, reported, not gated), and alone writes the
registry (D-334): a candidate per stage-2 selection with ``parent_id`` = the stage-2 candidate,
**one trial per cell per segment** (D-160), the gate rows; and the artifacts: ``summary.json``
per candidate (surfaces as data), trades for passing candidates' selected cells, the index.

Every constant comes from ``configs/stages/s03_entry.yaml`` or the gate YAML (rule 1): the trade
minimum is stage 2's (``s02_screen``'s ``min_trades_good_cells``) and the plateau cut is the
``s03_entry`` gate's ``stability_ratio`` threshold. The stage reads the development segment only
and holds no split manager (D-616).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from strategy_factory.core.config import EngineConfig, canonical_json, config_hash
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.costs.arrays import CostArrays
from strategy_factory.costs.profile import load_assignments, load_profiles
from strategy_factory.data.result_io import write_run_result
from strategy_factory.gates.engine import GateEngine, GateResult, to_registry_rows
from strategy_factory.metrics.containers import RunMeta, RunResult
from strategy_factory.metrics.family import overlap
from strategy_factory.metrics.plateau import (
    accepted,
    edge_slope,
    extent,
    fill_failed,
    plateau,
    select,
    smooth,
    stability_ratio,
    step_distance,
)
from strategy_factory.metrics.standard import core_metrics
from strategy_factory.pipeline.backtest import to_run_result
from strategy_factory.pipeline.executor import unit_seed
from strategy_factory.robustness.spp import spp
from strategy_factory.stages.base import ArtifactRef, RunContext, StageResult
from strategy_factory.stages.common import UnsupportedSymbol, cost_arrays, require_research_engine
from strategy_factory.stages.config import EdgeTypeSpec
from strategy_factory.stages.control import permute_returns
from strategy_factory.stages.edge_profile import GateLine, SnapshotId, clean
from strategy_factory.stages.optimize_artifact import (
    SCHEMA_VERSION,
    SEGMENTS,
    Axis,
    EntryIdentity,
    EntryOptimisation,
    GridInfo,
    HalfTwo,
    Leg,
    OverlapLine,
    Segment,
    Selection,
    SppReport,
    SurfaceCell,
    WholeAtSelected,
    ZeroCost,
    json_schema,
)
from strategy_factory.stages.optimize_config import (
    STAGE,
    S03EntryConfig,
    load_s03_config,
    stage_config_hash,
)
from strategy_factory.stages.optimize_grid import FineGrid, fine_grid
from strategy_factory.stages.screen import cell_signals, segment_run
from strategy_factory.stages.screen_artifact import MethodScreen
from strategy_factory.stages.screen_config import STAGE as S02_STAGE

Direction = Literal["long", "short"]
_SIGN = {"long": 1, "short": -1}
MIN_TRADES_METRIC = "min_trades_good_cells"  # stage 2's trade minimum (T14 §4)
STABILITY_METRIC = "stability_ratio"  # the plateau cut and the half-2 test (D-650 (f), (g))


# --------------------------------------------------------------------------------------
# Work unit (one candidate): picklable, computed in a worker
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EntryTask:
    candidate_id: str
    parent_id: str  # the stage-2 candidate
    method: str
    symbol: str
    timeframe: str
    direction: Direction
    grid: FineGrid
    bars: dict[str, np.ndarray]  # development segment: ts (µs), open, high, low, close
    costs: CostArrays
    engine: EngineConfig
    exits: EdgeTypeSpec
    min_trades: int  # the whole window
    min_trades_half: int  # each half (D-647)
    ratio: float  # the stability threshold: plateau cut and half-2 test
    failed_cell: str
    spp_low: float
    spp_high: float


@dataclass(frozen=True)
class Surfaces:
    """Per (segment, leg): trades, target and average annual profit %, shaped like the grid."""

    n: dict[tuple[str, str], np.ndarray]
    target: dict[tuple[str, str], np.ndarray]
    profit: dict[tuple[str, str], np.ndarray]


@dataclass(frozen=True)
class EntryOutput:
    task: EntryTask
    segments: dict[str, tuple[int, int]]
    keys: np.ndarray  # canonical JSON of each cell's parameters, grid-shaped
    surfaces: Surfaces
    smoothed: dict[str, np.ndarray]  # h1_cost, h2_cost, h1_zero
    selected: tuple[int, ...] | None
    stability: float
    plateau_mask: np.ndarray
    slope: float
    inf_targets: dict[str, int]
    half2: HalfTwo
    zero_selected: tuple[int, ...] | None
    spp: Any
    position: np.ndarray  # in-position bars of the selected cell's whole after-cost run (D-643)
    trades: RunResult | None
    warnings: tuple[str, ...]


def candidate_id(
    *,
    parent_id: str,
    control: str,
    stage_config_hash: str,
    min_trades: int,
    min_trades_half: int,
    plateau_cut: float,
) -> str:
    """sha256 of what identifies a stage-3 candidate (D-651 (c), D-807): the stage, the parent
    stage-2 candidate (which names the method and its profile), the control, the stage-config hash
    (D-805's pattern) and **the gate values that shape the surfaces** -- the trade minimum of the
    whole window and of each half, and the plateau cut. They come from the gate YAML, not the
    stage config, and a different value is a different result, so it must not reuse an id (D-807;
    T15 recalibrates exactly these)."""
    payload = {
        "stage": STAGE,
        "parent_id": parent_id,
        "control": control,
        "stage_config_hash": stage_config_hash,
        "min_trades": int(min_trades),
        "min_trades_half": int(min_trades_half),
        "plateau_cut": float(plateau_cut),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def halves(n: int) -> dict[str, tuple[int, int]]:
    """D-641: the whole window and its two halves of equal bar count (half 2 takes an odd bar)."""
    mid = n // 2
    return {"whole": (0, n), "h1": (0, mid), "h2": (mid, n)}


def _meta(task: EntryTask) -> RunMeta:
    return RunMeta(
        symbol=task.symbol,
        timeframe=task.timeframe,
        spec_hash=hashlib.sha256(canonical_json({"method": task.method}).encode()).hexdigest(),
        cost_status="placeholder" if task.costs.placeholder else "verified",
        intrabar_mode="pessimistic",
    )


def segment_runs(
    task: EntryTask, params: dict[str, Any], segments: dict[str, tuple[int, int]]
) -> dict[tuple[str, str], RunResult]:
    """One cell on every segment and both legs. The signals are computed once per segment end on
    the bars up to that end (rule 3): half 1 never reads half 2. The stage and the leakage test
    both call this."""
    sig_by_end = {
        e: cell_signals(
            task.bars, task.method, params, task.exits, task.direction, task.engine.atr_length, e
        )
        for e in sorted({e for _, e in segments.values()})
    }
    meta = _meta(task)
    out: dict[tuple[str, str], RunResult] = {}
    for seg, (s, e) in segments.items():
        for leg in ("zero", "cost"):
            sim = segment_run(
                sig_by_end[e],
                task.exits,
                task.direction,
                task.engine,
                task.costs if leg == "cost" else None,
                start=s,
            )
            out[(seg, leg)] = to_run_result(
                sim, task.bars["ts"][s:e], _SIGN[task.direction], meta, task.engine
            )
    return out


def compute_entry(task: EntryTask) -> EntryOutput:
    """One candidate, start to verdict inputs (module level: pickled for ``spawn``)."""
    grid = task.grid
    shape = grid.shape
    n_bars = int(np.asarray(task.bars["close"]).shape[0])
    segs = halves(n_bars)
    keys = np.empty(shape, dtype=object)
    n: dict[tuple[str, str], np.ndarray] = {}
    tg: dict[tuple[str, str], np.ndarray] = {}
    pr: dict[tuple[str, str], np.ndarray] = {}
    for seg in segs:
        for leg in ("zero", "cost"):
            n[(seg, leg)] = np.zeros(shape, dtype=np.int64)
            tg[(seg, leg)] = np.full(shape, np.nan)
            pr[(seg, leg)] = np.full(shape, np.nan)
    for flat, params in enumerate(grid.cells()):
        idx = np.unravel_index(flat, shape)
        keys[idx] = canonical_json(params)
        for k2, rr in segment_runs(task, params, segs).items():
            cm = core_metrics(rr.equity)
            n[k2][idx] = len(rr.trades)
            tg[k2][idx] = float(cm.profit_dd_ratio)
            pr[k2][idx] = float(cm.avg_annual_profit_pct)
    how: Any = task.failed_cell
    v1 = n[("h1", "cost")] >= task.min_trades_half
    v2 = n[("h2", "cost")] >= task.min_trades_half
    vz = n[("h1", "zero")] >= task.min_trades_half
    vw = n[("whole", "cost")] >= task.min_trades
    x1, inf1 = fill_failed(tg[("h1", "cost")], v1, how)
    x2, inf2 = fill_failed(tg[("h2", "cost")], v2, how)
    xz, _ = fill_failed(tg[("h1", "zero")], vz, how)
    s1, s2, sz = smooth(x1), smooth(x2), smooth(xz)
    sel = select(s1, v1, keys)  # D-642: the after-cost surface
    zsel = select(sz, vz, keys)
    warnings: list[str] = []
    mask = np.zeros(shape, dtype=np.bool_)
    stab = slope = math.nan
    position = np.zeros(n_bars, dtype=np.bool_)
    trades: RunResult | None = None
    if sel is None:
        warnings.append("no cell reaches the trade minimum on half 1")
        half2 = HalfTwo(
            valid=False, n_trades=0, raw=None, smoothed=None, stability_ratio=None, accepted=False
        )
    else:
        stab = stability_ratio(x1, sel)
        mask = plateau(s1, sel, task.ratio)
        slope = edge_slope(s1, mask, sel)
        half2 = HalfTwo(
            valid=bool(v2[sel]),
            n_trades=int(n[("h2", "cost")][sel]),
            raw=clean(float(tg[("h2", "cost")][sel])),
            smoothed=clean(float(s2[sel])),
            stability_ratio=clean(stability_ratio(x2, sel)),
            accepted=accepted(x2, s2, v2, sel, task.ratio),  # D-641
        )
        whole = segment_runs(task, grid.cells()[int(np.ravel_multi_index(sel, shape))],
                             {"whole": segs["whole"]})  # fmt: skip
        trades = whole[("whole", "cost")]
        position = np.asarray(trades.equity.in_position, dtype=np.bool_)
    if inf1 or inf2:
        warnings.append(f"+inf targets replaced before smoothing: half 1 {inf1}, half 2 {inf2}")
    return EntryOutput(
        task=task,
        segments=segs,
        keys=keys,
        surfaces=Surfaces(n=n, target=tg, profit=pr),
        smoothed={"h1_cost": s1, "h2_cost": s2, "h1_zero": sz},
        selected=sel,
        stability=stab,
        plateau_mask=mask,
        slope=slope,
        inf_targets={"h1": inf1, "h2": inf2},
        half2=half2,
        zero_selected=zsel,
        spp=spp(tg[("whole", "cost")], vw, task.spp_low, task.spp_high),
        position=position,
        trades=trades,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------------------
# Inputs: the stage-2 selections
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage2Input:
    screen: MethodScreen
    parent_run_id: str


def read_stage2_selections(
    artifacts_root: Path, run_id: str, timeframes: Sequence[str]
) -> list[Stage2Input]:
    """The methods a stage-2 run selected (index + ``summary.json``), for ``timeframes``. A
    stage-2 control run is refused: the control reruns the real selections (D-651 (b))."""
    run_dir = artifacts_root / run_id / S02_STAGE
    index = run_dir / "index.csv"
    if not index.is_file():
        raise ConfigError(f"stage-2 index not found: {index}")
    out: list[Stage2Input] = []
    with index.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("selected") != "True" or row["timeframe"] not in timeframes:
                continue
            path = run_dir / row["candidate_id"] / "summary.json"
            art = MethodScreen.model_validate_json(path.read_text(encoding="utf-8"))
            if art.identity.control != "none":
                raise ConfigError(
                    f"stage-2 run {run_id} is a control run: stage 3 reads real selections "
                    "(D-651 (b))"
                )
            out.append(Stage2Input(screen=art, parent_run_id=run_id))
    return sorted(
        out,
        key=lambda p: (
            p.screen.identity.timeframe,
            p.screen.identity.symbol,
            p.screen.identity.direction,
            p.screen.identity.method,
        ),
    )


def stage2_selection_symbols(
    artifacts_root: Path, run_id: str, timeframes: Sequence[str]
) -> tuple[str, ...]:
    """The symbols ``symbol_scope: stage_inputs`` expands to (T14 §3)."""
    return tuple(
        sorted(
            {
                s.screen.identity.symbol
                for s in read_stage2_selections(artifacts_root, run_id, timeframes)
            }
        )
    )


def _threshold(gates: GateEngine, stage: str, metric: str, context: dict[str, str]) -> float:
    for crit in gates.criteria(stage, context):
        if crit.metric == metric:
            return float(crit.threshold)
    raise ConfigError(f"the {stage} gate has no {metric} criterion")


def _write_json(path: Path, data: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


INDEX_COLUMNS = (
    "symbol",
    "timeframe",
    "edge_type",
    "direction",
    "method",
    "parent_id",
    "candidate_id",
    "unconfirmed",
    "grid_cells",
    "small_grid",
    "selected_params",
    "stability_ratio",
    "plateau_area",
    "plateau_cells",
    "half2_raw",
    "selected_in_both_halves",
    "spp_median_target",
    "zero_cost_shift_steps",
    "max_overlap",
    "gate_passed",
    "failed_criteria",
    "quality_status",
    "reason",
)


@dataclass
class _Work:
    source: Stage2Input
    asset_class: str
    task: EntryTask


@dataclass
class EntryStage:
    """``s03_entry``: inputs are the ``(symbol, timeframe)`` pairs of the resolved config; the
    candidates come from the stage-2 run named in ``stage_inputs``."""

    name: str = STAGE
    stage_config_path: Path | None = None
    s01_config_path: Path | None = None
    costs_dir: Path = Path("configs") / "costs"
    batch_units: int | None = None
    _index: list[dict[str, Any]] = field(default_factory=list)

    def run(self, inputs: Sequence[tuple[str, str]], ctx: RunContext) -> StageResult:
        cfg = load_s03_config(self.stage_config_path, self.s01_config_path)
        require_research_engine(ctx, STAGE)
        from strategy_factory.core.universe import load_universe

        parent_run = ctx.config.stage_inputs.get(S02_STAGE)
        if not parent_run:
            raise ConfigError(f"stage 3 needs stage_inputs.{S02_STAGE} (the stage-2 run to read)")
        wanted = set(inputs)
        sources = [
            s
            for s in read_stage2_selections(ctx.artifacts_root, parent_run, ctx.config.timeframes)
            if (s.screen.identity.symbol, s.screen.identity.timeframe) in wanted
        ]
        universe = load_universe(ctx.config.universe).by_symbol()
        run_dir = ctx.artifacts_root / (str(ctx.run_id) if ctx.run_id else "dry-run") / STAGE
        result = StageResult()
        self._index = []
        s_hash = stage_config_hash(cfg)
        c_hash = config_hash(ctx.config)
        cost_profiles, assignments = load_profiles(self.costs_dir), load_assignments(self.costs_dir)
        _write_json(run_dir / "entry_optimisation.schema.json", json_schema())
        cache: dict[tuple[str, str], tuple[dict[str, np.ndarray], CostArrays] | str] = {}
        by_profile: dict[str, list[_Work]] = {}
        for src in sources:
            ident = src.screen.identity
            key = (ident.symbol, ident.timeframe)
            pinned = ctx.config.data_snapshots[ident.symbol][ident.timeframe]
            if pinned.snapshot_hash != ident.snapshot.snapshot_hash:
                raise DataError(
                    f"{ident.symbol} {ident.timeframe}: the reference moved since stage 2 "
                    f"({ident.snapshot.snapshot_hash[:12]} -> {pinned.snapshot_hash[:12]})",
                    stage=STAGE,
                    symbol=ident.symbol,
                )
            if key not in cache:
                bars = ctx.data.arrays(*key)
                bars = {c: bars[c] for c in ("ts", "open", "high", "low", "close")}
                if ctx.config.control == "random_walk":  # D-644, T12's key (D-651 (b))
                    bars = permute_returns(
                        bars, unit_seed(ctx.seed, f"{key[0]}|{key[1]}|random_walk")
                    )
                try:
                    costs = cost_arrays(
                        key[0], universe[key[0]].asset_class, key[1], bars, self.costs_dir,
                        cost_profiles, assignments,
                    )  # fmt: skip
                    cache[key] = (bars, costs)
                except UnsupportedSymbol as exc:
                    cache[key] = str(exc)
            cached = cache[key]
            if isinstance(cached, str):
                self._index.append(self._skip_row(src, cached))
                continue
            bars, costs = cached
            asset_class = universe[ident.symbol].asset_class
            context = {"asset_class": asset_class, "timeframe": ident.timeframe}
            min_trades = math.ceil(_threshold(ctx.gates, S02_STAGE, MIN_TRADES_METRIC, context))
            min_half = min_trades if cfg.half_min_trades == "full" else math.ceil(min_trades / 2)
            median = src.screen.baseline.cell
            if median is None:
                self._index.append(self._skip_row(src, "stage 2 has no good-region median cell"))
                continue
            grid = fine_grid(
                ident.method,
                [c.params for c in src.screen.grid if c.good_region],
                median,
                margin=cfg.fine_grid.margin_coarse_steps,
                max_cells=cfg.fine_grid.max_cells,
                max_free_params=cfg.fine_grid.max_free_params,
            )
            cut = _threshold(ctx.gates, STAGE, STABILITY_METRIC, context)
            task = EntryTask(
                candidate_id=candidate_id(
                    parent_id=ident.candidate_id,
                    control=ctx.config.control,
                    stage_config_hash=s_hash,
                    min_trades=min_trades,
                    min_trades_half=min_half,
                    plateau_cut=cut,
                ),
                parent_id=ident.candidate_id,
                method=ident.method,
                symbol=ident.symbol,
                timeframe=ident.timeframe,
                direction=ident.direction,
                grid=grid,
                bars=bars,
                costs=costs,
                engine=ctx.config.engine,
                exits=cfg.exits[ident.edge_type],
                min_trades=min_trades,
                min_trades_half=min_half,
                ratio=cut,
                failed_cell=cfg.failed_cell,
                spp_low=cfg.spp_percentiles.low,
                spp_high=cfg.spp_percentiles.high,
            )
            by_profile.setdefault(ident.parent_id, []).append(
                _Work(source=src, asset_class=asset_class, task=task)
            )
        limit = self.batch_units or cfg.batch_units
        pending: list[list[_Work]] = []
        size = 0
        for work in by_profile.values():  # a profile is never split across batches (D-643)
            pending.append(work)
            size += len(work)
            if size >= limit:
                self._flush(pending, cfg, ctx, run_dir, result, s_hash, c_hash)
                pending, size = [], 0
        if pending:
            self._flush(pending, cfg, ctx, run_dir, result, s_hash, c_hash)
        if ctx.registry is not None:
            ctx.registry.flush()
        _write_index(run_dir / "index.csv", self._index)
        result.summary = summarize(self._index)
        return result

    def _flush(
        self,
        profiles: list[list[_Work]],
        cfg: S03EntryConfig,
        ctx: RunContext,
        run_dir: Path,
        result: StageResult,
        s_hash: str,
        c_hash: str,
    ) -> None:
        tasks = [w.task for work in profiles for w in work]
        outputs = list(ctx.executor.map(compute_entry, tasks))
        pos = 0
        for work in profiles:
            mine = outputs[pos : pos + len(work)]
            pos += len(work)
            self._decide(work, mine, cfg, ctx, run_dir, result, s_hash, c_hash)

    def _decide(
        self,
        work: list[_Work],
        outs: list[EntryOutput],
        cfg: S03EntryConfig,
        ctx: RunContext,
        run_dir: Path,
        result: StageResult,
        s_hash: str,
        c_hash: str,
    ) -> None:
        gates: list[GateResult] = []
        values: list[dict[str, float]] = []
        for w, o in zip(work, outs, strict=True):
            context = {"asset_class": w.asset_class, "timeframe": w.task.timeframe}
            v = gate_values(o)
            values.append(v)
            gates.append(ctx.gates.evaluate(STAGE, o.task.candidate_id, v, context))
        for i, (w, o) in enumerate(zip(work, outs, strict=True)):
            lines = tuple(
                OverlapLine(
                    candidate_id=outs[j].task.candidate_id,
                    method=outs[j].task.method,
                    # D-643; no overlap is defined against a candidate without a selection
                    overlap=(
                        clean(overlap(o.position, outs[j].position))
                        if o.selected is not None and outs[j].selected is not None
                        else None
                    ),
                    gate_passed=gates[j].passed,
                )
                for j in range(len(outs))
                if j != i
            )
            art = self._artifact(w, o, values[i], gates[i], lines, cfg, ctx, s_hash, c_hash)
            cdir = run_dir / o.task.candidate_id
            sha = _write_json(cdir / "summary.json", art.model_dump(mode="json"))
            refs = [
                ArtifactRef(
                    "entry_optimisation",
                    cdir / "summary.json",
                    o.task.candidate_id,
                    sha,
                    SCHEMA_VERSION,
                )
            ]
            if gates[i].passed and o.trades is not None:
                tdir = write_run_result(o.trades, cdir / "trades")
                refs.append(ArtifactRef("trades", tdir, o.task.candidate_id, "", "1"))
                result.passed.append(o.task.candidate_id)
            result.artifacts.extend(refs)
            result.gate_results.append(gates[i])
            self._index.append(self._index_row(art, w))
            if ctx.registry is not None and ctx.run_id is not None:
                self._write_registry(o, art, gates[i], refs, ctx)

    @staticmethod
    def _artifact(
        w: _Work,
        o: EntryOutput,
        values: dict[str, float],
        gate: GateResult,
        overlaps: tuple[OverlapLine, ...],
        cfg: S03EntryConfig,
        ctx: RunContext,
        s_hash: str,
        c_hash: str,
    ) -> EntryOptimisation:
        screen = w.source.screen
        ident = screen.identity
        t = o.task
        grid = t.grid
        su = o.surfaces
        ts = np.asarray(t.bars["ts"], dtype=np.int64)
        cells = grid.cells()
        surface: list[SurfaceCell] = []
        for flat, params in enumerate(cells):
            idx = np.unravel_index(flat, grid.shape)

            def leg(name: str, idx: Any = idx) -> Leg:
                return Leg(
                    n_trades=[int(su.n[(s, name)][idx]) for s in SEGMENTS],
                    target=[clean(float(su.target[(s, name)][idx])) for s in SEGMENTS],
                )

            surface.append(
                SurfaceCell(
                    params=params,
                    cost=leg("cost"),
                    zero=leg("zero"),
                    avg_annual_profit_pct_cost=clean(float(su.profit[("whole", "cost")][idx])),
                    smoothed_h1_cost=clean(float(o.smoothed["h1_cost"][idx])),
                    smoothed_h2_cost=clean(float(o.smoothed["h2_cost"][idx])),
                    smoothed_h1_zero=clean(float(o.smoothed["h1_zero"][idx])),
                    in_plateau=bool(o.plateau_mask[idx]),
                )
            )
        sel = o.selected
        failed = {
            "whole": int(np.count_nonzero(su.n[("whole", "cost")] < t.min_trades)),
            "h1": int(np.count_nonzero(su.n[("h1", "cost")] < t.min_trades_half)),
            "h2": int(np.count_nonzero(su.n[("h2", "cost")] < t.min_trades_half)),
        }
        ext = extent(o.plateau_mask, list(grid.axes.values()))
        selection = Selection(
            params=cells[int(np.ravel_multi_index(sel, grid.shape))] if sel is not None else None,
            h1_raw=clean(float(su.target[("h1", "cost")][sel])) if sel is not None else None,
            h1_smoothed=clean(float(o.smoothed["h1_cost"][sel])) if sel is not None else None,
            stability_ratio=clean(o.stability),
            plateau_area=float(o.plateau_mask.sum()) / grid.size,
            plateau_cells=int(o.plateau_mask.sum()),
            plateau_extent={
                name: [clean(lo), clean(hi)] for name, (lo, hi) in zip(grid.names, ext, strict=True)
            },
            edge_slope=clean(o.slope),
            failed_cells=failed,
            inf_targets=o.inf_targets,
        )
        whole = None
        if sel is not None:
            whole = WholeAtSelected(
                n_trades_cost=int(su.n[("whole", "cost")][sel]),
                target_cost=clean(float(su.target[("whole", "cost")][sel])),
                avg_annual_profit_pct_cost=clean(float(su.profit[("whole", "cost")][sel])),
                n_trades_zero=int(su.n[("whole", "zero")][sel]),
                target_zero=clean(float(su.target[("whole", "zero")][sel])),
            )
        zsel = o.zero_selected
        return EntryOptimisation(
            identity=EntryIdentity(
                candidate_id=t.candidate_id,
                parent_id=ident.candidate_id,
                run_id=str(ctx.run_id) if ctx.run_id else None,
                parent_run_id=w.source.parent_run_id,
                symbol=ident.symbol,
                timeframe=ident.timeframe,
                edge_type=ident.edge_type,
                direction=ident.direction,
                asset_class=w.asset_class,
                method=ident.method,
                snapshot=SnapshotId(
                    source=ident.snapshot.source, snapshot_hash=ident.snapshot.snapshot_hash
                ),
                config_hash=c_hash,
                stage_config_hash=s_hash,
                code_version=ctx.code_version,
                control=ctx.config.control,
                unconfirmed=ident.unconfirmed,  # D-645: carried unchanged
            ),
            grid=GridInfo(
                axes=[
                    Axis(name=k2, values=list(v), multiplier=grid.multipliers[k2])
                    for k2, v in grid.axes.items()
                ],
                fixed=grid.fixed,
                stage2_median_cell=dict(screen.baseline.cell or {}),
                size=grid.size,
                size_d639=grid.size_d639,
                small_grid=grid.size < cfg.small_grid_cells,
            ),
            segments={
                name: Segment(
                    start=s,
                    end=e,
                    first_ts_us=int(ts[s]),
                    last_ts_us=int(ts[e - 1]),
                    min_trades=t.min_trades if name == "whole" else t.min_trades_half,
                )
                for name, (s, e) in o.segments.items()
            },
            surface=tuple(surface),
            cells_run=grid.size * len(SEGMENTS),
            selection=selection,
            half2=o.half2,
            whole=whole,
            spp=SppReport(
                median=clean(o.spp.median),
                p_low=clean(o.spp.p_low),
                p_high=clean(o.spp.p_high),
                low_pct=t.spp_low,
                high_pct=t.spp_high,
                median_valid=clean(o.spp.median_valid),
                cells=o.spp.cells,
                failed=o.spp.failed,
            ),
            zero_cost=ZeroCost(
                params=cells[int(np.ravel_multi_index(zsel, grid.shape))]
                if zsel is not None
                else None,
                shift_steps=step_distance(sel, zsel)
                if sel is not None and zsel is not None
                else None,
            ),
            overlaps=overlaps,
            gate_values={k2: clean(v) for k2, v in values.items()},
            gate=tuple(
                GateLine(
                    metric=it.metric,
                    op=it.op,
                    threshold=it.threshold,
                    value=clean(it.value),
                    passed=it.passed,
                    reason=it.reason,
                )
                for it in gate.items
            ),
            gate_passed=gate.passed,
            caveats=screen.caveats,
            warnings=o.warnings,
        )

    @staticmethod
    def _index_row(art: EntryOptimisation, w: _Work) -> dict[str, Any]:
        ident = art.identity
        ov = [o.overlap for o in art.overlaps if o.overlap is not None]
        return {
            "symbol": ident.symbol,
            "timeframe": ident.timeframe,
            "edge_type": ident.edge_type,
            "direction": ident.direction,
            "method": ident.method,
            "parent_id": ident.parent_id,
            "candidate_id": ident.candidate_id,
            "unconfirmed": ident.unconfirmed,
            "grid_cells": art.grid.size,
            "small_grid": art.grid.small_grid,
            "selected_params": canonical_json(art.selection.params)
            if art.selection.params is not None
            else "",
            "stability_ratio": art.selection.stability_ratio,
            "plateau_area": art.selection.plateau_area,
            "plateau_cells": art.selection.plateau_cells,
            "half2_raw": art.half2.raw,
            "selected_in_both_halves": art.half2.accepted,
            "spp_median_target": art.spp.median,
            "zero_cost_shift_steps": art.zero_cost.shift_steps,
            "max_overlap": max(ov) if ov else "",
            "gate_passed": art.gate_passed,
            "failed_criteria": ";".join(g.metric for g in art.gate if not g.passed),
            "quality_status": w.source.screen.caveats.quality_status,
            "reason": "",
        }

    @staticmethod
    def _skip_row(src: Stage2Input, reason: str) -> dict[str, Any]:
        ident = src.screen.identity
        return {
            "symbol": ident.symbol,
            "timeframe": ident.timeframe,
            "edge_type": ident.edge_type,
            "direction": ident.direction,
            "method": ident.method,
            "parent_id": ident.candidate_id,
            "gate_passed": False,
            "quality_status": src.screen.caveats.quality_status,
            "reason": reason,
        }

    @staticmethod
    def _write_registry(
        o: EntryOutput,
        art: EntryOptimisation,
        gate: GateResult,
        refs: list[ArtifactRef],
        ctx: RunContext,
    ) -> None:
        from strategy_factory.registry.writer import CandidateRecord, TrialRecord

        w, run_id, ident = ctx.registry, ctx.run_id, art.identity
        assert run_id is not None
        spec = {
            "stage": STAGE,
            "method": ident.method,
            "params": art.selection.params,
            "control": ident.control,
        }
        w.upsert_candidate(
            CandidateRecord(
                id=ident.candidate_id,
                parent_id=ident.parent_id,
                run_id=run_id,
                symbol=ident.symbol,
                timeframe=ident.timeframe,
                direction=ident.direction,
                edge_type=ident.edge_type,
                spec=spec,
                spec_hash=hashlib.sha256(canonical_json(spec).encode()).hexdigest(),
                current_stage=STAGE,
                status="active" if art.gate_passed else "rejected",
            )
        )
        rows = []
        for c in art.surface:
            for k2, seg in enumerate(SEGMENTS):
                rows.append(
                    TrialRecord(
                        run_id=run_id,
                        stage=STAGE,
                        candidate_id=ident.candidate_id,
                        family_id=ident.method,
                        spec_hash=hashlib.sha256(
                            canonical_json({"method": ident.method, "params": c.params}).encode()
                        ).hexdigest(),
                        params={
                            "method": ident.method,
                            "params": c.params,
                            "direction": ident.direction,
                            "segment": seg,
                            "stage_config_hash": ident.stage_config_hash,
                        },
                        n_trades=c.cost.n_trades[k2],
                        profit_dd_ratio=c.cost.target[k2],
                        extra={
                            "n_trades_zero": c.zero.n_trades[k2],
                            "target_zero": c.zero.target[k2],
                        },
                    )
                )
        w.add_trials(rows)
        w.flush()
        w.add_gate_results(to_registry_rows(gate, run_id))
        for ref in refs:
            w.add_artifact(
                run_id,
                STAGE,
                ref.kind,
                ref.path.as_posix(),
                ref.schema_version,
                ref.sha256,
                candidate_id=ref.candidate_id,
            )


def gate_values(o: EntryOutput) -> dict[str, float]:
    """F-3.7: the ``s03_entry`` gate's inputs (after costs, D-642)."""
    return {
        "spp_median_target": float(o.spp.median),
        "stability_ratio": float(o.stability),
        "plateau_area": float(o.plateau_mask.sum()) / o.task.grid.size,
        "plateau_cells": float(o.plateau_mask.sum()),
        "selected_in_both_halves": 1.0 if o.half2.accepted else 0.0,
    }


def _write_index(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_COLUMNS, restval="")
        writer.writeheader()
        for row in sorted(
            rows,
            key=lambda r: (
                str(r["timeframe"]),
                str(r["symbol"]),
                str(r["direction"]),
                str(r.get("method", "")),
            ),
        ):
            writer.writerow(row)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts per timeframe: candidates, gate passes, small grids, skipped."""
    out: dict[str, Any] = {}
    for tf in sorted({r["timeframe"] for r in rows}):
        mine = [r for r in rows if r["timeframe"] == tf]
        run = [r for r in mine if not r.get("reason")]
        out[tf] = {
            "candidates": len(run),
            "gate_passed": sum(1 for r in run if r["gate_passed"]),
            "small_grids": sum(1 for r in run if r["small_grid"]),
            "skipped": len(mine) - len(run),
        }
    return out


__all__ = [
    "EntryStage",
    "EntryTask",
    "candidate_id",
    "compute_entry",
    "gate_values",
    "halves",
    "read_stage2_selections",
    "segment_runs",
    "stage2_selection_symbols",
]
