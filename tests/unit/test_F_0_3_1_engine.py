"""F-0.3.1: engine core against hand-computed fixtures (every number derived in the comments).

Decisions: D-001 (next-open fills), D-003 (MTM equity), D-004 (sizing), D-307/D-328
(conversion), D-312 (swap on MTM notional), D-315 (lots), D-329 (futures contracts).
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.engine import Case, flags, run_engine, to_result

from strategy_factory.costs.arrays import commission_kernel as costs_commission
from strategy_factory.costs.arrays import size_lots
from strategy_factory.engine import kernel as k
from strategy_factory.engine.commission import commission_kernel as engine_commission
from strategy_factory.metrics.containers import ExitReason

R = 1e-12


def approx(x: float) -> object:
    return pytest.approx(x, rel=R, abs=1e-9)


def const(n: int, v: float) -> np.ndarray:
    return np.full(n, v)


# -- fixture 1: long, signal exit, spread + slippage + percent commission ------------------------
def long_case() -> Case:
    o = np.array([100, 100, 100, 101, 103, 105, 104, 104], float)
    c = np.array([100, 100, 101, 103, 104, 104, 104, 104], float)
    h = np.array([101, 101, 102, 104, 105, 106, 105, 105], float)
    lo = np.array([99, 99, 99.5, 100.5, 102.5, 103.5, 103, 103], float)
    n = 8
    return Case(
        o=o, h=h, lo=lo, c=c, atr=const(n, 1.0), entry=flags(n, 1), exit_=flags(n, 4),
        half_spread=const(n, 0.05), slip_fixed=const(n, 0.02), slip_frac=0.1,
        comm_code=1, comm_p=(0.001, 0.0, 0.0), notional=1000.0,
    )  # fmt: skip


def test_F_0_3_1_long_signal_exit_hand_computed() -> None:
    sim = run_engine(long_case())
    # signal at close 1 -> entry at open 2 (100); exit signal at close 4 -> exit at open 5 (105)
    assert sim.entry_idx.tolist() == [2] and sim.exit_idx.tolist() == [5]
    assert sim.exit_reason.tolist() == [ExitReason.SIGNAL]
    assert sim.qty[0] == 10.0  # floor(1000 / 100 / 1) x 1 (D-315)
    # each fill pays 0.05 + 0.02 + 0.1 x ATR 1 = 0.17
    assert sim.entry_price[0] == approx(100.17) and sim.exit_price[0] == approx(104.83)
    assert sim.pnl_gross[0] == approx(50.0)  # 10 x (105 - 100)
    assert sim.cost_spread[0] == approx(1.0)  # 10 x 0.05 x 2
    assert sim.cost_slippage[0] == approx(2.4)  # 10 x 0.12 x 2
    assert sim.cost_commission[0] == approx(0.001 * 10 * 100.17 + 0.001 * 10 * 104.83)  # 2.05
    assert sim.cost_swap[0] == 0.0
    assert sim.pnl_net[0] == approx(44.55)
    assert sim.mfe[0] == approx(50.0)  # best high 105 (bar 4) / exit 105: 5 x 10
    assert sim.mae[0] == approx(5.0)  # worst low 99.5 (bar 2): 0.5 x 10
    assert sim.atr_at_entry[0] == 1.0
    entry_costs = 0.5 + 1.2 + 1.0017
    expected = [0, 0, 10 - entry_costs, 30 - entry_costs, 40 - entry_costs, 44.55, 44.55, 44.55]
    np.testing.assert_allclose(sim.equity, 100_000 + np.array(expected), rtol=R)
    assert sim.in_position.tolist() == [0, 0, 1, 1, 1, 0, 0, 0]
    np.testing.assert_allclose(sim.realized_pnl, [0] * 5 + [44.55] * 3, rtol=R, atol=1e-9)
    assert sim.open_pnl_end == 0.0
    to_result(long_case(), sim)  # the T09 contract holds


# -- fixture 2: short, time exit, swap on the MTM notional with a triple day (D-312) -------------
def short_case() -> Case:
    n = 8
    o = np.array([50, 50, 50, 49, 48, 47, 47, 47], float)
    c = np.array([50, 50, 49, 48, 47, 47, 47, 47], float)
    return Case(
        o=o, h=np.maximum(o, c) + 0.5, lo=np.minimum(o, c) - 0.5, c=c, atr=const(n, 1.0),
        entry=flags(n, 1), exit_=flags(n), direction=-1, time_exit=3,
        swap_short=const(n, -0.0001), rollover=flags(n, 2, 3, 4), triple=flags(n, 3),
        notional=1000.0,
    )  # fmt: skip


def test_F_0_3_1_short_time_exit_with_swap_hand_computed() -> None:
    sim = run_engine(short_case())
    # entry at open 2 (50); time exit after 3 bars: scheduled at close 4, fills at open 5 (47)
    assert (sim.entry_idx[0], sim.exit_idx[0], sim.exit_reason[0]) == (2, 5, ExitReason.TIME_EXIT)
    assert sim.qty[0] == 20.0  # 1000 / 50
    assert sim.pnl_gross[0] == approx(60.0)  # -1 x 20 x (47 - 50)
    # swap charged at the closes of bars 2, 3 (triple), 4 on |qty| x close (D-312):
    # 0.0001 x 20 x (49 + 3 x 48 + 47) = 0.48
    assert sim.cost_swap[0] == approx(0.48)
    assert sim.pnl_net[0] == approx(59.52)
    swap_2, swap_3 = 0.0001 * 20 * 49, 0.0001 * 20 * 49 + 0.0001 * 20 * 3 * 48
    expected = [0, 0, 20 - swap_2, 40 - swap_3, 59.52, 59.52, 59.52, 59.52]
    np.testing.assert_allclose(sim.equity, 100_000 + np.array(expected), rtol=R)
    assert sim.mfe[0] == approx(70.0) and sim.mae[0] == approx(10.0)  # low 46.5 / high 50.5
    to_result(short_case(), sim)


# -- fixture 3: non-USD quote, USD commission per lot, conversion (D-307, D-315, D-328) ----------
def fx_case() -> Case:
    n = 6
    o = np.array([1.0, 1.0, 1.0, 1.02, 1.03, 1.03])
    c = np.array([1.0, 1.0, 1.01, 1.03, 1.03, 1.03])
    return Case(
        o=o, h=np.maximum(o, c) + 0.005, lo=np.minimum(o, c) - 0.005, c=c, atr=const(n, 0.01),
        entry=flags(n, 1), exit_=flags(n, 3), half_spread=const(n, 0.00002),
        comm_code=3, comm_p=(100_000.0, 3.0, 0.0),
        fx_open=np.array([1.1, 1.1, 1.2, 1.1, 1.1, 1.1]),
        fx_close=np.array([1.1, 1.1, 1.15, 1.1, 1.25, 1.1]),
        contract_size=100_000.0, step=0.01, min_volume=0.01,
    )  # fmt: skip


def test_F_0_3_1_non_usd_quote_hand_computed() -> None:
    sim = run_engine(fx_case())
    # size at the fill bar's open in USD: 1.0 x 1.2 -> 100000 / 120000 = 0.8333 lot -> 0.83
    assert sim.qty[0] == approx(83_000.0)
    # gross in the quote currency x fx_close of the exit bar: 83000 x 0.03 x 1.25
    assert sim.pnl_gross[0] == approx(83_000 * 0.03 * 1.25)
    assert sim.cost_spread[0] == approx(83_000 * 0.00002 * 1.15 + 83_000 * 0.00002 * 1.25)
    assert sim.cost_commission[0] == approx(2 * 0.83 * 3.0)  # USD: not converted
    net = 83_000 * 0.03 * 1.25 - (83_000 * 0.00002 * (1.15 + 1.25)) - 4.98
    assert sim.pnl_net[0] == approx(net)
    entry_costs = 83_000 * 0.00002 * 1.15 + 2.49
    expected = [
        0,
        0,
        83_000 * 0.01 * 1.15 - entry_costs,
        83_000 * 0.03 * 1.1 - entry_costs,
        net,
        net,
    ]
    np.testing.assert_allclose(sim.equity, 100_000 + np.array(expected), rtol=R)
    to_result(fx_case(), sim)


# -- fixture 4: futures, fixed contracts x point value (D-061, D-329) ----------------------------
def test_F_0_3_1_futures_contracts_hand_computed() -> None:
    n = 6
    o = np.array([4000, 4000, 4000, 4005, 4010, 4010], float)
    c = np.array([4000, 4000, 4004, 4008, 4010, 4010], float)
    case = Case(
        o=o, h=np.maximum(o, c) + 1, lo=np.minimum(o, c) - 1, c=c, atr=const(n, 10.0),
        entry=flags(n, 1), exit_=flags(n, 3), sizing="contracts", contracts=2.0,
        point_value=50.0,
    )  # fmt: skip
    sim = run_engine(case)
    assert sim.qty[0] == 2.0
    assert sim.pnl_gross[0] == approx(2 * (4010 - 4000) * 50.0)  # 1000 USD
    expected = [0, 0, 2 * 4 * 50, 2 * 8 * 50, 1000, 1000]
    np.testing.assert_allclose(sim.equity, 100_000 + np.array(expected, float), rtol=R)
    to_result(case, sim)


# -- pins between the engine and the other layers ------------------------------------------------
def test_F_0_3_1_exit_reason_codes_match_the_contract() -> None:
    for name in (
        "SIGNAL",
        "STOP_LOSS",
        "TAKE_PROFIT",
        "DISASTER_STOP",
        "TIME_EXIT",
        "TRAILING_STOP",
    ):
        assert getattr(k, name) == int(ExitReason[name])


@pytest.mark.parametrize(
    "params",
    [(0, 0.0, 0.0, 0.0), (1, 0.001, 0.0, 0.0), (2, 0.005, 1.0, 7.0), (2, 0.005, 1.0, np.inf),
     (3, 100_000.0, 3.0, 0.0), (4, 12.0, 0.0, 0.0)],
)  # fmt: skip
def test_F_0_3_1_engine_commission_kernel_equals_costs_kernel(params: tuple) -> None:
    for qty in (0.5, 10.0, 1234.5, 92_592.59):
        for price in (1.08, 50.0, 4000.0):
            assert engine_commission(*params, qty, price) == costs_commission(*params, qty, price)


@pytest.mark.parametrize(
    ("notional", "price", "cs", "step", "minv"),
    [(1e5, 1.0837, 1e5, 0.01, 0.01), (1e5, 211.07, 1.0, 0.1, 0.1), (1e5, 100.0, 1.0, 0.1, 0.1),
     (1e5, 2e6, 1.0, 0.1, 0.1), (1e5, 150_000.0, 1.0, 1.0, 1.0), (1e5, 0.3, 1.0, 1.0, 1.0)],
)  # fmt: skip
def test_F_0_3_1_engine_lots_equal_costs_size_lots(
    notional: float, price: float, cs: float, step: float, minv: float
) -> None:
    lots, skipped = k.research_lots(notional, price, cs, step, minv, 1e-9)
    ref = size_lots(notional, price, cs, step, minv)
    assert (lots, skipped) == (ref.lots, ref.skipped_min_volume)
