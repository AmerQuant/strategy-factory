"""T16, D-722: the faithful ONC against hierarchical clustering with a correlation cut, on the same
synthetic trial matrices as the plan (docs/tasks/T16_plan.md §2), plus a 2-D parameter grid.
Measurement only; the supervisor chooses F-7.3's default from it. **Resumable**::

    uv run python scripts/analysis/T16_onc_vs_hier.py
        [--seed-from-log <the interrupted run's log>]   # once: import its finished ONC results

Every finished case is appended to ``docs/reviews/T16_onc_vs_hier.csv`` at once, with a progress
line on stdout, so a stop loses at most the case in flight; a re-run skips what the CSV holds and
computes only what is missing (ONC and hierarchical separately). At the end the summary is written
to ``docs/reviews/T16_onc_vs_hier_summary.csv``.

* **ONC** is the library's ``stats.neff.onc`` (faithful to Lopez de Prado's published code:
  k = 2 .. n - 1, 10 restarts, the recursive re-clustering), seed 0, **with** the identical-trials
  guard (the 54 cases imported from the interrupted run ran with it too). Wherever the guard
  fires, the case also runs **without** it (``onc_unguarded``), so both variants are in the table.
* **Hierarchical** is the library's ``stats.neff.hierarchical_labels``: average linkage on
  ``d = sqrt((1 - rho) / 2)`` cut where the linkage distance reaches ``d(rho_cut)``, for rho_cut
  in 0.2, 0.3, 0.4, 0.5; its seconds include the linkage, per cut.

Per scenario and seed: N_eff, seconds, and SR_0 (the DSR's expected maximum Sharpe of N_eff null
trials, in units of the trials' Sharpe standard deviation) -- what the choice does to the DSR bar.
The 1,000-trial scenario runs ONC capped at k <= 100 (the uncapped sweep would take hours).
Cases run one at a time by default (``T16_WORKERS`` to change it), so the timings are clean.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import polars as pl

from strategy_factory.cli import utf8_output
from strategy_factory.stats.neff import (
    correlation,
    hierarchical_labels,
    identical_guard_fires,
    onc,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import T16_plan_neff as plan

OUT = Path("docs") / "reviews" / "T16_onc_vs_hier.csv"
SUMMARY = Path("docs") / "reviews" / "T16_onc_vs_hier_summary.csv"
CUTS = (0.2, 0.3, 0.4, 0.5)
SEEDS = (1, 2, 3)
COLUMNS = ("scenario", "truth", "n_trials", "seed", "method", "n_eff", "seconds", "sr0", "note")


def grid2d(side: int, length: float, t: int, rng: np.random.Generator) -> np.ndarray:
    """A 2-D parameter grid, side x side cells: corr = exp(-|di| / L) * exp(-|dj| / L)."""
    idx = np.arange(side)
    a = np.exp(-np.abs(idx[:, None] - idx[None, :]) / length)
    chol = np.linalg.cholesky(np.kron(a, a))
    return chol @ rng.standard_normal((side * side, t))


def scenarios() -> list[tuple[str, int | None, int | None, int]]:
    """(name, truth, ONC cap, trials); the matrices are rebuilt from ``plan`` and the seeds."""
    out = [
        (name, truth, 100 if "N=1000" in name else None, 1000 if "N=1000" in name else 200)
        for name, _, truth, _ in plan.scenarios()
    ]
    out += [("grid2d 15x15 L=2", None, None, 225), ("grid2d 15x15 L=5", None, None, 225)]
    return out


def matrix(name: str, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if name.startswith("grid2d"):
        return grid2d(15, float(name.split("L=")[1]), 1000, rng)
    make = next(m for n, _, _, m in plan.scenarios() if n == name)
    return make(rng)


def job(
    args: tuple[str, int | None, int | None, int, bool, bool, bool],
) -> list[dict[str, object]]:
    name, truth, cap, seed, need_hier, need_onc, need_unguarded = args
    x = matrix(name, seed)
    n = x.shape[0]
    rows: list[dict[str, object]] = []
    if need_hier:
        c = correlation(x)
        for cut in CUTS:
            t1 = time.perf_counter()
            k = len(np.unique(hierarchical_labels(c, cut)))
            rows.append(
                {"scenario": name, "truth": truth, "n_trials": n, "seed": seed,
                 "method": f"hier_{cut}", "n_eff": k,
                 "seconds": round(time.perf_counter() - t1, 3),
                 "sr0": round(plan.sr0(k), 4), "note": ""}
            )  # fmt: skip
    if need_onc:
        t0 = time.perf_counter()
        r = onc(x, seed=0, max_clusters=cap)
        rows.append(
            {"scenario": name, "truth": truth, "n_trials": n, "seed": seed, "method": "onc",
             "n_eff": r.n_effective, "seconds": round(time.perf_counter() - t0, 1),
             "sr0": round(plan.sr0(r.n_effective), 4),
             "note": f"ONC capped at k <= {cap}" if cap else ""}
        )  # fmt: skip
    if need_unguarded:  # the published method without the identical-trials guard (D-722)
        t0 = time.perf_counter()
        r = onc(x, seed=0, max_clusters=cap, identical_guard=False)
        rows.append(
            {"scenario": name, "truth": truth, "n_trials": n, "seed": seed,
             "method": "onc_unguarded", "n_eff": r.n_effective,
             "seconds": round(time.perf_counter() - t0, 1),
             "sr0": round(plan.sr0(r.n_effective), 4),
             "note": "the guard fires on this case; ONC without it"}
        )  # fmt: skip
    return rows


def guard_fires(name: str, seed: int) -> bool:
    return identical_guard_fires(correlation(matrix(name, seed)))


def _done() -> tuple[set[tuple[str, int]], set[tuple[str, int]], set[tuple[str, int]]]:
    onc_done: set[tuple[str, int]] = set()
    hier_done: set[tuple[str, int]] = set()
    unguarded_done: set[tuple[str, int]] = set()
    if OUT.is_file():
        with OUT.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                key = (row["scenario"], int(row["seed"]))
                if row["method"] == "onc":
                    onc_done.add(key)
                elif row["method"] == "onc_unguarded":
                    unguarded_done.add(key)
                else:
                    hier_done.add(key)
    return onc_done, hier_done, unguarded_done


def seed_from_log(log: Path) -> int:
    """Import the ONC results of an interrupted run's log (lines ``<scenario> <seed> onc <n>``);
    they carry no timing and say so."""
    meta = {name: (truth, trials) for name, truth, _, trials in scenarios()}
    onc_done, _, _ = _done()
    rows = []
    for line in log.read_text(encoding="utf-8").splitlines():
        parts = line.rsplit(" ", 3)
        if len(parts) != 4 or parts[2] != "onc" or parts[0] not in meta:
            continue
        name, seed, n_eff = parts[0], int(parts[1]), int(parts[3])
        if (name, seed) in onc_done:
            continue
        truth, trials = meta[name]
        rows.append(
            {"scenario": name, "truth": truth, "n_trials": trials, "seed": seed, "method": "onc",
             "n_eff": n_eff, "seconds": "", "sr0": round(plan.sr0(n_eff), 4),
             "note": "interrupted run of 2026-09-30: no timing"}
        )  # fmt: skip
    _append(rows)
    return len(rows)


def _append(rows: list[dict[str, object]]) -> None:
    new = not OUT.is_file()
    with OUT.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(rows)


def main() -> int:
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed-from-log", type=Path, help="An interrupted run's log to import.")
    args = parser.parse_args()
    if args.seed_from_log:
        print(f"imported {seed_from_log(args.seed_from_log)} ONC result(s)", flush=True)
    onc_done, hier_done, unguarded_done = _done()
    fires = {(n, s): guard_fires(n, s) for n, _, _, _ in scenarios() for s in SEEDS}
    print(
        f"identical-trials guard fires on: {sorted(k for k, v in fires.items() if v)}", flush=True
    )
    jobs = [
        (n, tr, cap, s, (n, s) not in hier_done, (n, s) not in onc_done,
         fires[(n, s)] and (n, s) not in unguarded_done)
        for n, tr, cap, _ in scenarios()
        for s in SEEDS
    ]  # fmt: skip
    jobs = [j for j in jobs if j[4] or j[5] or j[6]]
    print(f"{time.strftime('%H:%M:%S')} {len(jobs)} case(s) to run", flush=True)
    workers = int(os.environ.get("T16_WORKERS", "1"))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for spec, out in zip(jobs, pool.map(job, jobs), strict=True):
            _append(out)
            got = {r["method"]: r["n_eff"] for r in out}
            secs = next((r["seconds"] for r in out if r["method"] == "onc"), "-")
            print(
                f"{time.strftime('%H:%M:%S')} {spec[0]} seed {spec[3]}: {got} onc {secs}s",
                flush=True,
            )
    df = pl.read_csv(OUT)
    summary = df.group_by("scenario", "truth", "method", maintain_order=True).agg(
        pl.col("n_eff").mean().round(1).alias("n_eff_mean"),
        pl.col("n_eff").min().alias("n_eff_min"),
        pl.col("n_eff").max().alias("n_eff_max"),
        pl.col("sr0").mean().round(3).alias("sr0_mean"),
        pl.col("seconds").mean().round(2).alias("seconds_mean"),
    )
    summary = summary.with_columns(
        pl.struct("scenario", "method")
        .map_elements(
            lambda r: (
                any(fires[(r["scenario"], s)] for s in SEEDS) if r["method"] == "onc" else None
            ),
            return_dtype=pl.Boolean,
        )
        .alias("guard_fired_on_a_seed")
    )
    summary.write_csv(SUMMARY)
    pl.Config.set_tbl_rows(200)
    pl.Config.set_tbl_formatting("ASCII_MARKDOWN")
    print(summary.pivot(on="method", index=["scenario", "truth"], values="n_eff_mean"))
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
