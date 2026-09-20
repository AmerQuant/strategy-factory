"""F-0.3.1 sizing and swap rules required by D-312 ... D-315, plus D-327, D-328 and the glue.

1. multi-day swap with a changing price and a triple day (long, short, non-USD) = hand value =
   the T06b oracle ``round_trip_cost``;
2. quantity floored to the volume step (share CFD, FX), notional <= 100,000;
3. a signal below the minimum volume is skipped, counted, flagged (single run, grid, RunMeta,
   gate dict);
4. parity (tradingview) sizing is unaffected by the rounding;
5. volume_step_assumed / contracts_fixed reach RunMeta.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pytest
from fixtures.engine import Case, flags, run_engine, to_result

from strategy_factory.core.errors import ConfigError
from strategy_factory.costs.arrays import build_cost_arrays, round_trip_cost
from strategy_factory.costs.profile import CostProfile
from strategy_factory.data.conversion import ConversionArrays
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import simulate_grid
from strategy_factory.metrics.standard import compute_metrics
from strategy_factory.pipeline.backtest import (
    BacktestSpec,
    EngineConfig,
    FuturesSizing,
    cost_inputs,
    market_arrays,
    run_backtest,
    sizing_inputs,
)

EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
ROLL = {"rollover_time_local": "17:00", "rollover_tz": "America/New_York"}
CFG = EngineConfig(
    initial_capital=100_000.0, notional=100_000.0, disaster_stop_atr=3.0, atr_length=2,
    futures_contracts=1.0,
)  # fmt: skip


def profile(swap: dict[str, Any], **extra: Any) -> CostProfile:
    base: dict[str, Any] = {
        "name": "t",
        "status": "verified",
        "spread": {"mode": "fixed", "fixed": {"value": 0.0}},
        "commission": {"model": "none"},
        "swap": swap,
        "volume_step_assumed": False,
    }
    base.update(extra)
    return CostProfile.model_validate(base)


def daily(days: list[dt.date], close: list[float]) -> dict[str, np.ndarray]:
    ts = [dt.datetime.combine(d, dt.time(), tzinfo=dt.UTC) for d in days]
    c = np.asarray(close, dtype=np.float64)
    return {
        "ts": np.array([(t - EPOCH) // dt.timedelta(microseconds=1) for t in ts], np.int64),
        "open": c.copy(), "high": c + 0.5, "low": c - 0.5, "close": c,
    }  # fmt: skip


def case_from(bars: dict[str, np.ndarray], costs: Any, **kw: Any) -> Case:
    n = bars["close"].shape[0]
    base: dict[str, Any] = {
        "o": bars["open"], "h": bars["high"], "lo": bars["low"], "c": bars["close"],
        "atr": bars["close"] * 0.1, "entry": flags(n, 0), "exit_": flags(n, 4),
        "half_spread": costs.half_spread, "slip_fixed": costs.slippage_fixed,
        "swap_long": costs.swap_long_per_notional_day,
        "swap_short": costs.swap_short_per_notional_day, "rollover": costs.rollover_mask,
        "triple": costs.triple_mask, "contract_size": costs.contract_size,
        "step": costs.volume_step, "min_volume": costs.min_volume,
    }  # fmt: skip
    base.update(kw)
    return Case(**base)


# Tue 9, Wed 10, Thu 11, Fri 12 (triple), Mon 15, Tue 16; closes change every day
DAYS = [dt.date(2024, 1, d) for d in (9, 10, 11, 12, 15, 16)]
CLOSE = [100.0, 100.0, 104.0, 99.0, 101.0, 103.0]


# -- 1. D-312: multi-day swap on the MTM notional with a triple day ------------------------------
@pytest.mark.parametrize(("direction", "rate"), [(1, -0.0688), (-1, -0.035)])
def test_F_0_3_1_d312_multi_day_swap_changing_price_triple_day(direction: int, rate: float) -> None:
    p = profile(
        {"model": "annual_rate", "long": -0.0688, "short": -0.035, "day_count": 360,
         "triple_weekday": "FRI", **ROLL},
        volume_step=0.1, min_volume=0.1,
    )  # fmt: skip
    bars = daily(DAYS, CLOSE)
    costs = build_cost_arrays(bars, p, timeframe="1D")
    case = case_from(bars, costs, direction=direction, notional=1000.0)
    sim = run_engine(case)
    # entry at open 1 (Wed, 100): 1000 / 100 / 0.1 = 100 steps -> 10 shares; exit at open 5
    assert (sim.entry_idx[0], sim.exit_idx[0], sim.qty[0]) == (1, 5, 10.0)
    # held at the closes of Wed 100, Thu 104, Fri 99 (x3), Mon 101 = 602 price-days x 10 shares
    hand = -rate / 360 * 10 * (100 + 104 + 3 * 99 + 101)
    assert sim.cost_swap[0] == pytest.approx(hand, rel=1e-12)
    oracle = round_trip_cost(
        costs, 1, 5, 10.0, direction, 100.0, 103.0, 1.0, 1.0, close=bars["close"]
    )
    assert sim.cost_swap[0] == pytest.approx(oracle["swap"], rel=1e-12)
    to_result(case, sim)


def test_F_0_3_1_d312_non_usd_swap_converted_at_each_rollover_bar() -> None:
    p = profile(
        {"model": "currency_per_lot_day", "long": -3.4908, "short": 0.1106,
         "triple_weekday": "FRI", **ROLL},
        quote_ccy="EUR", contract_size=1.0, volume_step=0.01, min_volume=0.01,
    )  # fmt: skip
    bars = daily(DAYS, [16000.0, 16000.0, 16100.0, 15900.0, 16050.0, 16000.0])
    costs = build_cost_arrays(bars, p, timeframe="1D")
    fx = np.array([1.10, 1.10, 1.09, 1.08, 1.07, 1.06])
    case = case_from(bars, costs, fx_open=fx, fx_close=fx)
    sim = run_engine(case)
    lots = sim.qty[0]  # floor(100000 / (16000 x 1.10) / 0.01) x 0.01 = 5.68
    assert lots == pytest.approx(5.68)
    # Wed x1 at 1.10, Thu x1 at 1.09, Fri x3 at 1.08, Mon x1 at 1.07 (EUR -> USD, D-307)
    hand = 3.4908 * lots * (1.10 + 1.09 + 3 * 1.08 + 1.07)
    assert sim.cost_swap[0] == pytest.approx(hand, rel=1e-12)
    oracle = round_trip_cost(
        costs, 1, 5, lots, 1, 16000.0, 16000.0, 1.0, 1.0, close=bars["close"], fx_close=fx
    )
    assert sim.cost_swap[0] == pytest.approx(oracle["swap"], rel=1e-12)


# -- 2. D-313/D-315: floor to the step -----------------------------------------------------------
@pytest.mark.parametrize(
    ("price", "cs", "step", "expected_qty"),
    [(211.07, 1.0, 0.1, 473.7), (1.0837, 100_000.0, 0.01, 92_000.0)],
)
def test_F_0_3_1_d315_qty_floored_to_the_volume_step(
    price: float, cs: float, step: float, expected_qty: float
) -> None:
    n = 6
    o = np.full(n, price)
    case = Case(o=o, h=o * 1.001, lo=o * 0.999, c=o.copy(), atr=np.full(n, price * 0.01),
                entry=flags(n, 1), exit_=flags(n, 3), contract_size=cs, step=step,
                min_volume=step)  # fmt: skip
    sim = run_engine(case)
    assert sim.qty[0] == pytest.approx(expected_qty, rel=1e-12)
    assert sim.qty[0] * price <= 100_000.0  # the notional never exceeds 100,000 USD (D-313)
    assert sim.qty[0] * price > 100_000.0 - step * cs * price  # and it is the largest step


# -- 3. D-313: below the minimum volume -> skipped, counted, flagged ------------------------------
def expensive_case(**kw: Any) -> Case:
    n = 8
    o = np.full(n, 2_000_000.0)  # 100,000 / 2,000,000 = 0.05 share < 0.1 minimum
    base: dict[str, Any] = {
        "o": o, "h": o * 1.001, "lo": o * 0.999, "c": o.copy(), "atr": np.full(n, 1000.0),
        "entry": flags(n, 1), "exit_": flags(n, 4), "step": 0.1, "min_volume": 0.1,
    }  # fmt: skip
    base.update(kw)
    return Case(**base)


def test_F_0_3_1_d313_signal_below_minimum_volume_is_skipped() -> None:
    case = expensive_case()
    sim = run_engine(case)
    assert sim.entry_idx.size == 0 and sim.n_skipped_min_volume == 1
    assert not sim.in_position.any()
    assert np.all(sim.equity == 100_000.0)  # the strategy stays flat
    res = to_result(case, sim)
    assert res.meta.n_skipped_min_volume == 1
    gate = compute_metrics(res, calendar="24x5").as_gate_dict()
    assert gate["n_skipped_min_volume"] == 1.0 and gate["min_volume_skip_flag"] == 1.0
    grid = grid_of(case, 3)
    assert grid.n_skipped_min_volume.tolist() == [1, 1, 1]
    assert grid.n_closed_trades.tolist() == [0, 0, 0]


def grid_of(case: Case, k_: int) -> Any:
    from fixtures.engine import SIZE

    from strategy_factory.engine.api import CostInputs, MarketArrays, SizingInputs

    nan = np.full(k_, np.nan)
    return simulate_grid(
        MarketArrays(case.o, case.h, case.lo, case.c, case.atr),
        np.column_stack([case.entry] * k_), np.column_stack([case.exit_] * k_), case.direction,
        np.zeros(k_, np.int64), nan, nan, nan, case.disaster,
        CostInputs(case.half_spread, case.slip_fixed, case.slip_frac, case.swap_long,
                   case.swap_short, case.rollover, case.triple, (0, 0.0, 0.0, 0.0)),
        SizingInputs(SIZE[case.sizing], case.notional, case.capital, case.contract_size,
                     case.step, case.min_volume, case.step_tol),
        k.MODE_PESSIMISTIC,
    )  # fmt: skip


# -- 4. parity sizing unaffected by the rounding (D-313, D-337) ----------------------------------
def parity_case(price: float, qty_step: float, **kw: Any) -> Case:
    n = 6
    o = np.full(n, price)
    base: dict[str, Any] = {
        "o": o, "h": o * 1.001, "lo": o * 0.999, "c": o.copy(), "atr": np.full(n, price * 0.02),
        "entry": flags(n, 1), "exit_": flags(n, 3), "sizing": "parity", "mode": "tradingview",
        "parity_qty_step": qty_step, "step": 0.1, "min_volume": 0.1,
    }  # fmt: skip
    base.update(kw)
    return Case(**base)


@pytest.mark.parametrize(
    ("price", "step", "expected"),
    [
        (211.07, 1.0, 473.0),  # BATS:SPY-like: 473.7765... -> 473 whole shares
        (2345.67, 0.01, 42.63),  # OANDA:XAUUSD-like: 42.63354... -> 42.63
        (100.0, 1.0, 1000.0),  # an exact multiple survives the float guard
        (0.4, 0.01, 250_000.0),  # 250000.0 exactly, with a fractional step
    ],
)
def test_F_0_3_1_d347_parity_qty_floored_to_the_tradingview_step(
    price: float, step: float, expected: float
) -> None:
    """D-347: qty = floor(notional / close[signal] / step) x step (the exports show flooring)."""
    sim = run_engine(parity_case(price, step))  # step here is the TradingView quantity step
    assert sim.qty[0] == pytest.approx(expected, rel=1e-12)
    assert sim.qty[0] * price <= 100_000.0 + 1e-6
    assert sim.n_skipped_min_volume == 0
    to_result(parity_case(price, step), sim)


def test_F_0_3_1_d347_parity_qty_zero_is_skipped_and_counted() -> None:
    sim = run_engine(parity_case(2_000_000.0, 1.0))  # 0.05 -> floor 0 -> no trade
    assert sim.entry_idx.size == 0 and sim.n_skipped_min_volume == 1
    assert not sim.in_position.any()


def test_F_0_3_1_d347_parity_ignores_the_broker_step_and_minimum() -> None:
    """The broker volume step and minimum volume never apply in parity mode (D-347)."""
    loose = run_engine(parity_case(211.07, 0.01, step=1.0, min_volume=10_000.0))
    assert loose.qty[0] == pytest.approx(473.77) and loose.n_skipped_min_volume == 0
    research = run_engine(parity_case(211.07, 0.01, sizing="research", mode="pessimistic"))
    assert research.qty[0] == pytest.approx(473.7)  # broker step 0.1 (D-315), not the TV step


def test_F_0_3_1_d347_parity_step_is_required() -> None:
    with pytest.raises(ValueError, match="parity_qty_step"):
        run_engine(parity_case(211.07, 1.0).with_(parity_qty_step=None))
    with pytest.raises(ValueError, match="parity_qty_step"):
        run_engine(parity_case(211.07, 1.0).with_(parity_qty_step=0.0))
    bars = signal_bars()
    costs = build_cost_arrays(bars, profile({"model": "none"}), timeframe="1D")
    with pytest.raises(ConfigError, match="parity_qty_step"):
        run_backtest(bars, SPEC, costs, symbol="X", timeframe="1D", direction="long",
                     intrabar_mode="tradingview", config=CFG)  # fmt: skip
    parity_cfg = CFG.model_copy(update={"parity_qty_step": 1.0})
    res = run_backtest(bars, SPEC, costs, symbol="X", timeframe="1D", direction="long",
                       intrabar_mode="tradingview", config=parity_cfg)  # fmt: skip
    assert np.all(res.trades.qty == np.floor(res.trades.qty))  # whole shares at step 1


# -- D-327: a stop exit inside a rollover bar -----------------------------------------------------
@pytest.mark.parametrize(
    ("mode", "rate", "charged"),
    [("pessimistic", -0.001, True), ("pessimistic", 0.001, False), ("tradingview", -0.001, False)],
)
def test_F_0_3_1_d327_stop_inside_a_rollover_bar(mode: str, rate: float, charged: bool) -> None:
    n = 6
    o = np.full(n, 100.0)
    lo = o - 0.5
    lo[3] = 96.0  # disaster hit inside bar 3, which contains a rollover
    case = Case(o=o, h=o + 0.5, lo=lo, c=o.copy(), atr=np.ones(n), entry=flags(n, 1),
                exit_=flags(n), swap_long=np.full(n, rate), rollover=flags(n, 3),
                sizing="contracts", mode=mode)  # fmt: skip
    sim = run_engine(case)
    assert (sim.exit_idx[0], sim.exit_reason[0]) == (3, k.DISASTER_STOP)
    expected = 0.001 * 1 * 100.0 if charged else 0.0  # |qty| x close[3], one day
    assert sim.cost_swap[0] == pytest.approx(expected)


# -- D-328: sizing uses the conversion OPEN of the fill bar (no look-ahead) ------------------------
def test_F_0_3_1_d328_sizing_uses_the_fill_bar_open_rate_only() -> None:
    n = 6
    o = np.full(n, 1.0)
    base = {"o": o, "h": o + 0.005, "lo": o - 0.005, "c": o.copy(), "atr": np.full(n, 0.01),
            "entry": flags(n, 1), "exit_": flags(n, 3), "contract_size": 100_000.0,
            "step": 0.01, "min_volume": 0.01}  # fmt: skip
    fx = np.full(n, 1.2)
    a = run_engine(Case(**base, fx_open=fx.copy(), fx_close=fx.copy()))
    later = fx.copy()
    later[2:] = 5.0  # the close of the fill bar and every later value change
    b = run_engine(Case(**base, fx_open=fx.copy(), fx_close=later))
    assert a.qty[0] == b.qty[0] == pytest.approx(83_000.0)
    moved = fx.copy()
    moved[2] = 1.0  # only the fill bar's open changes
    c = run_engine(Case(**base, fx_open=moved, fx_close=fx.copy()))
    assert c.qty[0] == pytest.approx(100_000.0)


# -- 5. glue: flags reach RunMeta; errors ---------------------------------------------------------
def signal_bars(n: int = 120, seed: int = 3) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n)))
    o = np.concatenate([[c[0]], c[:-1]])
    epoch_us = (dt.datetime(2024, 1, 2, tzinfo=dt.UTC) - EPOCH) // dt.timedelta(microseconds=1)
    return {
        "ts": epoch_us + np.arange(n, dtype=np.int64) * 86_400_000_000,
        "open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99, "close": c,
    }  # fmt: skip


SPEC = BacktestSpec(entry="mr_three_down_closes", exit={"time_exit_bars": 5})


def test_F_0_3_1_run_backtest_flags_and_validation() -> None:
    bars = signal_bars()
    assumed = profile({"model": "none"})
    assumed = assumed.model_copy(update={"volume_step_assumed": True})
    costs = build_cost_arrays(bars, assumed, timeframe="1D")
    res = run_backtest(bars, SPEC, costs, symbol="X", timeframe="1D", direction="long",
                       intrabar_mode="pessimistic", config=CFG)  # fmt: skip
    assert len(res.trades) > 0 and res.meta.volume_step_assumed and not res.meta.contracts_fixed
    fut = run_backtest(bars, SPEC, costs, symbol="X", timeframe="1D", direction="long",
                       intrabar_mode="pessimistic", config=CFG,
                       futures=FuturesSizing(point_value=50.0))  # fmt: skip
    assert fut.meta.contracts_fixed and fut.meta.volume_step_assumed  # D-314: whole contracts
    assert np.all(fut.trades.qty == CFG.futures_contracts)
    gate = compute_metrics(fut, calendar="us_equity").as_gate_dict()
    assert gate["contracts_fixed"] == 1.0
    assert (
        SPEC.spec_hash()
        == BacktestSpec(entry="mr_three_down_closes", exit={"time_exit_bars": 5}).spec_hash()
    )


def test_F_0_3_1_run_backtest_refuses_missing_inputs() -> None:
    bars = signal_bars()
    costs = build_cost_arrays(bars, profile({"model": "none"}), timeframe="1D")
    with pytest.raises(ConfigError, match="signal_exit"):
        run_backtest(bars, BacktestSpec(entry="mr_three_down_closes", exit={"signal_exit": True}),
                     costs, symbol="X", timeframe="1D", direction="long",
                     intrabar_mode="pessimistic", config=CFG)  # fmt: skip
    eur = build_cost_arrays(bars, profile({"model": "none"}, quote_ccy="EUR"), timeframe="1D")
    with pytest.raises(ConfigError, match="needs conversion"):
        run_backtest(bars, SPEC, eur, symbol="X", timeframe="1D", direction="long",
                     intrabar_mode="pessimistic", config=CFG)  # fmt: skip
    peg = ConversionArrays(np.full(120, 1 / 7.8), np.full(120, 1 / 7.8), "EUR", "peg:7.8", True)
    res = run_backtest(bars, SPEC, eur, symbol="X", timeframe="1D", direction="long",
                       intrabar_mode="pessimistic", config=CFG, fx=peg)  # fmt: skip
    assert res.meta.fx_peg


def test_F_0_3_1_glue_matches_the_kernel_inputs() -> None:
    bars = signal_bars()
    p = profile({"model": "none"}, volume_step=0.1, min_volume=0.1)
    costs = build_cost_arrays(bars, p, timeframe="1D")
    s = sizing_inputs(costs, CFG, "pessimistic", None)
    assert (s.mode, s.volume_step, s.min_volume) == (k.SIZE_RESEARCH, 0.1, 0.1)
    assert sizing_inputs(costs, CFG, "tradingview", None).mode == k.SIZE_PARITY
    assert cost_inputs(costs).commission_params == costs.commission_params
    m = market_arrays(bars, 2)
    assert np.isnan(m.atr[0]) and m.atr[1] > 0


def test_F_0_3_1_reproducible_bit_identical() -> None:
    """Two runs with the same inputs are bit-identical (CLAUDE.md rule 8)."""
    bars = signal_bars()
    p = profile(
        {"model": "annual_rate", "long": -0.05, "short": -0.03, "day_count": 360, **ROLL},
        spread={"mode": "fixed", "fixed": {"value": 2.0, "unit": "bps"}},
        commission={"model": "per_order", "amount": 1.0},
        volume_step=0.1, min_volume=0.1,
    )  # fmt: skip
    costs = build_cost_arrays(bars, p, timeframe="1D")
    spec = BacktestSpec(entry="mr_three_down_closes", exit={"sl_atr": 1.0, "time_exit_bars": 5})
    runs = [
        run_backtest(
            bars,
            spec,
            costs,
            symbol="X",
            timeframe="1D",
            direction="long",
            intrabar_mode="pessimistic",
            config=CFG,
        )
        for _ in range(2)
    ]
    assert len(runs[0].trades) > 0
    for col, values in runs[0].trades.columns().items():
        assert np.array_equal(values, runs[1].trades.columns()[col]), col
    for name in ("equity_mtm", "in_position", "realized_pnl"):
        assert np.array_equal(getattr(runs[0].equity, name), getattr(runs[1].equity, name))
    assert runs[0].meta == runs[1].meta
