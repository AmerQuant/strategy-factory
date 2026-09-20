"""Batch and parallel execution (F-0.3.7, ADR-005, design §10).

Two levels on one machine, behind one interface:

1. **inside a process:** the Numba grid kernel over ``prange`` (T08);
2. **between processes:** an :class:`Executor` over work units, one unit = one
   ``(symbol, timeframe, stage)`` triple (design §10).

Rules
-----
* **Deterministic.** ``map`` returns results in **input order**, and every unit gets a seed
  derived from ``(run seed, unit key)``, never from a worker id (D-334). Parallel therefore
  equals serial, bit for bit.
* **Start method ``spawn`` everywhere** (D-334), so Windows and Ubuntu behave the same and a
  worker never inherits a half-initialised Numba or database handle.
* **Thread budget** (D-334): ``workers x numba_threads <= os.cpu_count()``. Both come from
  ``configs/pipeline/executor.yaml``; each worker calls ``numba.set_num_threads`` before any
  kernel runs.
* **Grid chunking** (D-331): a grid runs in column chunks small enough that
  ``n_bars x chunk_cols x 8 bytes x 2`` (equity and in-position matrices) stays under
  ``max_grid_bytes``. Only the metrics of each chunk are kept, never the matrices.
* **Only the parent writes to the registry** (D-012, D-334): workers return results, the
  parent turns them into trial rows and hands them to the batched ``RegistryWriter``. One
  trial per evaluated configuration (F-0.7.1).
* A failing unit does not lose the finished ones: both executors run **every** unit, then
  raise one :class:`ExecutorError` that carries the results of the units that completed (with
  ``None`` where a unit failed) and names every failed unit by its key.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import multiprocessing
import os
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar

import numpy as np
import yaml
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.core.env import mark_executor_worker
from strategy_factory.core.errors import ConfigError, ExecutorError
from strategy_factory.engine.api import CostInputs, MarketArrays, SizingInputs, simulate_grid
from strategy_factory.metrics.batch import core_metrics_batch

DEFAULT_EXECUTOR_CONFIG = Path("configs") / "pipeline" / "executor.yaml"
#: Bytes per configuration and bar held while a chunk runs: the float64 equity matrix plus
#: the in-position matrix, counted as float64 too (D-331, the task's ``8 bytes x 2``).
BYTES_PER_CELL = 16
T = TypeVar("T")
R = TypeVar("R")


# --------------------------------------------------------------------------------------
# Configuration and thread budget
# --------------------------------------------------------------------------------------
class ExecutorConfig(BaseModel):
    """``configs/pipeline/executor.yaml``; defaults live here (CLAUDE.md rule 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workers: int | Literal["auto"] = "auto"
    numba_threads: int | Literal["auto"] = "auto"
    max_grid_bytes: int = Field(default=512 * 1024 * 1024, gt=0)  # D-331

    def _positive(self) -> None:
        for name in ("workers", "numba_threads"):
            value = getattr(self, name)
            if value != "auto" and int(value) < 1:
                raise ValueError(f"{name} must be >= 1 or 'auto'")


def load_executor_config(path: Path | None = None) -> ExecutorConfig:
    target = path if path is not None else DEFAULT_EXECUTOR_CONFIG
    if not target.is_file():
        return ExecutorConfig()
    try:
        cfg = ExecutorConfig.model_validate(
            yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        )
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read executor config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid executor config: {exc}", config_path=target) from exc
    try:
        cfg._positive()
    except ValueError as exc:
        raise ConfigError(f"invalid executor config: {exc}", config_path=target) from exc
    return cfg


@dataclass(frozen=True)
class ThreadBudget:
    """How many processes run, and how many Numba threads each of them may use."""

    workers: int
    numba_threads: int
    cpu_count: int

    @property
    def total_threads(self) -> int:
        return self.workers * self.numba_threads


def resolve_budget(cfg: ExecutorConfig, cpu_count: int | None = None) -> ThreadBudget:
    """Split ``cpu_count`` cores between processes and Numba threads (D-334; rule: D-351).

    ``auto`` resolves as follows, so the product never exceeds the core count:

    * both auto: ``workers = floor(sqrt(cpu))``, ``numba_threads = cpu // workers``;
    * one given: the other is ``max(1, cpu // given)``;
    * both given: used as they are, and refused when their product exceeds ``cpu``.
    """
    cpu = int(cpu_count if cpu_count is not None else (os.cpu_count() or 1))
    cpu = max(1, cpu)
    w_cfg, t_cfg = cfg.workers, cfg.numba_threads
    if w_cfg == "auto" and t_cfg == "auto":
        workers = max(1, int(cpu**0.5))
        threads = max(1, cpu // workers)
    elif w_cfg == "auto":
        threads = max(1, int(t_cfg))
        workers = max(1, cpu // threads)
    elif t_cfg == "auto":
        workers = max(1, int(w_cfg))
        threads = max(1, cpu // workers)
    else:
        workers, threads = max(1, int(w_cfg)), max(1, int(t_cfg))
        if workers * threads > cpu:
            raise ConfigError(
                f"executor config asks for {workers} workers x {threads} numba threads = "
                f"{workers * threads} threads on {cpu} cores (D-334)",
                config_path=DEFAULT_EXECUTOR_CONFIG,
            )
    return ThreadBudget(workers=workers, numba_threads=threads, cpu_count=cpu)


# --------------------------------------------------------------------------------------
# Work units and seeds
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class WorkUnit:
    """One unit of work: a symbol, a timeframe and a stage (design §10), plus its payload.

    ``seed`` is filled by :func:`seeded` before the units are handed to an executor, so the
    work function reads it from the unit instead of deriving anything from the process it
    runs in (D-334).
    """

    symbol: str
    timeframe: str
    stage: str
    payload: Any = None
    seed: int | None = None

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.timeframe}|{self.stage}"


class HasKey(Protocol):
    @property
    def key(self) -> str: ...


def unit_key(unit: object) -> str:
    """The stable key of a work unit: its ``key`` attribute, else its ``repr``."""
    key = getattr(unit, "key", None)
    return key if isinstance(key, str) else repr(unit)


def unit_seed(run_seed: int, key: str) -> int:
    """Seed of one work unit: sha256 of ``(run seed, key)`` (D-334), never a worker id."""
    digest = hashlib.sha256(f"{int(run_seed)}|{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def unit_seeds(run_seed: int, units: Iterable[object]) -> dict[str, int]:
    """``{unit key: seed}`` for ``units``; the same key always gives the same seed."""
    return {unit_key(u): unit_seed(run_seed, unit_key(u)) for u in units}


def seeded(run_seed: int, units: Iterable[WorkUnit]) -> list[WorkUnit]:
    """``units`` with their seed filled from ``(run_seed, key)`` (D-334).

    Call this once in the parent; a worker then never derives a seed itself, so a unit
    computed serially and in parallel starts from the same state.
    """
    return [replace(u, seed=unit_seed(run_seed, u.key)) for u in units]


# --------------------------------------------------------------------------------------
# Executors
# --------------------------------------------------------------------------------------
class Executor(Protocol):
    """Runs ``fn`` over work units and returns the results **in input order** (ADR-005)."""

    def map(self, fn: Callable[[Any], Any], work_units: Sequence[Any]) -> list[Any]: ...


class SerialExecutor:
    """The reference implementation: one process, in order. Always available."""

    name = "serial"

    def map(self, fn: Callable[[Any], Any], work_units: Sequence[Any]) -> list[Any]:
        units = list(work_units)
        results: list[Any] = [None] * len(units)
        failed: dict[str, BaseException] = {}
        for i, unit in enumerate(units):
            try:
                results[i] = fn(unit)
            except Exception as exc:  # any unit error, reported per unit below
                failed[unit_key(unit)] = exc
        if failed:
            raise _failure(units, results, failed)
        return results


def _failure(
    units: Sequence[Any], results: list[Any], failed: dict[str, BaseException]
) -> ExecutorError:
    """One error shape for both executors: every failed key, the finished results kept."""
    names = ", ".join(sorted(failed))
    first = next(iter(failed.values()))
    return ExecutorError(
        f"{len(failed)} of {len(units)} work unit(s) failed: {names} "
        f"(first error: {first}); {len(units) - len(failed)} result(s) kept",
        results=results,
        failed=failed,
    )


def _init_worker(numba_threads: int) -> None:
    """Worker start-up: mark the process and pin the Numba thread count before any kernel.

    The count is clamped to Numba's own maximum (``NUMBA_NUM_THREADS``, fixed when numba is
    imported), so an environment that allows fewer threads than the budget lowers the budget
    instead of failing silently. Any other failure kills the worker loudly.
    """
    import numba

    mark_executor_worker()  # D-012: a worker may not write to the registry
    allowed = int(getattr(numba.config, "NUMBA_NUM_THREADS", numba_threads))
    numba.set_num_threads(max(1, min(numba_threads, allowed)))


class LocalExecutor:
    """Process pool on one machine (ADR-005), ``spawn`` on every platform (D-334)."""

    name = "local"

    def __init__(self, config: ExecutorConfig | None = None, cpu_count: int | None = None) -> None:
        self.config = config if config is not None else load_executor_config()
        self.budget = resolve_budget(self.config, cpu_count)

    def map(self, fn: Callable[[Any], Any], work_units: Sequence[Any]) -> list[Any]:
        units = list(work_units)
        if not units:
            return []
        ctx = multiprocessing.get_context("spawn")
        results: list[Any] = [None] * len(units)
        failed: dict[str, BaseException] = {}
        with cf.ProcessPoolExecutor(
            max_workers=self.budget.workers,
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(self.budget.numba_threads,),
        ) as pool:
            futures = [pool.submit(fn, unit) for unit in units]
            for i, (unit, future) in enumerate(zip(units, futures, strict=True)):
                try:
                    results[i] = future.result()
                except Exception as exc:  # any worker error, reported per unit below
                    failed[unit_key(unit)] = exc
        if failed:
            raise _failure(units, results, failed)
        return results


def make_executor(config: ExecutorConfig | None = None, cpu_count: int | None = None) -> Executor:
    """:class:`SerialExecutor` when the budget allows one worker, else :class:`LocalExecutor`."""
    cfg = config if config is not None else load_executor_config()
    if resolve_budget(cfg, cpu_count).workers == 1:
        return SerialExecutor()
    return LocalExecutor(cfg, cpu_count)


# --------------------------------------------------------------------------------------
# Grid execution in column chunks (D-331)
# --------------------------------------------------------------------------------------
def chunk_columns(n_bars: int, n_configs: int, max_grid_bytes: int) -> int:
    """Configurations per chunk so ``n_bars x chunk x 16 bytes <= max_grid_bytes`` (D-331)."""
    if n_bars < 1 or n_configs < 1:
        raise ValueError("n_bars and n_configs must be >= 1")
    per_col = n_bars * BYTES_PER_CELL
    return max(1, min(n_configs, max_grid_bytes // per_col))


@dataclass(frozen=True)
class GridJob:
    """One parameter grid on one series: signal matrices ``(n_bars, n_configs)`` + exits."""

    market: MarketArrays
    entry_matrix: NDArray[np.bool_]
    exit_matrix: NDArray[np.bool_]
    direction: int
    time_exit_bars: NDArray[np.int64]
    sl_atr: NDArray[np.float64]
    tp_atr: NDArray[np.float64]
    trail_atr: NDArray[np.float64]
    disaster_atr: float
    costs: CostInputs
    sizing: SizingInputs
    intrabar_mode: int
    ts: NDArray[np.datetime64]
    initial_capital: float
    fx_open: NDArray[np.float64] | None = None
    fx_close: NDArray[np.float64] | None = None

    @property
    def n_bars(self) -> int:
        return int(np.asarray(self.entry_matrix).shape[0])

    @property
    def n_configs(self) -> int:
        return int(np.asarray(self.entry_matrix).shape[1])

    def columns(self, lo: int, hi: int) -> GridJob:
        """The same job restricted to the configurations ``[lo, hi)``."""
        return replace(
            self,
            entry_matrix=np.ascontiguousarray(self.entry_matrix[:, lo:hi]),
            exit_matrix=np.ascontiguousarray(self.exit_matrix[:, lo:hi]),
            time_exit_bars=np.ascontiguousarray(self.time_exit_bars[lo:hi]),
            sl_atr=np.ascontiguousarray(self.sl_atr[lo:hi]),
            tp_atr=np.ascontiguousarray(self.tp_atr[lo:hi]),
            trail_atr=np.ascontiguousarray(self.trail_atr[lo:hi]),
        )


def _metrics_of(job: GridJob) -> dict[str, NDArray[Any]]:
    grid = simulate_grid(
        job.market,
        job.entry_matrix,
        job.exit_matrix,
        job.direction,
        job.time_exit_bars,
        job.sl_atr,
        job.tp_atr,
        job.trail_atr,
        job.disaster_atr,
        job.costs,
        job.sizing,
        job.intrabar_mode,
        job.fx_open,
        job.fx_close,
    )
    table = core_metrics_batch(
        grid.equity.T, grid.in_position.T, grid.n_closed_trades, job.ts, job.initial_capital
    )
    table["n_skipped_min_volume"] = np.asarray(grid.n_skipped_min_volume, dtype=np.int64)
    return table


def run_grid(
    job: GridJob, chunk_cols: int | None = None, max_grid_bytes: int | None = None
) -> dict[str, NDArray[Any]]:
    """Run ``job`` in column chunks and return one metrics table for the whole grid (D-331).

    The chunk size comes from ``chunk_cols`` when given, else from ``max_grid_bytes``
    (default: the executor config). Chunk results are concatenated in column order, so a
    chunked grid is identical to an unchunked one.
    """
    n_configs = job.n_configs
    if chunk_cols is None:
        budget = (
            max_grid_bytes if max_grid_bytes is not None else load_executor_config().max_grid_bytes
        )
        chunk_cols = chunk_columns(job.n_bars, n_configs, budget)
    chunk = max(1, min(int(chunk_cols), n_configs))
    parts = [
        _metrics_of(job.columns(lo, min(lo + chunk, n_configs)))
        for lo in range(0, n_configs, chunk)
    ]
    return {name: np.concatenate([p[name] for p in parts]) for name in parts[0]}


# --------------------------------------------------------------------------------------
# Registry: one trial per evaluated configuration (F-0.7.1, D-012)
# --------------------------------------------------------------------------------------
#: Batch metric name -> trial column. Columns the batch path does not compute stay ``None``.
TRIAL_METRIC_COLUMNS: dict[str, str] = {
    "n_trades": "n_trades",
    "avg_annual_profit_usd": "avg_annual_profit",
    "avg_annual_dd_ystart_usd": "avg_annual_dd_ystart",
    "profit_dd_ratio": "profit_dd_ratio",
    "exposure": "exposure",
}


def grid_trial_rows(
    run_id: uuid.UUID,
    stage: str,
    family_id: str,
    spec_hash: str,
    params: Sequence[Mapping[str, Any]],
    table: Mapping[str, NDArray[Any]],
    candidate_id: str | None = None,
) -> list[Any]:
    """One ``TrialRecord`` per configuration of a grid, in column order (F-0.7.1).

    ``params`` holds one parameter dict per column; ``table`` is the metrics table of
    :func:`run_grid`. Only the parent process calls this (D-012, D-334).
    """
    from strategy_factory.registry.writer import TrialRecord

    n = len(params)
    for name, values in table.items():
        if len(values) != n:
            raise ExecutorError(f"metric {name!r} has {len(values)} values for {n} configurations")
    rows: list[Any] = []
    for i, cell in enumerate(params):
        cells: dict[str, float] = {
            column: float(table[metric][i])
            for metric, column in TRIAL_METRIC_COLUMNS.items()
            if metric in table
        }
        n_trades = cells.pop("n_trades", None)
        rows.append(
            TrialRecord(
                run_id=run_id,
                stage=stage,
                candidate_id=candidate_id,
                family_id=family_id,
                spec_hash=spec_hash,
                params=dict(cell),
                n_trades=None if n_trades is None else int(n_trades),
                **cells,
                extra=(
                    {"n_skipped_min_volume": int(table["n_skipped_min_volume"][i])}
                    if "n_skipped_min_volume" in table
                    else None
                ),
            )
        )
    return rows
