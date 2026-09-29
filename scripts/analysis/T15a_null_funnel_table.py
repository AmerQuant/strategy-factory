"""T15a plan: M4's per-candidate table (``docs/reviews/T15a_plan_null_funnel.csv``).

Reads the dry-run artifacts that ``T15a_null_funnel.py`` wrote under ``<out>/<tf>_<variant>`` and
writes one row per null candidate per stage: the stage-1 passes, every stage-2 method screened for
them, and every stage-3 candidate, with the verdict and the failing criteria.

    uv run python scripts/analysis/T15a_null_funnel_table.py --out <dir> --csv docs/reviews/T15a_plan_null_funnel.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

KEEP = {
    "s01_edge": ["symbol", "edge_type", "direction", "ess", "passed", "quality_status"],
    "s02_screen": ["symbol", "edge_type", "direction", "method", "method_q_value", "gate_passed",
                   "selected", "failed_criteria"],
    "s03_entry": ["symbol", "edge_type", "direction", "method", "grid_cells", "selected_params",
                  "stability_ratio", "plateau_area", "plateau_cells", "half2_raw",
                  "selected_in_both_halves", "gate_passed", "failed_criteria"],
}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--csv", type=Path, required=True)
    args = ap.parse_args()
    frames: list[pl.DataFrame] = []
    for run in sorted(p for p in args.out.iterdir() if (p / "dry-run").is_dir()):
        tf, variant = run.name.split("_", 1)
        for stage, cols in KEEP.items():
            index = run / "dry-run" / stage / "index.csv"
            if not index.is_file():
                continue
            df = pl.read_csv(index, infer_schema=False)
            if stage == "s01_edge":
                df = df.filter(pl.col("passed") == "True")
            df = df.select([c for c in cols if c in df.columns])
            frames.append(df.with_columns(
                pl.lit(variant).alias("variant"), pl.lit(tf).alias("tf"), pl.lit(stage).alias("stage")
            ))  # fmt: skip
    out = pl.concat(frames, how="diagonal")
    lead = ["variant", "tf", "stage"]
    out = out.select(lead + [c for c in out.columns if c not in lead])
    out.write_csv(args.csv)
    print(out.group_by("variant", "tf", "stage").len().sort("variant", "tf", "stage"))


if __name__ == "__main__":
    main()
