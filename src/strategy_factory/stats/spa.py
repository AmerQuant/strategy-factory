"""F-7.6: Hansen's test of Superior Predictive Ability, via ``arch`` (T16, D-659, D-723).

Is the best candidate better than the benchmark, once the whole set it was chosen from is taken
into account (Hansen 2005)? The benchmark is **a zero return: not trading** (D-723).

``arch.bootstrap.SPA`` works on **losses** (lower is better), so the candidates' returns are
negated and the benchmark's loss is 0. ``arch`` returns pandas objects; they are converted here and
nothing pandas leaves this module (CLAUDE.md: pandas only at the edges). The block size of SPA's
stationary bootstrap is an explicit argument: ``arch`` would otherwise pick its own.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from arch.bootstrap import SPA

from strategy_factory.stats.results import SPAResult


def spa_test(returns: npt.ArrayLike, *, block_size: int, reps: int, seed: int) -> SPAResult:
    """F-7.6: the three SPA p-values of a ``time x models`` return matrix against not trading."""
    x = np.asarray(returns, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError(f"returns must be time x models, got {x.shape}")
    if np.isnan(x).any():
        raise ValueError("returns contain NaN")
    if block_size < 1 or reps < 1:
        raise ValueError(f"block_size and reps must be >= 1, got {block_size}, {reps}")
    t, n = x.shape
    spa = SPA(np.zeros(t), -x, block_size=block_size, reps=reps, seed=seed)
    spa.compute()
    p = spa.pvalues
    return SPAResult(
        p_consistent=float(p["consistent"]),
        p_lower=float(p["lower"]),
        p_upper=float(p["upper"]),
        n_models=n,
        n_obs=t,
        block_size=block_size,
        reps=reps,
        seed=seed,
    )
