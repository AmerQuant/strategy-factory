"""T15a plan, measurement M3: a planted edge of known strength, and where stage 1 starts to see it.

The planted edge is added to the calibrated null (``t_vp`` of M1) and is **timing, never drift**:

* ``MR`` (long): events at seeded random bars, ``--events-per-year`` on average. At an event bar
  the close is pushed down by ``s`` x ATR (the null's own ATR(14) at the previous bar, as a
  fraction of price); over the next ``k`` bars it reverts in equal steps. Net zero, so the
  drift is unchanged.
* ``TF`` (long): segments of ``L`` bars starting at seeded random bars (``--segments-per-year``);
  inside a segment each bar's return gains ``d`` x the bar's volatility. The whole series is then
  re-centred so its mean return equals the null's (the edge is when, not how much).

Short edges are the mirror (not measured here; the stages mirror every rule, D-626). For each
strength the script reports (a) the planted effect in its own statistic -- the mean forward
return after the planted events in ATR units against every other bar, or the TF segments' mean
return against the rest -- and (b) stage 1 on the planted series (a dry run, as M2): the planted
type's profile percentiles, ESS, and pass rate, plus the other types' pass rate (a planted MR
edge must not make TF pass).

    uv run python scripts/analysis/T15a_planted.py --out <dir> --timeframe 1D --n 30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from T15a_null_fit import fit, generate, slots, vol_path, wick_scales
from T15a_null_stage1 import HALF_LIFE_1D, T12, probe_rows, run_dir

from strategy_factory.core.config import PipelineConfig, resolve_config
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import DataAccess, RegistryLedger, SplitManager
from strategy_factory.data.store import SnapshotStore
from strategy_factory.gates.engine import GateEngine
from strategy_factory.pipeline.executor import (
    ExecutorConfig,
    make_executor,
    unit_seed,
)
from strategy_factory.registry.engine import make_engine
from strategy_factory.stages.base import RunContext
from strategy_factory.stages.edge import EdgeStage
from strategy_factory.stages.reference import ReferenceInfo

BARS_PER_YEAR = {"1D": 252.0, "1H": 252.0 * 7}
ATR_N = 14


def atr_frac_series(b: dict[str, np.ndarray]) -> np.ndarray:
    """ATR(14)/close known at each bar's previous close (NaN during the warm-up)."""
    h, lo, c = b["high"], b["low"], b["close"]
    tr = np.empty(c.size)
    tr[0] = h[0] - lo[0]
    tr[1:] = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    atr = np.full(c.size, np.nan)
    atr[ATR_N - 1 :] = np.convolve(tr, np.ones(ATR_N) / ATR_N, mode="valid")
    frac = atr / c
    return np.concatenate(([np.nan], frac[:-1]))


def _rebuild(null: dict[str, np.ndarray], add: np.ndarray) -> dict[str, np.ndarray]:
    """Add ``add`` (log) to each bar's body; shift the rest of the path, keep bar shapes."""
    cum = np.cumsum(add)
    out = dict(null)
    lo = np.log(null["open"]) + (cum - add)
    lc = np.log(null["close"]) + cum
    top_w = np.log(null["high"]) - np.maximum(np.log(null["open"]), np.log(null["close"]))
    bot_w = np.minimum(np.log(null["open"]), np.log(null["close"])) - np.log(null["low"])
    out["open"], out["close"] = np.exp(lo), np.exp(lc)
    out["high"] = np.exp(np.maximum(lo, lc) + top_w)
    out["low"] = np.exp(np.minimum(lo, lc) - bot_w)
    return out


def plant(
    null: dict[str, np.ndarray], kind: str, strength: float, seed: int, tf: str, args: Any
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    rng = np.random.default_rng(seed)
    n = null["close"].size
    add = np.zeros(n)
    marks = np.zeros(n, dtype=np.int8)
    if kind == "MR":
        a = atr_frac_series(null)
        p = args.events_per_year / BARS_PER_YEAR[tf]
        k = args.k
        t = ATR_N + 1
        while t < n - k - 1:
            if rng.random() < p and np.isfinite(a[t]):
                drop = strength * a[t]
                add[t] -= drop
                add[t + 1 : t + 1 + k] += drop / k
                marks[t] = 1
                t += k + 1
            else:
                t += 1
    else:  # TF
        r = np.diff(np.log(null["close"]), prepend=np.log(null["close"][0]))
        vol = np.full(n, np.std(r[1:]))
        p = args.segments_per_year / BARS_PER_YEAR[tf]
        seg = args.seg_len * (7 if tf == "1H" else 1)
        t = 1
        while t < n - seg:
            if rng.random() < p:
                add[t : t + seg] += strength * vol[t : t + seg]
                marks[t : t + seg] = 1
                t += seg
            else:
                t += 1
        add[1:] -= add[1:].mean()  # re-centre: the edge is timing, not drift
    return _rebuild(null, add), marks


def own_statistic(b: dict[str, np.ndarray], marks: np.ndarray, kind: str, k: int) -> float:
    """MR: mean k-bar forward log return after an event bar's close, in ATR units, minus the
    same after every other bar. TF: mean return inside the segments minus outside, per bar,
    in units of the bar volatility."""
    lc = np.log(b["close"])
    if kind == "MR":
        a = atr_frac_series(b)
        fwd = np.full(lc.size, np.nan)
        fwd[:-k] = (lc[k:] - lc[:-k]) / np.where(a[:-k] > 0, a[:-k], np.nan)
        ok = np.isfinite(fwd)
        ev = ok & (marks == 1)
        return (
            float(np.nanmean(fwd[ev]) - np.nanmean(fwd[ok & (marks == 0)]))
            if ev.any()
            else float("nan")
        )
    r = np.diff(lc, prepend=lc[0])
    sd = np.std(r[1:])
    inside = marks == 1
    return float((r[inside].mean() - r[~inside].mean()) / sd) if inside.any() else float("nan")


class PlantedDataAccess(DataAccess):
    def __init__(
        self, splits: SplitManager, kind: str, strength: float, seed: int, args: Any
    ) -> None:
        super().__init__(splits)
        self.kind, self.strength, self.seed, self.args = kind, strength, seed, args
        self.own: dict[str, float] = {}
        self.own_null: dict[str, float] = {}

    def arrays(self, symbol: str, timeframe: str) -> dict[str, np.ndarray[Any, Any]]:
        real = super().arrays(symbol, timeframe)
        slot = slots(real["ts"], timeframe)
        params = fit(real, slot)
        vp = vol_path(real, slot, HALF_LIFE_1D * (7 if timeframe == "1H" else 1))
        ws = wick_scales(real, slot, params, "t_vp", vp)
        null = generate(
            real,
            slot,
            params,
            unit_seed(self.seed, f"{symbol}|{timeframe}|null|t_vp"),
            "t_vp",
            ws,
            vp,
        )
        planted, marks = plant(null, self.kind, self.strength,
                               unit_seed(self.seed, f"{symbol}|{timeframe}|plant"), timeframe, self.args)  # fmt: skip
        self.own[symbol] = own_statistic(planted, marks, self.kind, self.args.k)
        self.own_null[symbol] = own_statistic(null, marks, self.kind, self.args.k)
        return planted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeframe", choices=["1D", "1H"], required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--kinds", default="MR,TF")
    ap.add_argument("--mr-ladder", default="0.25,0.5,1,1.5,2,3")
    ap.add_argument("--tf-ladder", default="0.05,0.1,0.15,0.2,0.3,0.5")
    ap.add_argument("--events-per-year", type=float, default=12.0)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--segments-per-year", type=float, default=1.0)
    ap.add_argument("--seg-len", type=int, default=60, help="1D bars (1H: x7)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    tf = args.timeframe
    out = args.out / tf
    out.mkdir(parents=True, exist_ok=True)
    index = pl.read_csv(run_dir(T12[(tf, "real")]) / "index.csv")
    profiled = sorted(set(index.filter(pl.col("status") == "profiled")["symbol"].to_list()))
    rng = np.random.default_rng(args.seed)
    sample = sorted(rng.choice(profiled, size=min(args.n, len(profiled)), replace=False).tolist())
    store = SnapshotStore()
    catalog = Catalog(store.root)
    cfg = resolve_config(
        PipelineConfig(symbols=tuple(sample), timeframes=(tf,), stages=("s01_edge",), seed=42),
        catalog_root=store.root,
    )
    splits = SplitManager(RegistryLedger(make_engine()), load_split_config(), store, catalog)
    rows: list[dict[str, Any]] = []
    own_rows: list[dict[str, Any]] = []
    for kind in args.kinds.split(","):
        ladder = [float(x) for x in (args.mr_ladder if kind == "MR" else args.tf_ladder).split(",")]
        for s in ladder:
            root = out / f"{kind}_{s}"
            data = PlantedDataAccess(splits, kind, s, cfg.seed, args)
            ctx = RunContext(
                config=cfg,
                data=data,
                references=ReferenceInfo(catalog),
                executor=make_executor(ExecutorConfig(workers=args.workers, numba_threads=1)),
                gates=GateEngine.from_file(cfg.gates),
                artifacts_root=root,
                code_version="T15a-plan-M3",
            )
            t0 = time.perf_counter()
            EdgeStage().run([(x, tf) for x in sample], ctx)
            for r in probe_rows(root / "dry-run" / "s01_edge", set(sample), f"{kind}_{s}"):
                rows.append({**r, "planted": kind, "strength": s})
            for sym in sample:
                own_rows.append({"planted": kind, "strength": s, "symbol": sym,
                                 "own": data.own.get(sym), "own_null": data.own_null.get(sym)})  # fmt: skip
            print(kind, s, f"{time.perf_counter() - t0:.0f} s", flush=True)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_csv(out / "probes.csv")
    own = pl.DataFrame(own_rows, infer_schema_length=None)
    own.write_csv(out / "own_statistic.csv")
    prof = df.unique(["planted", "strength", "symbol", "edge_type", "direction"])
    power = (
        prof.group_by("planted", "strength", "edge_type", "direction")
        .agg(
            pl.col("passed").cast(pl.Int64).mean().alias("pass_rate"),
            pl.col("ess").median().alias("ess_median"),
        )
        .sort("planted", "strength", "edge_type", "direction")
    )
    pct = (
        df.filter(pl.col("percentile").is_not_null())
        .group_by("planted", "strength", "edge_type", "direction")
        .agg(
            pl.col("percentile").mean().alias("pct_mean"),
            (pl.col("percentile") >= 90).mean().alias("ge90"),
        )
    )
    power = power.join(pct, on=["planted", "strength", "edge_type", "direction"])
    own_s = (
        own.group_by("planted", "strength")
        .agg(
            pl.col("own").mean().alias("own_mean"), pl.col("own_null").mean().alias("own_null_mean")
        )
        .sort("planted", "strength")
    )
    power.write_csv(out / "power.csv")
    own_s.write_csv(out / "own_summary.csv")
    (out / "sample.json").write_text(json.dumps(sample), encoding="utf-8")
    with pl.Config(tbl_rows=200, float_precision=3):
        print(own_s)
        print(power)


if __name__ == "__main__":
    main()
