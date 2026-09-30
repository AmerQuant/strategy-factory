"""F-7.2: the Monte-Carlo permutation p-value (T16, D-660).

The observed statistic of a candidate is compared with the same statistic on random-entry runs
over the same data (stage 1's matched baseline, F-1.4, supplies them; producing them is not this
library's). The p-value counts the null runs at least as good as the observation, with the
standard +1 correction so that it is never 0 and is exactly valid under the null:

    p = (1 + #{null >= observed}) / (1 + n)

A NaN observation gives a NaN p (D-651 (1): NaN never passes); NaN null values are dropped and not
counted in ``n``.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from strategy_factory.stats.results import PermutationResult


def permutation_p_value(observed: float, null: npt.ArrayLike) -> PermutationResult:
    """F-7.2: ``(1 + #{null >= observed}) / (1 + n)``, one-sided (larger is better)."""
    values = np.asarray(null, dtype=np.float64).ravel()
    values = values[~np.isnan(values)]
    n = int(values.size)
    if math.isnan(observed):
        p = math.nan
    else:
        p = (1 + int(np.count_nonzero(values >= observed))) / (1 + n)
    return PermutationResult(observed=observed, p_value=p, n_null=n)
