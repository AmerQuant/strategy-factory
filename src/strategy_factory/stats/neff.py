"""F-7.3: the effective number of trials, by clustering correlated results (T16, D-160, D-722).

The input is a trials x time matrix of returns (D-724: which trials, and where the matrix comes
from, are the stage-7 task's). Trials are compared by the correlation distance
``d_ij = sqrt((1 - rho_ij) / 2)``; a trial with constant returns has no correlation and is treated
as uncorrelated (rho = 0), as in the reference code.

**ONC** -- Lopez de Prado's optimal number of clusters (*Machine Learning for Asset Managers*,
2020, section 4.4; Lopez de Prado & Lewis 2019), implemented faithfully to the published code:

1. *Base:* the rows of the distance matrix are the features. For ``n_init`` restarts and every
   ``k`` from 2 to ``max_clusters``, k-means (k-means++ seeding, Lloyd iterations, one
   initialisation per fit) partitions them; each partition is scored by the silhouette's
   t-statistic ``mean(s) / std(s)`` (sklearn's ``silhouette_samples`` semantics: Euclidean distance
   between the feature rows, 0 for a singleton), and the best partition is kept.
2. *Top:* each cluster's own silhouette t-statistic is computed; the clusters below the average
   are pooled and re-clustered recursively on their own correlation matrix; the new partition
   replaces the old only if its mean cluster t-statistic is higher than the re-clustered ones'.

One guard, documented: when every trial is identical (all distances 0), the method has no
partition to score (it never tries ``k = 1``); the result is then one cluster, as F-7.3's
acceptance requires ("close to 1 on perfectly correlated trials").

``n_effective`` is the number of clusters. The default between this and hierarchical clustering
with a correlation cut is the supervisor's choice from the comparison (D-722).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from strategy_factory.stats.results import NeffResult

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


def correlation(returns: npt.ArrayLike) -> FloatArray:
    """The trials' correlation matrix; a constant trial correlates 0 with every other one."""
    x = np.asarray(returns, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] < 1:
        raise ValueError(f"returns must be trials x time, got {x.shape}")
    if np.isnan(x).any():
        raise ValueError("returns contain NaN")
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.corrcoef(x) if x.shape[0] > 1 else np.ones((1, 1))
    c = np.nan_to_num(np.atleast_2d(c), nan=0.0)
    np.fill_diagonal(c, 1.0)
    return np.clip(c, -1.0, 1.0)


def distance(corr: FloatArray) -> FloatArray:
    """``sqrt((1 - rho) / 2)``: 0 for identical trials, 1 for perfectly opposite ones."""
    d = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, None))
    np.fill_diagonal(d, 0.0)
    return d


def _pairwise(x: FloatArray) -> FloatArray:
    sq = (x**2).sum(axis=1)
    return np.sqrt(np.clip(sq[:, None] + sq[None, :] - 2 * x @ x.T, 0.0, None))


def _kmeans(x: FloatArray, k: int, rng: np.random.Generator, max_iter: int = 300) -> IntArray:
    """Lloyd's k-means with k-means++ seeding, one initialisation (as sklearn ``n_init=1``);
    convergence when the squared centre shift falls below ``1e-4`` x the mean feature variance."""
    n = x.shape[0]
    centres = np.empty((k, x.shape[1]))
    centres[0] = x[rng.integers(n)]
    closest = ((x - centres[0]) ** 2).sum(axis=1)
    for j in range(1, k):
        total = closest.sum()
        pick = rng.integers(n) if total <= 0 else rng.choice(n, p=closest / total)
        centres[j] = x[pick]
        closest = np.minimum(closest, ((x - centres[j]) ** 2).sum(axis=1))
    tol = 1e-4 * float(np.mean(np.var(x, axis=0)))
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(max_iter):
        dist2 = (x**2).sum(axis=1)[:, None] - 2 * x @ centres.T + (centres**2).sum(axis=1)[None, :]
        labels = np.argmin(dist2, axis=1).astype(np.int64)
        member = np.zeros((k, n))
        member[labels, np.arange(n)] = 1.0
        counts = member.sum(axis=1)
        sums = member @ x
        new = np.where(counts[:, None] > 0, sums / np.maximum(counts, 1)[:, None], centres)
        shift = float(((new - centres) ** 2).sum())
        centres = new
        if shift <= tol:
            break
    return labels


def _silhouette(pair: FloatArray, labels: IntArray) -> FloatArray:
    """sklearn ``silhouette_samples`` on precomputed distances: ``(b - a) / max(a, b)``, 0 for a
    singleton and where ``a = b = 0``."""
    ks, inv = np.unique(labels, return_inverse=True)
    n = len(labels)
    if len(ks) < 2:
        return np.zeros(n)
    onehot = np.zeros((n, len(ks)))
    onehot[np.arange(n), inv] = 1.0
    sums = pair @ onehot
    sizes = onehot.sum(axis=0)
    own = sizes[inv]
    a = np.where(own > 1, sums[np.arange(n), inv] / np.maximum(own - 1, 1), 0.0)
    means = sums / sizes[None, :]
    means[np.arange(n), inv] = np.inf
    b = means.min(axis=1)
    denom = np.maximum(a, b)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(denom > 0, (b - a) / denom, 0.0)
    return np.where(own > 1, s, 0.0)


def _tstat(s: FloatArray) -> float:
    sd = float(s.std())
    return float(s.mean()) / sd if sd > 0 else float("nan")


def _onc_base(
    corr: FloatArray, max_k: int, n_init: int, rng: np.random.Generator
) -> tuple[IntArray, FloatArray]:
    x = distance(corr)
    pair = _pairwise(x)
    best_labels = np.zeros(len(corr), dtype=np.int64)
    best_s = np.zeros(len(corr))
    best_stat = float("nan")
    for _ in range(n_init):
        for k in range(2, max_k + 1):
            labels = _kmeans(x, k, rng)
            s = _silhouette(pair, labels)
            stat = _tstat(s)
            if np.isnan(best_stat) or stat > best_stat:
                best_labels, best_s, best_stat = labels, s, stat
    _, relabel = np.unique(best_labels, return_inverse=True)
    return relabel.astype(np.int64), best_s


def _cluster_tstats(labels: IntArray, s: FloatArray) -> dict[int, float]:
    return {int(k): _tstat(s[labels == k]) for k in np.unique(labels)}


def _mean_finite(values: list[float]) -> float:
    finite = [v for v in values if np.isfinite(v)]
    return float(np.mean(finite)) if finite else float("nan")


def _onc_top(
    corr: FloatArray, max_k: int | None, n_init: int, rng: np.random.Generator
) -> tuple[IntArray, FloatArray]:
    n = len(corr)
    if n < 3:
        return np.zeros(n, dtype=np.int64), np.zeros(n)
    cap = n - 1 if max_k is None else min(max_k, n - 1)
    labels, s = _onc_base(corr, cap, n_init, rng)
    tstats = _cluster_tstats(labels, s)
    mean_t = _mean_finite(list(tstats.values()))
    redo = [k for k, v in tstats.items() if np.isfinite(v) and v < mean_t]
    if len(redo) <= 1:
        return labels, s
    redo_idx = np.flatnonzero(np.isin(labels, redo))
    mean_redo = _mean_finite([tstats[k] for k in redo])
    sub_labels, _ = _onc_top(corr[np.ix_(redo_idx, redo_idx)], cap, n_init, rng)
    new = labels.copy()
    keep = sorted(k for k in tstats if k not in redo)
    for i, k in enumerate(keep):
        new[labels == k] = i
    new[redo_idx] = len(keep) + sub_labels
    new_s = _silhouette(_pairwise(distance(corr)), new)
    new_mean = _mean_finite(list(_cluster_tstats(new, new_s).values()))
    if not new_mean > mean_redo:
        return labels, s
    return new, new_s


def onc(
    returns: npt.ArrayLike, *, seed: int, n_init: int = 10, max_clusters: int | None = None
) -> NeffResult:
    """F-7.3 by ONC: the clusters of a trials x time return matrix and their count.

    ``max_clusters`` caps ``k`` (the reference default is ``n - 1``); ``n_init`` restarts each ``k``
    (the reference default is 10). Randomness only through ``seed`` (D-660)."""
    corr = correlation(returns)
    n = len(corr)
    if float(distance(corr).max()) <= 1e-12:  # identical trials: one cluster (see the docstring)
        labels = np.zeros(n, dtype=np.int64)
    else:
        labels, _ = _onc_top(corr, max_clusters, n_init, np.random.default_rng(seed))
    return NeffResult(
        method="onc",
        n_raw=n,
        n_effective=len(np.unique(labels)),
        labels=tuple(int(v) for v in labels),
    )
