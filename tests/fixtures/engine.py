"""Builders for engine tests (T08): inputs for the kernel and for the naive oracle alike."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import (
    CostInputs,
    ExitParams,
    MarketArrays,
    ParityInputs,
    SimResult,
    SizingInputs,
    simulate,
)
from strategy_factory.metrics.containers import RunMeta, RunResult

T0 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
MODE = {"tradingview": k.MODE_TRADINGVIEW, "pessimistic": k.MODE_PESSIMISTIC}
SIZE = {"research": k.SIZE_RESEARCH, "contracts": k.SIZE_CONTRACTS, "parity": k.SIZE_PARITY}


@dataclass
class Case:
    """Everything one run needs, in plain arrays and scalars (shared by kernel and oracle)."""

    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    entry: np.ndarray
    exit_: np.ndarray
    direction: int = 1
    time_exit: int = 0
    sl: float | None = None
    tp: float | None = None
    trail: float | None = None
    disaster: float = 3.0
    half_spread: np.ndarray | None = None
    slip_fixed: np.ndarray | None = None
    slip_frac: float = 0.0
    swap_long: np.ndarray | None = None
    swap_short: np.ndarray | None = None
    rollover: np.ndarray | None = None
    triple: np.ndarray | None = None
    comm_code: int = 0
    comm_p: tuple[float, float, float] = (0.0, 0.0, 0.0)
    comm_in_quote: bool = False
    fx_open: np.ndarray | None = None
    fx_close: np.ndarray | None = None
    sizing: str = "research"
    notional: float = 100_000.0
    contracts: float = 1.0
    point_value: float = 1.0
    contract_size: float = 1.0
    step: float = 1.0
    min_volume: float = 1.0
    parity_qty_step: float | None = None  # required in parity mode (D-347)
    # D-366 / D-367: the two parity-only options, off by default (= research behaviour)
    parity_tick: float | None = None
    entry_requires_flat: bool = False
    step_tol: float = 1e-9
    capital: float = 100_000.0
    mode: str = "pessimistic"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.c)
        z = np.zeros(n)
        f = np.zeros(n, dtype=np.bool_)
        for name in ("half_spread", "slip_fixed", "swap_long", "swap_short"):
            if getattr(self, name) is None:
                setattr(self, name, z.copy())
        for name in ("rollover", "triple"):
            if getattr(self, name) is None:
                setattr(self, name, f.copy())

    @property
    def n(self) -> int:
        return len(self.c)

    def with_(self, **kw: Any) -> Case:
        return replace(self, **kw)


def ohlc(o: list[float], h: list[float], lo: list[float], c: list[float]) -> dict[str, np.ndarray]:
    return {
        k_: np.asarray(v, dtype=np.float64) for k_, v in (("o", o), ("h", h), ("lo", lo), ("c", c))
    }


def flags(n: int, *idx: int) -> np.ndarray:
    a = np.zeros(n, dtype=np.bool_)
    a[list(idx)] = True
    return a


def _nan(x: float | None) -> float:
    return math.nan if x is None else float(x)


def run_engine(case: Case) -> SimResult:
    costs = CostInputs(
        half_spread=case.half_spread,
        slippage_fixed=case.slip_fixed,
        slippage_atr_frac=case.slip_frac,
        swap_long=case.swap_long,
        swap_short=case.swap_short,
        rollover_mask=case.rollover,
        triple_mask=case.triple,
        commission_params=(case.comm_code, *case.comm_p),
        commission_in_quote=case.comm_in_quote,
    )  # type: ignore[arg-type]
    sizing = SizingInputs(
        mode=SIZE[case.sizing],
        notional=case.notional,
        initial_capital=case.capital,
        contract_size=case.contract_size,
        volume_step=case.step,
        min_volume=case.min_volume,
        parity_qty_step=case.parity_qty_step,
        step_rel_tol=case.step_tol,
        contracts=case.contracts,
        point_value=case.point_value,
    )
    exits = ExitParams(
        case.time_exit, _nan(case.sl), _nan(case.tp), _nan(case.trail), case.disaster
    )
    return simulate(
        MarketArrays(case.o, case.h, case.lo, case.c, case.atr),
        case.entry,
        case.exit_,
        case.direction,
        exits,
        costs,
        sizing,
        MODE[case.mode],
        case.fx_open,
        case.fx_close,
        ParityInputs(tick_size=case.parity_tick, entry_requires_flat=case.entry_requires_flat),
    )


def run_oracle(case: Case) -> Any:
    from oracle.naive_engine import run

    return run(
        o=case.o, h=case.h, lo=case.lo, c=case.c, atr=case.atr, entry=case.entry,
        exit_=case.exit_, direction=case.direction, time_exit=case.time_exit, sl=case.sl,
        tp=case.tp, trail=case.trail, disaster=case.disaster, half_spread=case.half_spread,
        slip_fixed=case.slip_fixed, slip_frac=case.slip_frac, swap_long=case.swap_long,
        swap_short=case.swap_short, rollover=case.rollover, triple=case.triple,
        comm_code=case.comm_code, comm_p=case.comm_p, comm_in_quote=case.comm_in_quote,
        fx_open=case.fx_open, fx_close=case.fx_close, sizing=case.sizing,
        notional=case.notional, contracts=case.contracts, point_value=case.point_value,
        contract_size=case.contract_size, step=case.step, min_volume=case.min_volume,
        parity_qty_step=case.parity_qty_step, step_tol=case.step_tol, capital=case.capital,
        mode=case.mode, parity_tick=case.parity_tick,
        entry_requires_flat=case.entry_requires_flat,
    )  # fmt: skip


def hourly_ts_us(n: int) -> np.ndarray:
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    t0 = (T0 - epoch) // dt.timedelta(microseconds=1)
    return t0 + np.arange(n, dtype=np.int64) * 3_600_000_000


def to_result(case: Case, sim: SimResult, ts_us: np.ndarray | None = None) -> RunResult:
    """The T09 containers of a run (validation included)."""
    from strategy_factory.pipeline.backtest import EngineConfig, to_run_result

    cfg = EngineConfig(
        initial_capital=case.capital, notional=case.notional, disaster_stop_atr=case.disaster,
        atr_length=14, futures_contracts=case.contracts,
    )  # fmt: skip
    meta = RunMeta(
        symbol="TEST", timeframe="1H", spec_hash="x", cost_status="verified",
        intrabar_mode=case.mode, n_skipped_min_volume=sim.n_skipped_min_volume,
    )  # type: ignore[arg-type]  # fmt: skip
    return to_run_result(
        sim, hourly_ts_us(case.n) if ts_us is None else ts_us, case.direction, meta, cfg
    )


def random_case(rng: np.random.Generator, n: int, **kw: Any) -> Case:
    """A random-walk series with random signals (positive prices, ATR ~ 1 % of price)."""
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    o = np.concatenate([[c[0]], c[:-1]]) * np.exp(rng.normal(0.0, 0.003, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0.0, 0.006, n)))
    lo = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0.0, 0.006, n)))
    atr = np.abs(h - lo) + 0.5
    atr[: int(rng.integers(0, 4))] = np.nan
    base = {
        "o": o, "h": h, "lo": lo, "c": c, "atr": atr,
        "entry": rng.random(n) < 0.2, "exit_": rng.random(n) < 0.15,
    }  # fmt: skip
    base.update(kw)
    return Case(**base)
