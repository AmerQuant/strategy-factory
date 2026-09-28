"""T13 plan: the proposed stage-2 coarse grids on real data, and the mirror rule against the
user's script (docs/tasks/T13_stage2_method_screening.md §4, §11; D-622 ... D-628).

Local only. Reads the development bars of the stage-1 passing profiles through ``DataAccess``
with an **in-memory** split ledger (the T04m pattern), so nothing is written to the registry or
the store; the holdout is never opened::

    uv run python scripts/analysis/T13_grid_check.py

Two measurements, written to ``docs/reviews/``:

1. ``T13_plan_grid_cells.csv`` / ``T13_plan_grid_summary.csv`` -- every cell of every proposed
   method grid, run with stage 1's fixed exits (D-622: MR ``close > high[1]`` or 5 bars, TF the
   reverse signal or 50 bars, the 3-ATR disaster stop on both) at **zero cost** and with the
   symbol's **full cost profile** (D-623), on each profile of the method's own edge type and
   direction (D-628). Per cell: closed trades and the target metric (``profit_dd_ratio``,
   spec §2.1). Per (profile, method): how many cells reach the trade minimum and how many are
   profitable -- the T13 §11 test "all cells fail, or all pass". Every grid runs twice: on
   the real development bars (``data=real``) and on the D-615 reshuffled-returns control of
   the same series (``data=control``, T12's seed), so a grid that "all passes" can be told
   apart from drift. Where the task's grid was badly placed, the plan's replacement grid
   (``PROPOSED``) runs next to it (``grid=proposed``).
3. ``T13_plan_duplicates.csv`` -- D-627's guard, measured on MSFT and K 1D and BAC 1H: any two
   (method, cell) with identical long and short signal vectors, across methods or inside one
   method's grid (a wasted cell).
4. ``T13_plan_baseline.csv`` -- per (data, profile, method, grid) the good-region median cell
   (D-624) against its 1,000 matched random entries (D-102, D-607, D-618): the percentile and
   empirical p of its mean ATR return, as stage 1 computes them for a probe. This measures a
   gate criterion the plan proposes (the draft gate has no baseline term and passes drift).
2. ``T13_plan_mirror.csv`` -- for every rule of the user's script at the script's own
   parameters: the script's literal long and short, next to the framework's long and its
   **mirror-rule short** (``Bars.mirrored``: ``p -> -p``), counted bar by bar on the same
   development bars. For ratio rules the naive mirror of the script's literal long is counted
   too, to show why those rules are written with ``|ref|`` (see ``_below``).

These are plan measurements, not stage code: the methods here are plain functions written from
``tools/tradingview/user_mr_suite.pine`` and the task's grids. The stage's components are built
in the implementation, with their own tests.
"""

from __future__ import annotations

import csv
import dataclasses
import itertools
import json
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from strategy_factory.baseline.random_entries import (
    allowed_range,
    atr_returns,
    baseline_seed,
    frictionless_costs,
    frictionless_sizing,
    run_baseline,
)
from strategy_factory.components import indicators as ind
from strategy_factory.components.base import Bars
from strategy_factory.core.config import load_pipeline_config
from strategy_factory.core.errors import HoldoutAccessError
from strategy_factory.core.universe import load_universe
from strategy_factory.costs.profile import load_assignments, load_profiles
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import DataAccess, SplitManager
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import ExitParams, simulate
from strategy_factory.metrics.containers import RunMeta
from strategy_factory.metrics.standard import core_metrics
from strategy_factory.pipeline.backtest import (
    cost_inputs,
    market_arrays,
    sizing_inputs,
    to_run_result,
)
from strategy_factory.pipeline.executor import unit_seed
from strategy_factory.stages.control import permute_returns
from strategy_factory.stages.edge import _cost_arrays
from strategy_factory.stats.edge import empirical_p, percentile_of

OUT = Path("docs") / "reviews"
PIPELINE = Path("configs") / "pipeline" / "s01_broker_1d.yaml"

# The stage-1 passes (T12 review §3; D-628). 1H TF-long are `unconfirmed` (D-621).
PROFILES_1D = (
    ("MSFT", "long"), ("TXN", "long"), ("RTX", "long"), ("TMUS", "long"), ("ETN", "long"),
    ("SHW", "long"), ("AAPL", "long"),
    ("TXN", "short"), ("K", "short"), ("TJX", "short"), ("LEN", "short"), ("GNRC", "short"),
    ("ADI", "short"), ("EEM", "short"),
)  # fmt: skip
PROFILES_1H = (("BAC", "long"), ("TSLA", "long"), ("ARKK", "long"), ("MRNA", "long"))
# the s01_probe / s02_screen trade minimum (configs/gates/default.yaml: 30, 1H override 100)
MIN_TRADES = {"1D": 30, "1H": 100}
EXITS = {"MR": ("prev_extreme", 5), "TF": ("reverse", 50)}  # D-101, D-614 (configs/stages)
RUN_SEED = 42  # T12's control runs (configs/pipeline/s01_broker_*_control.yaml)
GOOD_REGION_SHARE = 0.25  # D-624: the top quartile of cells
BASELINE_SIMULATIONS = 1000  # D-102 (configs/stages/s01_edge.yaml)
# The baseline's first allowed signal bar. The stage uses each method's exact warm-up; the
# plan uses one bound above every lookback measured here (the longest is 200 + 1 bars).
BASELINE_WARMUP = 210


class MemoryLedger:
    """Split ledger in memory: the check leaves no trace in the registry (T04m pattern)."""

    def __init__(self) -> None:
        self.splits: dict[Any, dict[str, Any]] = {}

    def register_snapshot(self, meta: Any, is_reference: bool) -> None:
        pass

    def get_split(self, key: Any) -> dict[str, Any] | None:
        return self.splits.get(key)

    def add_split(self, split: Any) -> None:
        self.splits[split.key] = {**split.boundaries(), "expected_holdout_trades": None}

    def record_holdout_access(self, candidate_id: str, result: dict[str, Any]) -> None:
        raise HoldoutAccessError("the grid check never opens a holdout")


# --------------------------------------------------------------------------- helpers
def prev(x: np.ndarray, n: int = 1) -> np.ndarray:
    """Pine ``x[n]``: NaN before the start."""
    out = np.full(x.shape[0], np.nan)
    if 0 < n < x.shape[0]:
        out[n:] = x[:-n]
    return out


def run_of(cond: np.ndarray, count: int) -> np.ndarray:
    """``cond`` true on this bar and the ``count - 1`` bars before it."""
    out = cond.astype(bool).copy()
    for j in range(1, count):
        shifted = np.zeros_like(out)
        shifted[j:] = cond[:-j]
        out &= shifted
    return out


def falling_run(x: np.ndarray, count: int) -> np.ndarray:
    """``x < x[1] < ... < x[count]`` (``count`` consecutive falls)."""
    return run_of(x < prev(x), count)


def _below(x: np.ndarray, ref: np.ndarray, frac: float) -> np.ndarray:
    """``x < ref * (1 - frac)`` for positive prices, written as ``x < ref - frac * |ref|``.

    The literal ratio form is not translation-equivariant, so ``Bars.mirrored`` (``p -> -p``)
    turns it into nonsense (``c > c[1] * 0.99`` instead of ``c > c[1] * 1.01``). With ``|ref|``
    the mirror is exact: ``-x < -ref - frac * |ref|`` is ``x > ref * (1 + frac)``.
    """
    return x < ref - frac * np.abs(ref)


def ibs100(b: Bars) -> np.ndarray:
    return ind.ibs(b.high, b.low, b.close) * 100.0


def rolling_sum(x: np.ndarray, m: int) -> np.ndarray:
    out = np.full(x.shape[0], np.nan)
    if m <= x.shape[0]:
        c = np.convolve(x, np.ones(m), mode="valid")
        out[m - 1 :] = c
    return out


def candle_total(b: Bars) -> np.ndarray:
    """The script's ``totalScore = selfScore + coScore`` (lines 329-331), exactly."""
    c, h, lo = b.close, b.high, b.low
    h1, l1 = prev(h), prev(lo)
    self_ = np.select(
        [5 * c > 4 * h + lo, 5 * c > 3 * h + 2 * lo, 5 * c > 2 * h + 3 * lo, 5 * c > h + 4 * lo],
        [2, 1, 0, -1],
        -2,
    )
    co = np.select(
        [c > h1, 3 * c > 2 * h1 + l1, 3 * c > h1 + 2 * l1, c > l1], [3, 2, 0, -2], -3
    )  # NaN comparisons are False, as Pine's na: bar 0 scores -3, like the script
    return (self_ + co).astype(np.float64)


def candle_ma(b: Bars, n: int) -> np.ndarray:
    """``ta.sma(totalScore, n) * n``: the score summed over ``n`` bars."""
    return rolling_sum(candle_total(b), n)


def williams100(b: Bars, n: int) -> np.ndarray:
    """The script's ``WilliamsPR`` (0..100 scale) = ``ta.wpr + 100``."""
    return ind.williams_r(b.high, b.low, b.close, n) + 100.0


def williams_latched(b: Bars, n: int, t: float) -> np.ndarray:
    """T13 §4.2's reading: %R < t arms a trigger; the first bar with ``high > high[1]`` fires
    it; %R > 100 - t disarms it. (The script declares the trigger without ``var``, so it
    actually resets every bar -- see ``williams_same_bar``.)"""
    w = williams100(b, n)
    up = b.high > prev(b.high)
    out = np.zeros(len(b), dtype=bool)
    armed = False
    for i in range(len(b)):
        if w[i] < t:
            armed = True
        if armed and up[i]:
            out[i] = True
            armed = False
        if w[i] > 100.0 - t:
            armed = False
    return out


def williams_same_bar(b: Bars, n: int, t: float) -> np.ndarray:
    """What the script computes: %R < t **and** ``high > high[1]`` on the same bar."""
    return (williams100(b, n) < t) & (b.high > prev(b.high))


def base_candle_direction(b: Bars, frac: float) -> tuple[np.ndarray, np.ndarray]:
    """The script's BaseCandle state machine (lines 387-413); ``frac`` = 1/3 is the script.

    Returns ``(direction, long_base)`` with ``long_base`` in {1, -1, 0}.
    """
    o, h, lo, c = b.open, b.high, b.low, b.close
    n = len(b)
    direction = np.zeros(n)
    long_base = np.zeros(n)
    base_high, base_low, long_dir = h[0], lo[0], True
    for i in range(n):
        rng = h[i] - lo[i]
        strong_up = c[i] > h[i] - frac * rng
        strong_dn = c[i] < lo[i] + frac * rng
        lb = 0
        if long_dir and strong_up and c[i] > o[i] and h[i] > base_high:
            base_high, base_low, lb = h[i], lo[i], 1
        elif (not long_dir) and strong_dn and c[i] < o[i] and lo[i] < base_low:
            base_high, base_low, lb = h[i], lo[i], -1
        elif long_dir and strong_dn and c[i] < o[i] and c[i] < base_low:
            base_high, base_low, long_dir, lb = h[i], lo[i], False, -1
        elif (not long_dir) and strong_up and c[i] > o[i] and c[i] > base_high:
            base_high, base_low, long_dir, lb = h[i], lo[i], True, 1
        direction[i] = 1.0 if long_dir else -1.0
        long_base[i] = lb
    return direction, long_base


def macd_hist(b: Bars) -> np.ndarray:
    return ind.macd(b.close, 12, 26, 9).hist


# --------------------------------------------------------------------------- methods
Rule = Callable[..., np.ndarray]


@dataclass(frozen=True)
class Method:
    name: str
    edge: str
    grid: dict[str, tuple[Any, ...]]
    long: Rule  # long(bars, **params) -> bool per bar; short = long(bars.mirrored(), ...)
    label: str = "task"  # "task": T13 §4's starting grid; "proposed": the plan's replacement

    def cells(self) -> Iterable[dict[str, Any]]:
        keys = list(self.grid)
        for vals in itertools.product(*(self.grid[k2] for k2 in keys)):
            yield dict(zip(keys, vals, strict=True))


def _ma_distance(b: Bars, n: int, unit: str, level: int) -> np.ndarray:
    e = ind.ema(b.close, n)
    if unit == "pct":
        return _below(b.close, e, (0.005, 0.01, 0.02, 0.03)[level])
    return b.close + (0.25, 0.5, 1.0, 1.5)[level] * ind.atr(b.high, b.low, b.close, 5) < e


def _daily_drop(b: Bars, d: float, atr_expanding: str) -> np.ndarray:
    sig = _below(b.close, prev(b.close), d)
    if atr_expanding == "on":
        sig &= ind.atr(b.high, b.low, b.close, 5) > ind.atr(b.high, b.low, b.close, 10)
    return sig


def _candle(b: Bars, n: int, level: float, mode: str) -> np.ndarray:
    tm = candle_ma(b, n)
    sig = tm <= n * level
    if mode == "rising":
        sig &= tm > prev(tm)
    return sig


def _psar_flip(b: Bars, step: float, maximum: float) -> np.ndarray:
    s = ind.psar(b.high, b.low, b.close, step, step, maximum)
    below = s < b.close
    return below & (prev(s) > prev(b.close))


def _base_flip(b: Bars, frac: float) -> np.ndarray:
    d, _ = base_candle_direction(b, frac)
    return (d == 1.0) & (prev(d) == -1.0)


MR_METHODS = (
    Method("mr_ibs", "MR", {"t": (10, 20, 30, 40), "k": (1, 2, 3)},
           lambda b, t, k: run_of(ibs100(b) < t, k)),
    Method("mr_rsi", "MR", {"n": (2, 3, 5, 14), "t": (10, 20, 30, 35)},
           lambda b, n, t: ind.rsi(b.close, n) < t),
    Method("mr_rsi_sum", "MR", {"n": (2, 3, 4, 5), "m": (2, 3), "level": (5, 10, 15, 20)},
           lambda b, n, m, level: rolling_sum(ind.rsi(b.close, n), m) < m * level),
    Method("mr_connors_rsi", "MR", {"rsi_len": (2, 3, 4, 5), "t": (5, 10, 15, 20)},
           lambda b, rsi_len, t: ind.connors_rsi(b.close, rsi_len, 2, 100) < t),
    Method("mr_down_closes", "MR", {"k": (1, 2, 3, 4)},
           lambda b, k: falling_run(b.close, k)),
    Method("mr_lower_lows", "MR", {"k": (2, 3, 4, 5)},
           lambda b, k: falling_run(b.low, k)),
    Method("mr_n_day_low", "MR", {"n": (3, 5, 7, 10), "basis": ("low", "close")},
           lambda b, n, basis: b.close < prev(ind.lowest(b.low if basis == "low" else b.close, n))),
    Method("mr_daily_drop", "MR", {"d": (0.005, 0.01, 0.02, 0.03), "atr_expanding": ("off", "on")},
           _daily_drop),
    Method("mr_ma_distance", "MR", {"n": (5, 10, 20, 50), "unit": ("pct", "atr"), "level": (0, 1, 2, 3)},
           _ma_distance),
    Method("mr_ema_slope_drop", "MR", {"n": (3, 5, 10, 20), "p": (0.0025, 0.005, 0.01, 0.015)},
           lambda b, n, p: _below(ind.ema(b.close, n), prev(ind.ema(b.close, n)), p)),
    Method("mr_ibs_after_new_high", "MR", {"n": (5, 10, 20, 50), "t": (10, 15, 20, 25)},
           lambda b, n, t: (b.high > prev(ind.highest(b.high, n))) & (ibs100(b) < t)),
    Method("mr_macd_hist_falling", "MR", {"k": (2, 3, 4, 5)},
           lambda b, k: falling_run(macd_hist(b), k) & (macd_hist(b) < 0) & (b.close < prev(b.close))),
    Method("mr_macd_hist_turn", "MR", {"k": (1, 2, 3, 4)},
           lambda b, k: run_of(macd_hist(b) > prev(macd_hist(b)), k) & (macd_hist(b) < 0)),
    Method("mr_macd_hist_trough", "MR", {"w": (3, 5, 7, 10)},
           lambda b, w: macd_hist(b) <= ind.lowest(macd_hist(b), w)),
    Method("mr_candle_score", "MR",
           {"n": (2, 3, 5, 8), "level": (-3.0, -2.5, -2.0, -1.5), "mode": ("level", "rising")},
           _candle),
    Method("mr_williams_confirm", "MR",
           {"n": (5, 10, 14, 20), "t": (5, 10, 20, 30), "confirm": ("off", "on")},
           lambda b, n, t, confirm: williams100(b, n) < t if confirm == "off"
           else williams_latched(b, n, t)),
    Method("mr_zscore", "MR", {"n": (10, 20, 30, 40), "t": (1.5, 2.0, 2.5, 3.0)},
           lambda b, n, t: ind.zscore(b.close, n) < -t),
    Method("mr_stochastic_k", "MR", {"n": (5, 9, 14, 21), "t": (5, 10, 20, 30)},
           lambda b, n, t: ind.stochastic(b.high, b.low, b.close, n, 3, 3).k < t),
    Method("mr_keltner_lower", "MR", {"n": (10, 20, 30, 40), "mult": (1.0, 1.5, 2.0, 2.5)},
           lambda b, n, mult: b.close < ind.keltner(b.high, b.low, b.close, n, mult).lower),
)  # fmt: skip


def _crossover(a: np.ndarray, c: np.ndarray) -> np.ndarray:
    return (a > c) & (prev(a) <= prev(c))


def _ichimoku(b: Bars, conversion: int, base: int, span_b: int) -> np.ndarray:
    ich = ind.ichimoku(b.high, b.low, conversion, base, span_b)
    top = np.maximum(prev(ich.span_a_raw, base - 1), prev(ich.span_b_raw, base - 1))
    return (b.close > top) & (ich.tenkan > ich.kijun)


def _adx_di(b: Bars, n: int, t: float) -> np.ndarray:
    d = ind.dmi(b.high, b.low, b.close, n, n)
    return _crossover(d.plus, d.minus) & (d.adx > t)


TF_METHODS = (
    Method("tf_ma_slope", "TF", {"n": (20, 50, 100, 200)},
           lambda b, n: (ind.sma_slope(b.close, n) > 0) & (prev(ind.sma_slope(b.close, n)) <= 0)),
    Method("tf_sma_cross", "TF", {"fast": (10, 20, 30, 40), "slow": (60, 100, 150, 200)},
           lambda b, fast, slow: _crossover(ind.sma(b.close, fast), ind.sma(b.close, slow))),
    Method("tf_donchian_breakout", "TF", {"n": (10, 20, 55, 100)},
           lambda b, n: b.close > prev(ind.highest(b.high, n))),
    Method("tf_bb_upper_cross", "TF", {"n": (10, 20, 30, 40), "mult": (1.5, 2.0, 2.5, 3.0)},
           lambda b, n, mult: _crossover(b.close, ind.bollinger(b.close, n, mult).upper)),
    Method("tf_supertrend_flip", "TF", {"atr": (7, 10, 14, 20), "factor": (2.0, 2.5, 3.0, 3.5)},
           lambda b, atr, factor: (lambda d: (d == -1.0) & (prev(d) == 1.0))(
               ind.supertrend(b.high, b.low, b.close, factor, atr).direction)),
    Method("tf_ichimoku_cloud", "TF",
           {"conversion": (7, 9, 12, 15), "base": (22, 26, 30, 40), "span_b": (44, 52, 60, 80)},
           _ichimoku),
    Method("tf_momentum_cross", "TF", {"n": (10, 20, 40, 60)},
           lambda b, n: (ind.momentum(b.close, n) > 0) & (prev(ind.momentum(b.close, n)) <= 0)),
    Method("tf_keltner_breakout", "TF", {"n": (10, 20, 30, 40), "mult": (1.0, 1.5, 2.0, 2.5)},
           lambda b, n, mult: _crossover(b.close, ind.keltner(b.high, b.low, b.close, n, mult).upper)),
    Method("tf_adx_di", "TF", {"n": (7, 14, 21, 28), "t": (15.0, 20.0, 25.0, 30.0)}, _adx_di),
    Method("tf_hma_turn", "TF", {"n": (9, 16, 25, 49)},
           lambda b, n: (lambda h: (h > prev(h)) & (prev(h) <= prev(h, 2)))(ind.hma(b.close, n))),
    Method("tf_kama_cross", "TF", {"n": (5, 10, 20, 30)},
           lambda b, n: _crossover(b.close, ind.kama(b.close, n, 2, 30))),
    Method("tf_psar_flip", "TF", {"step": (0.01, 0.02, 0.03, 0.04), "maximum": (0.1, 0.2, 0.3, 0.4)},
           _psar_flip),
    Method("tf_aroon_cross", "TF", {"n": (14, 25, 50, 100)},
           lambda b, n: (lambda a: _crossover(a.up, a.down))(ind.aroon(b.high, b.low, n))),
    Method("tf_atr_band", "TF", {"n": (5, 10, 20, 40), "k": (1.5, 2.0, 2.5, 3.0), "m": (10, 14, 25, 50)},
           lambda b, n, k, m: b.close > ind.lowest(b.low, n) + k * ind.atr(b.high, b.low, b.close, m)),
    Method("tf_base_candle", "TF", {"frac": (0.25, 1 / 3, 0.4, 0.5)}, _base_flip),
)  # fmt: skip


# The plan's replacement grids, for the task grids the first measurement found badly placed
# (most cells below the trade minimum, or the rule's own default outside the grid). Each is
# measured next to the task grid it replaces.
PROPOSED: dict[str, dict[str, tuple[Any, ...]]] = {
    "mr_ibs": {"t": (15, 20, 30, 40), "k": (1, 2, 3)},
    "mr_rsi": {"n": (2, 3, 5, 7), "t": (15, 20, 30, 35)},
    "mr_rsi_sum": {"n": (2, 3, 4, 5), "m": (2, 3), "level": (15, 20, 25, 30)},
    "mr_connors_rsi": {"rsi_len": (2, 3, 4, 5), "t": (15, 20, 25, 30)},
    "mr_lower_lows": {"k": (1, 2, 3, 4)},
    "mr_n_day_low": {"n": (3, 5, 10, 20), "basis": ("low", "close")},
    "mr_ema_slope_drop": {"n": (3, 5, 8, 10), "p": (0.0025, 0.005, 0.0075, 0.01)},
    "mr_ibs_after_new_high": {"n": (3, 5, 10, 20), "t": (15, 20, 25, 30)},
    "mr_candle_score": {"n": (2, 3, 4, 5), "level": (-2.5, -2.0, -1.5, -1.0),
                        "mode": ("level", "rising")},
    "mr_zscore": {"n": (10, 20, 30, 40), "t": (1.0, 1.25, 1.5, 2.0)},
    "mr_stochastic_k": {"n": (5, 9, 14, 21), "t": (10, 15, 20, 30)},
    "mr_keltner_lower": {"n": (10, 20, 30, 40), "mult": (0.5, 1.0, 1.5, 2.0)},
    "tf_sma_cross": {"fast": (5, 10, 15, 20), "slow": (30, 50, 75, 100)},
    "tf_bb_upper_cross": {"n": (10, 20, 30, 40), "mult": (1.0, 1.5, 2.0, 2.5)},
    "tf_keltner_breakout": {"n": (10, 20, 30, 40), "mult": (0.75, 1.0, 1.5, 2.0)},
    "tf_adx_di": {"n": (5, 7, 10, 14), "t": (10.0, 15.0, 20.0, 25.0)},
    "tf_aroon_cross": {"n": (10, 14, 25, 50)},
}  # fmt: skip


def with_proposals(methods: tuple[Method, ...]) -> tuple[Method, ...]:
    out = list(methods)
    for m in methods:
        if m.name in PROPOSED:
            out.append(dataclasses.replace(m, grid=PROPOSED[m.name], label="proposed"))
    return tuple(out)


def final_methods(methods: tuple[Method, ...]) -> tuple[Method, ...]:
    """The plan's grid per method: the replacement where one exists, else the task's."""
    return tuple(
        dataclasses.replace(m, grid=PROPOSED[m.name], label="proposed") if m.name in PROPOSED else m
        for m in methods
    )


def signals(m: Method, b: Bars, mb: Bars, p: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(m.long(b, **p), bool), np.asarray(m.long(mb, **p), bool)


# --------------------------------------------------------------------------- engine
@dataclass
class Series:
    symbol: str
    tf: str
    arrays: dict[str, np.ndarray]
    bars: Bars
    mirrored: Bars
    market: Any
    costs: Any


def run_cell(s: Series, entry: np.ndarray, exit_: np.ndarray, d: int, t_exit: int,
             engine: Any, full_cost: bool) -> tuple[int, float, float]:  # fmt: skip
    n = len(s.bars)
    exits = ExitParams(time_exit_bars=t_exit, disaster_atr=engine.disaster_stop_atr)
    if full_cost:
        cost_in, sizing = cost_inputs(s.costs), sizing_inputs(s.costs, engine, "pessimistic", None)
    else:
        cost_in = frictionless_costs(n)
        sizing = frictionless_sizing(engine.notional, engine.initial_capital)
    sim = simulate(s.market, entry, exit_, d, exits, cost_in, sizing, k.MODE_PESSIMISTIC)
    meta = RunMeta(symbol=s.symbol, timeframe=s.tf, spec_hash="t13-plan",
                   cost_status="verified", intrabar_mode="pessimistic")  # fmt: skip
    rr = to_run_result(sim, s.arrays["ts"], d, meta, engine)
    cm = core_metrics(rr.equity)
    return int(sim.entry_idx.shape[0]), float(cm.profit_dd_ratio), float(cm.avg_annual_profit_pct)


def exits_for(
    m: Method, s: Series, long_sig: np.ndarray, short_sig: np.ndarray, d: int
) -> np.ndarray:
    rule, _ = EXITS[m.edge]
    if rule == "prev_extreme":
        c, h, lo = s.bars.close, s.bars.high, s.bars.low
        return (c > prev(h)) if d == 1 else (c < prev(lo))
    return short_sig if d == 1 else long_sig


# --------------------------------------------------------------------------- mirror table
def mirror_rows(s: Series) -> list[dict[str, Any]]:
    """Script literal long/short vs the framework long and mirror short, script parameters."""
    b, mb = s.bars, s.mirrored
    c, h, lo = b.close, b.high, b.low
    c1 = prev(c)
    ibs = ibs100(b)
    atr5, atr10 = ind.atr(h, lo, c, 5), ind.atr(h, lo, c, 10)
    ema5 = ind.ema(c, 5)
    rsi2, rsi5 = ind.rsi(c, 2), ind.rsi(c, 5)
    hist = macd_hist(b)
    tm = candle_ma(b, 3)
    method = {mm.name: mm for mm in (*MR_METHODS, *TF_METHODS)}

    def fw(name: str, **p: Any) -> tuple[np.ndarray, np.ndarray]:
        return signals(method[name], b, mb, p)

    rows: list[
        tuple[str, np.ndarray, np.ndarray, tuple[np.ndarray, np.ndarray], np.ndarray | None]
    ] = []
    # (rule, script long, script short, framework (long, short), naive mirror of script long)
    for kk in (1, 2, 3):
        rows.append((f"#0 IBS<30 x{kk}", run_of(ibs < 30, kk), run_of(ibs > 70, kk),
                     fw("mr_ibs", t=30, k=kk), None))  # fmt: skip
    rows.append(("#1 RSI2<=20", rsi2 <= 20, rsi2 >= 80, fw("mr_rsi", n=2, t=20), None))
    s2 = rsi2 + prev(rsi2)
    rows.append(("#2 RSI2 sum<20", s2 < 20, s2 > 140, fw("mr_rsi_sum", n=2, m=2, level=10), None))
    rows.append(("#3 lower low x3", falling_run(lo, 3), run_of(h > prev(h), 3),
                 fw("mr_lower_lows", k=3), None))  # fmt: skip
    for kk in (1, 2, 3, 4):
        rows.append((f"#4 lower close x{kk}", falling_run(c, kk), run_of(c > c1, kk),
                     fw("mr_down_closes", k=kk), None))  # fmt: skip
    rows.append(("#5 close<lowest(5)[1]", c < prev(ind.lowest(lo, 5)), c > prev(ind.highest(h, 5)),
                 fw("mr_n_day_low", n=5, basis="low"), None))  # fmt: skip
    with np.errstate(invalid="ignore"):
        lit6 = c * 1.01 < c1
        rows.append(("#6 close*1.01<close[1], ATR5>ATR10", lit6 & (atr5 > atr10),
                     (c * 0.99 > c1) & (atr5 > atr10), fw("mr_daily_drop", d=0.01, atr_expanding="on"),
                     ((-c) * 1.01 < -c1) & (atr5 > atr10)))  # fmt: skip
        rows.append(("#7 close<close[1]*0.99", c < c1 * 0.99, c > c1 * 1.01,
                     fw("mr_daily_drop", d=0.01, atr_expanding="off"), (-c) < (-c1) * 0.99))  # fmt: skip
        rows.append(("#8 close+0.5ATR5<EMA5", c + 0.5 * atr5 < ema5, c - 0.5 * atr5 > ema5,
                     fw("mr_ma_distance", n=5, unit="atr", level=1), None))  # fmt: skip
        rows.append(("#9 close*1.01<EMA5", c * 1.01 < ema5, c * 0.99 > ema5,
                     fw("mr_ma_distance", n=5, unit="pct", level=1), (-c) * 1.01 < -ema5))  # fmt: skip
        rows.append(("#10 EMA5*1.005<EMA5[1]", ema5 * 1.005 < prev(ema5), ema5 * 0.995 > prev(ema5),
                     fw("mr_ema_slope_drop", n=5, p=0.005), (-ema5) * 1.005 < -prev(ema5)))  # fmt: skip
        band = ind.lowest(lo, 10) + 2.5 * ind.atr(h, lo, c, 25)
        rows.append(("#11 ATR band (TF)", c > band, np.zeros(len(b), bool),
                     fw("tf_atr_band", n=10, k=2.5, m=25), None))  # fmt: skip
        rows.append(("#14 new 10-bar high, IBS<15", (h > prev(ind.highest(h, 10))) & (ibs < 15),
                     (lo < prev(ind.lowest(lo, 10))) & (ibs > 85),
                     fw("mr_ibs_after_new_high", n=10, t=15), None))  # fmt: skip
        rows.append(("#17 MACD hist falling x4", falling_run(hist, 4) & (hist < 0) & (c < c1),
                     run_of(hist > prev(hist), 4) & (hist > 0) & (c > c1),
                     fw("mr_macd_hist_falling", k=4), None))  # fmt: skip
        rows.append(("#18 candle score(3)<=-7", tm <= -7, tm >= -7,
                     fw("mr_candle_score", n=3, level=-7 / 3, mode="level"), None))  # fmt: skip
        rows.append(("#18 candle score rising", (tm > prev(tm)) & (tm <= -7), (tm < prev(tm)) & (tm >= -7),
                     fw("mr_candle_score", n=3, level=-7 / 3, mode="rising"), None))  # fmt: skip
        rows.append(("#19 RSI5<=35", rsi5 <= 35, rsi5 >= 65, fw("mr_rsi", n=5, t=35), None))
        rows.append(("#20 MACD hist rising x2 below 0", run_of(hist > prev(hist), 2) & (hist < 0),
                     run_of(hist < prev(hist), 2) & (hist > 0), fw("mr_macd_hist_turn", k=2), None))  # fmt: skip
        same = williams_same_bar(b, 5, 20)
        rows.append(("#22 Williams (script: same bar)", same, np.zeros(len(b), bool),
                     (same, williams_same_bar(mb, 5, 20)), None))  # fmt: skip
        rows.append(("#22 Williams (task: latched)", same, np.zeros(len(b), bool),
                     fw("mr_williams_confirm", n=5, t=20, confirm="on"), None))  # fmt: skip
        d_, lb = base_candle_direction(b, 1 / 3)
        rows.append(("#23 BaseCandle flip", (d_ == 1) & (prev(d_) == -1), (d_ == -1) & (prev(d_) == 1),
                     fw("tf_base_candle", frac=1 / 3), None))  # fmt: skip
        sig = np.where(lb * d_ == 1, d_, 0)
        md, mlb = base_candle_direction(mb, 1 / 3)
        rows.append(("#24 BaseCandleSignal", sig == 1, sig == -1,
                     ((np.where(lb * d_ == 1, d_, 0) == 1), (np.where(mlb * md == 1, md, 0) == 1)),
                     None))  # fmt: skip

    out = []
    for rule, sl, ss, (fl, fs), naive in rows:
        sl, ss, fl, fs = (np.asarray(x, bool) for x in (sl, ss, fl, fs))
        out.append({
            "symbol": s.symbol, "timeframe": s.tf, "rule": rule, "bars": len(b),
            "script_long": int(sl.sum()), "framework_long": int(fl.sum()),
            "long_differ": int((sl ^ fl).sum()),
            "script_short": int(ss.sum()), "mirror_short": int(fs.sum()),
            "short_both": int((ss & fs).sum()), "short_differ": int((ss ^ fs).sum()),
            "naive_mirror_short": "" if naive is None else int(np.asarray(naive, bool).sum()),
        })  # fmt: skip
    return out


# --------------------------------------------------------------------------- main
def load_series(access: DataAccess, symbol: str, tf: str, universe: Any, profiles: Any,
                assignments: Any, engine: Any, data: str) -> Series:  # fmt: skip
    arr = access.arrays(symbol, tf)
    arr = {c2: arr[c2] for c2 in ("ts", "open", "high", "low", "close")}
    if data == "control":  # the D-615 control exactly as T12's control runs built it (seed 42)
        arr = permute_returns(arr, unit_seed(RUN_SEED, f"{symbol}|{tf}|random_walk"))
    b = Bars(*(np.asarray(arr[c2], np.float64) for c2 in ("open", "high", "low", "close")))
    costs = _cost_arrays(symbol, universe[symbol].asset_class, tf, arr, Path("configs") / "costs",
                         profiles, assignments)  # fmt: skip
    return Series(symbol, tf, arr, b, b.mirrored(), market_arrays(arr, engine.atr_length), costs)


def summarize(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    key = lambda r: (r["data"], r["timeframe"], r["symbol"], r["direction"], r["method"], r["grid"])  # noqa: E731
    for (data, tf, sym, direction, method, grid), grp in itertools.groupby(
        sorted(cells, key=key), key
    ):
        g = list(grp)
        mn = MIN_TRADES[tf]
        ok = [r for r in g if r["n_trades_cost"] >= mn]
        prof0 = sum(1 for r in ok if r["target_zero"] > 0)
        prof1 = sum(1 for r in ok if r["target_cost"] > 0)
        # failed cells count as non-profitable and sit at the bottom of the median (T13 §5)
        med1 = float(np.median([r["target_cost"] if r["n_trades_cost"] >= mn else -math.inf
                                for r in g]))  # fmt: skip
        n = len(g)
        flag = ("all_below_min_trades" if not ok else "all_cells_profitable" if prof1 == n
                else "no_cell_profitable" if prof1 == 0 else "")  # fmt: skip
        out.append({
            "data": data, "timeframe": tf, "symbol": sym, "direction": direction,
            "method": method, "grid": grid, "cells": n,
            "cells_min_trades": len(ok), "min_trades": min(r["n_trades_cost"] for r in g),
            "median_trades": float(np.median([r["n_trades_cost"] for r in g])),
            "max_trades": max(r["n_trades_cost"] for r in g),
            "profitable_share_zero": round(prof0 / n, 3), "profitable_share_cost": round(prof1 / n, 3),
            "median_target_cost": med1 if math.isfinite(med1) else "-inf", "flag": flag,
        })  # fmt: skip
    return out


def good_region_median_cell(grp: list[dict[str, Any]], min_trades: int) -> dict[str, Any] | None:
    """D-624: the good region is the top quartile of cells by the target metric (the zero-cost
    ranking leg, D-623); its median cell. Cells below the trade minimum are failed cells and
    never enter the good region (T13 §5)."""
    eligible = [r for r in grp if r["n_trades_zero"] >= min_trades]
    if not eligible:
        return None
    size = max(1, math.ceil(len(grp) * GOOD_REGION_SHARE))
    good = sorted(eligible, key=lambda r: -r["target_zero"])[:size]
    return good[len(good) // 2]


def baseline_rows(
    cells: list[dict[str, Any]], series: dict[tuple[str, str, str], Series], engine: Any
) -> list[dict[str, Any]]:
    """The good-region median cell of every (data, profile, method, grid) against its matched
    random baseline (D-624 via D-102, D-607, D-618): percentile and empirical p of its mean ATR
    return per trade, exactly as stage 1 computes them for a probe."""
    methods = {
        (m.name, m.label): m for m in (*with_proposals(MR_METHODS), *with_proposals(TF_METHODS))
    }
    key = lambda r: (r["data"], r["timeframe"], r["symbol"], r["direction"], r["method"], r["grid"])  # noqa: E731
    out = []
    for (data, tf, sym, direction, name, grid), grp in itertools.groupby(
        sorted(cells, key=key), key
    ):
        g = list(grp)
        cell = good_region_median_cell(g, MIN_TRADES[tf])
        row: dict[str, Any] = {"data": data, "timeframe": tf, "symbol": sym, "direction": direction,
                               "method": name, "grid": grid}  # fmt: skip
        if cell is None:
            out.append(
                {**row, "cell": "", "n_trades": 0, "mean_atr": "", "percentile": "", "p_value": ""}
            )
            continue
        m = methods[(name, grid)]
        s = series[(sym, tf, data)]
        d = 1 if direction == "long" else -1
        p = json.loads(cell["params"])
        lo_sig, sh_sig = signals(m, s.bars, s.mirrored, p)
        entry = lo_sig if d == 1 else sh_sig
        exits = ExitParams(time_exit_bars=EXITS[m.edge][1], disaster_atr=engine.disaster_stop_atr)
        n = len(s.bars)
        sim = simulate(s.market, entry, exits_for(m, s, lo_sig, sh_sig, d), d, exits,
                       frictionless_costs(n), frictionless_sizing(engine.notional, engine.initial_capital),
                       k.MODE_PESSIMISTIC)  # fmt: skip
        r = atr_returns(sim, d)
        lo, hi = allowed_range(n, BASELINE_WARMUP, s.market.atr)
        rng = np.random.default_rng(
            baseline_seed(RUN_SEED, sym, tf, f"{name}:{cell['params']}", direction)
        )
        base = run_baseline(s.market, np.asarray(s.arrays["ts"], np.int64), direction=d,
                            holdings=sim.exit_idx - sim.entry_idx, lo=lo, hi=hi,
                            simulations=BASELINE_SIMULATIONS, rng=rng, notional=engine.notional,
                            initial_capital=engine.initial_capital)  # fmt: skip
        means = base.sim_means[~np.isnan(base.sim_means)]
        mean = float(r.mean())
        out.append({**row, "cell": cell["params"], "n_trades": int(r.size), "mean_atr": mean,
                    "baseline_mean_atr": float(base.pooled_mean),
                    "percentile": percentile_of(mean, means),
                    "p_value": empirical_p(mean, means, 1.0 / (BASELINE_SIMULATIONS + 1))})  # fmt: skip
    return out


def duplicate_rows(series: dict[tuple[str, str, str], Series]) -> list[dict[str, Any]]:
    """D-627's guard, measured: every pair of (method, cell) whose long **and** short signal
    vectors are identical on a real series, across methods and within one method's grid."""
    out = []
    for (sym, tf, data), s in series.items():
        if data != "real" or (sym, tf) not in (("MSFT", "1D"), ("K", "1D"), ("BAC", "1H")):
            continue
        # the final grids only: a task grid and its replacement share cells by design
        methods = final_methods(MR_METHODS if tf == "1D" else TF_METHODS)
        seen: dict[bytes, tuple[str, str, str]] = {}
        for m in methods:
            for p in m.cells():
                lo_sig, sh_sig = signals(m, s.bars, s.mirrored, p)
                if not lo_sig.any() and not sh_sig.any():
                    continue
                h = lo_sig.tobytes() + sh_sig.tobytes()
                me = (m.name, m.label, json.dumps(p, sort_keys=True))
                if h in seen and seen[h][0] != m.name:
                    kind = "across_methods"
                elif h in seen:
                    kind = "within_method"
                else:
                    seen[h] = me
                    continue
                first = seen[h]
                out.append({"symbol": sym, "timeframe": tf, "kind": kind,
                            "method_a": first[0], "grid_a": first[1], "cell_a": first[2],
                            "method_b": m.name, "grid_b": m.label, "cell_b": me[2],
                            "signals": int(lo_sig.sum())})  # fmt: skip
    return out or [{"symbol": "", "timeframe": "", "kind": "none"}]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    started = time.perf_counter()
    engine = load_pipeline_config(PIPELINE).engine
    cfg = load_pipeline_config(PIPELINE)
    universe = load_universe(cfg.universe).by_symbol()
    profiles, assignments = (
        load_profiles(Path("configs") / "costs"),
        load_assignments(Path("configs") / "costs"),
    )
    access = DataAccess(SplitManager(MemoryLedger(), load_split_config()))
    cells: list[dict[str, Any]] = []
    mirror: list[dict[str, Any]] = []
    series: dict[tuple[str, str, str], Series] = {}
    plan = [(s, "1D", d, with_proposals(MR_METHODS)) for s, d in PROFILES_1D]
    plan += [(s, "1H", d, with_proposals(TF_METHODS)) for s, d in PROFILES_1H]
    plan2 = [(*p, data) for data in ("real", "control") for p in plan]
    for sym, tf, direction, methods, data in plan2:
        key = (sym, tf, data)
        if key not in series:
            series[key] = load_series(
                access, sym, tf, universe, profiles, assignments, engine, data
            )
            if data == "real":
                mirror += mirror_rows(series[key])
        s = series[key]
        d = 1 if direction == "long" else -1
        for m in methods:
            _, t_exit = EXITS[m.edge]
            for p in m.cells():
                lo_sig, sh_sig = signals(m, s.bars, s.mirrored, p)
                entry = lo_sig if d == 1 else sh_sig
                exit_ = exits_for(m, s, lo_sig, sh_sig, d)
                n0, t0, _ = run_cell(s, entry, exit_, d, t_exit, engine, full_cost=False)
                n1, t1, pr1 = run_cell(s, entry, exit_, d, t_exit, engine, full_cost=True)
                cells.append({
                    "data": data, "timeframe": tf, "symbol": sym, "direction": direction,
                    "method": m.name, "grid": m.label, "params": json.dumps(p, sort_keys=True), "signals": int(entry.sum()),
                    "n_trades_zero": n0, "target_zero": t0, "n_trades_cost": n1,
                    "target_cost": t1, "avg_annual_profit_pct_cost": pr1,
                })  # fmt: skip
        print(f"{data} {sym} {tf} {direction}: {len(cells)} cells so far, "
              f"{time.perf_counter() - started:.0f} s", flush=True)  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "T13_plan_grid_cells.csv", cells)
    write_csv(OUT / "T13_plan_grid_summary.csv", summarize(cells))
    write_csv(OUT / "T13_plan_mirror.csv", mirror)
    write_csv(OUT / "T13_plan_duplicates.csv", duplicate_rows(series))
    write_csv(OUT / "T13_plan_baseline.csv", baseline_rows(cells, series, engine))
    print(f"done: {len(cells)} cells, {len(mirror)} mirror rows, "
          f"{time.perf_counter() - started:.0f} s")  # fmt: skip


if __name__ == "__main__":
    main()
