"""D-615: the random-walk control permutes a series' own returns -- same volatility and drift,
no serial structure, every bar's shape kept."""

from __future__ import annotations

import numpy as np
from fixtures.indicator_cases import random_ohlc

from strategy_factory.stages.control import permute_returns


def series(n: int = 500) -> dict[str, np.ndarray]:
    o, h, lo, c = random_ohlc(3, n)
    return {"ts": np.arange(n, dtype=np.int64), "open": o, "high": h, "low": lo, "close": c,
            "volume": np.arange(n, dtype=np.float64)}  # fmt: skip


def test_F_1_5_d615_the_returns_are_a_permutation_of_the_originals() -> None:
    b = series()
    out = permute_returns(b, seed=7)
    before = np.sort(np.diff(np.log(b["close"])))
    after = np.sort(np.diff(np.log(out["close"])))
    np.testing.assert_allclose(after, before, atol=1e-12)  # same multiset: vol and drift kept
    assert out["close"][0] == b["close"][0]
    np.testing.assert_allclose(out["close"][-1], b["close"][-1], rtol=1e-9)  # same total drift
    assert not np.allclose(out["close"], b["close"])  # but a different path


def test_F_1_5_d615_each_bar_keeps_its_shape_and_the_rest_is_untouched() -> None:
    b = series()
    out = permute_returns(b, seed=7)
    for col in ("open", "high", "low"):
        np.testing.assert_allclose(out[col] / out["close"], b[col] / b["close"], rtol=1e-12)
    assert (out["high"] >= out["low"]).all()
    np.testing.assert_array_equal(out["ts"], b["ts"])
    np.testing.assert_array_equal(out["volume"], b["volume"])


def test_F_1_5_d615_the_control_is_seeded() -> None:
    b = series()
    np.testing.assert_array_equal(permute_returns(b, 1)["close"], permute_returns(b, 1)["close"])
    assert not np.array_equal(permute_returns(b, 1)["close"], permute_returns(b, 2)["close"])


def test_F_1_5_d615_serial_structure_is_destroyed() -> None:
    """A strongly trending-then-reverting path has lag-1 autocorrelation near 0 after it."""
    n = 4000
    rng = np.random.default_rng(0)
    r = np.empty(n - 1)
    r[0] = 0.0
    for i in range(1, n - 1):  # AR(1) with phi = 0.6
        r[i] = 0.6 * r[i - 1] + rng.normal(0, 0.01)
    close = 100 * np.exp(np.concatenate(([0.0], np.cumsum(r))))
    b = {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close}
    out = np.diff(np.log(permute_returns(b, 5)["close"]))
    ac = np.corrcoef(out[:-1], out[1:])[0, 1]
    assert abs(np.corrcoef(r[:-1], r[1:])[0, 1] - 0.6) < 0.05
    assert abs(ac) < 0.05
