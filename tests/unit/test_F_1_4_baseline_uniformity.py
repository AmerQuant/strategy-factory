"""F-1.4 acceptance: on random-walk data the probe percentiles are approximately uniform.

Every probe of both edge types, both directions, on independent random walks. The pooled
percentiles must look like draws from U(0, 100): mean near 50, about 10 % at or above 90 (the
probe gate's threshold), and a small Kolmogorov-Smirnov distance. Probes on one series are
correlated with each other, so the tolerances are those of a few hundred effective draws, not
of the ~1,000 values pooled.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.edge_stage import make_task, stage_config, synthetic_bars

from strategy_factory.stages.edge import compute_profile

pytestmark = pytest.mark.slow

SERIES = 30


def pooled_percentiles() -> np.ndarray:
    cfg = stage_config(simulations=200)
    out: list[float] = []
    for seed in range(SERIES):
        bars = synthetic_bars(1500, 1000 + seed, phi=0.0)
        for edge_type in ("MR", "TF"):
            for direction in ("long", "short"):
                prof = compute_profile(
                    make_task(
                        bars, edge_type=edge_type, direction=direction, cfg=cfg, run_seed=seed
                    )
                ).profile
                out += [p.percentile for p in prof.probes if p.percentile is not None]
    return np.array(out)


def test_F_1_4_probe_percentiles_on_random_walks_are_about_uniform() -> None:
    pct = pooled_percentiles()
    assert pct.size > 800
    assert abs(pct.mean() - 50.0) < 5.0
    assert 0.05 < float(np.mean(pct >= 90.0)) < 0.16
    grid = np.sort(pct) / 100.0
    ecdf = np.arange(1, grid.size + 1) / grid.size
    assert float(np.max(np.abs(ecdf - grid))) < 0.08  # KS distance to U(0, 1)


def drifted_bars(n: int, seed: int, mu: float, vol: float = 0.006) -> dict:
    """A geometric random walk with drift ``mu`` per bar: no serial structure at all."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(mu, vol, n)))
    open_ = np.concatenate(([100.0], close[:-1]))
    wick = np.abs(rng.normal(0.0, vol / 2, (2, n)))
    return {
        "ts": 1_325_462_400_000_000 + np.arange(n, dtype=np.int64) * 3_600_000_000,
        "open": open_,
        "high": np.maximum(open_, close) * (1 + wick[0]),
        "low": np.minimum(open_, close) * (1 - wick[1]),
        "close": close,
    }


@pytest.mark.parametrize("direction", ["long", "short"])
def test_F_1_4_d618_drift_does_not_make_trend_probes_look_significant(direction: str) -> None:
    """D-618 (amends D-615, P-100). With a second disaster stop in the baseline, a drifted
    random walk gave TF long a mean percentile of 77 with 42 % at or above 90 (the T12 pilot's
    two random-walk control passes). With the baseline holding exactly its drawn periods it is
    about 50 with about 10 %. The bounds catch the old failure; the measured residual (TF short
    up to 58 / 17 % under drift) is reported in docs/reviews/T12_pilot.md, not hidden here."""
    cfg = stage_config(simulations=200)
    pct: list[float] = []
    for seed in range(15):
        prof = compute_profile(
            make_task(drifted_bars(6000, 500 + seed, 0.0006), edge_type="TF",
                      direction=direction, cfg=cfg, run_seed=seed)
        ).profile  # fmt: skip
        pct += [p.percentile for p in prof.probes if p.percentile is not None]
    arr = np.array(pct)
    assert 40.0 < arr.mean() < 62.0
    assert float(np.mean(arr >= 90.0)) < 0.20
