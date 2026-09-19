"""F-0.3.9: data-truncation (look-ahead) gate for components + engine. Mandatory; never skipped.

For every registered entry component and every exit type, running the whole backtest
(signals, ATR, cost arrays, engine) on bars ``[0, t)`` gives the same equity and position for
every bar ``< t`` and the same trades for every trade that exits before ``t``, as the run on
the full series.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pytest
from fixtures.indicator_cases import random_ohlc

from strategy_factory.components.base import ExitSpec
from strategy_factory.components.registry import default_registry
from strategy_factory.costs.arrays import build_cost_arrays
from strategy_factory.costs.profile import CostProfile
from strategy_factory.pipeline.backtest import (
    BacktestSpec,
    EngineConfig,
    entry_signals,
    run_backtest,
)

pytestmark = pytest.mark.leakage

N_BARS = 400  # long enough for every registered component to fire (SMA 100, Donchian 55)
SEED = 13
CUTS = (60, 131, 222, 305, 399)
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
T0 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
CFG = EngineConfig(
    initial_capital=100_000.0, notional=100_000.0, disaster_stop_atr=3.0, atr_length=14,
    futures_contracts=1.0,
)  # fmt: skip
PROFILE = CostProfile.model_validate(
    {
        "name": "leak",
        "status": "verified",
        "spread": {"mode": "fixed", "fixed": {"value": 2.0, "unit": "bps"}},
        "commission": {"model": "per_order", "amount": 1.0},
        "swap": {"model": "annual_rate", "long": -0.05, "short": -0.03, "day_count": 360},
        "slippage": {"fixed": {"value": 1.0, "unit": "bps"}, "atr_fraction": 0.05},
        "volume_step": 0.1,
        "min_volume": 0.1,
        "volume_step_assumed": False,
    }
)
EXITS = {
    "signal": ExitSpec(signal_exit=True),
    "time": ExitSpec(time_exit_bars=4),
    "stop_target": ExitSpec(sl_atr=1.0, tp_atr=1.5),
    "trailing": ExitSpec(trail_atr=1.2),
    "disaster_only": ExitSpec(),
}
ENTRIES = default_registry().entries()


def bars_of(seed: int) -> dict[str, np.ndarray]:
    o, h, lo, c = random_ohlc(seed, N_BARS, flat_prob=0.1)
    t0 = (T0 - EPOCH) // dt.timedelta(microseconds=1)
    ts = t0 + np.arange(N_BARS, dtype=np.int64) * 3_600_000_000
    return {"ts": ts, "open": o, "high": h, "low": lo, "close": c}


def head(bars: dict[str, np.ndarray], t: int) -> dict[str, np.ndarray]:
    return {k_: v[:t] for k_, v in bars.items()}


def backtest(
    bars: dict[str, np.ndarray], entry: Any, exit_name: str, direction: str, mode: str
) -> Any:
    from strategy_factory.components.base import Bars

    spec = BacktestSpec(entry=entry.name, exit=EXITS[exit_name])
    exit_signal = None
    if spec.exit.signal_exit:  # the opposite-direction signal of the same component (causal)
        b = Bars(bars["open"], bars["high"], bars["low"], bars["close"])
        long_, short = entry.signals(b)
        exit_signal = short if direction == "long" else long_
    costs = build_cost_arrays(bars, PROFILE, timeframe="1H")
    return run_backtest(
        bars, spec, costs, symbol="LEAK", timeframe="1H", direction=direction,
        intrabar_mode=mode, exit_signal=exit_signal, config=CFG,
    )  # type: ignore[arg-type]  # fmt: skip


@pytest.mark.parametrize("mode", ["pessimistic", "tradingview"])
@pytest.mark.parametrize("exit_name", sorted(EXITS))
@pytest.mark.parametrize("entry", ENTRIES, ids=[e.name for e in ENTRIES])
def test_F_0_3_9_engine_truncation_invariant(entry: Any, exit_name: str, mode: str) -> None:
    bars = bars_of(SEED)
    for direction in entry.directions:
        signals = entry_signals(bars, BacktestSpec(entry=entry.name), direction)
        assert signals.any(), f"{entry.name} {direction} never fires: the gate would be vacuous"
        full = backtest(bars, entry, exit_name, direction, mode)
        assert len(full.trades) > 0 or full.equity.in_position.any()  # a position was taken
        for t in CUTS:
            part = backtest(head(bars, t), entry, exit_name, direction, mode)
            np.testing.assert_array_equal(part.equity.equity_mtm, full.equity.equity_mtm[:t])
            np.testing.assert_array_equal(part.equity.in_position, full.equity.in_position[:t])
            done = full.trades.exit_idx <= t - 1
            for col, values in part.trades.columns().items():
                np.testing.assert_array_equal(values, full.trades.columns()[col][done], err_msg=col)
