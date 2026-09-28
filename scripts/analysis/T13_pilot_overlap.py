"""T13 pilot: the diversity walk (F-2.6) under two overlap definitions, on the pilot's own cells.

Local only; reads the pilot's ``summary.json`` files and the development bars through
``DataAccess`` with an in-memory split ledger (the T04m pattern; no registry or store write)::

    uv run python scripts/analysis/T13_pilot_overlap.py <s02 run id> [<s02 run id> ...]

For every profile of the runs: each method's good-region median cell is re-run with the full
costs (as the stage does) to get its in-position bars; the walk is then replayed in the stage's
rank order with the stage's own gate verdicts on every other criterion, once with the stage's
overlap (the share of the **smaller** candidate's in-position bars, ``metrics.family.overlap``)
and once with the intersection over the **union**. Printed: the selections under each, and the
pairwise overlaps of the top-ranked methods.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from strategy_factory.core.config import load_pipeline_config
from strategy_factory.core.errors import HoldoutAccessError
from strategy_factory.core.universe import load_universe
from strategy_factory.costs.profile import load_assignments, load_profiles
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import DataAccess, SplitManager
from strategy_factory.metrics.containers import RunMeta
from strategy_factory.metrics.family import overlap
from strategy_factory.pipeline.backtest import to_run_result
from strategy_factory.pipeline.stage_run import artifacts_root
from strategy_factory.stages.edge import _cost_arrays
from strategy_factory.stages.screen import method_run
from strategy_factory.stages.screen_config import load_s02_config

OVERLAP_MAX = 0.60  # the s02_screen gate's overlap_with_selected threshold (gate YAML)
MAX_SELECTED = 5


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


def union_overlap(a: np.ndarray, b: np.ndarray) -> float:
    u = int(np.count_nonzero(a | b))
    return int(np.count_nonzero(a & b)) / u if u else 0.0


def walk(order: list[dict[str, Any]], pos: dict[str, np.ndarray], fn: Any) -> list[str]:
    chosen: list[str] = []
    for a in order:
        m = a["identity"]["method"]
        others_ok = all(g["passed"] for g in a["gate"] if g["metric"] != "overlap_with_selected")
        ov = max((fn(pos[m], pos[c]) for c in chosen), default=0.0)
        if others_ok and ov <= OVERLAP_MAX and len(chosen) < MAX_SELECTED:
            chosen.append(m)
    return chosen


def main(run_ids: list[str]) -> None:
    root = artifacts_root()
    cfg2 = load_s02_config()
    engine = load_pipeline_config(Path("configs/pipeline/s02_screen_1d.yaml")).engine
    universe = load_universe(Path("configs/universe.yaml")).by_symbol()
    costs_dir = Path("configs") / "costs"
    profiles, assignments = load_profiles(costs_dir), load_assignments(costs_dir)
    access = DataAccess(SplitManager(MemoryLedger(), load_split_config()))
    for run in run_ids:
        arts = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in (root / run / "s02_screen").glob("*/summary.json")
        ]
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for a in arts:
            by_parent.setdefault(a["identity"]["parent_id"], []).append(a)
        for mine in by_parent.values():
            ident = mine[0]["identity"]
            sym, tf, d = ident["symbol"], ident["timeframe"], ident["direction"]
            bars = access.arrays(sym, tf)
            bars = {c: bars[c] for c in ("ts", "open", "high", "low", "close")}
            costs = _cost_arrays(
                sym, universe[sym].asset_class, tf, bars, costs_dir, profiles, assignments
            )
            exits = cfg2.exits[ident["edge_type"]]
            pos: dict[str, np.ndarray] = {}
            for a in mine:
                m, cell = a["identity"]["method"], a["baseline"]["cell"]
                if cell is None:
                    pos[m] = np.zeros(bars["close"].shape[0], dtype=bool)
                    continue
                sim = method_run(bars, m, cell, exits, d, engine, costs)
                meta = RunMeta(symbol=sym, timeframe=tf, spec_hash="x", cost_status="verified",
                               intrabar_mode="pessimistic")  # fmt: skip
                rr = to_run_result(sim, bars["ts"], 1 if d == "long" else -1, meta, engine)
                pos[m] = np.asarray(rr.equity.in_position, dtype=bool)
            order = sorted(mine, key=lambda a: a["family"]["rank"])
            smaller = walk(order, pos, overlap)
            union = walk(order, pos, union_overlap)
            print(f"\n{sym} {tf} {d}")
            print(f"  selected, share of the smaller: {smaller}")
            print(f"  selected, intersection / union: {union}")
            top = [a["identity"]["method"] for a in order[:6]]
            print("  pairwise overlap of the top 6 (smaller / union):")
            for i, a in enumerate(top):
                cells = [
                    f"{overlap(pos[a], pos[b]):.2f}/{union_overlap(pos[a], pos[b]):.2f}"
                    for b in top[:i]
                ]
                print(f"    {a:22} {' '.join(cells)}")


if __name__ == "__main__":
    main(sys.argv[1:])
