"""The matched random-entry baseline (F-1.4; D-102, D-607, D-615).

For one probe x direction with ``n`` closed trades holding ``h_1 … h_n`` bars, each of the
``simulations`` draws places ``n`` random trades on the **allowed** signal bars:

* the same direction and the same count;
* holding periods = an **exact random permutation** of the probe's own ``h_i`` (a trade the
  probe closed on its entry bar, ``h = 0``, is drawn as 1: a scheduled exit needs one bar,
  D-300);
* **no overlap**: trade ``k`` occupies signal bars ``s_k … s_k + h_k`` (entry signal at the
  close of ``s_k``, fill at ``s_k + 1``; exit signal at the close of ``s_k + h_k``, fill at
  ``s_k + h_k + 1``) and the next signal bar comes after that block;
* uniformly over all such placements, exactly: with the blocks in a random order, the ``n``
  gaps between them are a uniform random composition of the free bars ("stars and bars"),
  so no draw is rejected and none is biased towards the ends. A draw is impossible only when
  the blocks do not fit at all; it is then counted (``infeasible``), never forced.

Allowed signal bars run from ``max(warm-up, first bar with a usable ATR)`` to ``n - 2`` (the
last bar whose next open exists). No bar is masked for data quality (D-615). The engine runs
each draw with **zero costs** and frictionless sizing, exactly as the probe's own statistic
is measured (D-602); trades end at their drawn holding period or earlier on the 3-ATR
disaster stop (D-130).

Seeds (D-607): one generator per (run seed, symbol, timeframe, probe, direction) -- see
:func:`baseline_seed` -- drawn sequentially for its simulations, so execution order, chunking
and the worker count change no number. Baseline simulations are not trials (D-012).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import (
    CostInputs,
    ExitParams,
    MarketArrays,
    SimResult,
    SizingInputs,
    simulate,
)
from strategy_factory.pipeline.executor import unit_seed

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

_US_PER_YEAR_EPOCH = "datetime64[us]"


def baseline_seed(run_seed: int, symbol: str, timeframe: str, probe: str, direction: str) -> int:
    """D-607: ``sha256(run_seed, symbol, timeframe, probe, direction)`` via :func:`unit_seed`."""
    return unit_seed(run_seed, f"{symbol}|{timeframe}|{probe}|{direction}")


def frictionless_costs(n: int) -> CostInputs:
    """Zero spread, slippage, swap and commission (D-602: probes and baseline cost nothing)."""
    zeros = np.zeros(n)
    no = np.zeros(n, dtype=np.bool_)
    return CostInputs(
        half_spread=zeros,
        slippage_fixed=zeros.copy(),
        slippage_atr_frac=0.0,
        swap_long=zeros.copy(),
        swap_short=zeros.copy(),
        rollover_mask=no,
        triple_mask=no.copy(),
        commission_params=(0, 0.0, 0.0, 0.0),
    )


def frictionless_sizing(notional: float, initial_capital: float) -> SizingInputs:
    """Research sizing without a volume step or minimum: an ATR return does not depend on the
    quantity, and a skipped trade would change the count the baseline must match."""
    return SizingInputs(
        mode=k.SIZE_RESEARCH,
        notional=notional,
        initial_capital=initial_capital,
        volume_step=1e-9,
        min_volume=0.0,
    )


def atr_returns(sim: SimResult, direction: int) -> FloatArray:
    """Per-trade return in ATR units of the signal bar: ``d * (exit - entry) / atr``."""
    return np.asarray(
        direction * (sim.exit_price - sim.entry_price) / sim.atr_at_entry, dtype=np.float64
    )


def trade_years(ts_us: IntArray, entry_idx: IntArray) -> IntArray:
    """Calendar year (UTC) of each trade's entry bar."""
    years = ts_us[entry_idx].astype(_US_PER_YEAR_EPOCH).astype("datetime64[Y]")
    return np.asarray(years.astype(np.int64) + 1970, dtype=np.int64)


def allowed_range(n: int, warmup: int, atr: FloatArray) -> tuple[int, int]:
    """``(lo, hi)``: the first and last allowed signal bar (see the module docstring)."""
    usable = np.flatnonzero(np.isfinite(atr) & (atr > 0))
    first_atr = int(usable[0]) if usable.size else n
    return max(warmup, first_atr), n - 2


def draw_placements(
    rng: np.random.Generator, holdings: npt.ArrayLike, lo: int, hi: int
) -> tuple[IntArray, IntArray] | tuple[None, None]:
    """``(signal bars, holding bars)`` of one draw, in time order; ``(None, None)`` if the
    blocks cannot fit into ``lo … hi``."""
    held = np.maximum(np.asarray(holdings, dtype=np.int64), 1)
    n = held.size
    if n == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    held = rng.permutation(held)
    blocks = held + 1  # signal bars s … s + h
    free = (hi - lo + 1) - int(blocks.sum())
    if free < 0:
        return None, None
    cuts = np.sort(rng.choice(free + n, size=n, replace=False)) - np.arange(n)
    offsets = np.concatenate(([0], np.cumsum(blocks)[:-1]))
    return (lo + cuts + offsets).astype(np.int64), held


def baseline_signals(n: int, starts: IntArray, held: IntArray) -> tuple[BoolArray, BoolArray]:
    """Entry signals at ``s_k`` and exit signals at ``s_k + h_k`` (both at the close)."""
    entry = np.zeros(n, dtype=np.bool_)
    exit_ = np.zeros(n, dtype=np.bool_)
    entry[starts] = True
    exit_[starts + held] = True
    return entry, exit_


@dataclass(frozen=True)
class BaselineResult:
    direction: int
    sim_means: FloatArray  # mean ATR return per trade of each simulation (NaN: none)
    trades_per_sim: IntArray
    pooled_returns: FloatArray  # every simulated trade's ATR return
    pooled_years: IntArray  # the entry year of each pooled trade
    infeasible: int  # draws whose blocks did not fit
    clamped_holdings: int  # probe trades with 0 bars held, drawn as 1

    @property
    def pooled_mean(self) -> float:
        r = self.pooled_returns
        return float(r.mean()) if r.size else float("nan")


def run_baseline(
    market: MarketArrays,
    ts_us: IntArray,
    *,
    direction: int,
    holdings: npt.ArrayLike,
    lo: int,
    hi: int,
    simulations: int,
    disaster_atr: float,
    rng: np.random.Generator,
    notional: float = 100_000.0,
    initial_capital: float = 100_000.0,
) -> BaselineResult:
    """Run ``simulations`` matched draws through the engine (zero costs, D-602)."""
    n = int(market.close.shape[0])
    held_in = np.asarray(holdings, dtype=np.int64)
    costs = frictionless_costs(n)
    sizing = frictionless_sizing(notional, initial_capital)
    exits = ExitParams(disaster_atr=disaster_atr)
    means = np.full(simulations, np.nan)
    counts = np.zeros(simulations, dtype=np.int64)
    rets: list[FloatArray] = []
    years: list[IntArray] = []
    infeasible = 0
    for i in range(simulations):
        starts, held = draw_placements(rng, held_in, lo, hi)
        if starts is None or held is None:
            infeasible += 1
            continue
        entry, exit_ = baseline_signals(n, starts, held)
        sim = simulate(market, entry, exit_, direction, exits, costs, sizing, k.MODE_PESSIMISTIC)
        r = atr_returns(sim, direction)
        counts[i] = r.size
        if r.size:
            means[i] = float(r.mean())
            rets.append(r)
            years.append(trade_years(ts_us, sim.entry_idx))
    return BaselineResult(
        direction=direction,
        sim_means=means,
        trades_per_sim=counts,
        pooled_returns=np.concatenate(rets) if rets else np.zeros(0),
        pooled_years=np.concatenate(years) if years else np.zeros(0, dtype=np.int64),
        infeasible=infeasible,
        clamped_holdings=int(np.count_nonzero(held_in == 0)),
    )
