"""F-0.5.1: grid batch path equals the single-run functions exactly (hand fixtures)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fixtures.metrics_runs import CAPITAL, HAND_TS, hand_run, rising_run

from strategy_factory.metrics.batch import core_metrics_batch
from strategy_factory.metrics.standard import core_metrics

KEYS = (
    "avg_annual_profit_usd",
    "avg_annual_profit_pct",
    "avg_annual_dd_ystart_usd",
    "avg_annual_dd_ystart_pct",
    "profit_dd_ratio",
    "exposure",
)


def test_F_0_5_1_batch_equals_single_hand_fixtures() -> None:
    curves = [hand_run().equity, rising_run().equity]
    eq = np.column_stack([c.equity_mtm for c in curves])
    pos = np.column_stack([c.in_position for c in curves])
    out = core_metrics_batch(eq, pos, HAND_TS, CAPITAL)
    assert set(out) == {*KEYS, "n_trades"}
    for j, curve in enumerate(curves):
        single = core_metrics(curve)
        for key in KEYS:
            assert out[key][j] == getattr(single, key), key  # bit-identical
        assert out["n_trades"][j] == single.n_position_entries
    assert math.isinf(out["profit_dd_ratio"][1])
    assert out["n_trades"].tolist() == [3, 1]


def test_F_0_5_1_batch_layout_independent() -> None:
    rng = np.random.default_rng(3)
    n, m = 10, 64
    eq = CAPITAL + np.cumsum(rng.normal(0, 500, size=(n, m)), axis=0)
    pos = rng.random((n, m)) < 0.5
    a = core_metrics_batch(np.ascontiguousarray(eq), pos, HAND_TS, CAPITAL)
    b = core_metrics_batch(np.asfortranarray(eq), np.asfortranarray(pos), HAND_TS, CAPITAL)
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])


def test_F_0_5_1_batch_rejects_bad_shapes() -> None:
    eq = np.full((10, 2), CAPITAL)
    with pytest.raises(ValueError):
        core_metrics_batch(eq, np.zeros((10, 3), dtype=bool), HAND_TS, CAPITAL)
    with pytest.raises(ValueError):
        core_metrics_batch(eq, np.zeros((10, 2), dtype=bool), HAND_TS[:5], CAPITAL)
