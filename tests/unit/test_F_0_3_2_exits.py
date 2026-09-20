"""F-0.3.2 (basic exits) and F-0.3.4 (intrabar ambiguity): right bar, right price, right reason.

Long runs unless stated; zero costs; one contract (qty 1) so P&L = price difference; ATR 1,
so the disaster stop of an entry at 100 is at 97 (D-130). Entry signal at close 1 -> entry at
the open of bar 2 (D-001).
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.engine import Case, flags, run_engine, to_result

from strategy_factory.metrics.containers import ExitReason as R

N = 10


def flat_case(**kw: object) -> Case:
    o = np.full(N, 100.0)
    base = {
        "o": o, "h": o + 0.5, "lo": o - 0.5, "c": o.copy(), "atr": np.ones(N),
        "entry": flags(N, 1), "exit_": flags(N), "sizing": "contracts",
    }  # fmt: skip
    base.update(kw)
    return Case(**base)  # type: ignore[arg-type]


def bar(case: Case, j: int, *, o: float | None = None, h: float | None = None,
        lo: float | None = None, c: float | None = None) -> Case:  # fmt: skip
    for name, v in (("o", o), ("h", h), ("lo", lo), ("c", c)):
        if v is not None:
            getattr(case, name)[j] = v
    return case


def one_trade(case: Case) -> tuple[int, int, int, float]:
    sim = run_engine(case)
    to_result(case, sim)  # every scenario satisfies the T09 contract
    assert sim.entry_idx.size == 1, sim.entry_idx
    return (
        int(sim.entry_idx[0]),
        int(sim.exit_idx[0]),
        int(sim.exit_reason[0]),
        float(sim.pnl_gross[0]),
    )


# -- F-0.3.2: each exit type --------------------------------------------------------------------
def test_F_0_3_2_signal_exit_at_next_open() -> None:
    case = bar(flat_case(exit_=flags(N, 3)), 4, o=101.0, h=101.5)
    assert one_trade(case) == (2, 4, R.SIGNAL, 1.0)  # signal at close 3 -> open 4 (101)


def test_F_0_3_2_time_exit_after_n_bars() -> None:
    case = bar(flat_case(time_exit=2), 4, o=100.7, h=101.0)
    assert one_trade(case) == (2, 4, R.TIME_EXIT, pytest.approx(0.7))  # bars_held = 2


def test_F_0_3_2_disaster_stop_intrabar_at_the_level() -> None:
    case = bar(flat_case(), 3, lo=96.9)
    assert one_trade(case) == (2, 3, R.DISASTER_STOP, -3.0)  # 100 - 3 x ATR 1 = 97


def test_F_0_3_2_disaster_stop_gapped_through_fills_at_the_open() -> None:
    case = bar(flat_case(), 3, o=95.0, h=95.5, lo=94.5, c=95.0)
    assert one_trade(case) == (2, 3, R.DISASTER_STOP, -5.0)  # the open 95 is worse than 97


def test_F_0_3_2_stop_loss_and_disaster_touched_the_nearer_wins() -> None:
    case = bar(flat_case(sl=1.0), 3, lo=96.0)
    assert one_trade(case) == (2, 3, R.STOP_LOSS, -1.0)  # 99 is reached before 97


def test_F_0_3_2_take_profit_intrabar_and_gap() -> None:
    assert one_trade(bar(flat_case(tp=2.0), 3, h=102.5)) == (2, 3, R.TAKE_PROFIT, 2.0)
    gap = bar(flat_case(tp=2.0), 3, o=103.0, h=103.5, lo=102.8, c=103.0)
    assert one_trade(gap) == (2, 3, R.TAKE_PROFIT, 3.0)  # a gap through the target: the open


def test_F_0_3_2_trailing_stop_follows_the_high() -> None:
    case = flat_case(trail=1.0)
    bar(case, 3, h=103.0, lo=100.0, c=102.5)  # level 99 -> 99.5 (close 2) -> 102 (close 3)
    bar(case, 4, o=102.5, h=102.6, lo=101.9, c=102.0)
    assert one_trade(case) == (2, 4, R.TRAILING_STOP, pytest.approx(2.0))


def test_F_0_3_2_first_hit_signal_beats_time_on_the_same_close() -> None:
    case = flat_case(time_exit=2, exit_=flags(N, 3))
    assert one_trade(case)[:3] == (2, 4, R.SIGNAL)


def test_F_0_3_2_first_hit_intrabar_disaster_beats_a_later_signal() -> None:
    case = bar(flat_case(exit_=flags(N, 3)), 3, lo=96.0)
    assert one_trade(case)[:3] == (2, 3, R.DISASTER_STOP)


def test_F_0_3_2_exit_and_reentry_at_the_same_open_open_at_the_end() -> None:
    case = flat_case(entry=flags(N, 1, 3), exit_=flags(N, 3))
    bar(case, 9, c=104.0)
    sim = run_engine(case)
    assert sim.entry_idx.tolist() == [2] and sim.exit_idx.tolist() == [4]
    assert sim.in_position.tolist() == [0, 0, 1, 1, 1, 1, 1, 1, 1, 1]  # re-entered at open 4
    assert sim.open_pnl_end == pytest.approx(4.0)
    res = to_result(case, sim)  # D-336 + the T09 validator fix: the open run starts at bar 4
    assert res.open_position_marked


def test_F_0_3_2_last_bar_signal_not_filled_and_warm_up_skipped() -> None:
    last = flat_case(entry=flags(N, N - 1))
    assert run_engine(last).entry_idx.size == 0 and not run_engine(last).in_position.any()
    warm = flat_case()
    warm.atr[1] = np.nan  # no ATR at the signal bar: no entry (warm-up)
    assert run_engine(warm).entry_idx.size == 0


def test_F_0_3_2_short_mirror_of_each_exit() -> None:
    case = flat_case(direction=-1, sl=1.0, tp=2.0)
    assert one_trade(bar(case, 3, h=101.2)) == (2, 3, R.STOP_LOSS, -1.0)
    case = flat_case(direction=-1, tp=2.0)
    assert one_trade(bar(case, 3, lo=97.5)) == (2, 3, R.TAKE_PROFIT, 2.0)
    case = flat_case(direction=-1)
    assert one_trade(bar(case, 3, o=104.0, h=104.5, lo=103.5, c=104.0)) == (
        2, 3, R.DISASTER_STOP, -4.0,
    )  # fmt: skip


# -- F-0.3.4: stop and target in the same bar ---------------------------------------------------
@pytest.mark.parametrize(
    ("h", "lo", "tradingview", "pessimistic"),
    [
        (101.2, 98.5, R.TAKE_PROFIT, R.STOP_LOSS),  # high nearer the open: O->H->L->C
        (101.8, 98.9, R.STOP_LOSS, R.STOP_LOSS),  # low nearer: O->L->H->C
        (101.5, 98.5, R.STOP_LOSS, R.STOP_LOSS),  # tie: pessimistic order (D-335)
    ],
)
def test_F_0_3_4_stop_and_target_touched(
    h: float, lo: float, tradingview: int, pessimistic: int
) -> None:
    for mode, expected in (("tradingview", tradingview), ("pessimistic", pessimistic)):
        case = bar(flat_case(sl=1.0, tp=1.0, mode=mode), 3, h=h, lo=lo)
        assert one_trade(case)[2] == expected, mode


def test_F_0_3_4_disaster_versus_target() -> None:
    for mode, expected in (("tradingview", R.TAKE_PROFIT), ("pessimistic", R.DISASTER_STOP)):
        case = bar(flat_case(tp=2.0, mode=mode), 3, h=102.2, lo=96.5)
        assert one_trade(case)[2] == expected


def test_F_0_3_4_short_stop_and_target_touched() -> None:
    # short: the target is below; low nearer the open -> target first in tradingview mode
    for mode, expected in (("tradingview", R.TAKE_PROFIT), ("pessimistic", R.STOP_LOSS)):
        case = bar(flat_case(direction=-1, sl=1.0, tp=1.0, mode=mode), 3, h=101.5, lo=98.8)
        assert one_trade(case)[2] == expected


def test_F_0_3_4_same_bar_exit_on_the_entry_bar() -> None:
    case = bar(flat_case(), 2, lo=96.5)  # entered at open 2, disaster hit inside bar 2
    sim = run_engine(case)
    assert (sim.entry_idx[0], sim.exit_idx[0], sim.exit_reason[0]) == (2, 2, R.DISASTER_STOP)
    assert not sim.in_position[2]  # a same-bar trade occupies no bar (T09)
    res = to_result(case, sim)
    assert res.trades.bars_held.tolist() == [0]
