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
