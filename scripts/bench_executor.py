"""Executor scalability benchmark for the T10b review (F-0.3.7 acceptance).

Runs the same work with 1, 2, 4, ... workers up to the core count and prints wall time,
speed-up and efficiency. No thresholds: the numbers are reported only.

Every row uses **one Numba thread per worker**, so the x-axis is pure process-level
scaling (the grid kernel's own ``prange`` would otherwise use the same cores). The last
two rows show the reference points: the serial executor and the ``auto`` budget of
``configs/pipeline/executor.yaml``, both of which let the kernel use all cores.

    uv run python scripts/bench_executor.py [--units N] [--bars N] [--configs N]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from fixtures.executor import run_unit

from strategy_factory.pipeline.executor import (
    Executor,
    ExecutorConfig,
    LocalExecutor,
    SerialExecutor,
    WorkUnit,
    resolve_budget,
)


def worker_counts(cpu: int) -> list[int]:
    out, w = [], 1
    while w <= cpu:
        out.append(w)
        w *= 2
    if out[-1] != cpu:
        out.append(cpu)
    return out


def strip_pid(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items() if k != "pid"} for r in results]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", type=int, default=20)
    ap.add_argument("--bars", type=int, default=5000)
    ap.add_argument("--configs", type=int, default=1000)
    args = ap.parse_args()

    cpu = os.cpu_count() or 1
    units = [
        WorkUnit(f"SYM{i:02d}", "1D", "s02_screen",
                 {"n_bars": args.bars, "n_configs": args.configs, "run_seed": 42, "seed": i})
        for i in range(args.units)
    ]  # fmt: skip
    print(
        f"{args.units} work units x {args.configs} configurations x {args.bars} bars = "
        f"{args.units * args.configs:,} configurations on {cpu} cores"
    )
    expected = strip_pid([run_unit(units[0])])  # compile the kernel before timing

    rows: list[tuple[str, str, float]] = []
    baseline = 0.0
    for workers in worker_counts(cpu):
        ex: Executor = LocalExecutor(ExecutorConfig(workers=workers, numba_threads=1), cpu)
        t = time.perf_counter()
        results = ex.map(run_unit, units)
        wall = time.perf_counter() - t
        assert strip_pid(results[:1]) == expected, "parallel result differs from serial"
        baseline = baseline or wall
        rows.append((str(workers), "1", wall))

    t = time.perf_counter()
    SerialExecutor().map(run_unit, units)
    rows.append(("serial", "all", time.perf_counter() - t))
    budget = resolve_budget(ExecutorConfig(), cpu)
    t = time.perf_counter()
    LocalExecutor(ExecutorConfig(), cpu).map(run_unit, units)
    rows.append((f"{budget.workers} (auto)", str(budget.numba_threads), time.perf_counter() - t))

    print(f"\n{'workers':>10} {'threads':>8} {'wall (s)':>10} {'speed-up':>9} {'efficiency':>11}")
    for workers, threads, wall in rows:
        speed_up = baseline / wall
        n = int(workers.split()[0]) if workers[0].isdigit() else 1
        print(f"{workers:>10} {threads:>8} {wall:>10.2f} {speed_up:>9.2f} {speed_up / n:>11.2f}")
    print("\nspeed-up and efficiency are relative to 1 worker x 1 thread.")


if __name__ == "__main__":
    main()
