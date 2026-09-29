"""T14 pilot: two stage-3 runs of the same config must be identical (D-607, rule 8).

Local only; reads two run folders under ``SFAC_ARTIFACTS_ROOT``::

    uv run python scripts/analysis/T14_pilot_compare.py <run id A> <run id B>

Compares every ``summary.json`` with its run-specific fields (``run_id``) removed, and the index
(which carries no run id); prints the per-candidate table the pilot report quotes.
"""

from __future__ import annotations

import csv
import json
import sys
from typing import Any

from strategy_factory.pipeline.stage_run import artifacts_root


def _load(run: str) -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted((artifacts_root() / run / "s03_entry").glob("*/summary.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        data["identity"]["run_id"] = None
        out[p.parent.name] = data
    return out


def main(a: str, b: str) -> None:
    ra, rb = _load(a), _load(b)
    same = ra == rb
    ia = (artifacts_root() / a / "s03_entry" / "index.csv").read_text(encoding="utf-8")
    ib = (artifacts_root() / b / "s03_entry" / "index.csv").read_text(encoding="utf-8")
    print(
        f"candidates {len(ra)} / {len(rb)}; summaries identical: {same}; index identical: {ia == ib}"
    )
    for row in csv.DictReader(ia.splitlines()):
        print(
            f"{row['timeframe']} {row['symbol']:5} {row['direction']:5} {row['method']:22} "
            f"cells {row['grid_cells']:>5} small {row['small_grid']:5} sel {row['selected_params']:38} "
            f"stab {row['stability_ratio'][:5]:5} area {row['plateau_area'][:5]:5} "
            f"cells {row['plateau_cells']:>4} h2 {row['half2_raw'][:6]:6} "
            f"both {row['selected_in_both_halves']:5} spp {row['spp_median_target'][:6]:6} "
            f"shift {row['zero_cost_shift_steps']:>2} ov {row['max_overlap'][:4]:4} "
            f"pass {row['gate_passed']:5} {row['failed_criteria']}"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
