"""T14 review: the per-candidate tables of the full runs and their controls (read-only).

    uv run python scripts/analysis/T14_review_tables.py <1D> <1H> <1D control> <1H control>

Copies each run's index to ``docs/reviews/T14_index_{1D,1H,1D_control,1H_control}.csv`` and prints
per candidate, real beside control: grid, selected centre, plateau extent, stability, plateau
cells / area, half 2, SPP, the zero-cost shift, overlaps, the verdict; then per-criterion counts.
"""

from __future__ import annotations

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


def main(runs: list[str]) -> None:
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
