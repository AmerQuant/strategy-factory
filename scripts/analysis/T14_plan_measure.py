"""T14 plan: measure stage 3's fine grids and the two T14 §10 questions on the real candidates.

Local only; reads the T13 ``summary.json`` files and the development bars through ``DataAccess``
with an in-memory split ledger (the T13 pattern; no registry or store write)::

    uv run python scripts/analysis/T14_plan_measure.py run   # the cells
    uv run python scripts/analysis/T14_plan_analyse.py       # the variants, CSVs for the plan

``run``: for every method selected by the T13 runs (25 on 1D, 6 on 1H), the fine grid of D-639 /
D-640 -- the good region's range per numeric parameter plus one coarse step of margin on each side
(the neighbouring coarse value; beyond the last one, the last coarse interval), clipped to the
parameter's range, at ``fine_step``; choice parameters fixed at the median cell's values. A grid
above 2000 cells is run on a **coarsened lattice** (the widest axis's step multiplied until the
grid fits), because smoothing needs neighbours and a Sobol sample has none (plan §4). Every cell
runs on the whole development window and on each half (equal bar counts, D-641), zero cost and
full cost, on the real bars and on the reshuffled-returns control (D-615 seeds, D-644). A half is
simulated on its own bars; its signals and ATR are computed on the bars **up to the half's end**,
so half 2 is warmed up by half 1's history and half 1 never reads half 2. Output:
``<artifacts>/_analysis/T14_plan/cells.parquet``.

Also writes ``docs/reviews/T14_plan_grids.csv`` (each candidate's fine grid and its size).
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from strategy_factory.baseline.random_entries import frictionless_costs, frictionless_sizing
from strategy_factory.components.base import Bars
from strategy_factory.components.exits.probe import probe_exit_signals
from strategy_factory.components.registry import default_registry
from strategy_factory.core.config import EngineConfig, canonical_json, load_pipeline_config
from strategy_factory.core.errors import HoldoutAccessError
from strategy_factory.core.universe import load_universe
from strategy_factory.costs.arrays import CostArrays
from strategy_factory.costs.profile import load_assignments, load_profiles
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import DataAccess, SplitManager
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import ExitParams, MarketArrays, simulate
from strategy_factory.metrics.containers import RunMeta
from strategy_factory.metrics.standard import core_metrics
from strategy_factory.pipeline.backtest import (
    cost_inputs,
    market_arrays,
    sizing_inputs,
    to_run_result,
)
from strategy_factory.pipeline.executor import unit_seed
from strategy_factory.pipeline.stage_run import artifacts_root
from strategy_factory.stages.config import EdgeTypeSpec
from strategy_factory.stages.control import permute_returns
from strategy_factory.stages.edge import _cost_arrays
from strategy_factory.stages.screen_config import load_s02_config

RUNS = {"1D": "dea1d423-6621-43f9-8057-227e6e576ee0", "1H": "6025ef15-35cb-4acd-a4c8-5f936329d78f"}
CAP = 2000  # D-120 / D-639
SEED = 42  # the T12 / T13 runs' seed (configs/pipeline/s02_screen_*.yaml)
COLS = ("ts", "open", "high", "low", "close")
OUT = "_analysis/T14_plan"
SIGN = {"long": 1, "short": -1}


class MemoryLedger:
    def __init__(self) -> None:
        self.splits: dict[Any, dict[str, Any]] = {}

    def register_snapshot(self, meta: Any, is_reference: bool) -> None:
        pass

    def get_split(self, key: Any) -> dict[str, Any] | None:
        return self.splits.get(key)

    def add_split(self, split: Any) -> None:
        self.splits[split.key] = {**split.boundaries(), "expected_holdout_trades": None}

    def record_holdout_access(self, candidate_id: str, result: dict[str, Any]) -> None:
        raise HoldoutAccessError("never")


# ------------------------------------------------------------------ the fine grid (D-639 / D-640)
def _on_step(spec: Any, lo: float, hi: float, step: float) -> list[float | int]:
    base = float(spec.min)
    i0 = math.ceil((lo - base) / step - 1e-9)
    i1 = math.floor((hi - base) / step + 1e-9)
    vals = [round(base + i * step, 10) for i in range(i0, i1 + 1)]
    return [int(v) for v in vals] if spec.kind == "int" else vals


def fine_axis(spec: Any, good_vals: list[float], mult: int = 1) -> list[float | int]:
    coarse = [float(v) for v in spec.coarse_values]
    lo_g, hi_g = min(good_vals), max(good_vals)
    i_lo, i_hi = coarse.index(lo_g), coarse.index(hi_g)
    lo = coarse[i_lo - 1] if i_lo > 0 else lo_g - (coarse[1] - coarse[0])
    hi = coarse[i_hi + 1] if i_hi < len(coarse) - 1 else hi_g + (coarse[-1] - coarse[-2])
    lo, hi = max(lo, float(spec.min)), min(hi, float(spec.max))
    return _on_step(spec, lo, hi, float(spec.fine_step) * mult)


@dataclass(frozen=True)
class Grid:
    axes: dict[str, list[float | int]]  # numeric axes, in declaration order
    fixed: dict[str, str]  # choice parameters (D-640)
    size_full: int  # before any coarsening
    size_all_good: int  # reading B: bounds from every good cell, whatever its choice values
    mult: dict[str, int]  # the step multiplier per axis (1 unless above the cap)


def fine_grid(art: dict[str, Any]) -> Grid:
    comp = default_registry().get(art["identity"]["method"])
    median = art["baseline"]["cell"]
    choices = {p.name: median[p.name] for p in comp.params if p.kind == "choice"}
    good = [c["params"] for c in art["grid"] if c["good_region"]]
    same = [g for g in good if all(g[n] == v for n, v in choices.items())]
    numeric = [p for p in comp.params if p.kind != "choice"]
    axes = {p.name: fine_axis(p, [float(g[p.name]) for g in same]) for p in numeric}
    axes_b = {p.name: fine_axis(p, [float(g[p.name]) for g in good]) for p in numeric}
    size = math.prod(len(v) for v in axes.values())
    size_b = math.prod(len(v) for v in axes_b.values())
    mult = {p.name: 1 for p in numeric}
    while math.prod(len(v) for v in axes.values()) > CAP:
        widest = max(axes, key=lambda n: len(axes[n]))
        mult[widest] += 1
        spec = next(p for p in numeric if p.name == widest)
        axes[widest] = fine_axis(spec, [float(g[widest]) for g in same], mult[widest])
    return Grid(axes=axes, fixed=choices, size_full=size, size_all_good=size_b, mult=mult)


def cells_of(grid: Grid) -> list[dict[str, Any]]:
    names = list(grid.axes)
    return [
        {**dict(zip(names, vals, strict=True)), **grid.fixed}
        for vals in itertools.product(*(grid.axes[n] for n in names))
    ]


# ------------------------------------------------------------------ one candidate's cells
@dataclass(frozen=True)
class Job:
    key: str  # candidate id + control
    art: dict[str, Any]
    control: str
    bars: dict[str, np.ndarray]
    costs: dict[str, CostArrays]  # per segment: "whole", "h1", "h2"
    engine: EngineConfig
    exits: EdgeTypeSpec


def _segments(n: int) -> dict[str, tuple[int, int]]:
    mid = n // 2
    return {"whole": (0, n), "h1": (0, mid), "h2": (mid, n)}


def _sim(
    job: Job,
    params: dict[str, Any],
    seg: str,
    s: int,
    e: int,
    costs: CostArrays | None,
    sig: tuple[np.ndarray, np.ndarray],
    market: MarketArrays,
) -> tuple[int, float, float]:
    ident = job.art["identity"]
    entry, exit_ = sig
    mk = MarketArrays(
        *(
            np.ascontiguousarray(getattr(market, f)[s:e])
            for f in ("open", "high", "low", "close", "atr")
        )
    )
    ex = ExitParams(
        time_exit_bars=job.exits.time_exit_bars, disaster_atr=job.engine.disaster_stop_atr
    )
    n = e - s
    if costs is None:
        cost_in, sizing = (
            frictionless_costs(n),
            frictionless_sizing(job.engine.notional, job.engine.initial_capital),
        )
    else:
        cost_in, sizing = cost_inputs(costs), sizing_inputs(costs, job.engine, "pessimistic", None)
    sim = simulate(
        mk,
        np.ascontiguousarray(entry[s:e]),
        np.ascontiguousarray(exit_[s:e]),
        SIGN[ident["direction"]],
        ex,
        cost_in,
        sizing,
        k.MODE_PESSIMISTIC,
    )
    meta = RunMeta(
        symbol=ident["symbol"],
        timeframe=ident["timeframe"],
        spec_hash="x",
        cost_status="verified",
        intrabar_mode="pessimistic",
    )
    rr = to_run_result(sim, job.bars["ts"][s:e], SIGN[ident["direction"]], meta, job.engine)
    cm = core_metrics(rr.equity)
    return int(sim.entry_idx.shape[0]), float(cm.profit_dd_ratio), float(cm.avg_annual_profit_pct)


def run_job(job: Job) -> list[dict[str, Any]]:
    ident = job.art["identity"]
    method, direction = ident["method"], ident["direction"]
    comp = default_registry().get(method)
    grid = fine_grid(job.art)
    n = int(job.bars["close"].shape[0])
    segs = _segments(n)
    rows: list[dict[str, Any]] = []
    for params in cells_of(grid):
        cache: dict[int, tuple[tuple[np.ndarray, np.ndarray], MarketArrays]] = {}
        for seg, (s, e) in segs.items():
            if e not in cache:
                pre = {c: job.bars[c][:e] for c in COLS}
                b = Bars(
                    *(
                        np.asarray(pre[c], dtype=np.float64)
                        for c in ("open", "high", "low", "close")
                    )
                )
                le, se = comp.signals(b, params)
                lx, sx = probe_exit_signals(job.exits.exit_signal, comp, b, params)
                sig = (le, lx) if direction == "long" else (se, sx)
                cache[e] = (sig, market_arrays(pre, job.engine.atr_length))
            sig, market = cache[e]
            for leg, costs in (("zero", None), ("cost", job.costs[seg])):
                nt, tgt, prof = _sim(job, params, seg, s, e, costs, sig, market)
                rows.append(
                    {
                        "key": job.key,
                        "control": job.control,
                        "timeframe": ident["timeframe"],
                        "symbol": ident["symbol"],
                        "direction": direction,
                        "method": method,
                        "candidate_id": ident["candidate_id"],
                        "params": canonical_json(params),
                        "segment": seg,
                        "leg": leg,
                        "n_trades": nt,
                        "target": tgt,
                        "profit_pct": prof,
                    }
                )
    return rows


def _selected() -> list[dict[str, Any]]:
    import csv

    root = artifacts_root()
    out = []
    for run in RUNS.values():
        d = root / run / "s02_screen"
        with (d / "index.csv").open(encoding="utf-8", newline="") as fh:
            ids = [r["candidate_id"] for r in csv.DictReader(fh) if r["selected"] == "True"]
        out += [json.loads((d / c / "summary.json").read_text(encoding="utf-8")) for c in ids]
    return out


def cmd_run() -> None:
    arts = _selected()
    cfg2 = load_s02_config()
    engines = {
        tf: load_pipeline_config(Path(f"configs/pipeline/s02_screen_{tf.lower()}.yaml")).engine
        for tf in RUNS
    }
    universe = load_universe(Path("configs/universe.yaml")).by_symbol()
    costs_dir = Path("configs") / "costs"
    profiles, assignments = load_profiles(costs_dir), load_assignments(costs_dir)
    access = DataAccess(SplitManager(MemoryLedger(), load_split_config()))
    jobs: list[Job] = []
    grids = []
    for a in arts:
        ident = a["identity"]
        sym, tf = ident["symbol"], ident["timeframe"]
        g = fine_grid(a)
        grids.append(
            {
                "timeframe": tf,
                "symbol": sym,
                "direction": ident["direction"],
                "method": ident["method"],
                "candidate_id": ident["candidate_id"],
                "numeric_params": len(g.axes),
                "fixed": json.dumps(g.fixed),
                "axes": json.dumps({n: [v[0], v[-1], len(v)] for n, v in g.axes.items()}),
                "size_d639": g.size_full,
                "size_run": math.prod(len(v) for v in g.axes.values()),
                "size_all_good_cells": g.size_all_good,
                "step_mult": json.dumps(g.mult),
            }
        )
        raw = access.arrays(sym, tf)
        raw = {c: raw[c] for c in COLS}
        for control in ("none", "random_walk"):
            bars = (
                raw
                if control == "none"
                else permute_returns(raw, unit_seed(SEED, f"{sym}|{tf}|random_walk"))
            )
            n = int(bars["close"].shape[0])
            costs = {}
            for seg, (s, e) in _segments(n).items():
                sl = {c: bars[c][s:e] for c in COLS}
                costs[seg] = _cost_arrays(
                    sym, universe[sym].asset_class, tf, sl, costs_dir, profiles, assignments
                )
            jobs.append(
                Job(
                    key=f"{ident['candidate_id']}|{control}",
                    art=a,
                    control=control,
                    bars=bars,
                    costs=costs,
                    engine=engines[tf],
                    exits=cfg2.exits[ident["edge_type"]],
                )
            )
    out = artifacts_root() / OUT
    out.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(grids).write_csv(Path("docs/reviews/T14_plan_grids.csv"))
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=8) as ex:  # not all cores: stream B may be running
        for i, r in enumerate(ex.map(run_job, jobs), 1):
            rows += r
            print(
                f"{i}/{len(jobs)} {r[0]['symbol']} {r[0]['method']} {r[0]['control']} "
                f"{len(r) // 6} cells",
                flush=True,
            )
    pl.DataFrame(rows).write_parquet(out / "cells.parquet")
    print("written", out / "cells.parquet", len(rows))


if __name__ == "__main__":
    if sys.argv[1:] != ["run"]:
        sys.exit("usage: T14_plan_measure.py run   (the analysis is T14_plan_analyse.py)")
    cmd_run()
