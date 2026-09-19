"""F-0.5.1: grid batch path equals the single-run functions exactly (hand fixtures)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fixtures.metrics_runs import CAPITAL, HAND_TS, hand_run, rising_run

from strategy_factory.metrics import _kernels
from strategy_factory.metrics.batch import core_metrics_batch
from strategy_factory.metrics.standard import compute_metrics, core_metrics

KEYS = (
    "avg_annual_profit_usd",
    "avg_annual_profit_pct",
    "avg_annual_dd_ystart_usd",
    "avg_annual_dd_ystart_pct",
    "profit_dd_ratio",
    "exposure",
)


def test_F_0_5_1_batch_equals_single_hand_fixtures() -> None:
    runs = [hand_run(), rising_run()]
    eq = np.column_stack([r.equity.equity_mtm for r in runs])
    pos = np.column_stack([r.equity.in_position for r in runs])
    closed = np.array([len(r.trades) for r in runs])
    out = core_metrics_batch(eq, pos, closed, HAND_TS, CAPITAL)
    assert set(out) == {*KEYS, "n_trades", "n_entries"}
    for j, run in enumerate(runs):
        single = core_metrics(run.equity)
        for key in KEYS:
            assert out[key][j] == getattr(single, key), key  # bit-identical
        assert out["n_entries"][j] == single.n_entries
        report = compute_metrics(run, calendar="us_equity")
        assert out["n_trades"][j] == report.n_trades
    assert math.isinf(out["profit_dd_ratio"][1])
    # hand fixture: 2 closed trades but 3 entries (T3 is still open at the end)
    assert out["n_trades"].tolist() == [2, 1]
    assert out["n_entries"].tolist() == [3, 1]


def test_F_0_5_1_batch_n_trades_is_the_given_closed_count() -> None:
    rng = np.random.default_rng(5)
    n, m = 10, 16
    eq = CAPITAL + np.cumsum(rng.normal(0, 500, size=(n, m)), axis=0)
    pos = rng.random((n, m)) < 0.5
    closed = rng.integers(0, 20, size=m)
    out = core_metrics_batch(eq, pos, closed, HAND_TS, CAPITAL)
    np.testing.assert_array_equal(out["n_trades"], closed)
    assert out["n_trades"].dtype == np.int64
    # n_entries does not depend on the closed count
    other = core_metrics_batch(eq, pos, np.zeros(m, dtype=np.int64), HAND_TS, CAPITAL)
    np.testing.assert_array_equal(out["n_entries"], other["n_entries"])
    for j in range(m):
        assert out["n_entries"][j] == _kernels.position_entries(pos[:, j])


def test_F_0_5_1_batch_layout_independent() -> None:
    rng = np.random.default_rng(3)
    n, m = 10, 64
    eq = CAPITAL + np.cumsum(rng.normal(0, 500, size=(n, m)), axis=0)
    pos = rng.random((n, m)) < 0.5
    closed = np.arange(m)
    a = core_metrics_batch(np.ascontiguousarray(eq), pos, closed, HAND_TS, CAPITAL)
    b = core_metrics_batch(np.asfortranarray(eq), np.asfortranarray(pos), closed, HAND_TS, CAPITAL)
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])


def test_F_0_5_1_batch_rejects_bad_inputs() -> None:
    eq = np.full((10, 2), CAPITAL)
    pos = np.zeros((10, 2), dtype=bool)
    closed = np.array([0, 0])
    with pytest.raises(ValueError):
        core_metrics_batch(eq, np.zeros((10, 3), dtype=bool), closed, HAND_TS, CAPITAL)
    with pytest.raises(ValueError):
        core_metrics_batch(eq, pos, closed, HAND_TS[:5], CAPITAL)
    with pytest.raises(ValueError, match="n_closed_trades"):
        core_metrics_batch(eq, pos, np.array([0, 0, 0]), HAND_TS, CAPITAL)
    with pytest.raises(ValueError, match="n_closed_trades"):
        core_metrics_batch(eq, pos, np.array([0.0, 1.0]), HAND_TS, CAPITAL)
    with pytest.raises(ValueError, match="n_closed_trades"):
        core_metrics_batch(eq, pos, np.array([0, -1]), HAND_TS, CAPITAL)
