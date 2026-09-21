"""F-0.3.8: the comparison classifies every difference with a reason (T11 §4, Tests).

The task asks for hand-built trade lists that exercise a perfect match, a one-bar entry shift,
a quantity difference, a missing trade and an extra trade, each landing in the expected bucket
with the expected reason. The real references only ever produce ``match`` (and ``quantity`` on
MR), so without these the classifier's other branches would be untested.

Each case starts from a **real** engine run -- the TF long reference, whose trades match
TradingView exactly -- and changes **one thing** on the TradingView side, so the expected reason
follows from that single change.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from strategy_factory.core.parity_config import load_parity_config
from strategy_factory.engine import kernel as k
from strategy_factory.selftest.parity_compare import Comparison, compare
from strategy_factory.selftest.parity_refs import TradeList, TradeRow
from strategy_factory.selftest.parity_run import ParityRun, run_reference

REPO = Path(__file__).resolve().parents[2]
TF_LONG = REPO / "configs/parity/xauusd_tf_1h_long.yaml"
N = 10  # the first ten TF long trades: a small, fully matching window
HOUR = dt.timedelta(hours=1)


@pytest.fixture(scope="module")
def tf() -> ParityRun:
    return run_reference(load_parity_config(TF_LONG))


def window(run: ParityRun, rows: list[TradeRow]) -> TradeList:
    return TradeList(name=run.tv.name, sha256=run.tv.sha256, rows=tuple(rows))


def rows_of(run: ParityRun, first: int = 1, last: int = N) -> list[TradeRow]:
    return [r for r in run.tv.rows if first <= r.trade <= last]


def row(rows: list[TradeRow], trade: int, kind: str) -> TradeRow:
    return next(r for r in rows if (r.trade, r.kind) == (trade, kind))


def edit(rows: list[TradeRow], trade: int, kind: str, **changes: object) -> list[TradeRow]:
    return [
        dataclasses.replace(r, **changes) if (r.trade, r.kind) == (trade, kind) else r  # type: ignore[arg-type]
        for r in rows
    ]


def compared(run: ParityRun, rows: list[TradeRow]) -> Comparison:
    return compare(
        run.chart,
        window(run, rows),
        run.result,
        tick_size=run.config.pine.tick_size,
        daily=False,
        sub_tick_ticks=run.config.sub_tick_tolerance_ticks,
        qty_step=float(run.config.engine.parity_qty_step or 0.0),
    )


def engine_trade_of(run: ParityRun, tv_trade: int) -> int:
    """The engine index matched to TradingView trade number ``tv_trade``."""
    tv_index = next(i for i, (e, _) in enumerate(run.tv.trades()) if e.trade == tv_trade)
    pair = next(p for p in run.comparison.pairs if p.tv_index == tv_index)
    assert pair.engine_index is not None
    return pair.engine_index


# -- the task's five cases -----------------------------------------------------------------
def test_F_0_3_8_compare_a_perfect_match(tf: ParityRun) -> None:
    c = compared(tf, rows_of(tf))
    assert c.tv_trades == N and c.engine_trades == N
    assert c.by_reason() == {"match": N}
    assert c.matched_share == 1.0 and c.differences() == []


def test_F_0_3_8_compare_a_quantity_difference(tf: ParityRun) -> None:
    """Same bars and prices, a different size: classified, never a match (found on MR)."""
    rows = rows_of(tf)
    qty = row(rows, 3, "entry").quantity
    c = compared(tf, edit(rows, 3, "entry", quantity=qty + 1.0))
    assert c.by_reason() == {"match": N - 1, "quantity": 1}
    (diff,) = c.differences()
    assert diff.reason == "quantity" and "quantity" in diff.detail
    # half a step is the tolerance: float noise is still a match
    assert compared(tf, edit(rows, 3, "entry", quantity=qty + 1e-9)).by_reason() == {"match": N}


def test_F_0_3_8_compare_a_missing_trade(tf: ParityRun) -> None:
    """A TradingView trade on a bar where the engine did not enter."""
    rows = rows_of(tf)
    exit4, entry5 = row(rows, 4, "exit"), row(rows, 5, "entry")
    assert (entry5.when - exit4.when) // HOUR >= 3, "trades 4 and 5 are too close"
    fake = [
        dataclasses.replace(row(rows, 4, "entry"), trade=99, when=exit4.when + HOUR),
        dataclasses.replace(exit4, trade=99, when=exit4.when + 2 * HOUR),
    ]
    c = compared(tf, rows + fake)
    assert c.by_reason() == {"match": N, "missing_in_engine": 1}
    (diff,) = c.differences()
    assert diff.engine_index is None and diff.tv_index is not None


def test_F_0_3_8_compare_an_extra_trade(tf: ParityRun) -> None:
    """An engine trade inside the covered range that TradingView does not have."""
    c = compared(tf, [r for r in rows_of(tf) if r.trade != 5])
    assert c.tv_trades == N - 1 and c.engine_trades == N
    assert c.by_reason() == {"match": N - 1, "extra_in_engine": 1}
    (diff,) = c.differences()
    assert diff.tv_index is None and diff.engine_index is not None
    # D-373: the share is over the union, so the extra counts -- 9 of 10 -- and an extra
    # trade alone fails the 98 % gate
    assert c.extra == 1
    assert c.matched_share == pytest.approx((N - 1) / N)
    assert c.matched_share < tf.config.min_matched_share


def test_F_0_3_8_compare_a_one_bar_entry_shift(tf: ParityRun) -> None:
    """TradingView entering one bar later is a missing trade *and* an extra one, side by side."""
    rows = rows_of(tf)
    c = compared(tf, edit(rows, 6, "entry", when=row(rows, 6, "entry").when + HOUR))
    assert c.by_reason() == {"match": N - 1, "missing_in_engine": 1, "extra_in_engine": 1}
    missing = next(p for p in c.pairs if p.reason == "missing_in_engine")
    extra = next(p for p in c.pairs if p.reason == "extra_in_engine")
    assert missing.entry_bar == extra.entry_bar + 1  # the shift is visible in the report


# -- the exit side ---------------------------------------------------------------------------
def test_F_0_3_8_compare_the_other_level_on_the_same_bar_is_intrabar_path(tf: ParityRun) -> None:
    """D-335 can only change WHICH level fills on a bar that touched both -- same bar, the other
    price. That, and only that, is `intrabar_path`."""
    rows = rows_of(tf)
    t = tf.result.trades
    number = next(
        n for n in range(1, N + 1) if int(t.exit_reason[engine_trade_of(tf, n)]) in (1, 2)
    )
    x = row(rows, number, "exit")
    c = compared(tf, edit(rows, number, "exit", price=x.price + 40.0))  # far from any rounding
    assert c.by_reason() == {"match": N - 1, "intrabar_path": 1}
    (diff,) = c.differences()
    assert "same exit bar" in diff.detail


def test_F_0_3_8_compare_an_exit_on_another_bar_is_not_a_path_choice(tf: ParityRun) -> None:
    """A different exit bar cannot come from an intrabar path choice, so it is `unexplained`.
    (It was once labelled `intrabar_path`, which would have hidden a time- or signal-exit bug.)"""
    rows = rows_of(tf)
    x = row(rows, 7, "exit")
    c = compared(tf, edit(rows, 7, "exit", when=x.when + HOUR, price=x.price + 5.0))
    assert c.by_reason() == {"match": N - 1, "unexplained": 1}
    (diff,) = c.differences()
    assert "exit bar" in diff.detail


def test_F_0_3_8_compare_a_different_price_on_a_time_exit_is_unexplained() -> None:
    """Same bar, a different price, but the engine left at the open (a time exit): no level was
    chosen, so it is not D-335."""
    run = run_reference(load_parity_config(TF_LONG))
    t = run.result.trades
    time_exit = next(i for i in range(len(t.entry_idx)) if int(t.exit_reason[i]) == k.TIME_EXIT)
    number = next(p.tv_index for p in run.comparison.pairs if p.engine_index == time_exit)
    assert number is not None
    tv_no = run.tv.trades()[number][0].trade
    rows = rows_of(run, tv_no - 1, tv_no + 1)
    x = row(rows, tv_no, "exit")
    c = compared(run, edit(rows, tv_no, "exit", price=x.price + 40.0))
    assert c.by_reason() == {"match": 2, "unexplained": 1}
    (diff,) = c.differences()
    assert "non-level exit" in diff.detail


def test_F_0_3_8_compare_a_sub_tick_exit_price(tf: ParityRun) -> None:
    """An exit price within the configured tolerance is a rounding difference, not a decision."""
    rows = rows_of(tf)
    x = row(rows, 8, "exit")
    tick = tf.config.pine.tick_size
    near = compared(tf, edit(rows, 8, "exit", price=x.price + tick))
    assert near.by_reason() == {"match": N - 1, "sub_tick_level": 1}
    # ... on another bar too: a level one tick lower can be touched a bar later
    later = compared(tf, edit(rows, 8, "exit", price=x.price + tick, when=x.when + HOUR))
    assert later.by_reason() == {"match": N - 1, "sub_tick_level": 1}


# -- the entry side ------------------------------------------------------------------------
def test_F_0_3_8_compare_an_entry_in_the_atr_warm_up(tf: ParityRun) -> None:
    """HANDOFF §8.1: TradingView may enter before the engine's ATR is usable. The run tells the
    chart where that is, so such an entry is `atr_warm_up`, not a missing trade."""
    warm = tf.chart.atr_warm_up_bars
    assert warm > 0, "run_reference must set the warm-up (it once never did)"
    rows = rows_of(tf)
    first = row(rows, 1, "entry")
    start = dt.datetime.fromtimestamp(int(tf.chart.ts[warm - 2]), dt.UTC)
    fake = [
        dataclasses.replace(first, trade=0, when=start),
        dataclasses.replace(row(rows, 1, "exit"), trade=0, when=start + HOUR),
    ]
    c = compared(tf, fake + rows)
    assert c.by_reason() == {"match": N, "atr_warm_up": 1}


def test_F_0_3_8_compare_a_same_open_reentry_is_named() -> None:
    """D-336 / D-367, on real data: with the flat gate off the engine re-enters at the open
    where its previous trade exits, twice on TF long. Those are `same_open_reentry`, not bare
    extras -- the report says why."""
    cfg = load_parity_config(TF_LONG)
    off = cfg.model_copy(
        update={"engine": cfg.engine.model_copy(update={"entry_requires_flat_at_signal": False})}
    )
    c = run_reference(off).comparison
    assert c.by_reason() == {"match": 519, "same_open_reentry": 2}
    for p in c.differences():
        assert "D-336" in p.detail


def test_F_0_3_8_compare_the_opposite_direction(tf: ParityRun) -> None:
    rows = rows_of(tf)
    flipped = [dataclasses.replace(r, direction=-1) if r.trade == 2 else r for r in rows]
    c = compared(tf, flipped)
    assert c.by_reason() == {"match": N - 1, "unexplained": 1}
    (diff,) = c.differences()
    assert diff.detail == "opposite direction"
