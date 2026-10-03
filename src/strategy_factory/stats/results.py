"""Result types of the stage-7 statistics library (T16, F-7.1 ... F-7.7, D-660).

Every function of the library returns one of these frozen objects: the statistic, the p-value or
probability where one exists, and the sizes of what it was computed on. Arrays are stored as
tuples, so a result is immutable and hashable. A result never carries a pass/fail verdict: the
stage-7 gate compares it with ``configs/gates/`` (D-660).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TTestResult(_Result):
    """F-7.1: the t-test of "mean return = 0"; ``lags`` = 0 for the plain test."""

    method: Literal["student_t", "hac_newey_west"]
    statistic: float
    p_value: float  # two-sided
    mean: float
    n: int
    lags: int


class IntervalResult(_Result):
    """F-7.1: a bootstrap confidence interval for a statistic of a return series."""

    statistic_name: Literal["sharpe", "expectancy"]
    estimate: float
    lower: float
    upper: float
    level: float
    n: int
    scheme: Literal["stationary", "circular"]
    method: Literal["percentile", "basic", "bca", "studentized"]
    block_length: float
    reps: int
    seed: int


class PermutationResult(_Result):
    """F-7.2: the Monte-Carlo permutation p-value of an observed statistic."""

    observed: float
    p_value: float
    n_null: int


class NeffResult(_Result):
    """F-7.3: the effective number of trials, with the clusters behind it (D-722)."""

    method: Literal["onc", "hierarchical"]
    n_raw: int
    n_effective: int
    labels: tuple[int, ...]  # the cluster of each trial, in input order
    rho_cut: float | None = None  # hierarchical: the correlation level of the cut


class DSRResult(_Result):
    """F-7.4: the Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014). Sharpe ratios are per
    observation (not annualized); kurtosis is raw (normal = 3)."""

    sharpe: float
    sr0: float  # the expected maximum Sharpe of ``n_effective`` null trials
    probability: float  # the DSR
    n_effective: float
    sharpe_variance: float  # across the trials, per observation
    n_obs: int
    skewness: float
    kurtosis: float


class MinTRLResult(_Result):
    """F-7.7: the Minimum Track Record Length, in observations (Bailey & Lopez de Prado 2012)."""

    sharpe: float
    target_sharpe: float
    confidence: float
    skewness: float
    kurtosis: float
    min_track_record: float  # observations; inf when the Sharpe does not exceed the target


class PBOResult(_Result):
    """F-7.5: the probability of backtest overfitting by CSCV (Bailey et al. 2017)."""

    pbo: float
    logits: tuple[float, ...]  # one per split
    n_splits: int
    partitions: int  # S
    n_trials: int
    n_obs: int


class SPAResult(_Result):
    """F-7.6: Hansen's SPA against a zero benchmark (not trading; D-723), via ``arch``."""

    p_consistent: float
    p_lower: float
    p_upper: float
    n_models: int
    n_obs: int
    block_rule: str  # the rule that chose the block (D-723: pending the measurement)
    block_size: int
    reps: int
    seed: int
