"""F-0.3.1 engine invariants (design §6), Hypothesis, with volume-step rounding on.

1. P&L conservation: sum(pnl_net) + open P&L = final equity - initial capital;
2. no same-bar execution: fills happen one bar after the signal that caused them;
3. costs monotonic: raising any cost component never raises the net result;
4. truncation invariance (see also tests/leakage);
5. long/short mirror: short on the reflected series = long on the original (zero costs);
6. batch = single: every grid column equals the single run bit for bit.
Every generated run also passes the T09 RunResult validation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from fixtures.engine import SIZE, Case, random_case, run_engine, to_result
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import CostInputs, MarketArrays, SizingInputs, simulate_grid

SETTINGS = settings(max_examples=150, deadline=None)


@st.composite
def cases(draw: Any, costs: bool = True) -> Case:
    rng = np.random.default_rng(draw(st.integers(0, 2**31 - 1)))
    n = draw(st.integers(2, 70))
    mult = st.one_of(st.none(), st.floats(0.3, 3.0))
    case = random_case(
        rng, n, direction=draw(st.sampled_from([1, -1])), time_exit=draw(st.integers(0, 5)),
        sl=draw(mult), tp=draw(mult), trail=draw(mult), disaster=draw(st.floats(0.5, 3.0)),
        sizing=draw(st.sampled_from(["research", "contracts", "parity"])),
        mode=draw(st.sampled_from(["pessimistic", "tradingview"])),
        step=draw(st.sampled_from([1.0, 0.1])), min_volume=draw(st.sampled_from([1.0, 0.1])),
        notional=draw(st.sampled_from([100_000.0, 1000.0, 5.0])),
    )  # fmt: skip
    case.min_volume = max(case.min_volume, case.step)
    if costs:
        case.half_spread = rng.uniform(0, 0.05, n)
        case.slip_fixed = rng.uniform(0, 0.02, n)
        case.slip_frac = float(rng.uniform(0, 0.1))
        case.comm_code, case.comm_p = 1, (0.001, 0.0, 0.0)
        case.swap_long = rng.normal(0, 0.0005, n)
        case.swap_short = rng.normal(0, 0.0005, n)
        case.rollover = rng.random(n) < 0.4
        case.triple = case.rollover & (rng.random(n) < 0.3)
        if draw(st.booleans()):  # a non-USD quote: conversion at the open and the close
            case.fx_open = rng.uniform(0.5, 1.5, n)
            case.fx_close = rng.uniform(0.5, 1.5, n)
            case.comm_in_quote = draw(st.booleans())
    return case


@SETTINGS
@given(cases())
def test_F_0_3_1_pnl_conservation(case: Case) -> None:
    sim = run_engine(case)
    total = float(np.sum(sim.pnl_net)) + sim.open_pnl_end
    assert sim.equity[-1] - case.capital == pytest.approx(total, rel=1e-9, abs=1e-6)
    to_result(case, sim)


@SETTINGS
@given(cases())
def test_F_0_3_1_no_same_bar_execution(case: Case) -> None:
    sim = run_engine(case)
    for e, x, r in zip(sim.entry_idx, sim.exit_idx, sim.exit_reason, strict=True):
        assert e >= 1 and case.entry[e - 1], "an entry fills at the open after its signal bar"
        if r in (k.SIGNAL, k.TIME_EXIT):
            assert x >= e + 1
        if r == k.SIGNAL:
            assert case.exit_[x - 1], "a signal exit fills at the open after its signal bar"


COMPONENTS = ("half_spread", "slip_fixed", "slip_frac", "commission", "swap_charge")


@SETTINGS
@given(cases(), st.sampled_from(COMPONENTS), st.floats(1e-6, 0.5))
def test_F_0_3_1_costs_monotonic(case: Case, which: str, bump: float) -> None:
    base = run_engine(case)
    if which == "half_spread":
        more = replace(case, half_spread=case.half_spread + bump)
    elif which == "slip_fixed":
        more = replace(case, slip_fixed=case.slip_fixed + bump)
    elif which == "slip_frac":
        more = replace(case, slip_frac=case.slip_frac + bump)
    elif which == "commission":
        more = replace(case, comm_p=(case.comm_p[0] + bump / 100, 0.0, 0.0))
    else:
        more = replace(case, swap_long=case.swap_long - bump / 100,
                       swap_short=case.swap_short - bump / 100)  # fmt: skip
    raised = run_engine(more)
    assert raised.equity[-1] <= base.equity[-1] + 1e-9 * max(1.0, abs(base.equity[-1]))


@SETTINGS
@given(cases(), st.data())
def test_F_0_3_1_truncation_invariance(case: Case, data: Any) -> None:
    full = run_engine(case)
    t = data.draw(st.integers(2, case.n))
    part = run_engine(truncate(case, t))
    np.testing.assert_array_equal(part.equity, full.equity[:t])
    np.testing.assert_array_equal(part.in_position, full.in_position[:t])
    done = full.exit_idx <= t - 1
    np.testing.assert_array_equal(part.entry_idx, full.entry_idx[done])
    np.testing.assert_array_equal(part.pnl_net, full.pnl_net[done])


def truncate(case: Case, t: int) -> Case:
    cut = {}
    names = ("o", "h", "lo", "c", "atr", "entry", "exit_", "half_spread", "slip_fixed",
             "swap_long", "swap_short", "rollover", "triple", "fx_open", "fx_close")  # fmt: skip
    for name in names:
        v = getattr(case, name)
        cut[name] = None if v is None else v[:t]
    return replace(case, **cut)


@SETTINGS
@given(cases(costs=False))
def test_F_0_3_1_long_short_mirror(case: Case) -> None:
    long_ = replace(case, direction=1, sizing="contracts")
    k_ = 2.0 * float(np.max(case.h)) + 10.0  # reflection p -> K - p keeps prices positive
    short = replace(
        long_, direction=-1, o=k_ - case.o, h=k_ - case.lo, lo=k_ - case.h, c=k_ - case.c
    )
    a, b = run_engine(long_), run_engine(short)
    np.testing.assert_array_equal(a.entry_idx, b.entry_idx)
    np.testing.assert_array_equal(a.exit_idx, b.exit_idx)
    np.testing.assert_array_equal(a.exit_reason, b.exit_reason)
    np.testing.assert_allclose(a.pnl_net, b.pnl_net, rtol=1e-9, atol=1e-7)
    np.testing.assert_allclose(a.equity, b.equity, rtol=1e-12, atol=1e-7)


@SETTINGS
@given(st.lists(cases(), min_size=1, max_size=1), st.integers(1, 6), st.data())
def test_F_0_3_1_batch_equals_single(one: list[Case], n_cfg: int, data: Any) -> None:
    case = one[0]
    rng = np.random.default_rng(data.draw(st.integers(0, 10_000)))
    n = case.n
    entries = rng.random((n, n_cfg)) < 0.2
    exits = rng.random((n, n_cfg)) < 0.15
    te = rng.integers(0, 5, n_cfg)
    pick = lambda: np.where(rng.random(n_cfg) < 0.4, np.nan, rng.uniform(0.3, 3, n_cfg))  # noqa: E731
    sl, tp, tr = pick(), pick(), pick()
    grid = simulate_grid(
        MarketArrays(case.o, case.h, case.lo, case.c, case.atr), entries, exits, case.direction,
        te, sl, tp, tr, case.disaster,
        CostInputs(case.half_spread, case.slip_fixed, case.slip_frac, case.swap_long,
                   case.swap_short, case.rollover, case.triple,
                   (case.comm_code, *case.comm_p), case.comm_in_quote),  # type: ignore[arg-type]
        SizingInputs(SIZE[case.sizing], case.notional, case.capital, case.contract_size,
                     case.step, case.min_volume, case.step_tol, case.contracts,
                     case.point_value),
        k.MODE_PESSIMISTIC if case.mode == "pessimistic" else k.MODE_TRADINGVIEW,
        case.fx_open, case.fx_close,
    )  # fmt: skip
    for j in range(n_cfg):
        nan_or = lambda x: None if np.isnan(x) else float(x)  # noqa: E731
        single = run_engine(replace(
            case, entry=entries[:, j], exit_=exits[:, j], time_exit=int(te[j]),
            sl=nan_or(sl[j]), tp=nan_or(tp[j]), trail=nan_or(tr[j]),
        ))  # fmt: skip
        assert np.array_equal(grid.equity[j], single.equity)  # bit for bit
        assert np.array_equal(grid.in_position[j], single.in_position)
        assert grid.n_closed_trades[j] == single.entry_idx.size
        assert grid.n_skipped_min_volume[j] == single.n_skipped_min_volume
