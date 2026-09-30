"""F-7.5: the probability of backtest overfitting by CSCV (T16, D-660, D-724).

Bailey, Borwein, Lopez de Prado & Zhu (2017), "The Probability of Backtest Overfitting":

1. The trials x time performance matrix is cut into ``S`` (even) contiguous blocks of time.
2. For each of the ``C(S, S/2)`` ways to pick half the blocks as in-sample (the rest out of sample),
   the trial with the best in-sample Sharpe is selected, and its out-of-sample rank among all
   trials gives the relative rank ``w = rank / (N + 1)`` and the logit ``log(w / (1 - w))``.
3. ``PBO`` is the share of splits whose logit is <= 0: the selected trial did no better than the
   median out of sample.

The library takes any trials x time matrix (D-724); which trials and where the matrix comes from
are the stage-7 task's. Ties in the out-of-sample Sharpe share their average rank; a trial whose
Sharpe is undefined on a half (constant returns) ranks lowest.
"""

from __future__ import annotations

from itertools import combinations
from math import comb

import numpy as np
import numpy.typing as npt

from strategy_factory.stats.results import PBOResult


def _sharpe(sums: np.ndarray, sq: np.ndarray, cnt: np.ndarray, mask: np.ndarray) -> np.ndarray:
    k = cnt[mask].sum()
    mean = sums[:, mask].sum(axis=1) / k
    var = sq[:, mask].sum(axis=1) / k - mean**2
    with np.errstate(divide="ignore", invalid="ignore"):
        out = mean / np.sqrt(var)
    return np.where(var > 0, out, -np.inf)


def pbo_cscv(performance: npt.ArrayLike, partitions: int) -> PBOResult:
    """F-7.5: PBO over ``C(partitions, partitions / 2)`` splits of a trials x time matrix."""
    x = np.asarray(performance, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError(f"performance must be trials x time with at least 2 trials, got {x.shape}")
    n, t = x.shape
    if partitions < 2 or partitions % 2 or partitions > t:
        raise ValueError(f"partitions must be even, >= 2 and <= {t}, got {partitions}")
    if np.isnan(x).any():
        raise ValueError("performance contains NaN")
    blocks = np.array_split(np.arange(t), partitions)
    sums = np.stack([x[:, b].sum(axis=1) for b in blocks], axis=1)
    sq = np.stack([(x[:, b] ** 2).sum(axis=1) for b in blocks], axis=1)
    cnt = np.array([len(b) for b in blocks], dtype=np.float64)
    logits = []
    for is_blocks in combinations(range(partitions), partitions // 2):
        mask = np.zeros(partitions, dtype=bool)
        mask[list(is_blocks)] = True
        best = int(np.argmax(_sharpe(sums, sq, cnt, mask)))
        oos = _sharpe(sums, sq, cnt, ~mask)
        below = int(np.count_nonzero(oos < oos[best]))
        ties = int(np.count_nonzero(oos == oos[best])) - 1
        w = (below + 0.5 * ties + 1) / (n + 1)
        logits.append(float(np.log(w / (1 - w))))
    lg = np.asarray(logits)
    return PBOResult(
        pbo=float(np.mean(lg <= 0)),
        logits=tuple(logits),
        n_splits=comb(partitions, partitions // 2),
        partitions=partitions,
        n_trials=n,
        n_obs=t,
    )
