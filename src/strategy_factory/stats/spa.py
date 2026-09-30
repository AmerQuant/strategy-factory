"""F-7.6: Hansen's test of Superior Predictive Ability, via ``arch`` (T16, D-659, D-723).

Is the best candidate better than the benchmark, once the whole set it was chosen from is taken
into account (Hansen 2005)? The benchmark is **a zero return: not trading** (D-723).

``arch.bootstrap.SPA`` works on **losses** (lower is better), so the candidates' returns are
negated and the benchmark's loss is 0; each candidate's **loss differential** against the
benchmark is then its own return series. ``arch`` returns pandas objects; they are converted here
and nothing pandas leaves this module (CLAUDE.md: pandas only at the edges).

**The block length of SPA's stationary bootstrap is not decided** (D-723, amended: pending the
measurement of ``scripts/analysis/T16_spa_block.py``). The caller passes one rule, which the
stage-7 config will carry as a single key; there is no default:

* ``"pw_max"``, ``"pw_median"``, ``"pw_best"`` -- automatic: Politis-White (2004, with the 2009
  correction; ``arch``'s ``optimal_block_length``, stationary) on each candidate's loss
  differential, aggregated as the **maximum**, the **median**, or the **best candidate's** own
  (the highest mean return);
* ``"cube_root"`` -- fixed: ``round(T^(1/3))``;
* an ``int`` -- an explicit block length.

Automatic lengths are rounded to the nearest integer, at least 1 (``arch``'s SPA takes an int).
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import numpy.typing as npt
from arch.bootstrap import SPA, optimal_block_length

from strategy_factory.stats.results import SPAResult

SpaBlockRule = Literal["pw_max", "pw_median", "pw_best", "cube_root"]


def spa_block_length(returns: npt.ArrayLike, rule: SpaBlockRule | int) -> int:
    """The SPA block length of a ``time x models`` return matrix under ``rule``."""
    x = np.asarray(returns, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if isinstance(rule, int):
        if rule < 1:
            raise ValueError(f"an explicit block length must be >= 1, got {rule}")
        return rule
    t = x.shape[0]
    if rule == "cube_root":
        return max(1, round(t ** (1 / 3)))
    if rule == "pw_best":
        x = x[:, [int(np.argmax(x.mean(axis=0)))]]
    lengths = optimal_block_length(x)["stationary"].to_numpy(dtype=np.float64)
    if rule == "pw_max":
        value = float(lengths.max())
    elif rule == "pw_median":
        value = float(np.median(lengths))
    elif rule == "pw_best":
        value = float(lengths[0])
    else:
        raise ValueError(f"unknown SPA block rule {rule!r}")
    return max(1, round(value))


def spa_test(
    returns: npt.ArrayLike, *, block: SpaBlockRule | int, reps: int, seed: int
) -> SPAResult:
    """F-7.6: the three SPA p-values of a ``time x models`` return matrix against not trading."""
    x = np.asarray(returns, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError(f"returns must be time x models, got {x.shape}")
    if np.isnan(x).any():
        raise ValueError("returns contain NaN")
    if reps < 1:
        raise ValueError(f"reps must be >= 1, got {reps}")
    t, n = x.shape
    block_size = spa_block_length(x, block)
    spa = SPA(np.zeros(t), -x, block_size=block_size, reps=reps, seed=seed)
    spa.compute()
    p = spa.pvalues
    return SPAResult(
        p_consistent=float(p["consistent"]),
        p_lower=float(p["lower"]),
        p_upper=float(p["upper"]),
        n_models=n,
        n_obs=t,
        block_rule=str(block),
        block_size=block_size,
        reps=reps,
        seed=seed,
    )
