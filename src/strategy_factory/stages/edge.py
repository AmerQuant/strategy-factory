"""Stage 1 -- edge discovery (``s01_edge``; T12, F-1.1 … F-1.9).

For one symbol, timeframe, edge type and direction (D-604): **is there an edge at all?**

Per profile (:func:`compute_profile`, one executor work unit, pure computation):

1. every probe of the edge type runs with its fixed parameters and fixed exits (F-1.3, D-101,
   D-614) at **zero costs** (D-602): its trades' returns in ATR of the signal bar give the
   **mean** (D-601, the percentile statistic) and the median (reported);
2. the matched random baseline (F-1.4, D-615) gives the distribution of the same mean over
   ``simulations`` draws: percentile (strictly below, x100) and empirical p (floored at
   ``1/(n+1)``, D-606); **excess** = the probe's mean minus its own baseline's mean (D-613);
3. consistency: per calendar year of the development window, the probe's mean minus the
   baseline's mean of the trades entering that year; years with too few probe trades are
   excluded and counted (D-613);
4. the same signals run again with the symbol's **full cost profile** for the profit factor
   (D-602);
5. Benjamini-Hochberg over the profile's p-values (D-605); the ``s01_probe`` gate per probe;
   accepted groups; ESS over **every probe run** (D-606, D-613); the ``s01_edge`` gate.

The parent (:class:`EdgeStage`) builds the work units from the development bars, runs them
through the executor and alone writes the registry (D-334) and the artifacts: candidate rows,
one trial per probe (D-012, D-616), the gate rows, ``summary.json`` per profile, trades only
for the accepted probes of passing profiles (D-608), and the universe index (D-617).

Every constant comes from ``configs/stages/s01_edge.yaml`` or the gate YAML (rule 1); the
engine settings only from the run's ``PipelineConfig.engine`` (D-354 (1)).
"""

from __future__ import annotations

import csv
import functools
import hashlib
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
from strategy_factory.costs.arrays import CostArrays, build_cost_arrays, resolve_from_data
from strategy_factory.costs.profile import (
    SpreadBrokerScaled,
    SpreadFromData,
    load_assignments,
    load_profiles,
    resolve_profile,
)
from strategy_factory.data.result_io import write_run_result
from strategy_factory.data.split import HistoryTooShortError
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import ExitParams, SimResult, simulate
from strategy_factory.gates.engine import GateEngine, GateResult, to_registry_rows
from strategy_factory.metrics.containers import RunMeta, RunResult
from strategy_factory.metrics.ess import as_json, raw_components, score_ess
from strategy_factory.metrics.standard import profit_factor
from strategy_factory.pipeline.backtest import (
    cost_inputs,
    market_arrays,
    sizing_inputs,
    to_run_result,
)
from strategy_factory.pipeline.executor import unit_seed
from strategy_factory.stages.base import ArtifactRef, RunContext, StageResult
from strategy_factory.stages.config import (
    PROBE_STAGE,
    STAGE,
    EdgeTypeSpec,
    S01EdgeConfig,
    load_s01_config,
)
from strategy_factory.stages.control import permute_returns
from strategy_factory.stages.edge_profile import (
    SCHEMA_VERSION,
    Caveat,
    EdgeProfile,
    GateLine,
    Identity,
    ProbeResult,
    ProfileVerdict,
    SnapshotId,
    clean,
    json_schema,
)
from strategy_factory.stats.edge import bh_qvalues, empirical_p, percentile_of

Direction = Literal["long", "short"]
DIRECTIONS: tuple[Direction, ...] = ("long", "short")
_SIGN = {"long": 1, "short": -1}


# --------------------------------------------------------------------------------------
# Work unit (D-604): picklable, computed in a worker
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProfileTask:
    symbol: str
    timeframe: str
    edge_type: str
    direction: Direction
    asset_class: str
    candidate_id: str
    bars: dict[str, np.ndarray]  # development segment: ts (µs), open, high, low, close
    costs: CostArrays
    engine: EngineConfig
    stage: S01EdgeConfig
    gates_path: Path
    run_seed: int
    identity: Identity
    caveats: Caveat
    keep_trades: bool = True


@dataclass(frozen=True)
class ProfileOutput:
    profile: EdgeProfile
    probe_gates: tuple[GateResult, ...]
    profile_gate: GateResult
    trades: dict[str, RunResult]  # accepted probes of a passing profile only (D-608)


@functools.cache
def _gate_engine(path: Path) -> GateEngine:
    return GateEngine.from_file(path)


def candidate_id(
    *,
    symbol: str,
    timeframe: str,
    edge_type: str,
    direction: str,
    snapshot_hash: str,
    probes: dict[str, dict[str, Any]],
    control: str,
) -> str:
    """D-616: sha256 of the canonical JSON of what identifies a stage-1 profile."""
    payload = {
        "stage": STAGE,
        "symbol": symbol,
        "timeframe": timeframe,
        "edge_type": edge_type,
        "direction": direction,
        "snapshot_hash": snapshot_hash,
        "probes": probes,
        "control": control,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def stage_config_hash(cfg: S01EdgeConfig) -> str:
    return hashlib.sha256(canonical_json(cfg.model_dump(mode="json")).encode("utf-8")).hexdigest()


def probe_params(cfg: S01EdgeConfig, edge_type: str) -> dict[str, dict[str, Any]]:
    """The fixed (default) parameters of every probe of ``edge_type`` (F-1.1, F-1.2)."""
    reg = default_registry()
    return {p: {s.name: s.default for s in reg.get(p).params} for p in cfg.probes_of(edge_type)}


def _consistency(
    returns: np.ndarray,
    years: np.ndarray,
    base_returns: np.ndarray,
    base_years: np.ndarray,
    window_years: range,
    min_trades: int,
) -> tuple[float, int, int]:
    """``(share of positive counted years, years counted, years excluded)`` (D-613)."""
    positive = counted = 0
    for y in window_years:
        mine = returns[years == y]
        theirs = base_returns[base_years == y]
        if mine.size < min_trades or theirs.size == 0:
            continue
        counted += 1
        positive += int(float(mine.mean()) - float(theirs.mean()) > 0.0)
    excluded = len(window_years) - counted
    return (positive / counted if counted else float("nan")), counted, excluded


def probe_run(
    bars: dict[str, np.ndarray],
    probe: str,
    params: dict[str, Any],
    spec: EdgeTypeSpec,
    direction: Direction,
    engine: EngineConfig,
    costs: CostArrays | None = None,
) -> SimResult:
    """One probe run: its signals, its fixed exits (D-101, D-614), the engine (research mode).

    ``costs=None`` runs **frictionless** (the statistic, D-602); a ``CostArrays`` runs the same
    signals with the symbol's full costs (the profit factor). The 3-ATR disaster stop is on for
    every probe (D-130, D-614), from ``engine``. The stage and the leakage test both call this,
    so the test covers exactly what the stage runs.
    """
    comp = default_registry().get(probe)
    b = Bars(*(np.asarray(bars[c], dtype=np.float64) for c in ("open", "high", "low", "close")))
    long_e, short_e = comp.signals(b, params)
    long_x, short_x = probe_exit_signals(spec.exit_signal, comp, b, params)
    entry, exit_ = (long_e, long_x) if direction == "long" else (short_e, short_x)
    market = market_arrays(bars, engine.atr_length)
    n = len(b)
    exits = ExitParams(time_exit_bars=spec.time_exit_bars, disaster_atr=engine.disaster_stop_atr)
    if costs is None:
        cost_in = frictionless_costs(n)
        sizing = frictionless_sizing(engine.notional, engine.initial_capital)
    else:
        cost_in = cost_inputs(costs)
        sizing = sizing_inputs(costs, engine, "pessimistic", None)
    d = _SIGN[direction]
    return simulate(market, entry, exit_, d, exits, cost_in, sizing, k.MODE_PESSIMISTIC)


def compute_profile(task: ProfileTask) -> ProfileOutput:
    """One profile, start to verdict (module level: the executor pickles it for ``spawn``)."""
    cfg = task.stage
    spec = cfg.edge_types[task.edge_type]
    reg = default_registry()
    gates = _gate_engine(task.gates_path)
    context = {"asset_class": task.asset_class, "timeframe": task.timeframe}
    ts = np.asarray(task.bars["ts"], dtype=np.int64)
    market = market_arrays(task.bars, task.engine.atr_length)
    n = int(market.close.shape[0])
    d = _SIGN[task.direction]
    first_year, last_year = (int(y) for y in trade_years(ts, np.array([0, n - 1])))
    window = range(first_year, last_year + 1)
    params = probe_params(cfg, task.edge_type)
    warnings: list[str] = []

    rows: list[dict[str, Any]] = []
    full_runs: dict[str, SimResult] = {}
    for name in cfg.probes_of(task.edge_type):
        comp = reg.get(name)
        sim0 = probe_run(task.bars, name, params[name], spec, task.direction, task.engine)
        r = atr_returns(sim0, d)
        n_tr = int(r.size)
        row: dict[str, Any] = {
            "name": name,
            "group": comp.group,
            "trigger": comp.trigger,
            "params": params[name],
            "n_closed_trades": n_tr,
            "mean_atr": float(r.mean()) if n_tr else math.nan,
            "median_atr": float(np.median(r)) if n_tr else math.nan,
        }
        base_mean = pct = p = pos_share = math.nan
        counted = 0
        excluded = len(window)
        infeasible = clamped = 0
        if n_tr:
            lo, hi = allowed_range(n, cfg.probes[name].warmup_bars, market.atr)
            rng = np.random.default_rng(
                baseline_seed(task.run_seed, task.symbol, task.timeframe, name, task.direction)
            )
            base = run_baseline(
                market,
                ts,
                direction=d,
                holdings=sim0.exit_idx - sim0.entry_idx,
                lo=lo,
                hi=hi,
                simulations=cfg.baseline.simulations,
                rng=rng,
                notional=task.engine.notional,
                initial_capital=task.engine.initial_capital,
            )
            means = base.sim_means[~np.isnan(base.sim_means)]
            base_mean = base.pooled_mean
            pct = percentile_of(row["mean_atr"], means)
            p = empirical_p(row["mean_atr"], means, cfg.baseline.p_floor)
            pos_share, counted, excluded = _consistency(
                r,
                trade_years(ts, sim0.entry_idx),
                base.pooled_returns,
                base.pooled_years,
                window,
                cfg.ess.consistency_min_trades_per_year,
            )
            infeasible, clamped = base.infeasible, base.clamped_holdings
            if infeasible:
                warnings.append(f"{name}: {infeasible} baseline draw(s) did not fit")
            # D-620: the disaster-hit share and the mean/median gap are reported as numbers,
            # never as warnings (both fired on almost every probe and said nothing).
            disaster = float(np.mean(sim0.exit_reason == k.DISASTER_STOP))
        else:
            disaster = math.nan
        sim1 = probe_run(
            task.bars, name, params[name], spec, task.direction, task.engine, task.costs
        )
        full_runs[name] = sim1
        pf = profit_factor(sim1.pnl_net)
        if math.isinf(pf):
            warnings.append(f"{name}: profit factor is infinite (no losing trade)")
        row.update(
            baseline_mean_atr=base_mean,
            excess_atr=row["mean_atr"] - base_mean,
            percentile=pct,
            p_value=p,
            profit_factor=pf,
            pf_n_trades=int(sim1.entry_idx.shape[0]),
            pf_skipped_min_volume=int(sim1.n_skipped_min_volume),
            positive_year_share=pos_share,
            years_counted=counted,
            years_excluded=excluded,
            disaster_share=disaster,
            baseline_infeasible=infeasible,
            clamped_holdings=clamped,
        )
        rows.append(row)

    q = bh_qvalues([r["p_value"] for r in rows])
    probe_gates: list[GateResult] = []
    results: list[ProbeResult] = []
    for row, qv in zip(rows, q, strict=True):
        gate = gates.evaluate(
            PROBE_STAGE,
            task.candidate_id,
            {
                "n_trades": row["n_closed_trades"],
                "probe_percentile": row["percentile"],
                "profit_factor": row["profit_factor"],
                "probe_q_value": float(qv),
            },
            context,
        )
        probe_gates.append(gate)
        results.append(
            ProbeResult(
                **row,
                q_value=float(qv),
                accepted=gate.passed,
                failed_criteria=tuple(i.metric for i in gate.failed()),
            )
        )
    accepted_groups = tuple(sorted({r.group for r in results if r.accepted}))
    ess = score_ess(
        raw_components(
            accepted_groups=len(accepted_groups),
            applicable_groups=len(spec.applicable_groups),
            excess=[r["excess_atr"] for r in rows],
            p_values=[r["p_value"] for r in rows],
            positive_year_share=[r["positive_year_share"] for r in rows],
        ),
        cfg.ess,
    )
    profile_gate = gates.evaluate(
        STAGE,
        task.candidate_id,
        {"accepted_probe_groups": len(accepted_groups), "ess": ess.total},
        context,
    )
    profile = EdgeProfile(
        identity=task.identity,
        probes=tuple(results),
        profile=ProfileVerdict(
            ess=as_json(ess),
            accepted_groups=accepted_groups,
            applicable_groups=spec.applicable_groups,
            gate=tuple(
                GateLine(
                    metric=i.metric,
                    op=i.op,
                    threshold=i.threshold,
                    value=clean(i.value),
                    passed=i.passed,
                    reason=i.reason,
                )
                for i in profile_gate.items
            ),
            passed=profile_gate.passed,
        ),
        probes_run=len(results),
        caveats=task.caveats,
        warnings=tuple(warnings),
    )
    trades: dict[str, RunResult] = {}
    if task.keep_trades and profile_gate.passed:
        for pr in results:
            if pr.accepted:
                meta = RunMeta(
                    symbol=task.symbol,
                    timeframe=task.timeframe,
                    spec_hash=hashlib.sha256(
                        canonical_json({"probe": pr.name, "params": pr.params}).encode()
                    ).hexdigest(),
                    cost_status="placeholder" if task.costs.placeholder else "verified",
                    intrabar_mode="pessimistic",
                    n_skipped_min_volume=pr.pf_skipped_min_volume,
                    volume_step_assumed=task.costs.volume_step_assumed,
                )
                trades[pr.name] = to_run_result(full_runs[pr.name], ts, d, meta, task.engine)
    return ProfileOutput(profile, tuple(probe_gates), profile_gate, trades)


# --------------------------------------------------------------------------------------
# The stage (parent side): build the units, run them, write everything
# --------------------------------------------------------------------------------------
class UnsupportedSymbol(Exception):
    """A symbol stage 1 cannot run yet: it is listed as skipped with the reason, never aborts."""


def _cost_arrays(
    symbol: str,
    asset_class: str,
    timeframe: str,
    bars: dict[str, np.ndarray],
    costs_dir: Path,
    profiles: Any,
    assignments: Any,
) -> CostArrays:
    profile = resolve_profile(symbol, asset_class, profiles, assignments, costs_dir)
    if isinstance(profile.spread, SpreadFromData | SpreadBrokerScaled):
        profile, _ = resolve_from_data(profile, bars)  # development bars only (D-340)
    costs = build_cost_arrays(bars, profile, timeframe=timeframe)
    if costs.quote_ccy != "USD":
        raise UnsupportedSymbol(
            f"quote currency {costs.quote_ccy}: stage 1 runs USD-quoted symbols only for now "
            "(no conversion arrays are wired in; P-105)"
        )
    return costs


def _write_json(path: Path, data: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_research_engine(ctx: RunContext) -> None:
    """D-354 (1): the engine settings come from the run's config -- and stage 1 is a research
    stage, so a parity setting there is refused rather than silently ignored."""
    problems = []
    if ctx.config.intrabar_mode != "pessimistic":
        problems.append(f"intrabar_mode {ctx.config.intrabar_mode!r} (research runs 'pessimistic')")
    if ctx.config.engine.entry_requires_flat_at_signal:
        problems.append("engine.entry_requires_flat_at_signal (a parity-only option, D-367)")
    if problems:
        raise ConfigError(
            "stage 1 runs research settings only; the config sets " + "; ".join(problems)
        )


INDEX_COLUMNS = (
    "symbol",
    "timeframe",
    "edge_type",
    "direction",
    "candidate_id",
    "status",
    "passed",
    "ess",
    "breadth",
    "magnitude",
    "significance",
    "consistency",
    "accepted_groups",
    "probes_run",
    "quality_status",
    "warning_checks",
    "research_window",
    "trimmed",
    "reason",
)


@dataclass
class EdgeStage:
    """``s01_edge``: inputs are ``(symbol, timeframe)`` pairs of the resolved config."""

    name: str = STAGE
    stage_config_path: Path | None = None
    costs_dir: Path = Path("configs") / "costs"
    batch_units: int | None = None  # None: the stage config's batch_units
    keep_trades: bool = True

    def run(self, inputs: Sequence[tuple[str, str]], ctx: RunContext) -> StageResult:
        cfg = load_s01_config(self.stage_config_path)
        _require_research_engine(ctx)
        from strategy_factory.core.universe import load_universe

        universe = load_universe(ctx.config.universe).by_symbol()
        run_dir = ctx.artifacts_root / (str(ctx.run_id) if ctx.run_id else "dry-run") / STAGE
        result = StageResult()
        index: list[dict[str, Any]] = []
        s_hash = stage_config_hash(cfg)
        # parsed once per run, not per symbol: re-reading every profile YAML cost 0.5 s a
        # symbol in the parent while the workers waited (T12 pilot profiling)
        profiles, assignments = load_profiles(self.costs_dir), load_assignments(self.costs_dir)
        c_hash = config_hash(ctx.config)
        _write_json(run_dir / "edge_profile.schema.json", json_schema())
        pending: list[ProfileTask] = []
        for symbol, tf in inputs:
            pinned = ctx.config.data_snapshots[symbol][tf]
            meta = ctx.references.reference(symbol, tf)
            if meta.snapshot_hash != pinned.snapshot_hash:
                raise DataError(
                    f"{symbol} {tf}: the reference moved since the config was resolved "
                    f"({pinned.snapshot_hash[:12]} -> {str(meta.snapshot_hash)[:12]})",
                    stage=STAGE,
                    symbol=symbol,
                )
            caveats = ctx.references.caveats(symbol, tf)
            try:
                split = ctx.data.split(symbol, tf)
            except HistoryTooShortError as exc:
                index.append(
                    _skip_row(symbol, tf, caveats, f"too short for a split (D-008): {exc}")
                )
                continue
            bars = ctx.data.arrays(symbol, tf)
            if ctx.config.control == "random_walk":
                bars = permute_returns(bars, unit_seed(ctx.seed, f"{symbol}|{tf}|random_walk"))
            asset_class = universe[symbol].asset_class
            try:
                costs = _cost_arrays(
                    symbol, asset_class, tf, bars, self.costs_dir, profiles, assignments
                )
            except UnsupportedSymbol as exc:
                index.append(_skip_row(symbol, tf, caveats, str(exc)))
                continue
            for edge_type in cfg.runnable_edge_types():
                probes = probe_params(cfg, edge_type)
                for direction in DIRECTIONS:
                    cid = candidate_id(
                        symbol=symbol,
                        timeframe=tf,
                        edge_type=edge_type,
                        direction=direction,
                        snapshot_hash=pinned.snapshot_hash,
                        probes=probes,
                        control=ctx.config.control,
                    )
                    identity = Identity(
                        candidate_id=cid,
                        run_id=str(ctx.run_id) if ctx.run_id else None,
                        symbol=symbol,
                        timeframe=tf,
                        edge_type=edge_type,
                        direction=direction,
                        asset_class=asset_class,
                        snapshot=SnapshotId(
                            source=pinned.source, snapshot_hash=pinned.snapshot_hash
                        ),
                        config_hash=c_hash,
                        stage_config_hash=s_hash,
                        code_version=ctx.code_version,
                        control=ctx.config.control,
                        dev_start=split.dev_start.isoformat(),
                        dev_end=split.dev_end.isoformat(),
                        dev_bars=int(bars["close"].shape[0]),
                    )
                    pending.append(
                        ProfileTask(
                            symbol=symbol,
                            timeframe=tf,
                            edge_type=edge_type,
                            direction=direction,
                            asset_class=asset_class,
                            candidate_id=cid,
                            bars={c: bars[c] for c in ("ts", "open", "high", "low", "close")},
                            costs=costs,
                            engine=ctx.config.engine,
                            stage=cfg,
                            gates_path=ctx.config.gates,
                            run_seed=ctx.seed,
                            identity=identity,
                            caveats=caveats,
                            keep_trades=self.keep_trades,
                        )
                    )
            if len(pending) >= (self.batch_units or cfg.batch_units):
                self._flush(pending, ctx, run_dir, result, index)
                pending = []
        if pending:
            self._flush(pending, ctx, run_dir, result, index)
        if ctx.registry is not None:
            ctx.registry.flush()
        _write_index(run_dir / "index.csv", index)
        result.summary = summarize(index)
        return result

    def _flush(
        self,
        tasks: list[ProfileTask],
        ctx: RunContext,
        run_dir: Path,
        result: StageResult,
        index: list[dict[str, Any]],
    ) -> None:
        for out in ctx.executor.map(compute_profile, tasks):
            self._record(out, ctx, run_dir, result)
            index.append(_index_row(out.profile))

    def _record(
        self, out: ProfileOutput, ctx: RunContext, run_dir: Path, result: StageResult
    ) -> None:
        prof = out.profile
        ident = prof.identity
        cdir = run_dir / ident.candidate_id
        sha = _write_json(cdir / "summary.json", prof.model_dump(mode="json"))
        refs = [
            ArtifactRef(
                "edge_profile", cdir / "summary.json", ident.candidate_id, sha, SCHEMA_VERSION
            )
        ]
        for probe, rr in out.trades.items():
            tdir = write_run_result(rr, cdir / "trades" / probe)
            refs.append(ArtifactRef("trades", tdir, ident.candidate_id, "", "1"))
        result.artifacts.extend(refs)
        result.gate_results.extend([*out.probe_gates, out.profile_gate])
        if prof.profile.passed:
            result.passed.append(ident.candidate_id)
        if ctx.registry is None or ctx.run_id is None:
            return
        self._write_registry(out, ctx, refs)

    @staticmethod
    def _write_registry(out: ProfileOutput, ctx: RunContext, refs: list[ArtifactRef]) -> None:
        from strategy_factory.registry.writer import CandidateRecord, TrialRecord

        prof, ident, w, run_id = out.profile, out.profile.identity, ctx.registry, ctx.run_id
        assert run_id is not None
        spec = {p.name: p.params for p in prof.probes}
        w.upsert_candidate(
            CandidateRecord(
                id=ident.candidate_id,
                run_id=run_id,
                symbol=ident.symbol,
                timeframe=ident.timeframe,
                direction=ident.direction,
                edge_type=ident.edge_type,
                spec={"stage": STAGE, "probes": spec, "control": ident.control},
                spec_hash=hashlib.sha256(canonical_json(spec).encode()).hexdigest(),
                current_stage=STAGE,
                status="active" if prof.profile.passed else "rejected",
            )
        )
        w.add_trials(
            [
                TrialRecord(
                    run_id=run_id,
                    stage=STAGE,
                    candidate_id=ident.candidate_id,
                    family_id=ident.edge_type,  # addendum §1.7: a search family per edge type
                    spec_hash=hashlib.sha256(
                        canonical_json({"probe": p.name, "params": p.params}).encode()
                    ).hexdigest(),
                    params={
                        "probe": p.name,
                        "params": p.params,
                        "direction": ident.direction,
                        "stage_config_hash": ident.stage_config_hash,  # D-606: which constants
                    },
                    n_trades=p.n_closed_trades,
                    profit_factor=p.profit_factor,
                    extra={
                        k2: v
                        for k2, v in p.model_dump(mode="json").items()
                        if k2 not in ("name", "params", "n_closed_trades", "profit_factor")
                    },
                )
                for p in prof.probes
            ]
        )
        w.flush()
        rows = []
        for probe, gate in zip(prof.probes, out.probe_gates, strict=True):
            rows += [
                r.model_copy(update={"criterion": f"{probe.name}:{r.criterion}"})
                for r in to_registry_rows(gate, run_id)
            ]
        rows += to_registry_rows(out.profile_gate, run_id)
        w.add_gate_results(rows)
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


def _skip_row(symbol: str, tf: str, caveats: Caveat, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": tf,
        "status": "skipped",
        "passed": False,
        "quality_status": caveats.quality_status,
        "warning_checks": ";".join(caveats.warning_checks),
        "research_window": caveats.research_window,
        "trimmed": caveats.trimmed,
        "reason": reason,
    }


def _index_row(prof: EdgeProfile) -> dict[str, Any]:
    ident, verdict, cav = prof.identity, prof.profile, prof.caveats
    points = verdict.ess["points"]
    return {
        "symbol": ident.symbol,
        "timeframe": ident.timeframe,
        "edge_type": ident.edge_type,
        "direction": ident.direction,
        "candidate_id": ident.candidate_id,
        "status": "profiled",
        "passed": verdict.passed,
        "ess": verdict.ess["total"],
        "breadth": points["breadth"],
        "magnitude": points["magnitude"],
        "significance": points["significance"],
        "consistency": points["consistency"],
        "accepted_groups": ";".join(verdict.accepted_groups),
        "probes_run": prof.probes_run,
        "quality_status": cav.quality_status,
        "warning_checks": ";".join(cav.warning_checks),
        "research_window": cav.research_window,
        "trimmed": cav.trimmed,
        "reason": "",
    }


def _write_index(path: Path, rows: list[dict[str, Any]]) -> None:
    """The universe index (D-617): the heatmap's data, one row per profile or skip.

    CSV rather than Parquet: Parquet I/O belongs to the data layer (D-302), which stage 1
    does not extend.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_COLUMNS, restval="")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: tuple(str(r.get(c, "")) for c in INDEX_COLUMNS[:4])):
            writer.writerow(row)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts per timeframe (the review's numbers are recomputed from the index)."""
    out: dict[str, Any] = {}
    for tf in sorted({r["timeframe"] for r in rows}):
        mine = [r for r in rows if r["timeframe"] == tf]
        prof = [r for r in mine if r["status"] == "profiled"]
        out[tf] = {
            "profiles": len(prof),
            "passed": sum(1 for r in prof if r["passed"]),
            "skipped": len(mine) - len(prof),
        }
    return out


__all__ = [
    "EdgeStage",
    "ProfileOutput",
    "ProfileTask",
    "candidate_id",
    "compute_profile",
    "stage_config_hash",
]
