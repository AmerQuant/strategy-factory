"""T16, D-722: the faithful ONC against hierarchical clustering with a correlation cut, on the same
synthetic trial matrices as the plan (docs/tasks/T16_plan.md §2), plus a 2-D parameter grid.
Measurement only; the supervisor chooses F-7.3's default from it::

    uv run python scripts/analysis/T16_onc_vs_hier.py      # -> docs/reviews/T16_onc_vs_hier.csv

* **ONC** is the library's ``stats.neff.onc`` (faithful to Lopez de Prado's published code:
  k = 2 .. n - 1, 10 restarts, the recursive re-clustering), seed 0.
* **Hierarchical** is average linkage on ``d = sqrt((1 - rho) / 2)`` cut where the linkage
  distance reaches ``d(rho_cut)``, for rho_cut in 0.2, 0.3, 0.4, 0.5 (scipy's ``linkage`` and
  ``fcluster``: the calls the library makes once scipy is declared).

Per scenario and seed: N_eff, seconds, and SR_0 (the DSR's expected maximum Sharpe of N_eff null
trials, in units of the trials' Sharpe standard deviation) -- what the choice does to the DSR bar.
The 1,000-trial scenario runs ONC capped at k <= 100 (the uncapped sweep would take hours); the
cap is stated in its row.
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import polars as pl
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from strategy_factory.cli import utf8_output
from strategy_factory.stats.neff import correlation, distance, onc

sys.path.insert(0, str(Path(__file__).resolve().parent))
import T16_plan_neff as plan

OUT = Path("docs") / "reviews" / "T16_onc_vs_hier.csv"
CUTS = (0.2, 0.3, 0.4, 0.5)
SEEDS = (1, 2, 3)
WORKERS = 6


def grid2d(side: int, length: float, t: int, rng: np.random.Generator) -> np.ndarray:
    """A 2-D parameter grid, side x side cells: corr = exp(-|di| / L) * exp(-|dj| / L)."""
    idx = np.arange(side)
    a = np.exp(-np.abs(idx[:, None] - idx[None, :]) / length)
    chol = np.linalg.cholesky(np.kron(a, a))
    return chol @ rng.standard_normal((side * side, t))


def scenarios() -> list[tuple[str, int | None, int | None]]:
    """(name, truth, ONC cap); the matrices are rebuilt in each worker from ``plan`` + seeds."""
    out: list[tuple[str, int | None, int | None]] = [
        (name, truth, 100 if "N=1000" in name else None) for name, _, truth, _ in plan.scenarios()
    ]
    out += [("grid2d 15x15 L=2", None, None), ("grid2d 15x15 L=5", None, None)]
    return out


def matrix(name: str, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if name.startswith("grid2d"):
        return grid2d(15, float(name.split("L=")[1]), 1000, rng)
    make = next(m for n, _, _, m in plan.scenarios() if n == name)
    return make(rng)


def job(args: tuple[str, int | None, int | None, int]) -> list[dict[str, object]]:
    name, truth, cap, seed = args
    x = matrix(name, seed)
    c = correlation(x)
    rows: list[dict[str, object]] = []
    t0 = time.perf_counter()
    z = linkage(squareform(distance(c), checks=False), method="average")
    link_s = time.perf_counter() - t0
    for cut in CUTS:
        t1 = time.perf_counter()
        k = int(fcluster(z, t=np.sqrt((1 - cut) / 2), criterion="distance").max())
        rows.append(
            {"scenario": name, "truth": truth, "n_trials": len(c), "seed": seed,
             "method": f"hier_{cut}", "n_eff": k,
             "seconds": round(link_s + time.perf_counter() - t1, 3), "sr0": round(plan.sr0(k), 4),
             "note": ""}
        )  # fmt: skip
    t0 = time.perf_counter()
    r = onc(x, seed=0, max_clusters=cap)
    rows.append(
        {"scenario": name, "truth": truth, "n_trials": len(c), "seed": seed, "method": "onc",
         "n_eff": r.n_effective, "seconds": round(time.perf_counter() - t0, 1),
         "sr0": round(plan.sr0(r.n_effective), 4),
         "note": f"ONC capped at k <= {cap}" if cap else ""}
    )  # fmt: skip
    return rows


def main() -> int:
    utf8_output()
    jobs = [(n, tr, cap, s) for n, tr, cap in scenarios() for s in SEEDS]
    rows: list[dict[str, object]] = []
    workers = int(os.environ.get("T16_WORKERS", WORKERS))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for out in pool.map(job, jobs):
            rows.extend(out)
            print(out[-1]["scenario"], out[-1]["seed"], "onc", out[-1]["n_eff"], flush=True)
    df = pl.DataFrame(rows)
    df.write_csv(OUT)
    summary = df.group_by("scenario", "truth", "method", maintain_order=True).agg(
        pl.col("n_eff").mean().round(1)
    )
    pl.Config.set_tbl_rows(200)
    pl.Config.set_tbl_formatting("ASCII_MARKDOWN")
    print(summary.pivot(on="method", index=["scenario", "truth"], values="n_eff"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
