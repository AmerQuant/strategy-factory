"""T15a planted pilot (RUNBOOK_T15a step 8, D-665): power per planted cell at each stage.

Reads a funnel run's ``funnel.json`` and ``truth.json`` and the index of each of its stage runs,
and reports per cell (type, direction, strength): the share of its symbols whose planted profile
(TF: long or short, the plant is two-sided) passes stage 1, has a stage-2 selection, and passes
stage 3; the passes of the other profiles on the same symbols (a planted edge must not show up as
another type); the control arms' passes; and the planted effect in its own statistic.

    uv run python scripts/analysis/T15a_planted_pilot.py --funnel <id> [--csv out.csv]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.core.config import SourceRef
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import RegistryLedger, SplitManager
from strategy_factory.data.store import SnapshotStore
from strategy_factory.pipeline.funnel_run import funnel_folder
from strategy_factory.pipeline.stage_run import artifacts_root
from strategy_factory.registry.engine import make_engine
from strategy_factory.registry.funnel import FunnelRegistry
from strategy_factory.synthetic.access import SyntheticDataAccess
from strategy_factory.synthetic.config import PlantedConfig
from strategy_factory.synthetic.planted import own_statistic

STAGES = ("s01_edge", "s02_screen", "s03_entry")
PASS_COL = {"s01_edge": "passed", "s02_screen": "selected", "s03_entry": "gate_passed"}


def index(root: Path, run_id: str | None, stage: str) -> pl.DataFrame:
    if run_id is None:
        return pl.DataFrame()
    path = root / run_id / stage / "index.csv"
    return pl.read_csv(path, infer_schema=False) if path.is_file() else pl.DataFrame()


def passing(df: pl.DataFrame, stage: str) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame({"symbol": [], "edge_type": [], "direction": []}, schema={
            "symbol": pl.Utf8, "edge_type": pl.Utf8, "direction": pl.Utf8})  # fmt: skip
    return df.filter(pl.col(PASS_COL[stage]) == "True").select("symbol", "edge_type", "direction")


def matches(cell: str, edge_type: str, direction: str) -> bool:
    kind, d, _ = cell.split("|")
    return edge_type == kind and (d == "both" or d == direction)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--funnel", required=True)
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args()
    root = artifacts_root()
    folder = funnel_folder(root, args.funnel)
    summary = json.loads((folder / "funnel.json").read_text(encoding="utf-8"))
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    runs = {(s["timeframe"], s["stage"], s["arm"]): s["run_id"] for s in summary["stages"]}
    row = FunnelRegistry(make_engine()).funnel(__import__("uuid").UUID(args.funnel))
    source = SourceRef.model_validate(row["config"]["source"])
    cfg = PlantedConfig.model_validate(source.generator)
    store = SnapshotStore()
    splits = SplitManager(
        RegistryLedger(make_engine()), load_split_config(), store, Catalog(store.root)
    )
    data = SyntheticDataAccess(splits, source)
    out: list[dict[str, Any]] = []
    for tf, per in truth["timeframes"].items():
        passes = {
            (stage, arm): passing(index(root, runs.get((tf, stage, arm)), stage), stage)
            for stage in STAGES
            for arm in ("real", "control")
        }
        for sym, t in sorted(per.items()):
            cell = t["cell"]
            rec: dict[str, Any] = {"timeframe": tf, "symbol": sym, "cell": cell}
            for stage in STAGES:
                for arm in ("real", "control"):
                    p = passes[(stage, arm)].filter(pl.col("symbol") == sym)
                    hit = [
                        matches(cell, e, d)
                        for e, d in zip(p["edge_type"], p["direction"], strict=True)
                    ]
                    rec[f"{stage}_{arm}_planted"] = any(hit)
                    rec[f"{stage}_{arm}_other"] = sum(1 for h in hit if not h)
            bars = data.arrays(sym, tf)
            tr, _ = data.truth(sym, tf)
            rec["own_statistic"] = own_statistic(bars, tr, cfg)
            out.append(rec)
    df = pl.DataFrame(out)
    if args.csv:
        df.write_csv(args.csv, float_precision=4)
    agg = (
        df.group_by("timeframe", "cell")
        .agg(
            pl.len().alias("symbols"),
            pl.col("own_statistic").mean().alias("own_mean"),
            *[pl.col(f"{s}_real_planted").mean().alias(f"{s}_power") for s in STAGES],
            *[pl.col(f"{s}_real_other").sum().alias(f"{s}_other") for s in STAGES],
            *[pl.col(f"{s}_control_planted").sum().alias(f"{s}_ctrl") for s in STAGES],
        )
        .sort("timeframe", "cell")
    )
    with pl.Config(tbl_rows=50, tbl_cols=20, tbl_width_chars=250, float_precision=3):
        print(agg)


if __name__ == "__main__":
    main()
