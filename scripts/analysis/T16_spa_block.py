"""T16, D-723 (4): Hansen's SPA under each block-length rule, measured before one is chosen.

Measurement only; resumable; each finished simulation is appended to the runs CSV and a progress
line is printed (flushed), so a stop loses at most the simulation in flight::

    uv run python scripts/analysis/T16_spa_block.py            # the full measurement
    uv run python scripts/analysis/T16_spa_block.py --smoke    # a tiny check (seconds)

Rules (``stats.spa.spa_block_length``): ``pw_max``, ``pw_median``, ``pw_best`` (Politis-White on
each trial's loss differential against the zero benchmark -- its own return -- aggregated as the
maximum, the median, or the best trial's own) and ``cube_root`` (``round(T^(1/3))``).

Data: trials x time returns, T = 1,000, unit variance, from four processes -- i.i.d.; AR(1) phi
0.2; AR(1) phi 0.5; overlapping 5-bar holds, an MA(4) ``(e_t + ... + e_{t-4}) / sqrt(5)``.

* **null**: every trial's mean is 0 -> the false-rejection rate of ``p_consistent < 0.05`` and its
  Monte-Carlo standard error ``sqrt(p (1 - p) / sims)``;
* **edge**: one trial carries a real mean of 0.1 (a daily Sharpe of 0.1) -> the power;

each among 50 trials and among 5,000. Per simulation and rule: the block length chosen, the
seconds to choose it, the seconds of the SPA test (``reps`` bootstrap replications), and whether it
rejected. Distinct block lengths are tested once per simulation and shared between rules.

Outputs: ``docs/reviews/T16_spa_block_runs.csv`` (every simulation) and
``docs/reviews/T16_spa_block.csv`` (the summary, rewritten at the end of a run).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import polars as pl
from arch.bootstrap import SPA

from strategy_factory.cli import utf8_output
from strategy_factory.stats.spa import spa_block_length

REVIEWS = Path("docs") / "reviews"
RUNS = REVIEWS / "T16_spa_block_runs.csv"
SUMMARY = REVIEWS / "T16_spa_block.csv"
RULES = ("pw_max", "pw_median", "pw_best", "cube_root")
PROCESSES = ("iid", "ar1_0.2", "ar1_0.5", "ma4")
EDGE = 0.1
T = 1000
REPS = 500
# (case, trials, simulations)
PLAN = (("null", 50, 400), ("edge", 50, 200), ("null", 5000, 25), ("edge", 5000, 25))
COLUMNS = (
    "process", "case", "n_trials", "sim", "rule", "block", "block_seconds", "spa_seconds",
    "p_consistent", "rejected",
)  # fmt: skip


def returns(process: str, n: int, t: int, rng: np.random.Generator) -> np.ndarray:
    """``t x n`` returns with unit unconditional variance and mean 0."""
    if process == "iid":
        return rng.standard_normal((t, n))
    if process == "ma4":
        e = rng.standard_normal((t + 4, n))
        return sum(e[k : k + t] for k in range(5)) / math.sqrt(5)
    phi = float(process.split("_")[1])
    e = rng.standard_normal((t + 200, n)) * math.sqrt(1 - phi**2)
    x = np.empty_like(e)
    x[0] = e[0]
    for i in range(1, len(e)):
        x[i] = phi * x[i - 1] + e[i]
    return x[200:]


def simulate(
    process: str, case: str, n: int, sim: int, t: int, reps: int
) -> list[dict[str, object]]:
    seed = zlib.crc32(f"{process}|{case}|{n}|{sim}".encode())  # stable across runs
    x = returns(process, n, t, np.random.default_rng(seed))
    if case == "edge":
        x[:, 0] += EDGE
    blocks: dict[str, tuple[int, float]] = {}
    for rule in RULES:
        t0 = time.perf_counter()
        blocks[rule] = (spa_block_length(x, rule), time.perf_counter() - t0)  # type: ignore[arg-type]
    tested: dict[int, tuple[float, float]] = {}
    for b in sorted({b for b, _ in blocks.values()}):
        t0 = time.perf_counter()
        spa = SPA(np.zeros(t), -x, block_size=b, reps=reps, seed=sim)
        spa.compute()
        tested[b] = (float(spa.pvalues["consistent"]), time.perf_counter() - t0)
    return [
        {
            "process": process, "case": case, "n_trials": n, "sim": sim, "rule": rule,
            "block": b, "block_seconds": round(bs, 4), "spa_seconds": round(tested[b][1], 3),
            "p_consistent": round(tested[b][0], 5), "rejected": int(tested[b][0] < 0.05),
        }
        for rule, (b, bs) in blocks.items()
    ]  # fmt: skip


def done_keys(path: Path) -> set[tuple[str, str, int, int]]:
    if not path.is_file():
        return set()
    seen: dict[tuple[str, str, int, int], set[str]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row["process"], row["case"], int(row["n_trials"]), int(row["sim"]))
            seen.setdefault(key, set()).add(row["rule"])
    return {k for k, rules in seen.items() if rules >= set(RULES)}


def summarise(path: Path, out: Path) -> pl.DataFrame:
    df = pl.read_csv(path)
    s = (
        df.group_by("process", "case", "n_trials", "rule", maintain_order=True)
        .agg(
            pl.len().alias("sims"),
            (100 * pl.col("rejected").mean()).round(2).alias("rejection_pct"),
            pl.col("block").median().alias("median_block"),
            pl.col("block").min().alias("min_block"),
            pl.col("block").max().alias("max_block"),
            pl.col("block_seconds").mean().round(4).alias("block_seconds"),
            pl.col("spa_seconds").mean().round(3).alias("spa_seconds"),
        )
        .with_columns(
            (
                100
                * (
                    pl.col("rejection_pct")
                    / 100
                    * (1 - pl.col("rejection_pct") / 100)
                    / pl.col("sims")
                ).sqrt()
            )
            .round(2)
            .alias("mc_se_pct")
        )
    )
    s.write_csv(out)
    return s


def main() -> int:
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--smoke", action="store_true", help="2 simulations, 20 / 200 trials.")
    args = parser.parse_args()
    plan = PLAN
    runs, summary, t, reps = RUNS, SUMMARY, T, REPS
    if args.smoke:
        plan = (("null", 20, 2), ("edge", 200, 1))
        runs = REVIEWS / "T16_spa_block_smoke_runs.csv"
        summary = REVIEWS / "T16_spa_block_smoke.csv"
        t, reps = 500, 100
    done = done_keys(runs)
    new_file = not runs.is_file()
    with runs.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        for case, n, sims in plan:
            for process in PROCESSES:
                for sim in range(sims):
                    if (process, case, n, sim) in done:
                        continue
                    t0 = time.perf_counter()
                    rows = simulate(process, case, n, sim, t, reps)
                    writer.writerows(rows)
                    fh.flush()
                    blocks = {r["rule"]: r["block"] for r in rows}
                    rej = {r["rule"]: r["rejected"] for r in rows}
                    print(
                        f"{time.strftime('%H:%M:%S')} {process:8s} {case:4s} N={n:<5d} sim {sim + 1}/{sims} "
                        f"blocks {blocks} rejected {rej} {time.perf_counter() - t0:.1f}s",
                        flush=True,
                    )  # fmt: skip
    s = summarise(runs, summary)
    pl.Config.set_tbl_rows(200)
    pl.Config.set_tbl_cols(20)
    pl.Config.set_tbl_formatting("ASCII_MARKDOWN")
    print(s)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
