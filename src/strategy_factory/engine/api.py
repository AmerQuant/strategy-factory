"""NumPy front-end of the engine kernels (F-0.3.1): typed inputs, validated shapes.

Still pure: arrays and scalars in, arrays out; no files, config or logging. The caller
(``pipeline/backtest.py``) turns components, cost profiles and config into these inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from strategy_factory.engine import kernel as k


@dataclass(frozen=True)
class MarketArrays:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    atr: np.ndarray  # ATR of each bar; the engine reads atr[signal bar]


@dataclass(frozen=True)
class CostInputs:
    half_spread: np.ndarray
    slippage_fixed: np.ndarray
    slippage_atr_frac: float
    swap_long: np.ndarray  # credit per unit of notional at the bar's close
    swap_short: np.ndarray
    rollover_mask: np.ndarray
    triple_mask: np.ndarray
    commission_params: tuple[int, float, float, float]
    commission_in_quote: bool = False


@dataclass(frozen=True)
class SizingInputs:
    mode: int  # kernel.SIZE_RESEARCH | SIZE_CONTRACTS | SIZE_PARITY
    notional: float
    initial_capital: float
    contract_size: float = 1.0
    volume_step: float = 1.0
    min_volume: float = 1.0
    step_rel_tol: float = 0.0
    contracts: float = 1.0
    point_value: float = 1.0
    parity_qty_step: float | None = None  # required in parity mode (D-347), no default


@dataclass(frozen=True)
class ExitParams:
    time_exit_bars: int = 0  # 0 = unused
    sl_atr: float = math.nan  # NaN = unused
    tp_atr: float = math.nan
    trail_atr: float = math.nan
    disaster_atr: float = math.nan  # required (D-130); from config


@dataclass(frozen=True)
class SimResult:
    entry_idx: np.ndarray
    exit_idx: np.ndarray
    qty: np.ndarray
    entry_price: np.ndarray
    exit_price: np.ndarray
    pnl_gross: np.ndarray
    cost_spread: np.ndarray
    cost_slippage: np.ndarray
    cost_commission: np.ndarray
    cost_swap: np.ndarray
    pnl_net: np.ndarray
    exit_reason: np.ndarray
    mae: np.ndarray
    mfe: np.ndarray
    atr_at_entry: np.ndarray
    equity: np.ndarray
    in_position: np.ndarray
    realized_pnl: np.ndarray
    open_pnl_end: float
    n_skipped_min_volume: int


@dataclass(frozen=True)
class GridResult:
    equity: np.ndarray  # (n_configs, n_bars)
    in_position: np.ndarray  # (n_configs, n_bars)
    n_closed_trades: np.ndarray  # (n_configs,) int64 (D-301)
    n_skipped_min_volume: np.ndarray  # (n_configs,) int64


def _f(a: Any, n: int, name: str) -> np.ndarray:
    arr = np.ascontiguousarray(a, dtype=np.float64)
    if arr.shape != (n,):
        raise ValueError(f"{name} has shape {arr.shape}, expected ({n},)")
    return arr


def _b(a: Any, n: int, name: str) -> np.ndarray:
    arr = np.ascontiguousarray(a, dtype=np.bool_)
    if arr.shape != (n,):
        raise ValueError(f"{name} has shape {arr.shape}, expected ({n},)")
    return arr


def _common(
    m: MarketArrays,
    direction: int,
    disaster_atr: float,
    c: CostInputs,
    fx_open: Any,
    fx_close: Any,
    s: SizingInputs,
    intrabar_mode: int,
) -> tuple[Any, ...]:
    n = np.asarray(m.close).shape[0]
    if n < 2:
        raise ValueError("the engine needs at least 2 bars")
    if direction not in (1, -1):
        raise ValueError("direction must be +1 or -1")
    if not (disaster_atr > 0):
        raise ValueError("disaster_atr must be > 0 (D-130)")
    if intrabar_mode not in (k.MODE_TRADINGVIEW, k.MODE_PESSIMISTIC):
        raise ValueError("unknown intrabar mode")
    if s.mode not in (k.SIZE_RESEARCH, k.SIZE_CONTRACTS, k.SIZE_PARITY):
        raise ValueError("unknown sizing mode")
    if s.mode == k.SIZE_PARITY and not (s.parity_qty_step is not None and s.parity_qty_step > 0):
        raise ValueError(
            "parity sizing needs a positive parity_qty_step per run (D-347): the TradingView "
            "quantity step of the symbol, e.g. 1 for BATS:SPY, 0.01 for OANDA:XAUUSD"
        )
    code, p0, p1, p2 = c.commission_params
    one = np.ones(n)
    return (
        _f(m.open, n, "open"), _f(m.high, n, "high"), _f(m.low, n, "low"),
        _f(m.close, n, "close"), _f(m.atr, n, "atr"), int(direction),
        float(disaster_atr),
        _f(c.half_spread, n, "half_spread"), _f(c.slippage_fixed, n, "slippage_fixed"),
        float(c.slippage_atr_frac), _f(c.swap_long, n, "swap_long"),
        _f(c.swap_short, n, "swap_short"), _b(c.rollover_mask, n, "rollover_mask"),
        _b(c.triple_mask, n, "triple_mask"), int(code), float(p0), float(p1), float(p2),
        bool(c.commission_in_quote),
        one if fx_open is None else _f(fx_open, n, "fx_open"),
        one if fx_close is None else _f(fx_close, n, "fx_close"),
        int(s.mode), float(s.notional), float(s.contracts), float(s.point_value),
        float(s.contract_size), float(s.volume_step), float(s.min_volume),
        float(s.parity_qty_step or 0.0), float(s.step_rel_tol), float(s.initial_capital),
        int(intrabar_mode),
    )  # fmt: skip


def simulate(
    market: MarketArrays,
    entry_sig: Any,
    exit_sig: Any,
    direction: int,
    exits: ExitParams,
    costs: CostInputs,
    sizing: SizingInputs,
    intrabar_mode: int,
    fx_open: Any = None,
    fx_close: Any = None,
) -> SimResult:
    """One run with its trade list (see :mod:`strategy_factory.engine.kernel`)."""
    a = _common(market, direction, exits.disaster_atr, costs, fx_open, fx_close, sizing,
                intrabar_mode)  # fmt: skip
    n = a[0].shape[0]
    (o, h, lo, c, atr, d, dis, hs, sf, saf, swl, sws, rm, tm, cc, p0, p1, p2, ciq,
     fo, fc, sm, nt, ct, pv, cs, vs, mv, pqs, tol, cap, im) = a  # fmt: skip
    out = k.simulate_one(
        o, h, lo, c, atr, _b(entry_sig, n, "entry_sig"), _b(exit_sig, n, "exit_sig"), d,
        int(exits.time_exit_bars), float(exits.sl_atr), float(exits.tp_atr),
        float(exits.trail_atr), dis, hs, sf, saf, swl, sws, rm, tm, cc, p0, p1, p2, ciq,
        fo, fc, sm, nt, ct, pv, cs, vs, mv, pqs, tol, cap, im,
    )  # fmt: skip
    fields_: list[Any] = [*out[:18], float(out[19]), int(out[20])]
    return SimResult(*fields_)


def simulate_grid(
    market: MarketArrays,
    entry_matrix: Any,
    exit_matrix: Any,
    direction: int,
    time_exit_bars: Any,
    sl_atr: Any,
    tp_atr: Any,
    trail_atr: Any,
    disaster_atr: float,
    costs: CostInputs,
    sizing: SizingInputs,
    intrabar_mode: int,
    fx_open: Any = None,
    fx_close: Any = None,
) -> GridResult:
    """Many configurations (columns) in parallel (``prange``); metrics inputs only."""
    a = _common(market, direction, disaster_atr, costs, fx_open, fx_close, sizing,
                intrabar_mode)  # fmt: skip
    n = a[0].shape[0]
    ent = np.asarray(entry_matrix, dtype=np.bool_)
    ext = np.asarray(exit_matrix, dtype=np.bool_)
    if ent.ndim != 2 or ent.shape[0] != n or ext.shape != ent.shape:
        raise ValueError("entry/exit matrices must be (n_bars, n_configs) and equal in shape")
    kc = ent.shape[1]

    def col(x: Any, dtype: Any, name: str) -> np.ndarray:
        arr = np.ascontiguousarray(x, dtype=dtype)
        if arr.shape != (kc,):
            raise ValueError(f"{name} must have one value per configuration")
        return arr

    (o, h, lo, c, atr, d, dis, hs, sf, saf, swl, sws, rm, tm, cc, p0, p1, p2, ciq,
     fo, fc, sm, nt, ct, pv, cs, vs, mv, pqs, tol, cap, im) = a  # fmt: skip
    eq, ip, ncl, nsk = k.simulate_grid_kernel(
        o, h, lo, c, atr, ent, ext, d,
        col(time_exit_bars, np.int64, "time_exit_bars"), col(sl_atr, np.float64, "sl_atr"),
        col(tp_atr, np.float64, "tp_atr"), col(trail_atr, np.float64, "trail_atr"), dis,
        hs, sf, saf, swl, sws, rm, tm, cc, p0, p1, p2, ciq,
        fo, fc, sm, nt, ct, pv, cs, vs, mv, pqs, tol, cap, im,
    )  # fmt: skip
    return GridResult(eq, ip, ncl, nsk)
