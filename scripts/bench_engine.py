"""Engine benchmark for the T08 review (no thresholds; numbers are reported only).

uv run python scripts/bench_engine.py
"""

from __future__ import annotations

import math
import os
import time

import numba
import numpy as np

from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import (
    CostInputs,
    ExitParams,
    MarketArrays,
    SizingInputs,
    simulate,
    simulate_grid,
)


def series(n: int, seed: int) -> MarketArrays:
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, n)))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.002, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.002, n)))
    return MarketArrays(o, h, lo, c, np.abs(h - lo) + 0.05)


def costs(n: int) -> CostInputs:
    z = np.zeros(n)
    roll = np.zeros(n, np.bool_)
    roll[::24] = True
    return CostInputs(np.full(n, 0.01), np.full(n, 0.005), 0.02, np.full(n, -0.0002), z, roll,
                      np.zeros(n, np.bool_), (3, 1.0, 0.03, 0.0))  # fmt: skip


def main() -> None:
    sizing = SizingInputs(k.SIZE_RESEARCH, 100_000.0, 100_000.0, 1.0, 0.1, 0.1, 1e-9)
    n = 60_000
    m = series(n, 1)
    rng = np.random.default_rng(2)
    ent, ext = rng.random(n) < 0.05, rng.random(n) < 0.05
    exits = ExitParams(20, 1.5, 3.0, math.nan, 3.0)
    simulate(m, ent, ext, 1, exits, costs(n), sizing, k.MODE_PESSIMISTIC)  # compile
    t = time.perf_counter()
    r = simulate(m, ent, ext, 1, exits, costs(n), sizing, k.MODE_PESSIMISTIC)
    single = time.perf_counter() - t
    print(f"simulate: {n} bars, {r.entry_idx.size} trades: {single * 1000:.1f} ms")

    n, cfg = 2_500, 2_000
    m = series(n, 3)
    ent = rng.random((n, cfg)) < 0.05
    ext = rng.random((n, cfg)) < 0.05
    te = rng.integers(0, 30, cfg)
    sl = rng.uniform(0.5, 3, cfg)
    nan = np.full(cfg, np.nan)
    args = (m, ent, ext, 1, te, sl, nan, nan, 3.0, costs(n), sizing, k.MODE_PESSIMISTIC)
    simulate_grid(*args)  # compile
    t = time.perf_counter()
    g = simulate_grid(*args)
    grid = time.perf_counter() - t
    print(
        f"simulate_grid: {cfg} configs x {n} bars ({int(g.n_closed_trades.sum())} trades), "
        f"{numba.get_num_threads()} threads, {os.cpu_count()} cores: {grid * 1000:.1f} ms"
    )


if __name__ == "__main__":
    main()
