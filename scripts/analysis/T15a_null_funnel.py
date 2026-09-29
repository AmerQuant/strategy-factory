"""T15a plan, measurement M4: the calibrated null through stages 1 -> 2 -> 3, today's thresholds.

D-656's number before anything is built: the share of symbols whose null series reaches the end
of stage 3. The three real stages run as **dry runs** (no registry rows; artifacts under
``--out``, each stage reading the previous one's ``dry-run`` folder through ``stage_inputs``),
on the full T12 scope of a timeframe (the symbols T12 profiled), with each symbol's bars replaced
by the null of M1/M2 (``NullDataAccess``). The configs are the shipped ones: the gates, the
stage configs and the engine are not touched.

    uv run python scripts/analysis/T15a_null_funnel.py --out <dir> --timeframe 1D --variant t_vp
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from T15a_null_stage1 import T12, NullDataAccess, run_dir  # noqa: E402

from strategy_factory.core.config import PipelineConfig, resolve_config  # noqa: E402
from strategy_factory.data.catalog import Catalog  # noqa: E402
from strategy_factory.data.config import load_split_config  # noqa: E402
from strategy_factory.data.split import RegistryLedger, SplitManager  # noqa: E402
from strategy_factory.data.store import SnapshotStore  # noqa: E402
from strategy_factory.gates.engine import GateEngine  # noqa: E402
from strategy_factory.pipeline.executor import ExecutorConfig, make_executor  # noqa: E402
from strategy_factory.registry.engine import make_engine  # noqa: E402
from strategy_factory.stages.base import RunContext  # noqa: E402
from strategy_factory.stages.edge import EdgeStage  # noqa: E402
from strategy_factory.stages.optimize import EntryStage, stage2_selection_symbols  # noqa: E402
from strategy_factory.stages.reference import ReferenceInfo  # noqa: E402
from strategy_factory.stages.screen import ScreenStage, stage1_pass_symbols  # noqa: E402

DRY = "dry-run"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeframe", choices=["1D", "1H"], required=True)
    ap.add_argument("--variant", default="t_vp")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="first N symbols only (smoke test)")
    ap.add_argument("--symbols", default="", help="comma-separated subset (smoke test)")
    args = ap.parse_args()
    tf = args.timeframe
    root = args.out / f"{tf}_{args.variant}"
    root.mkdir(parents=True, exist_ok=True)
    index = pl.read_csv(run_dir(T12[(tf, "real")]) / "index.csv")
    scope = sorted(set(index.filter(pl.col("status") == "profiled")["symbol"].to_list()))
    if args.symbols:
        scope = sorted(set(args.symbols.split(",")) & set(scope))
    if args.limit:
        scope = scope[: args.limit]
    store = SnapshotStore()
    catalog = Catalog(store.root)
    splits = SplitManager(RegistryLedger(make_engine()), load_split_config(), store, catalog)
    executor = make_executor(ExecutorConfig(workers=args.workers, numba_threads=1))
    report: dict[str, Any] = {"timeframe": tf, "variant": args.variant, "symbols": len(scope)}

    def ctx_for(cfg: PipelineConfig) -> RunContext:
        return RunContext(
            config=resolve_config(cfg, catalog_root=store.root),
            data=NullDataAccess(splits, args.variant, 42),
            references=ReferenceInfo(catalog),
            executor=executor,
            gates=GateEngine.from_file(cfg.gates),
            artifacts_root=root,
            code_version="T15a-plan-M4",
        )

    t0 = time.perf_counter()
    cfg1 = PipelineConfig(symbols=tuple(scope), timeframes=(tf,), stages=("s01_edge",), seed=42)
    r1 = EdgeStage().run([(s, tf) for s in scope], ctx_for(cfg1))
    report["s01_seconds"] = time.perf_counter() - t0
    report["s01_passed_profiles"] = len(r1.passed)
    s2_symbols = stage1_pass_symbols(root, DRY, (tf,))
    report["s01_passed_symbols"] = len(s2_symbols)
    print(json.dumps(report), flush=True)
    if s2_symbols:
        t0 = time.perf_counter()
        cfg2 = PipelineConfig(
            symbols=s2_symbols, timeframes=(tf,), stages=("s02_screen",), seed=42,
            stage_inputs={"s01_edge": DRY},
        )  # fmt: skip
        r2 = ScreenStage().run([(s, tf) for s in s2_symbols], ctx_for(cfg2))
        report["s02_seconds"] = time.perf_counter() - t0
        report["s02_selected"] = len(r2.passed)
        s3_symbols = stage2_selection_symbols(root, DRY, (tf,))
        report["s02_selected_symbols"] = len(s3_symbols)
        print(json.dumps(report), flush=True)
        if s3_symbols:
            t0 = time.perf_counter()
            cfg3 = PipelineConfig(
                symbols=s3_symbols, timeframes=(tf,), stages=("s03_entry",), seed=42,
                stage_inputs={"s02_screen": DRY},
            )  # fmt: skip
            r3 = EntryStage().run([(s, tf) for s in s3_symbols], ctx_for(cfg3))
            report["s03_seconds"] = time.perf_counter() - t0
            report["s03_passed"] = len(r3.passed)
            idx3 = pl.read_csv(root / DRY / "s03_entry" / "index.csv", infer_schema=False)
            passed3 = idx3.filter(pl.col("gate_passed") == "True")
            report["s03_passed_symbols"] = passed3["symbol"].n_unique()
            report["s03_passed_rows"] = passed3.select(
                [c for c in ("symbol", "edge_type", "direction", "method") if c in passed3.columns]
            ).to_dicts()
    report["end_of_stage3_symbol_share"] = report.get("s03_passed_symbols", 0) / len(scope)
    (root / "funnel.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
