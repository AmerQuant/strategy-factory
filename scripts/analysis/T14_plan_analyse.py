"""T14 plan: the stage-3 surface rules replayed on the measured cells (T14 §4, §10).

Reads ``<artifacts>/_analysis/T14_plan/cells.parquet`` (``T14_plan_measure.py run``) and
``docs/reviews/T14_plan_grids.csv``::

    uv run python scripts/analysis/T14_plan_analyse.py

Per candidate (real and control), per **failed-cell treatment** and per **per-half trade
minimum**: the half-1 after-cost surface is smoothed (mean over the cell and its neighbours at
+-1 step in every numeric dimension, only those that exist), the selected cell is the maximum of
the smoothed surface among the cells at the minimum (ties: the canonical JSON of the
parameters), the stability ratio is the mean of its raw neighbours over its raw value, the
plateau is the connected set (same neighbourhood) of cells whose smoothed value is at least
0.8 x the selected cell's, the half-2 check is D-641's acceptance region, and SPP is the
whole-window after-cost distribution with failed cells ranked below every valid one (stage 2's
convention, D-636 (a)). A +inf target (no drawdown) is replaced by the surface's largest finite
value before smoothing, and counted.

Treatments of a failed cell (below the trade minimum) in the smoothed mean and the neighbour
mean: ``skip`` (left out -- the reference the task forbids), ``worst`` (the surface's lowest valid
value), ``zero`` (0: no edge), ``worst0`` (min(worst, 0)), ``neginf`` (-inf: any failed
neighbour sinks the cell).
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from strategy_factory.pipeline.stage_run import artifacts_root

MIN = {"1D": 30, "1H": 100}  # the s02/s03 trade minimum (gate YAML), as stages 1 and 2
STAB, AREA = 0.8, 0.10  # the s03_entry gate thresholds (gate YAML)
TREATMENTS = ("skip", "worst", "zero", "worst0", "neginf")
HALF_RULES = ("full", "half")
SMALL = 10  # a grid below this many cells: one cell is >= 10 % of it
OUT = Path("docs/reviews")


def _lattice(
    grid_row: dict[str, Any], cells: pl.DataFrame
) -> tuple[list[str], dict[str, tuple[int, ...]]]:
    axes = json.loads(grid_row["axes"])
    names = list(axes)
    values: dict[str, list[Any]] = {n: [] for n in names}
    for p in cells["params"].unique().to_list():
        d = json.loads(p)
        for n in names:
            values[n].append(d[n])
    uniq = {n: sorted(set(values[n])) for n in names}
    index = {}
    for p in cells["params"].unique().to_list():
        d = json.loads(p)
        index[p] = tuple(uniq[n].index(d[n]) for n in names)
    shape = tuple(len(uniq[n]) for n in names)
    return names, {"__shape__": shape, **index}  # type: ignore[dict-item]


def _surface(
    df: pl.DataFrame, index: dict[str, Any], seg: str, leg: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    shape = index["__shape__"]
    t = np.full(shape, np.nan)
    n = np.zeros(shape, dtype=np.int64)
    keys = np.empty(shape, dtype=object)
    sub = df.filter((pl.col("segment") == seg) & (pl.col("leg") == leg))
    for p, nt, tg in zip(sub["params"], sub["n_trades"], sub["target"], strict=True):
        i = index[p]
        t[i], n[i], keys[i] = tg, nt, p
    return t, n, keys


def _offsets(ndim: int) -> list[tuple[int, ...]]:
    return [o for o in itertools.product((-1, 0, 1), repeat=ndim) if any(o)]


def _neigh(idx: tuple[int, ...], shape: tuple[int, ...]) -> list[tuple[int, ...]]:
    out = []
    for o in _offsets(len(shape)):
        j = tuple(a + b for a, b in zip(idx, o, strict=True))
        if all(0 <= x < s for x, s in zip(j, shape, strict=True)):
            out.append(j)
    return out


def _treated(t: np.ndarray, valid: np.ndarray, how: str) -> tuple[np.ndarray, int]:
    x = t.copy()
    fin = valid & np.isfinite(x)
    n_inf = int(np.count_nonzero(valid & np.isposinf(x)))
    if n_inf:
        x[valid & np.isposinf(x)] = np.max(x[fin]) if fin.any() else 0.0
    worst = float(np.min(x[valid])) if valid.any() else math.nan
    fill = {
        "skip": math.nan,
        "worst": worst,
        "zero": 0.0,
        "worst0": min(worst, 0.0),
        "neginf": -math.inf,
    }[how]
    x[~valid] = fill
    return x, n_inf


def _smooth(x: np.ndarray) -> np.ndarray:
    s = np.full(x.shape, np.nan)
    for idx in itertools.product(*(range(k) for k in x.shape)):
        vals = [x[idx], *(x[j] for j in _neigh(idx, x.shape))]
        vals = [v for v in vals if not math.isnan(v)]
        s[idx] = float(np.mean(vals)) if vals else math.nan
    return s


def _stab(x: np.ndarray, idx: tuple[int, ...]) -> float:
    own = x[idx]
    nb = [x[j] for j in _neigh(idx, x.shape)]
    nb = [v for v in nb if not math.isnan(v)]
    if not nb or not own > 0 or math.isinf(own):
        return math.nan
    return float(np.mean(nb)) / float(own)


def _plateau(s: np.ndarray, idx: tuple[int, ...]) -> float:
    top = s[idx]
    if not top > 0:
        return 0.0
    ok = s >= STAB * top
    seen = {idx}
    stack = [idx]
    while stack:
        c = stack.pop()
        for j in _neigh(c, s.shape):
            if j not in seen and ok[j]:
                seen.add(j)
                stack.append(j)
    return len(seen) / s.size


def _select(s: np.ndarray, valid: np.ndarray, keys: np.ndarray) -> tuple[int, ...] | None:
    best: tuple[float, str, tuple[int, ...]] | None = None
    for idx in itertools.product(*(range(k) for k in s.shape)):
        if not valid[idx] or math.isnan(s[idx]):
            continue
        cand = (-s[idx], keys[idx], idx)
        if best is None or cand[:2] < best[:2]:
            best = cand
    return None if best is None else best[2]


def _spp(t: np.ndarray, n: np.ndarray, mt: int) -> tuple[float, float, float, float]:
    vals = np.where(n >= mt, t, -np.inf).ravel()
    q = np.sort(vals)

    def pick(p: float) -> float:  # nearest rank
        return float(q[min(len(q) - 1, math.floor(p * (len(q) - 1) + 0.5))])

    valid = t[n >= mt]
    med_valid = float(np.median(valid[np.isfinite(valid)])) if valid.size else math.nan
    return pick(0.5), pick(0.05), pick(0.95), med_valid


def analyse_one(df: pl.DataFrame, grid: dict[str, Any], how: str, rule: str) -> dict[str, Any]:
    tf = grid["timeframe"]
    mt = MIN[tf]
    mt_half = mt if rule == "full" else math.ceil(mt / 2)
    _, index = _lattice(grid, df)
    t1, n1, keys = _surface(df, index, "h1", "cost")
    t2, n2, _ = _surface(df, index, "h2", "cost")
    tw, nw, _ = _surface(df, index, "whole", "cost")
    z1, zn1, _ = _surface(df, index, "h1", "zero")
    v1, v2, vz = n1 >= mt_half, n2 >= mt_half, zn1 >= mt_half
    x1, inf1 = _treated(t1, v1, how)
    x2, inf2 = _treated(t2, v2, how)
    xz, _ = _treated(z1, vz, how)
    s1, s2, sz = _smooth(x1), _smooth(x2), _smooth(xz)
    sel = _select(s1, v1, keys)
    selz = _select(sz, vz, keys)
    spp = _spp(tw, nw, mt)
    row: dict[str, Any] = {
        "treatment": how,
        "half_min": rule,
        "min_trades_half": mt_half,
        "cells": int(t1.size),
        "failed_h1": int(np.count_nonzero(~v1)),
        "failed_h2": int(np.count_nonzero(~v2)),
        "failed_whole": int(np.count_nonzero(nw < mt)),
        "inf_h1": inf1,
        "inf_h2": inf2,
        "spp_median": spp[0],
        "spp_p5": spp[1],
        "spp_p95": spp[2],
        "spp_median_valid_only": spp[3],
    }
    if sel is None:
        return {
            **row,
            "selected": None,
            "stability": math.nan,
            "plateau_area": 0.0,
            "h2_smoothed": math.nan,
            "h2_stability": math.nan,
            "in_both": False,
            "shift_steps_zero_vs_cost": None,
            "passed": False,
            "failed": "no_valid_cell",
        }
    stab = _stab(x1, sel)
    area = _plateau(s1, sel)
    h2s, h2stab = s2[sel], _stab(x2, sel)
    in_both = bool(v2[sel] and h2s > 0 and h2stab >= STAB)
    fails = [
        m
        for m, ok in (
            ("spp_median_target", spp[0] > 0),
            ("stability_ratio", stab >= STAB),
            ("plateau_area", area >= AREA),
            ("selected_in_both_halves", in_both),
        )
        if not ok
    ]
    return {
        **row,
        "selected": keys[sel],
        "stability": stab,
        "plateau_area": area,
        "h1_raw": float(t1[sel]),
        "h1_smoothed": float(s1[sel]),
        "h2_raw": float(t2[sel]),
        "h2_smoothed": float(h2s),
        "h2_stability": h2stab,
        "in_both": in_both,
        "shift_steps_zero_vs_cost": (
            max(abs(a - b) for a, b in zip(sel, selz, strict=True)) if selz is not None else None
        ),
        "passed": not fails,
        "failed": ";".join(fails),
    }


def cmd_analyse() -> None:
    cells = pl.read_parquet(artifacts_root() / "_analysis/T14_plan/cells.parquet")
    grids = {r["candidate_id"]: r for r in pl.read_csv(OUT / "T14_plan_grids.csv").to_dicts()}
    rows = []
    for (key,), df in cells.group_by(["key"], maintain_order=True):
        cid, control = str(key).split("|")
        g = grids[cid]
        for how in TREATMENTS:
            for rule in HALF_RULES:
                r = analyse_one(df, g, how, rule)
                rows.append(
                    {
                        "control": control,
                        "timeframe": g["timeframe"],
                        "symbol": g["symbol"],
                        "direction": g["direction"],
                        "method": g["method"],
                        "grid_cells": g["size_run"],
                        "numeric_params": g["numeric_params"],
                        "small_grid": g["size_run"] < SMALL,
                        "candidate_id": cid,
                        **r,
                    }
                )
    out = pl.DataFrame(rows, infer_schema_length=None)
    out.write_csv(OUT / "T14_plan_variants.csv")
    with pl.Config(tbl_rows=200, tbl_cols=20, tbl_width_chars=250):
        print(
            out.group_by(["control", "treatment", "half_min"])
            .agg(
                pl.len().alias("n"),
                pl.col("passed").sum().alias("pass"),
                # polars orders NaN above every number, so ``NaN >= 0.8`` is true: exclude it (the
                # T14 review's erratum -- the plan's printed counts included NaN stabilities)
                ((pl.col("stability") >= STAB) & pl.col("stability").is_not_nan())
                .sum()
                .alias("stab_ok"),
                (pl.col("plateau_area") >= AREA).sum().alias("area_ok"),
                pl.col("in_both").sum().alias("both_ok"),
                (pl.col("spp_median") > 0).sum().alias("spp_ok"),
                pl.col("failed_h1").sum(),
                pl.col("failed_h2").sum(),
            )
            .sort(["control", "treatment", "half_min"])
        )


if __name__ == "__main__":
    cmd_analyse()
