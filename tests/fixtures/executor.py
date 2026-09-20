"""Picklable helpers for the executor tests (F-0.3.7).

Everything a worker runs must be importable in a **spawned** child process (D-334), so the
work functions live here, at module level, not in the test module.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import numpy as np

from strategy_factory.engine.api import CostInputs, MarketArrays, SizingInputs
from strategy_factory.pipeline.executor import GridJob, WorkUnit, run_grid

T0 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def bars(n: int, seed: int = 7) -> dict[str, np.ndarray]:
    """A deterministic synthetic series with a usable ATR and a few turning points."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n))
    close = np.maximum(close, 10.0)
    high = close + rng.uniform(0.2, 1.2, n)
    low = close - rng.uniform(0.2, 1.2, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    atr = np.full(n, 1.0)
    ts = np.array([np.datetime64(T0.replace(tzinfo=None), "ns")] * n) + (
        np.arange(n) * np.timedelta64(1, "D")
    )
    return {"open": open_, "high": high, "low": low, "close": close, "atr": atr, "ts": ts}


def grid_job(n_bars: int, n_configs: int, seed: int = 7, atr_scale: float = 1.0) -> GridJob:
    """A grid of ``n_configs`` exit variants on one synthetic series."""
    b = bars(n_bars, seed)
    rng = np.random.default_rng(seed + 1)
    entry = rng.random((n_bars, n_configs)) < 0.05
    exit_ = np.zeros((n_bars, n_configs), dtype=np.bool_)
    zeros = np.zeros(n_bars)
    return GridJob(
        market=MarketArrays(
            b["open"], b["high"], b["low"], b["close"], b["atr"] * float(atr_scale)
        ),
        entry_matrix=entry,
        exit_matrix=exit_,
        direction=1,
        time_exit_bars=np.full(n_configs, 5, dtype=np.int64),
        sl_atr=np.linspace(1.0, 3.0, n_configs),
        tp_atr=np.linspace(1.5, 4.0, n_configs),
        trail_atr=np.full(n_configs, np.nan),
        disaster_atr=3.0,
        costs=CostInputs(
            half_spread=np.full(n_bars, 0.01),
            slippage_fixed=zeros.copy(),
            slippage_atr_frac=0.0,
            swap_long=zeros.copy(),
            swap_short=zeros.copy(),
            rollover_mask=np.zeros(n_bars, dtype=np.bool_),
            triple_mask=np.zeros(n_bars, dtype=np.bool_),
            commission_params=(0, 0.0, 0.0, 0.0),
        ),
        sizing=SizingInputs(mode=0, notional=100_000.0, initial_capital=100_000.0),
        intrabar_mode=1,
        ts=b["ts"],
        initial_capital=100_000.0,
    )


# -- work functions (must be importable in a spawned worker) ---------------------------
def run_unit(unit: WorkUnit) -> dict[str, Any]:
    """Run the unit's grid and return its metrics table plus the unit's seed and pid."""
    payload = dict(unit.payload or {})
    job = grid_job(
        payload["n_bars"],
        payload["n_configs"],
        payload.get("seed", 7),
        payload.get("atr_scale", 1.0),
    )
    table = run_grid(job, chunk_cols=payload.get("chunk_cols"))
    return {
        "key": unit.key,
        "seed": unit.seed,  # filled by `seeded` in the parent (D-334)
        "pid": os.getpid(),
        "metrics": {name: values.tolist() for name, values in sorted(table.items())},
    }


def echo_key(unit: WorkUnit) -> str:
    """Trivial unit of work: its own key (used for order and failure tests)."""
    return unit.key


def fail_on_qqq(unit: WorkUnit) -> str:
    """Fails for the QQQ unit only, so the error names one key and the rest survive."""
    if unit.symbol == "QQQ":
        raise ValueError("planted failure")
    return unit.key


def numba_threads(unit: WorkUnit) -> int:
    """The Numba thread count the worker was initialised with (D-334)."""
    import numba

    return int(numba.get_num_threads())


def write_from_worker(unit: WorkUnit) -> str:
    """Try to create a registry writer inside the worker (D-012: the parent writes)."""
    from typing import cast

    from sqlalchemy import Engine

    from strategy_factory.registry.writer import RegistryWriter

    RegistryWriter(cast(Engine, None))
    return unit.key


def worker_flag(unit: WorkUnit) -> bool:
    """Whether this process is marked as an executor worker."""
    from strategy_factory.core.env import in_executor_worker

    return in_executor_worker()
