"""T15a plan, measurement M2: is the calibrated null calibrated for stage 1?

Runs the real stage 1 (``EdgeStage``, a dry run: no registry rows, artifacts under ``--out``) on
a seeded sample of symbols whose bars are replaced by a null variant of M1
(``scripts/analysis/T15a_null_fit.py``), and compares, for the same symbols, with T12's full
runs on the real data and on the D-615 control (read from their artifacts, not re-run):

* the probe percentiles (a calibrated null gives a mean near 50 and about 10 % at or above 90,
  the probe gate's threshold -- T12 review section 2);
* ESS and the profile passes.

Only development bars are read (``DataAccess``); the null is generated in memory in the parent
process (as the stages will, D-654) and nothing is written outside ``--out``.

    uv run python scripts/analysis/T15a_null_stage1.py --out <dir> --timeframe 1D --n 80
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
from T15a_null_fit import fit, generate, slots, vol_path, wick_scales  # noqa: E402

from strategy_factory.core.config import PipelineConfig, resolve_config  # noqa: E402
from strategy_factory.data.catalog import Catalog  # noqa: E402
from strategy_factory.data.config import load_split_config  # noqa: E402
from strategy_factory.data.split import DataAccess, RegistryLedger, SplitManager  # noqa: E402
from strategy_factory.data.store import SnapshotStore  # noqa: E402
from strategy_factory.gates.engine import GateEngine  # noqa: E402
from strategy_factory.pipeline.executor import ExecutorConfig, make_executor, unit_seed  # noqa: E402
from strategy_factory.registry.engine import make_engine  # noqa: E402
from strategy_factory.stages.base import RunContext  # noqa: E402
from strategy_factory.stages.edge import EdgeStage  # noqa: E402
from strategy_factory.stages.reference import ReferenceInfo  # noqa: E402

ARTIFACTS = Path("D:/SfacData/artifacts")
T12 = {  # T12 review section 1
    ("1D", "real"): "db666562-0e9b-446d-8531-25437c64c6e2",
    ("1D", "control"): "279018ed-1a3c-44e1-94d5-de9d64ce63dc",
    ("1H", "real"): "6f603a07",
    ("1H", "control"): "9c4fcde5",
}
HALF_LIFE_1D = 20.0


class NullDataAccess(DataAccess):
    """``DataAccess`` whose bars are a null variant of the real development bars."""

    def __init__(self, splits: SplitManager, kind: str, seed: int) -> None:
        super().__init__(splits)
        self.kind = kind
        self.seed = seed

    def arrays(self, symbol: str, timeframe: str) -> dict[str, np.ndarray[Any, Any]]:
        real = super().arrays(symbol, timeframe)
        slot = slots(real["ts"], timeframe)
        params = fit(real, slot)
        vp = vol_path(real, slot, HALF_LIFE_1D * (7 if timeframe == "1H" else 1))
        ws = wick_scales(real, slot, params, self.kind, vp)
        seed = unit_seed(self.seed, f"{symbol}|{timeframe}|null|{self.kind}")
        return generate(real, slot, params, seed, self.kind, ws, vp)


def run_dir(prefix: str) -> Path:
    hits = [p for p in ARTIFACTS.iterdir() if p.name.startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit(f"run {prefix}: {len(hits)} artifact folders")
    return hits[0] / "s01_edge"


def probe_rows(folder: Path, symbols: set[str], label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for summary in folder.glob("*/summary.json"):
        s = json.loads(summary.read_text(encoding="utf-8"))
        ident = s["identity"]
        if ident["symbol"] not in symbols:
            continue
        prof = s["profile"]
        ess = prof.get("ess") or {}
        for p in s["probes"]:
            rows.append({
                "variant": label, "symbol": ident["symbol"], "edge_type": ident["edge_type"],
                "direction": ident["direction"], "probe": p["name"], "percentile": p["percentile"],
                "ess": ess.get("total"), "magnitude_pts": (ess.get("points") or {}).get("magnitude"),
                "passed": prof.get("passed"),
            })  # fmt: skip
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeframe", choices=["1D", "1H"], required=True)
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--variants", default="t,t_vp")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    tf = args.timeframe
    out = args.out / tf
    out.mkdir(parents=True, exist_ok=True)
    index = pl.read_csv(run_dir(T12[(tf, "real")]).parent / "s01_edge" / "index.csv")
    profiled = sorted(set(index.filter(pl.col("status") == "profiled")["symbol"].to_list()))
    rng = np.random.default_rng(args.seed)
    sample = sorted(rng.choice(profiled, size=min(args.n, len(profiled)), replace=False).tolist())
    (out / "sample.json").write_text(json.dumps(sample), encoding="utf-8")

    store = SnapshotStore()
    catalog = Catalog(store.root)
    cfg = PipelineConfig(symbols=tuple(sample), timeframes=(tf,), stages=("s01_edge",), seed=42)
    cfg = resolve_config(cfg, catalog_root=store.root)
    splits = SplitManager(RegistryLedger(make_engine()), load_split_config(), store, catalog)
    rows: list[dict[str, Any]] = []
    timing: dict[str, float] = {}
    for kind in args.variants.split(","):
        root = out / kind
        ctx = RunContext(
            config=cfg,
            data=NullDataAccess(splits, kind, cfg.seed),
            references=ReferenceInfo(catalog),
            executor=make_executor(ExecutorConfig(workers=args.workers, numba_threads=1)),
            gates=GateEngine.from_file(cfg.gates),
            artifacts_root=root,
            code_version="T15a-plan-M2",
        )
        t0 = time.perf_counter()
        EdgeStage().run([(s, tf) for s in sample], ctx)
        timing[kind] = time.perf_counter() - t0
        rows += probe_rows(root / "dry-run" / "s01_edge", set(sample), kind)
        print(kind, f"{timing[kind]:.0f} s", flush=True)
    for label in ("real", "control"):
        rows += probe_rows(run_dir(T12[(tf, label)]), set(sample), label)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_csv(out / "probes.csv")
    (out / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
    pct = df.filter(pl.col("percentile").is_not_null())
    summary = (
        pct.group_by("variant", "edge_type", "direction")
        .agg(
            pl.col("percentile").mean().alias("pct_mean"),
            (pl.col("percentile") >= 90).mean().alias("share_ge_90"),
            pl.len().alias("probes"),
        )
        .sort("edge_type", "direction", "variant")
    )
    profiles = (
        df.unique(["variant", "symbol", "edge_type", "direction"])
        .group_by("variant")
        .agg(
            pl.len().alias("profiles"),
            (pl.col("ess") >= 50).sum().alias("ess_ge_50"),
            pl.col("passed").cast(pl.Int64).sum().alias("passed"),
            pl.col("ess").median().alias("ess_median"),
            pl.col("magnitude_pts").mean().alias("magnitude_pts_mean"),
        )
        .sort("variant")
    )
    pooled = pct.group_by("variant").agg(
        pl.col("percentile").mean().alias("pct_mean"),
        (pl.col("percentile") >= 90).mean().alias("share_ge_90"),
    ).sort("variant")
    summary.write_csv(out / "summary_by_type.csv")
    profiles.write_csv(out / "summary_profiles.csv")
    pooled.write_csv(out / "summary_pooled.csv")
    with pl.Config(tbl_rows=100, float_precision=3):
        print(pooled)
        print(summary)
        print(profiles)


if __name__ == "__main__":
    main()
