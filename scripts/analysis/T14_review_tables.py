"""T14 review: the per-candidate tables of the full runs and their controls (read-only).

    uv run python scripts/analysis/T14_review_tables.py <1D> <1H> <1D control> <1H control>

Copies each run's index to ``docs/reviews/T14_index_{1D,1H,1D_control,1H_control}.csv`` and prints
per candidate, real beside control: grid, selected centre, plateau extent, stability, plateau
cells / area, half 2, SPP, the zero-cost shift, overlaps, the verdict; then per-criterion counts.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from strategy_factory.core.config import canonical_json
from strategy_factory.pipeline.stage_run import artifacts_root

NAMES = ("1D", "1H", "1D_control", "1H_control")
CRITERIA = (
    "spp_median_target",
    "stability_ratio",
    "plateau_area",
    "plateau_cells",
    "selected_in_both_halves",
)


def load(run: str) -> dict[str, dict[str, Any]]:
    d = artifacts_root() / run / "s03_entry"
    out = {}
    for p in sorted(d.glob("*/summary.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        out[a["identity"]["parent_id"]] = a
    return out


def fmt(v: Any, n: int = 2) -> str:
    return "—" if v is None else f"{v:.{n}f}"


def line(a: dict[str, Any]) -> str:
    s = a["selection"]
    ext = "; ".join(f"{k} {fmt(lo, 2)}–{fmt(hi, 2)}" for k, (lo, hi) in s["plateau_extent"].items())
    failed = [g["metric"] for g in a["gate"] if not g["passed"]]
    ov = [o["overlap"] for o in a["overlaps"] if o["overlap"] is not None]
    return (
        f"sel {canonical_json(s['params']) if s['params'] else '—'} | ext {ext} | "
        f"stab {fmt(s['stability_ratio'])} | plateau {s['plateau_cells']}/{s['plateau_area']:.3f} | "
        f"h2 {fmt(a['half2']['raw'])} {'Y' if a['half2']['accepted'] else 'n'} | "
        f"spp {fmt(a['spp']['median'])} [{fmt(a['spp']['p_low'])}, {fmt(a['spp']['p_high'])}] | "
        f"shift {a['zero_cost']['shift_steps']} | ov {fmt(max(ov) if ov else None)} | "
        f"{'PASS' if a['gate_passed'] else 'fail: ' + ','.join(failed)}"
    )


def candidate_rows(runs: list[str]) -> list[dict[str, Any]]:
    """One row per candidate and dataset: everything T14 §8 asks the review to report."""
    rows = []
    for name, run in zip(NAMES, runs, strict=True):
        for a in load(run).values():
            i, s, g = a["identity"], a["selection"], a["grid"]
            rows.append(
                {
                    "data": "control" if name.endswith("control") else "real",
                    "timeframe": i["timeframe"],
                    "symbol": i["symbol"],
                    "direction": i["direction"],
                    "method": i["method"],
                    "unconfirmed": i["unconfirmed"],
                    "grid_cells": g["size"],
                    "grid_cells_d639": g["size_d639"],
                    "step_multipliers": canonical_json(
                        {x["name"]: x["multiplier"] for x in g["axes"]}
                    ),
                    "small_grid": g["small_grid"],
                    "stage2_median_cell": canonical_json(g["stage2_median_cell"]),
                    "selected": canonical_json(s["params"]) if s["params"] else "",
                    "plateau_extent": canonical_json(s["plateau_extent"]),
                    "plateau_cells": s["plateau_cells"],
                    "plateau_area": s["plateau_area"],
                    "stability_ratio": s["stability_ratio"],
                    "edge_slope": s["edge_slope"],
                    "half2_raw": a["half2"]["raw"],
                    "half2_accepted": a["half2"]["accepted"],
                    "spp_median": a["spp"]["median"],
                    "spp_p5": a["spp"]["p_low"],
                    "spp_p95": a["spp"]["p_high"],
                    "zero_cost_selected": canonical_json(a["zero_cost"]["params"])
                    if a["zero_cost"]["params"]
                    else "",
                    "zero_cost_shift_steps": a["zero_cost"]["shift_steps"],
                    "overlaps": canonical_json({o["method"]: o["overlap"] for o in a["overlaps"]}),
                    "gate_passed": a["gate_passed"],
                    "failed_criteria": ";".join(x["metric"] for x in a["gate"] if not x["passed"]),
                }
            )
    return rows


def main(runs: list[str]) -> None:
    rows = candidate_rows(runs)
    with (Path("docs/reviews") / "T14_candidates.csv").open(
        "w", encoding="utf-8", newline=""
    ) as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for name, run in zip(NAMES, runs, strict=True):
        shutil.copyfile(
            artifacts_root() / run / "s03_entry" / "index.csv",
            Path("docs/reviews") / f"T14_index_{name}.csv",
        )
    for real_run, ctrl_run in ((runs[0], runs[2]), (runs[1], runs[3])):
        real, ctrl = load(real_run), load(ctrl_run)
        for pid in sorted(
            real,
            key=lambda k: (
                real[k]["identity"]["symbol"],
                real[k]["identity"]["direction"],
                real[k]["identity"]["method"],
            ),
        ):
            a = real[pid]
            i = a["identity"]
            g = a["grid"]
            print(
                f"\n{i['timeframe']} {i['symbol']} {i['direction']} {i['method']} "
                f"(grid {g['size']}{'/' + str(g['size_d639']) if g['size'] != g['size_d639'] else ''}"
                f"{', small' if g['small_grid'] else ''}; stage-2 cell "
                f"{canonical_json(g['stage2_median_cell'])}; failed h1/h2 "
                f"{a['selection']['failed_cells']['h1']}/{a['selection']['failed_cells']['h2']})"
            )
            print("  real   ", line(a))
            print("  control", line(ctrl[pid]))
        for label, arts in (("real", real), ("control", ctrl)):
            c: Counter[str] = Counter()
            for a in arts.values():
                for gl in a["gate"]:
                    c[gl["metric"]] += gl["passed"]
            passed = sum(a["gate_passed"] for a in arts.values())
            print(
                f"\n{label}: {len(arts)} candidates, {passed} pass; criteria met: "
                + ", ".join(f"{k} {c[k]}" for k in CRITERIA)
            )


if __name__ == "__main__":
    main(sys.argv[1:])
