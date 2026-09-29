"""Stage 2 -- method screening (``s02_screen``; T13, F-2.1 ... F-2.7; D-622 ... D-636).

For every stage-1 pass (D-609, D-628): **which methods capture the edge best**, measured over a
coarse grid of each method's parameters with the exits still fixed (D-622).

Per (profile, method) -- one executor work unit, pure computation (:func:`compute_method`):

1. every cell of the method's grid runs with stage 1's exits at **zero cost** (the ranking leg)
   and with the symbol's **full cost profile** (the gate leg, D-623); per cell the closed trades
   and the target metric (profit / drawdown against initial capital, spec §2.1);
2. the **good region** is the top quartile of cells by the zero-cost target among the cells at
   the trade minimum; its **median cell** is run against 1,000 matched random entries (D-624,
   D-102, D-607 seeds, D-618): percentile, empirical p, excess return;
3. the family score's raw components (F-2.4, D-636).

The parent (:class:`ScreenStage`) then, per profile: **Benjamini-Hochberg over the methods'
p-values** (D-629), the family score and the **weighted rank-sum** (F-2.5), the walk in rank
order with the **gate** as the acceptance test and the 60 % overlap rule (F-2.6, F-2.7), at most
5 selected (D-625). It alone writes the registry (D-334): a candidate per (profile, method) with
``parent_id`` = the stage-1 candidate, **one trial per cell**, the gate rows; and the artifacts:
``summary.json`` per method, trades for the selected methods' good-region median cells only,
and the index.

Every constant comes from ``configs/stages/s02_screen.yaml`` or the gate YAML (rule 1); the
engine settings only from the run's ``PipelineConfig.engine`` (D-354 (1)). The stage reads the
development segment only and holds no split manager (D-616).
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from strategy_factory.baseline.random_entries import (
    allowed_range,
    atr_returns,
    baseline_seed,
    frictionless_costs,
    frictionless_sizing,
    run_baseline,
    trade_years,
)
from strategy_factory.components.base import Bars
from strategy_factory.components.exits.probe import probe_exit_signals
from strategy_factory.components.registry import default_registry
from strategy_factory.core.config import EngineConfig, canonical_json, config_hash
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.costs.arrays import CostArrays
from strategy_factory.costs.profile import load_assignments, load_profiles
from strategy_factory.data.result_io import write_run_result
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import ExitParams, MarketArrays, SimResult, simulate
from strategy_factory.gates.engine import GateEngine, GateResult, to_registry_rows
from strategy_factory.metrics.containers import RunMeta, RunResult
from strategy_factory.metrics.family import (
    FamilyRaw,
    good_region,
    grid_median,
    median_cell,
    median_ignoring_nan,
    overlap,
    profitable_share,
    rank_sum,
    score_family,
    select_diverse,
    year_share,
)
from strategy_factory.metrics.standard import core_metrics
from strategy_factory.pipeline.backtest import (
    cost_inputs,
    market_arrays,
    sizing_inputs,
    to_run_result,
)
from strategy_factory.pipeline.executor import unit_seed
from strategy_factory.stages.base import ArtifactRef, RunContext, StageResult
from strategy_factory.stages.config import STAGE as S01_STAGE
from strategy_factory.stages.config import EdgeTypeSpec
from strategy_factory.stages.control import permute_returns
from strategy_factory.stages.edge import UnsupportedSymbol, _cost_arrays, _require_research_engine
from strategy_factory.stages.edge_profile import EdgeProfile, GateLine, SnapshotId, clean
from strategy_factory.stages.screen_artifact import (
    SCHEMA_VERSION,
    BaselineTest,
    Cell,
    Family,
    MethodScreen,
    ScreenIdentity,
    json_schema,
)
from strategy_factory.stages.screen_config import (
    STAGE,
    S02ScreenConfig,
    load_s02_config,
    stage_config_hash,
)
from strategy_factory.stats.edge import bh_qvalues, empirical_p, percentile_of

Direction = Literal["long", "short"]
_SIGN = {"long": 1, "short": -1}
MIN_TRADES_METRIC = "min_trades_good_cells"


# --------------------------------------------------------------------------------------
# Work unit (one profile x one method): picklable, computed in a worker
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MethodTask:
    method: str
    symbol: str
    timeframe: str
    edge_type: str
    direction: Direction
    parent_id: str
    candidate_id: str
    bars: dict[str, np.ndarray]  # development segment: ts (µs), open, high, low, close
    costs: CostArrays
    engine: EngineConfig
    exits: EdgeTypeSpec
    min_trades: int
    good_region_share: float
    simulations: int
    consistency_min_trades: int
    run_seed: int


@dataclass(frozen=True)
class CellResult:
    params: dict[str, Any]
    key: str  # canonical JSON of the parameters (the tie-break, D-636 (g))
    n_trades_zero: int
    target_zero: float
    n_trades_cost: int
    target_cost: float
    profit_pct_cost: float
    year_profit: dict[int, float]  # zero-cost P&L by entry year
    year_trades: dict[int, int]


@dataclass(frozen=True)
class MethodOutput:
    task: MethodTask
    cells: tuple[CellResult, ...]
    good: tuple[int, ...]
    median: int | None
    baseline: BaselineTest
    raw: FamilyRaw
    grid_median_cost: float
    profitable_share_cost: float
    min_trades_good_cells: float
    position: np.ndarray  # in-position bars of the median cell's full-cost run (F-2.6)
    trades: RunResult | None  # the median cell's full-cost run (written if selected)
    warnings: tuple[str, ...]


def candidate_id(*, parent_id: str, method: str, control: str, stage_config_hash: str) -> str:
    """sha256 of what identifies a stage-2 candidate (D-636 (h)): the stage, the parent
    stage-1 candidate, the method, the control and the stage-config hash (D-805's pattern)."""
    payload = {
        "stage": STAGE,
        "parent_id": parent_id,
        "method": method,
        "control": control,
        "stage_config_hash": stage_config_hash,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def method_cells(method: str) -> list[dict[str, Any]]:
    """Every cell of the method's coarse grid, in declaration order (D-630: <= 64)."""
    comp = default_registry().get(method)
    names = [p.name for p in comp.params]
    return [
        dict(zip(names, vals, strict=True))
        for vals in itertools.product(*(p.coarse_values for p in comp.params))
    ]


@dataclass(frozen=True)
class CellSignals:
    """A cell's entry and exit signals and its market arrays, computed on bars ``[0, end)``."""

    entry: np.ndarray
    exit: np.ndarray
    market: MarketArrays

    @property
    def end(self) -> int:
        return int(self.entry.shape[0])


def cell_signals(
    bars: dict[str, np.ndarray],
    method: str,
    params: dict[str, Any],
    exits: EdgeTypeSpec,
    direction: Direction,
    atr_length: int,
    end: int | None = None,
) -> CellSignals:
    """The method's signals and stage 1's exit signals (D-622), and the ATR, on the bars up to
    ``end`` only -- nothing after ``end`` is read (rule 3; T14's halves, D-641, D-650 (c))."""
    head = {
        c: np.asarray(bars[c][:end], dtype=np.float64) for c in ("open", "high", "low", "close")
    }
    comp = default_registry().get(method)
    b = Bars(head["open"], head["high"], head["low"], head["close"])
    long_e, short_e = comp.signals(b, params)
    long_x, short_x = probe_exit_signals(exits.exit_signal, comp, b, params)
    entry, exit_ = (long_e, long_x) if direction == "long" else (short_e, short_x)
    return CellSignals(entry=entry, exit=exit_, market=market_arrays(head, atr_length))


def segment_run(
    sig: CellSignals,
    exits: EdgeTypeSpec,
    direction: Direction,
    engine: EngineConfig,
    costs: CostArrays | None = None,
    start: int = 0,
) -> SimResult:
    """Simulate bars ``[start, sig.end)`` only: the signals and the ATR come from ``sig`` (so a
    segment's indicators are warmed up by the earlier bars, D-650 (c)); no trade can enter
    before ``start``. ``costs`` covers the same bars as the series ``sig`` was computed on (the
    whole development window); it is cut to the segment here."""
    end = sig.end
    m = sig.market
    market = MarketArrays(
        *(np.ascontiguousarray(a[start:end]) for a in (m.open, m.high, m.low, m.close, m.atr))
    )
    entry = np.ascontiguousarray(sig.entry[start:end])
    exit_ = np.ascontiguousarray(sig.exit[start:end])
    n = end - start
    ex = ExitParams(time_exit_bars=exits.time_exit_bars, disaster_atr=engine.disaster_stop_atr)
    if costs is None:
        cost_in = frictionless_costs(n)
        sizing = frictionless_sizing(engine.notional, engine.initial_capital)
    else:
        seg = (
            costs
            if (start == 0 and costs.half_spread.shape[0] == end)
            else costs.segment(start, end)
        )
        cost_in = cost_inputs(seg)
        sizing = sizing_inputs(seg, engine, "pessimistic", None)
    return simulate(market, entry, exit_, _SIGN[direction], ex, cost_in, sizing, k.MODE_PESSIMISTIC)


def method_run(
    bars: dict[str, np.ndarray],
    method: str,
    params: dict[str, Any],
    exits: EdgeTypeSpec,
    direction: Direction,
    engine: EngineConfig,
    costs: CostArrays | None = None,
    start: int = 0,
    end: int | None = None,
) -> SimResult:
    """One cell: the method's signals with stage 1's fixed exits (D-622) in research mode.

    ``costs=None`` runs frictionless (the ranking leg); a ``CostArrays`` the full costs (the gate
    leg, D-623). The 3-ATR disaster stop is on (D-130). ``start`` / ``end`` restrict the run to a
    segment (stage 3's halves, D-641): the signals are computed on the bars up to ``end``, the
    simulation covers ``[start, end)``; the defaults run the whole series (stage 2). The stages
    and the leakage tests all call this, so the tests cover what the stages run.
    """
    sig = cell_signals(bars, method, params, exits, direction, engine.atr_length, end)
    return segment_run(sig, exits, direction, engine, costs, start)


def _meta(task: MethodTask, params: dict[str, Any]) -> RunMeta:
    return RunMeta(
        symbol=task.symbol,
        timeframe=task.timeframe,
        spec_hash=hashlib.sha256(
            canonical_json({"method": task.method, "params": params}).encode()
        ).hexdigest(),
        cost_status="placeholder" if task.costs.placeholder else "verified",
        intrabar_mode="pessimistic",
    )


def _target(sim: SimResult, task: MethodTask, params: dict[str, Any]) -> tuple[RunResult, Any]:
    rr = to_run_result(
        sim, task.bars["ts"], _SIGN[task.direction], _meta(task, params), task.engine
    )
    return rr, core_metrics(rr.equity)


def compute_method(task: MethodTask) -> MethodOutput:
    """One (profile, method), start to raw family score (module level: pickled for ``spawn``)."""
    comp = default_registry().get(task.method)
    ts = np.asarray(task.bars["ts"], dtype=np.int64)
    d = _SIGN[task.direction]
    warnings: list[str] = []
    cells: list[CellResult] = []
    zero_runs: list[SimResult] = []
    for params in method_cells(task.method):
        sim0 = method_run(task.bars, task.method, params, task.exits, task.direction, task.engine)
        _, cm0 = _target(sim0, task, params)
        sim1 = method_run(
            task.bars, task.method, params, task.exits, task.direction, task.engine, task.costs
        )
        _, cm1 = _target(sim1, task, params)
        years = trade_years(ts, sim0.entry_idx) if sim0.entry_idx.size else np.zeros(0, np.int64)
        profit: dict[int, float] = {}
        count: dict[int, int] = {}
        for y, pnl in zip(years.tolist(), sim0.pnl_net.tolist(), strict=True):
            profit[y] = profit.get(y, 0.0) + pnl
            count[y] = count.get(y, 0) + 1
        cells.append(
            CellResult(
                params=params,
                key=canonical_json(params),
                n_trades_zero=int(sim0.entry_idx.shape[0]),
                target_zero=float(cm0.profit_dd_ratio),
                n_trades_cost=int(sim1.entry_idx.shape[0]),
                target_cost=float(cm1.profit_dd_ratio),
                profit_pct_cost=float(cm1.avg_annual_profit_pct),
                year_profit=profit,
                year_trades=count,
            )
        )
        zero_runs.append(sim0)
    t0 = [c.target_zero for c in cells]
    n0 = [c.n_trades_zero for c in cells]
    good = good_region(t0, n0, task.min_trades, task.good_region_share, [c.key for c in cells])
    mid = median_cell(good)
    n_bars = int(ts.shape[0])
    position = np.zeros(n_bars, dtype=np.bool_)
    trades: RunResult | None = None
    if mid is None:
        warnings.append("no cell reaches the trade minimum: empty good region")
        base = BaselineTest(
            cell=None, n_trades=0, mean_atr=None, baseline_mean_atr=None, excess_atr=None,
            percentile=None, p_value=None, q_value=None, warmup_bars=None, baseline_infeasible=0,
        )  # fmt: skip
        excess = math.nan
    else:
        params = cells[mid].params
        sim0 = zero_runs[mid]
        r = atr_returns(sim0, d)
        warmup = int(comp.warmup(params))
        market = market_arrays(task.bars, task.engine.atr_length)
        lo, hi = allowed_range(n_bars, warmup, market.atr)
        rng = np.random.default_rng(
            baseline_seed(task.run_seed, task.symbol, task.timeframe, task.method, task.direction)
        )
        bl = run_baseline(
            market,
            ts,
            direction=d,
            holdings=sim0.exit_idx - sim0.entry_idx,
            lo=lo,
            hi=hi,
            simulations=task.simulations,
            rng=rng,
            notional=task.engine.notional,
            initial_capital=task.engine.initial_capital,
        )
        means = bl.sim_means[~np.isnan(bl.sim_means)]
        mean = float(r.mean())
        excess = mean - float(bl.pooled_mean)
        if bl.infeasible:
            warnings.append(f"{bl.infeasible} baseline draw(s) did not fit")
        base = BaselineTest(
            cell=params,
            n_trades=int(r.size),
            mean_atr=clean(mean),
            baseline_mean_atr=clean(float(bl.pooled_mean)),
            excess_atr=clean(excess),
            percentile=clean(percentile_of(mean, means)),
            p_value=clean(empirical_p(mean, means, 1.0 / (task.simulations + 1))),
            q_value=None,
            warmup_bars=warmup,
            baseline_infeasible=int(bl.infeasible),
        )
        sim1 = method_run(
            task.bars, task.method, params, task.exits, task.direction, task.engine, task.costs
        )
        trades, _ = _target(sim1, task, params)
        position = np.asarray(trades.equity.in_position, dtype=np.bool_)
    consistency = median_ignoring_nan(
        [
            year_share(cells[i].year_profit, cells[i].year_trades, task.consistency_min_trades)
            for i in good
        ]
    )
    raw = FamilyRaw(
        grid_median=grid_median(t0, n0, task.min_trades),
        profitable_share=profitable_share(t0, n0, task.min_trades),
        excess=excess,
        consistency=consistency,
    )
    t1 = [c.target_cost for c in cells]
    n1 = [c.n_trades_cost for c in cells]
    if any(math.isinf(c.target_zero) or math.isinf(c.target_cost) for c in cells):
        warnings.append("a cell has an infinite target (zero drawdown), ranked top (D-636)")
    return MethodOutput(
        task=task,
        cells=tuple(cells),
        good=tuple(good),
        median=mid,
        baseline=base,
        raw=raw,
        grid_median_cost=grid_median(t1, n1, task.min_trades),
        profitable_share_cost=profitable_share(t1, n1, task.min_trades),
        min_trades_good_cells=(
            float(min(cells[i].n_trades_cost for i in good)) if good else math.nan
        ),
        position=position,
        trades=trades,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------------------
# The stage (parent side)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProfileInput:
    """One stage-1 pass: its profile and where it came from."""

    profile: EdgeProfile
    parent_run_id: str


@dataclass(frozen=True)
class ProfileWork:
    source: ProfileInput
    asset_class: str
    unconfirmed: bool
    tasks: tuple[MethodTask, ...]


INDEX_COLUMNS = (
    "symbol",
    "timeframe",
    "edge_type",
    "direction",
    "parent_id",
    "method",
    "candidate_id",
    "unconfirmed",
    "cells_run",
    "family_total",
    "rank",
    "rank_sum",
    "grid_median_target",
    "profitable_cell_share",
    "min_trades_good_cells",
    "method_p_value",
    "method_q_value",
    "overlap_with_selected",
    "gate_passed",
    "failed_criteria",
    "selected",
    "selection_note",
    "quality_status",
    "reason",
)


def read_stage1_passes(
    artifacts_root: Path, run_id: str, timeframes: Sequence[str]
) -> list[ProfileInput]:
    """The passing profiles of a stage-1 run (index + ``summary.json``), for ``timeframes``."""
    run_dir = artifacts_root / run_id / S01_STAGE
    index = run_dir / "index.csv"
    if not index.is_file():
        raise ConfigError(f"stage-1 index not found: {index}")
    out: list[ProfileInput] = []
    with index.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["status"] != "profiled" or row["passed"] != "True":
                continue
            if row["timeframe"] not in timeframes:
                continue
            path = run_dir / row["candidate_id"] / "summary.json"
            prof = EdgeProfile.model_validate_json(path.read_text(encoding="utf-8"))
            if prof.identity.control != "none":
                raise ConfigError(
                    f"stage-1 run {run_id} is a control run: stage 2 reads real passes (T13 §10)"
                )
            out.append(ProfileInput(profile=prof, parent_run_id=run_id))
    return sorted(
        out,
        key=lambda p: (
            p.profile.identity.timeframe,
            p.profile.identity.symbol,
            p.profile.identity.edge_type,
            p.profile.identity.direction,
        ),
    )


def stage1_pass_symbols(
    artifacts_root: Path, run_id: str, timeframes: Sequence[str]
) -> tuple[str, ...]:
    """The symbols ``symbol_scope: stage_inputs`` expands to (T13 §3)."""
    return tuple(
        sorted(
            {
                p.profile.identity.symbol
                for p in read_stage1_passes(artifacts_root, run_id, timeframes)
            }
        )
    )


def _min_trades(gates: GateEngine, context: dict[str, str]) -> int:
    for crit in gates.criteria(STAGE, context):
        if crit.metric == MIN_TRADES_METRIC:
            return math.ceil(crit.threshold)
    raise ConfigError(f"the {STAGE} gate has no {MIN_TRADES_METRIC} criterion")


def _write_json(path: Path, data: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ScreenStage:
    """``s02_screen``: inputs are the ``(symbol, timeframe)`` pairs of the resolved config; the
    profiles come from the stage-1 run named in ``stage_inputs``."""

    name: str = STAGE
    stage_config_path: Path | None = None
    s01_config_path: Path | None = None
    costs_dir: Path = Path("configs") / "costs"
    batch_units: int | None = None

    def run(self, inputs: Sequence[tuple[str, str]], ctx: RunContext) -> StageResult:
        cfg = load_s02_config(self.stage_config_path, self.s01_config_path)
        _require_research_engine(ctx)
        from strategy_factory.core.universe import load_universe

        parent_run = ctx.config.stage_inputs.get(S01_STAGE)
        if not parent_run:
            raise ConfigError(f"stage 2 needs stage_inputs.{S01_STAGE} (the stage-1 run to read)")
        wanted = set(inputs)
        profiles = [
            p
            for p in read_stage1_passes(ctx.artifacts_root, parent_run, ctx.config.timeframes)
            if (p.profile.identity.symbol, p.profile.identity.timeframe) in wanted
        ]
        universe = load_universe(ctx.config.universe).by_symbol()
        run_dir = ctx.artifacts_root / (str(ctx.run_id) if ctx.run_id else "dry-run") / STAGE
        result = StageResult()
        index: list[dict[str, Any]] = []
        s_hash = stage_config_hash(cfg)
        c_hash = config_hash(ctx.config)
        cost_profiles, assignments = load_profiles(self.costs_dir), load_assignments(self.costs_dir)
        _write_json(run_dir / "method_screen.schema.json", json_schema())
        bars_cache: dict[tuple[str, str], tuple[dict[str, np.ndarray], CostArrays] | str] = {}
        pending: list[ProfileWork] = []
        n_pending = 0
        limit = self.batch_units or cfg.batch_units
        for src in profiles:
            ident = src.profile.identity
            key = (ident.symbol, ident.timeframe)
            pinned = ctx.config.data_snapshots[ident.symbol][ident.timeframe]
            if pinned.snapshot_hash != ident.snapshot.snapshot_hash:
                raise DataError(
                    f"{ident.symbol} {ident.timeframe}: the reference moved since stage 1 "
                    f"({ident.snapshot.snapshot_hash[:12]} -> {pinned.snapshot_hash[:12]})",
                    stage=STAGE,
                    symbol=ident.symbol,
                )
            if key not in bars_cache:
                bars = ctx.data.arrays(*key)
                bars = {c: bars[c] for c in ("ts", "open", "high", "low", "close")}
                if ctx.config.control == "random_walk":
                    bars = permute_returns(
                        bars, unit_seed(ctx.seed, f"{key[0]}|{key[1]}|random_walk")
                    )
                try:
                    costs = _cost_arrays(
                        key[0], universe[key[0]].asset_class, key[1], bars, self.costs_dir,
                        cost_profiles, assignments,
                    )  # fmt: skip
                    bars_cache[key] = (bars, costs)
                except UnsupportedSymbol as exc:
                    bars_cache[key] = str(exc)
            cached = bars_cache[key]
            if isinstance(cached, str):
                index.append(self._skip_row(src, cached))
                continue
            bars, costs = cached
            asset_class = universe[ident.symbol].asset_class
            context = {"asset_class": asset_class, "timeframe": ident.timeframe}
            min_trades = _min_trades(ctx.gates, context)
            tasks = tuple(
                MethodTask(
                    method=m,
                    symbol=ident.symbol,
                    timeframe=ident.timeframe,
                    edge_type=ident.edge_type,
                    direction=ident.direction,
                    parent_id=ident.candidate_id,
                    candidate_id=candidate_id(
                        parent_id=ident.candidate_id,
                        method=m,
                        control=ctx.config.control,
                        stage_config_hash=s_hash,
                    ),
                    bars=bars,
                    costs=costs,
                    engine=ctx.config.engine,
                    exits=cfg.exits[ident.edge_type],
                    min_trades=min_trades,
                    good_region_share=cfg.good_region_share,
                    simulations=cfg.baseline.simulations,
                    consistency_min_trades=cfg.family_score.consistency_min_trades_per_year,
                    run_seed=ctx.seed,
                )
                for m in cfg.methods_of(ident.edge_type)
            )
            if not tasks:
                index.append(self._skip_row(src, f"no stage-2 method for {ident.edge_type}"))
                continue
            pending.append(
                ProfileWork(
                    source=src,
                    asset_class=asset_class,
                    unconfirmed=ident.timeframe in cfg.unconfirmed_timeframes,
                    tasks=tasks,
                )
            )
            n_pending += len(tasks)
            if n_pending >= limit:
                self._flush(pending, cfg, ctx, run_dir, result, index, s_hash, c_hash)
                pending, n_pending = [], 0
        if pending:
            self._flush(pending, cfg, ctx, run_dir, result, index, s_hash, c_hash)
        if ctx.registry is not None:
            ctx.registry.flush()
        _write_index(run_dir / "index.csv", index)
        result.summary = summarize(index)
        return result

    # -- per batch: run the units, then decide each profile ---------------------------------
    def _flush(
        self,
        work: list[ProfileWork],
        cfg: S02ScreenConfig,
        ctx: RunContext,
        run_dir: Path,
        result: StageResult,
        index: list[dict[str, Any]],
        s_hash: str,
        c_hash: str,
    ) -> None:
        tasks = [t for w in work for t in w.tasks]
        outputs = list(ctx.executor.map(compute_method, tasks))
        pos = 0
        for w in work:
            mine = outputs[pos : pos + len(w.tasks)]
            pos += len(w.tasks)
            self._decide(w, mine, cfg, ctx, run_dir, result, index, s_hash, c_hash)

    def _decide(
        self,
        work: ProfileWork,
        outs: list[MethodOutput],
        cfg: S02ScreenConfig,
        ctx: RunContext,
        run_dir: Path,
        result: StageResult,
        index: list[dict[str, Any]],
        s_hash: str,
        c_hash: str,
    ) -> None:
        ident = work.source.profile.identity
        context = {"asset_class": work.asset_class, "timeframe": ident.timeframe}
        p_values = [
            o.baseline.p_value if o.baseline.p_value is not None else math.nan for o in outs
        ]
        q = bh_qvalues(p_values)  # D-629: BH within the profile
        scores = [score_family(o.raw, cfg.family_score) for o in outs]
        rsum = rank_sum([o.raw for o in outs], cfg.family_score.weights)
        order = sorted(range(len(outs)), key=lambda i: (-rsum[i], outs[i].task.method))
        rank = {i: r + 1 for r, i in enumerate(order)}
        gates: dict[int, GateResult] = {}
        values: dict[int, dict[str, float]] = {}

        def gate_values(i: int, ov: float) -> dict[str, float]:
            o = outs[i]
            return {
                "grid_median_target": o.grid_median_cost,
                "profitable_cell_share": o.profitable_share_cost,
                "min_trades_good_cells": o.min_trades_good_cells,
                "method_q_value": float(q[i]),
                "overlap_with_selected": ov,
            }

        def accept(i: int, ov: float) -> bool:
            values[i] = gate_values(i, ov)
            gates[i] = ctx.gates.evaluate(STAGE, outs[i].task.candidate_id, values[i], context)
            return gates[i].passed

        selected, overlaps = select_diverse(
            order, [o.position for o in outs], accept, cfg.selection.max_candidates
        )
        chosen = set(selected)
        few = len(selected) < cfg.selection.min_candidates
        for i, o in enumerate(outs):
            note = self._note(i, gates[i], chosen, selected, few, cfg)
            ov_all = {
                outs[j].task.method: clean(overlap(o.position, outs[j].position))
                for j in selected
                if j != i
            }
            art = self._artifact(
                o, work, scores[i], float(rsum[i]), rank[i], float(q[i]), values[i], gates[i],
                i in chosen, note, ov_all, overlaps.get(i, 0.0), ctx, s_hash, c_hash,
            )  # fmt: skip
            cdir = run_dir / o.task.candidate_id
            sha = _write_json(cdir / "summary.json", art.model_dump(mode="json"))
            refs = [
                ArtifactRef(
                    "method_screen", cdir / "summary.json", o.task.candidate_id, sha, SCHEMA_VERSION
                )
            ]
            if i in chosen and o.trades is not None:
                tdir = write_run_result(o.trades, cdir / "trades")
                refs.append(ArtifactRef("trades", tdir, o.task.candidate_id, "", "1"))
                result.passed.append(o.task.candidate_id)
            result.artifacts.extend(refs)
            result.gate_results.append(gates[i])
            index.append(self._index_row(art, work))
            if ctx.registry is not None and ctx.run_id is not None:
                self._write_registry(o, art, gates[i], refs, ctx)

    @staticmethod
    def _note(
        i: int,
        gate: GateResult,
        chosen: set[int],
        selected: list[int],
        few: bool,
        cfg: S02ScreenConfig,
    ) -> str:
        if i in chosen:
            n = len(selected)
            return (
                f"selected ({n} of the profile; fewer than {cfg.selection.min_candidates} "
                "passed, D-625)"
                if few
                else f"selected ({n} of the profile)"
            )
        failed = [c.metric for c in gate.failed()]
        if failed:
            return "gate failed: " + ", ".join(failed)
        return f"passed the gate; the cap of {cfg.selection.max_candidates} was reached (D-625)"

    @staticmethod
    def _artifact(
        o: MethodOutput,
        work: ProfileWork,
        score: Any,
        rsum: float,
        rank: int,
        q: float,
        values: dict[str, float],
        gate: GateResult,
        selected: bool,
        note: str,
        overlaps: dict[str, float | None],
        overlap_selected: float,
        ctx: RunContext,
        s_hash: str,
        c_hash: str,
    ) -> MethodScreen:
        ident = work.source.profile.identity
        good = set(o.good)
        grid = tuple(
            Cell(
                params=c.params,
                n_trades_zero=c.n_trades_zero,
                target_zero=clean(c.target_zero),
                n_trades_cost=c.n_trades_cost,
                target_cost=clean(c.target_cost),
                avg_annual_profit_pct_cost=clean(c.profit_pct_cost),
                inf_target=math.isinf(c.target_zero) or math.isinf(c.target_cost),
                good_region=idx in good,
            )
            for idx, c in enumerate(o.cells)
        )
        return MethodScreen(
            identity=ScreenIdentity(
                candidate_id=o.task.candidate_id,
                parent_id=ident.candidate_id,
                run_id=str(ctx.run_id) if ctx.run_id else None,
                parent_run_id=work.source.parent_run_id,
                symbol=ident.symbol,
                timeframe=ident.timeframe,
                edge_type=ident.edge_type,
                direction=ident.direction,
                asset_class=work.asset_class,
                method=o.task.method,
                snapshot=SnapshotId(
                    source=ident.snapshot.source, snapshot_hash=ident.snapshot.snapshot_hash
                ),
                config_hash=c_hash,
                stage_config_hash=s_hash,
                code_version=ctx.code_version,
                control=ctx.config.control,
                unconfirmed=work.unconfirmed,
            ),
            grid=grid,
            cells_run=len(grid),
            baseline=o.baseline.model_copy(update={"q_value": clean(q)}),
            family=Family(
                raw={k2: clean(v) for k2, v in score.raw.items()},
                share=score.share,
                points=score.points,
                total=score.total,
                rank_sum=rsum,
                rank=rank,
            ),
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
            overlap_with_selected=clean(overlap_selected),
            overlaps=overlaps,
            selected=selected,
            selection_note=note,
            caveats=work.source.profile.caveats,
            warnings=o.warnings,
        )

    @staticmethod
    def _index_row(art: MethodScreen, work: ProfileWork) -> dict[str, Any]:
        ident = art.identity
        return {
            "symbol": ident.symbol,
            "timeframe": ident.timeframe,
            "edge_type": ident.edge_type,
            "direction": ident.direction,
            "parent_id": ident.parent_id,
            "method": ident.method,
            "candidate_id": ident.candidate_id,
            "unconfirmed": ident.unconfirmed,
            "cells_run": art.cells_run,
            "family_total": art.family.total,
            "rank": art.family.rank,
            "rank_sum": art.family.rank_sum,
            "grid_median_target": art.gate_values.get("grid_median_target"),
            "profitable_cell_share": art.gate_values.get("profitable_cell_share"),
            "min_trades_good_cells": art.gate_values.get("min_trades_good_cells"),
            "method_p_value": art.baseline.p_value,
            "method_q_value": art.baseline.q_value,
            "overlap_with_selected": art.overlap_with_selected,
            "gate_passed": art.gate_passed,
            "failed_criteria": ";".join(g.metric for g in art.gate if not g.passed),
            "selected": art.selected,
            "selection_note": art.selection_note,
            "quality_status": work.source.profile.caveats.quality_status,
            "reason": "",
        }

    @staticmethod
    def _skip_row(src: ProfileInput, reason: str) -> dict[str, Any]:
        ident = src.profile.identity
        return {
            "symbol": ident.symbol,
            "timeframe": ident.timeframe,
            "edge_type": ident.edge_type,
            "direction": ident.direction,
            "parent_id": ident.candidate_id,
            "selected": False,
            "quality_status": src.profile.caveats.quality_status,
            "reason": reason,
        }

    @staticmethod
    def _write_registry(
        o: MethodOutput,
        art: MethodScreen,
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
            "median_cell": art.baseline.cell,
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
                status="active" if art.selected else "rejected",
            )
        )
        w.add_trials(
            [
                TrialRecord(
                    run_id=run_id,
                    stage=STAGE,
                    candidate_id=ident.candidate_id,
                    family_id=ident.method,  # the family is the parameterised method (F-2.4)
                    spec_hash=hashlib.sha256(
                        canonical_json({"method": ident.method, "params": c.params}).encode()
                    ).hexdigest(),
                    params={
                        "method": ident.method,
                        "params": c.params,
                        "direction": ident.direction,
                        "stage_config_hash": ident.stage_config_hash,
                    },
                    n_trades=c.n_trades_cost,
                    profit_dd_ratio=clean(c.target_cost),
                    extra={
                        "n_trades_zero": c.n_trades_zero,
                        "target_zero": clean(c.target_zero),
                        "avg_annual_profit_pct_cost": clean(c.profit_pct_cost),
                        "inf_target": math.isinf(c.target_zero) or math.isinf(c.target_cost),
                    },
                )
                for c in o.cells
            ]
        )
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
                int(r.get("rank") or 0),
                str(r.get("method", "")),
            ),
        ):
            writer.writerow(row)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts per timeframe: profiles, method rows, gate passes, selected, profiles with none."""
    out: dict[str, Any] = {}
    for tf in sorted({r["timeframe"] for r in rows}):
        mine = [r for r in rows if r["timeframe"] == tf and r.get("method")]
        profiles = {r["parent_id"] for r in rows if r["timeframe"] == tf}
        with_sel = {r["parent_id"] for r in mine if r["selected"]}
        out[tf] = {
            "profiles": len(profiles),
            "methods_screened": len(mine),
            "gate_passed": sum(1 for r in mine if r["gate_passed"]),
            "selected": sum(1 for r in mine if r["selected"]),
            "profiles_without_selection": len(profiles - with_sel),
        }
    return out


__all__ = [
    "CellSignals",
    "MethodTask",
    "ScreenStage",
    "candidate_id",
    "cell_signals",
    "compute_method",
    "method_cells",
    "method_run",
    "read_stage1_passes",
    "segment_run",
    "stage1_pass_symbols",
]
