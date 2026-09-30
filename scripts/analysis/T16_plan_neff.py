"""T16 plan, §7 (1): candidate estimators of the effective number of trials (F-7.3), measured on
synthetic trial matrices whose answer is known. Measurement only; nothing here is the library::

    uv run python scripts/analysis/T16_plan_neff.py            # -> docs/reviews/T16_plan_neff.csv

A trial matrix is ``trials x time`` daily returns. A scenario plants ``K`` independent groups: each
trial of group g is ``sqrt(rho) * f_g + sqrt(1 - rho) * e``, with independent standard normal factors
and noise, so trials within a group correlate at ``rho`` and across groups at 0. The known answer
is ``K``. Two further scenarios have **no single right answer** and show how the candidates read a
parameter grid: a 1-D grid whose neighbours correlate as ``exp(-|i - j| / L)``, and nested groups.

Candidates (the correlation matrix ``C`` of the trials, ``N`` trials, ``T`` observations):

* ``avg_corr``: ``N / (1 + (N - 1) * mean off-diagonal rho)``, rho floored at 0.
* ``eig_participation``: ``(sum lambda)^2 / sum lambda^2`` of ``C``'s eigenvalues.
* ``eig_li_ji``: Li & Ji (2005), ``sum_i [1(lambda_i >= 1) + (lambda_i - floor(lambda_i))]``.
* ``eig_mp``: eigenvalues above the Marchenko-Pastur edge ``(1 + sqrt(N / T))^2``, at least 1.
* ``hier_avg_0.5`` / ``hier_avg_0.3``: average-linkage clustering on ``d = sqrt((1 - rho) / 2)``,
  cut where the linkage distance reaches ``d(rho_cut)``; ``N_eff`` = the number of clusters.
* ``onc``: Lopez de Prado's ONC (2019): k-means on the rows of the distance matrix for
  ``k = 2 .. k_max`` with ``n_init`` restarts, keeping the partition with the highest silhouette
  quality ``mean(s) / std(s)``; ``N_eff`` = its ``k`` (1 if no partition is better than none).
  The base ONC, without the recursive re-clustering of poor clusters.

For each scenario and seed: every candidate's ``N_eff``, its runtime, and -- to show what the choice
does downstream -- the DSR's expected maximum Sharpe under the null, ``SR_0``, for trial Sharpes
with a fixed variance (Bailey & Lopez de Prado 2014, eq. 1 with ``V = 1``).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.cluster.vq import kmeans2
from scipy.spatial.distance import squareform
from scipy.stats import norm

from strategy_factory.cli import utf8_output

OUT = Path("docs") / "reviews" / "T16_plan_neff.csv"
EULER = 0.5772156649015329
SEEDS = (1, 2, 3)

Estimator = Callable[[np.ndarray, int], float]


def corr(x: np.ndarray) -> np.ndarray:
    c = np.corrcoef(x)
    np.fill_diagonal(c, 1.0)
    return np.clip(c, -1.0, 1.0)


def avg_corr(c: np.ndarray, t: int) -> float:
    n = c.shape[0]
    rho = max(0.0, float((c.sum() - n) / (n * (n - 1))))
    return n / (1 + (n - 1) * rho)


def eig_participation(c: np.ndarray, t: int) -> float:
    lam = np.clip(np.linalg.eigvalsh(c), 0, None)
    return float(lam.sum() ** 2 / (lam**2).sum())


def eig_li_ji(c: np.ndarray, t: int) -> float:
    lam = np.clip(np.linalg.eigvalsh(c), 0, None)
    return float(((lam >= 1).astype(float) + (lam - np.floor(lam))).sum())


def eig_mp(c: np.ndarray, t: int) -> float:
    n = c.shape[0]
    edge = (1 + np.sqrt(n / t)) ** 2
    return float(max(1, int((np.linalg.eigvalsh(c) > edge).sum())))


def _dist(c: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.clip((1 - c) / 2, 0, None))
    np.fill_diagonal(d, 0.0)
    return d


def hier(rho_cut: float) -> Estimator:
    def est(c: np.ndarray, t: int) -> float:
        z = linkage(squareform(_dist(c), checks=False), method="average")
        return float(fcluster(z, t=np.sqrt((1 - rho_cut) / 2), criterion="distance").max())

    return est


def _silhouette(d: np.ndarray, labels: np.ndarray) -> np.ndarray:
    ks = np.unique(labels)
    s = np.zeros(len(labels))
    if len(ks) < 2:
        return s
    means = np.stack([d[:, labels == k].mean(axis=1) for k in ks], axis=1)
    for i, lab in enumerate(labels):
        own = labels == lab
        n_own = own.sum()
        a = d[i, own].sum() / max(n_own - 1, 1)
        b = np.min(np.delete(means[i], np.searchsorted(ks, lab)))
        s[i] = 0.0 if n_own == 1 else (b - a) / max(a, b)
    return s


def onc(c: np.ndarray, t: int, n_init: int = 10, k_cap: int = 60) -> float:
    d = _dist(c)
    n = c.shape[0]
    rng = np.random.default_rng(0)
    best_q, best_k = 0.0, 1
    for k in range(2, min(n - 1, k_cap) + 1):
        for _ in range(n_init):
            _, lab = kmeans2(d, k, minit="++", seed=rng)
            if len(np.unique(lab)) < 2:
                continue
            s = _silhouette(d, lab)
            q = s.mean() / s.std() if s.std() > 0 else 0.0
            if q > best_q:
                best_q, best_k = q, len(np.unique(lab))
    return float(best_k)


ESTIMATORS: dict[str, Estimator] = {
    "avg_corr": avg_corr,
    "eig_participation": eig_participation,
    "eig_li_ji": eig_li_ji,
    "eig_mp": eig_mp,
    "hier_avg_0.5": hier(0.5),
    "hier_avg_0.3": hier(0.3),
    "onc": onc,
}


def sr0(n_eff: float, var: float = 1.0) -> float:
    """Bailey & Lopez de Prado (2014) eq. 1: the expected maximum of N_eff Sharpes under the null."""
    if n_eff <= 1:
        return 0.0
    return float(
        np.sqrt(var)
        * ((1 - EULER) * norm.ppf(1 - 1 / n_eff) + EULER * norm.ppf(1 - 1 / (n_eff * np.e)))
    )


def groups(n: int, sizes: list[int], rho: float, t: int, rng: np.random.Generator) -> np.ndarray:
    assert sum(sizes) == n
    f = rng.standard_normal((len(sizes), t))
    g = np.repeat(np.arange(len(sizes)), sizes)
    return np.sqrt(rho) * f[g] + np.sqrt(1 - rho) * rng.standard_normal((n, t))


def grid(n: int, length: float, t: int, rng: np.random.Generator) -> np.ndarray:
    """A 1-D parameter grid: cells correlate as exp(-|i - j| / L) (an AR(1) across cells)."""
    phi = np.exp(-1 / length)
    x = np.empty((n, t))
    x[0] = rng.standard_normal(t)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + np.sqrt(1 - phi**2) * rng.standard_normal(t)
    return x


def nested(t: int, rng: np.random.Generator) -> np.ndarray:
    """4 families x 5 methods x 10 parameter cells: family 0.3, method 0.7, cell 0.95 (cumulative)."""
    fam = rng.standard_normal((4, t))
    meth = rng.standard_normal((20, t))
    cell = rng.standard_normal((200, t))
    x = np.empty((200, t))
    for i in range(200):
        m = i // 10
        f = m // 5
        x[i] = np.sqrt(0.3) * fam[f] + np.sqrt(0.4) * meth[m] + np.sqrt(0.25) * cell[i]
    return x


def scenarios() -> list[tuple[str, str, int | None, Callable[[np.random.Generator], np.ndarray]]]:
    t = 1000
    out: list[tuple[str, str, int | None, Callable[[np.random.Generator], np.ndarray]]] = []
    for k in (1, 5, 20, 50):
        for rho in (0.95, 0.7, 0.4):
            out.append(
                (f"blocks K={k} rho={rho}", "equal", k,
                 lambda r, k=k, rho=rho: groups(200, [200 // k] * k, rho, t, r))
            )  # fmt: skip
    sizes = [100, 40, 20, 12, 8, 6, 5, 4, 3, 2]  # one dominant group, 10 in all
    out.append(("unequal K=10 rho=0.7", "unequal", 10, lambda r: groups(200, sizes, 0.7, t, r)))
    out.append(("independent N=200", "independent", 200, lambda r: r.standard_normal((200, t))))
    out.append(
        ("identical N=200", "identical", 1, lambda r: np.tile(r.standard_normal(t), (200, 1)))
    )
    out.append(("grid L=5", "grid (no single answer)", None, lambda r: grid(200, 5, t, r)))
    out.append(("grid L=20", "grid (no single answer)", None, lambda r: grid(200, 20, t, r)))
    out.append(("nested 4x5x10", "nested (4 / 20 / 200)", None, lambda r: nested(t, r)))
    out.append(
        ("scale K=50 rho=0.7 N=1000", "equal, N=1000", 50,
         lambda r: groups(1000, [20] * 50, 0.7, t, r))
    )  # fmt: skip
    return out


def main() -> int:
    utf8_output()
    rows = []
    for name, kind, truth, make in scenarios():
        for seed in SEEDS:
            x = make(np.random.default_rng(seed))
            c = corr(x)
            for est_name, est in ESTIMATORS.items():
                if est_name == "onc" and c.shape[0] > 200 and seed != SEEDS[0]:
                    continue  # ONC at N=1000 is slow: one seed is enough for its runtime
                t0 = time.perf_counter()
                val = est(c, x.shape[1])
                rows.append(
                    {
                        "scenario": name,
                        "kind": kind,
                        "n_trials": c.shape[0],
                        "truth": truth,
                        "seed": seed,
                        "estimator": est_name,
                        "n_eff": round(val, 2),
                        "seconds": round(time.perf_counter() - t0, 4),
                        "sr0_v1": round(sr0(val), 4),
                    }
                )
            print(name, seed, flush=True)
    df = pl.DataFrame(rows)
    df.write_csv(OUT)
    summary = df.group_by("scenario", "truth", "estimator", maintain_order=True).agg(
        pl.col("n_eff").mean().round(1), pl.col("seconds").mean().round(3)
    )
    pl.Config.set_tbl_rows(200)
    print(summary.pivot(on="estimator", index=["scenario", "truth"], values="n_eff"))
    print(summary.pivot(on="estimator", index=["scenario"], values="seconds"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
