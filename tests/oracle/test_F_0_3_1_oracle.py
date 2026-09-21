"""F-0.3.1 / D-330: the engine equals the naive pure-Python reference engine.

``naive_engine.py`` is written from the task's rules and shares no code with the engine. The
comparison covers costs, swap with triple days, conversion, rounding and skips, every exit
type, both intrabar modes and all three sizing modes. Never skipped (D-330).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pytest
from fixtures.engine import Case, random_case, run_engine, run_oracle, to_result
from fixtures.hypothesis_budget import examples
from hypothesis import given, settings
from hypothesis import strategies as st

TRADE_FIELDS = (
    "entry_idx", "exit_idx", "qty", "entry_price", "exit_price", "pnl_gross", "cost_spread",
    "cost_slippage", "cost_commission", "cost_swap", "pnl_net", "exit_reason", "mae", "mfe",
    "atr_at_entry",
)  # fmt: skip
NAIVE = {"exit_reason": "exit_reason"}


def assert_same(case: Case) -> None:
    sim = run_engine(case)
    ref = run_oracle(case)
    assert len(ref.trades) == sim.entry_idx.size
    for f in TRADE_FIELDS:
        got = getattr(sim, f)
        want = np.array([getattr(t, f) for t in ref.trades], dtype=got.dtype)
        np.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-9, err_msg=f)
    np.testing.assert_allclose(sim.equity, ref.equity, rtol=1e-12, atol=1e-9)
    np.testing.assert_array_equal(sim.in_position, ref.in_position)
    np.testing.assert_allclose(sim.realized_pnl, ref.realized, rtol=1e-12, atol=1e-9)
    assert sim.open_pnl_end == pytest.approx(ref.open_pnl_end, rel=1e-12, abs=1e-9)
    assert sim.n_skipped_min_volume == ref.n_skipped
    to_result(case, sim)  # and every run satisfies the T09 contract


def maybe(draw: Any, strat: Any) -> Any:
    return draw(st.one_of(st.none(), strat))


@st.composite
def cases(draw: Any) -> Case:
    seed = draw(st.integers(0, 2**31 - 1))
    n = draw(st.integers(2, 80))
    rng = np.random.default_rng(seed)
    sizing = draw(st.sampled_from(["research", "contracts", "parity"]))
    mode = draw(st.sampled_from(["pessimistic", "tradingview"]))
    mult = st.floats(0.3, 4.0)
    kw: dict[str, Any] = {
        "direction": draw(st.sampled_from([1, -1])),
        "time_exit": draw(st.integers(0, 6)),
        "sl": maybe(draw, mult), "tp": maybe(draw, mult), "trail": maybe(draw, mult),
        "disaster": draw(st.floats(0.5, 4.0)),
        "sizing": sizing, "mode": mode,
        "slip_frac": draw(st.floats(0.0, 0.1)),
        "comm_code": draw(st.sampled_from([0, 1, 2, 3, 4])),
        "comm_in_quote": draw(st.booleans()),
        "notional": draw(st.sampled_from([1000.0, 100_000.0, 5.0])),
        "contracts": draw(st.sampled_from([1.0, 2.0])),
        "point_value": draw(st.sampled_from([1.0, 50.0])) if sizing == "contracts" else 1.0,
        "step": draw(st.sampled_from([1.0, 0.1, 0.01])),
        "contract_size": draw(st.sampled_from([1.0, 1000.0])),
        "parity_qty_step": draw(st.sampled_from([1.0, 0.01, 0.5])),  # D-347
        # D-366 / D-367: the parity-only options, drawn in every mode so the oracle checks
        # them against the kernel (they were implemented in both but never run together)
        "parity_tick": draw(st.sampled_from([None, 0.01, 0.001, 0.25])),
        "entry_requires_flat": draw(st.booleans()),
    }  # fmt: skip
    kw["min_volume"] = kw["step"] * draw(st.sampled_from([1, 2]))
    kw["comm_p"] = {
        0: (0.0, 0.0, 0.0), 1: (0.001, 0.0, 0.0), 2: (0.005, 1.0, 7.0),
        3: (kw["contract_size"], 3.0, 0.0), 4: (12.0, 0.0, 0.0),
    }[kw["comm_code"]]  # fmt: skip
    case = random_case(rng, n, **kw)
    case.half_spread = rng.uniform(0.0, 0.05, n)
    case.slip_fixed = rng.uniform(0.0, 0.02, n)
    case.swap_long = rng.normal(0.0, 0.0005, n)
    case.swap_short = rng.normal(0.0, 0.0005, n)
    case.rollover = rng.random(n) < 0.4
    case.triple = case.rollover & (rng.random(n) < 0.3)
    if draw(st.booleans()):
        case.fx_open = rng.uniform(0.5, 1.5, n)
        case.fx_close = rng.uniform(0.5, 1.5, n)
    return case


@settings(max_examples=examples(400), deadline=None)
@given(cases())
def test_F_0_3_1_engine_equals_naive_oracle(case: Case) -> None:
    assert_same(case)


def test_F_0_3_1_oracle_on_the_hand_fixtures() -> None:
    import importlib

    hand = importlib.import_module("unit.test_F_0_3_1_engine")
    for build in (hand.long_case, hand.short_case, hand.fx_case):
        assert_same(build())


def test_F_0_3_1_oracle_sweep_covers_every_path() -> None:
    """600 seeded random cases: engine == oracle, and every exit reason, both intrabar modes,
    all sizing modes, same-bar exits, re-entries at the exit open and skips actually occur."""
    reasons: set[int] = set()
    seen = {"same_bar": 0, "reentry": 0, "skipped": 0, "swap": 0}
    # D-366 / D-367: each option must actually change some run -- an oracle that agrees with
    # the kernel only because the option never mattered would prove nothing
    bites = {"tick_rounding": 0, "flat_gate": 0}
    for seed in range(600):
        rng = np.random.default_rng(seed)
        n = int(rng.integers(20, 90))
        sizing = ["research", "contracts", "parity"][seed % 3]
        case = random_case(
            rng, n, direction=1 if seed % 2 else -1, time_exit=int(rng.integers(0, 5)),
            sl=float(rng.uniform(0.3, 2.0)) if seed % 5 else None,
            tp=float(rng.uniform(0.3, 3.0)) if seed % 4 else None,
            trail=float(rng.uniform(0.3, 2.0)) if seed % 7 == 0 else None,
            disaster=float(rng.uniform(0.5, 3.0)), sizing=sizing,
            mode="tradingview" if seed % 6 < 3 else "pessimistic",
            notional=[100_000.0, 5.0][int(rng.integers(0, 2))], step=0.1, min_volume=0.1,
            parity_qty_step=float(rng.choice([1.0, 0.01])),  # D-347
            parity_tick=[None, 0.01, 0.25][seed % 3 if seed % 4 else 0],  # D-366
            entry_requires_flat=bool(seed % 2),  # D-367
        )  # fmt: skip
        case.swap_long = np.full(n, -0.001)
        case.swap_short = np.full(n, -0.001)
        case.rollover = rng.random(n) < 0.5
        assert_same(case)
        sim = run_engine(case)
        reasons |= set(sim.exit_reason.tolist())
        seen["same_bar"] += int(np.sum(sim.exit_idx == sim.entry_idx))
        seen["reentry"] += int(np.sum(sim.entry_idx[1:] == sim.exit_idx[:-1]))
        seen["skipped"] += sim.n_skipped_min_volume
        seen["swap"] += int(np.sum(sim.cost_swap != 0))
        if case.parity_tick is not None:
            plain = run_engine(dataclasses.replace(case, parity_tick=None))
            bites["tick_rounding"] += int(not _same_trades(sim, plain))
        if case.entry_requires_flat:
            plain = run_engine(dataclasses.replace(case, entry_requires_flat=False))
            bites["flat_gate"] += int(not _same_trades(sim, plain))
    assert reasons == {0, 1, 2, 3, 4, 5}, reasons
    assert all(v > 0 for v in seen.values()), seen
    assert all(v > 0 for v in bites.values()), bites


def _same_trades(a: Any, b: Any) -> bool:
    if a.entry_idx.size != b.entry_idx.size:
        return False
    return bool(
        np.array_equal(a.entry_idx, b.entry_idx) and np.array_equal(a.exit_price, b.exit_price)
    )
