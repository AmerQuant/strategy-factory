"""Stage-1 statistics (F-1.5, D-601, D-605, D-606, D-617): pure NumPy, no thresholds.

* :func:`percentile_of` -- the share of baseline statistics **strictly below** the probe's,
  x100 (T12 §5.4);
* :func:`empirical_p` -- ``(1 + #{baseline >= probe}) / (1 + n)``, floored (D-606);
* :func:`bh_qvalues` -- Benjamini-Hochberg q-values within one profile (D-605);
* :func:`two_proportion_z` -- the pooled two-proportion z-test of the quality split, reported
  as evidence, never a gate (D-617).

A missing statistic (a probe without trades) is ``NaN`` and stays ``NaN``: it gets no
percentile, no p and no q, and does not count in the Benjamini-Hochberg ``m``.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def percentile_of(value: float, dist: npt.ArrayLike) -> float:
    """``100 * mean(dist < value)``; ``NaN`` when ``value`` is NaN or ``dist`` is empty."""
    d = np.asarray(dist, dtype=np.float64)
    if d.size == 0 or math.isnan(value):
        return float("nan")
    return float(100.0 * np.count_nonzero(d < value) / d.size)


def empirical_p(value: float, dist: npt.ArrayLike, floor: float) -> float:
    """One-sided empirical p of ``value`` against ``dist``: ties count against the probe."""
    d = np.asarray(dist, dtype=np.float64)
    if d.size == 0 or math.isnan(value):
        return float("nan")
    p = (1.0 + np.count_nonzero(d >= value)) / (1.0 + d.size)
    return float(max(p, floor))


def bh_qvalues(p: npt.ArrayLike) -> FloatArray:
    """Benjamini-Hochberg step-up q-values; NaN p-values are skipped and stay NaN."""
    pv = np.asarray(p, dtype=np.float64)
    q = np.full(pv.shape, np.nan)
    ok = ~np.isnan(pv)
    m = int(np.count_nonzero(ok))
    if m == 0:
        return q
    vals = pv[ok]
    order = np.argsort(vals, kind="stable")
    ranked = vals[order] * m / np.arange(1, m + 1)
    stepped = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(stepped, 1.0)
    q[ok] = out
    return q


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """``(z, two-sided p)`` of ``x1/n1`` vs ``x2/n2`` with the pooled standard error.

    ``(NaN, NaN)`` when either group is empty or the pooled rate is 0 or 1 (no variance).
    """
    if n1 <= 0 or n2 <= 0:
        return float("nan"), float("nan")
    pooled = (x1 + x2) / (n1 + n2)
    if pooled <= 0.0 or pooled >= 1.0:
        return float("nan"), float("nan")
    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
    z = (x1 / n1 - x2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2.0))
