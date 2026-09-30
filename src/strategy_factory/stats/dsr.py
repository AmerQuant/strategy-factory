"""F-7.4 the Deflated Sharpe Ratio and F-7.7 the Minimum Track Record Length (T16, D-660).

Both after Bailey & Lopez de Prado. Sharpe ratios are **per observation** (not annualized) and
kurtosis is **raw** (normal = 3), as in the papers' formulas; the reference values are in
``docs/tasks/T16_plan.md`` §6.

* The Probabilistic Sharpe Ratio of an observed ``SR`` against a reference ``SR*`` over ``T``
  observations (2012, eq. 3):
  ``PSR = Phi((SR - SR*) sqrt(T - 1) / sqrt(1 - g3 SR + (g4 - 1) / 4 SR^2))``.
* The DSR (2014) is the PSR against ``SR_0``, the expected maximum Sharpe of ``N`` independent
  null trials whose Sharpes have variance ``V`` (eq. 1, with Euler-Mascheroni ``gamma``):
  ``SR_0 = sqrt(V) ((1 - gamma) Phi^-1(1 - 1/N) + gamma Phi^-1(1 - 1/(N e)))``.
* MinTRL (2012, eq. 10): ``1 + (1 - g3 SR + (g4 - 1) / 4 SR^2) (Z_alpha / (SR - SR*))^2``.

No threshold lives here: the result carries the probability; the gate compares it (D-660).
"""

from __future__ import annotations

import math
from statistics import NormalDist

from strategy_factory.stats.results import DSRResult, MinTRLResult

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def _sr_scale(sharpe: float, skewness: float, kurtosis: float) -> float:
    """``1 - g3 SR + (g4 - 1) / 4 SR^2``: the Sharpe estimator's variance factor."""
    return 1.0 - skewness * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2


def probabilistic_sharpe(
    sharpe: float, reference: float, n_obs: int, skewness: float, kurtosis: float
) -> float:
    """The PSR: the probability that the true Sharpe exceeds ``reference``. NaN in, NaN out."""
    scale = _sr_scale(sharpe, skewness, kurtosis)
    if any(math.isnan(v) for v in (sharpe, reference, skewness, kurtosis)) or n_obs < 2:
        return math.nan
    if scale <= 0:
        return math.nan
    return _N.cdf((sharpe - reference) * math.sqrt(n_obs - 1) / math.sqrt(scale))


def expected_max_sharpe(n_effective: float, sharpe_variance: float) -> float:
    """``SR_0``: the expected maximum Sharpe of ``n_effective`` null trials (2014, eq. 1).

    One trial (or fewer) has no selection to deflate: ``SR_0 = 0``."""
    if math.isnan(n_effective) or math.isnan(sharpe_variance) or sharpe_variance < 0:
        return math.nan
    if n_effective <= 1:
        return 0.0
    return math.sqrt(sharpe_variance) * (
        (1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_effective)
        + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_effective * math.e))
    )


def deflated_sharpe(
    sharpe: float,
    n_obs: int,
    skewness: float,
    kurtosis: float,
    n_effective: float,
    sharpe_variance: float,
) -> DSRResult:
    """F-7.4: the DSR of the selected ``sharpe`` after ``n_effective`` trials (F-7.3)."""
    sr0 = expected_max_sharpe(n_effective, sharpe_variance)
    return DSRResult(
        sharpe=sharpe,
        sr0=sr0,
        probability=probabilistic_sharpe(sharpe, sr0, n_obs, skewness, kurtosis),
        n_effective=n_effective,
        sharpe_variance=sharpe_variance,
        n_obs=n_obs,
        skewness=skewness,
        kurtosis=kurtosis,
    )


def min_track_record_length(
    sharpe: float, target_sharpe: float, confidence: float, skewness: float, kurtosis: float
) -> MinTRLResult:
    """F-7.7: observations needed for ``sharpe`` to exceed ``target_sharpe`` at ``confidence``.

    Infinite when ``sharpe`` does not exceed the target: no track record is long enough."""
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    scale = _sr_scale(sharpe, skewness, kurtosis)
    if any(math.isnan(v) for v in (sharpe, target_sharpe, skewness, kurtosis)) or scale <= 0:
        length = math.nan
    elif sharpe <= target_sharpe:
        length = math.inf
    else:
        length = 1 + scale * (_N.inv_cdf(confidence) / (sharpe - target_sharpe)) ** 2
    return MinTRLResult(
        sharpe=sharpe,
        target_sharpe=target_sharpe,
        confidence=confidence,
        skewness=skewness,
        kurtosis=kurtosis,
        min_track_record=length,
    )
