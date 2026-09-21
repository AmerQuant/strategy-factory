"""F-0.3.8: the comparison classifies every difference with a reason (T11 §4, Tests).

The task asks for hand-built trade lists that exercise a perfect match, a one-bar entry shift,
a quantity difference, a missing trade and an extra trade, each landing in the expected bucket
with the expected reason. The real references only ever produce ``match`` (and ``quantity`` on
MR), so without these the classifier's other branches would be untested.

Each case starts from a **real** engine run -- the TF long reference, whose first ten trades
match TradingView exactly -- and changes **one thing** on the TradingView side, so the
expected reason follows from that single change.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from strategy_factory.core.parity_config import load_parity_config
from strategy_factory.selftest.parity_compare import Comparison, compare
from strategy_factory.selftest.parity_refs import TradeList, TradeRow
from strategy_factory.selftest.parity_run import ParityRun, run_reference

REPO = Path(__file__).resolve().parents[2]
N = 10  # the first ten TF long trades: a small, fully matching window


@pytest.fixture(scope="module")
def tf() -> ParityRun:
    return run_reference(load_parity_config(REPO / "configs/parity/xauusd_tf_1h_long.yaml"))


def window(run: ParityRun, rows: list[TradeRow] | None = None) -> TradeList:
    """The first ``N`` TradingView trades (or ``rows``), as a trade list of their own."""
    if rows is None:
        rows = [r for r in run.tv.rows if r.trade <= N]
    return TradeList(name=run.tv.name, sha256=run.tv.sha256, rows=tuple(rows))


def compared(run: ParityRun, tv: TradeList) -> Comparison:
    return compare(
        run.chart,
        tv,
        run.result,
        tick_size=run.config.pine.tick_size,
        daily=False,
        qty_step=run.config.engine.parity_qty_step,
    )


def edit(rows: list[TradeRow], trade: int, kind: str, **changes: object) -> list[TradeRow]:
    return [
        dataclasses.replace(r, **changes) if (r.trade, r.kind) == (trade, kind) else r  # type: ignore[arg-type]
        for r in rows
    ]


def base_rows(run: ParityRun) -> list[TradeRow]:
    return [r for r in run.tv.rows if r.trade <= N]


def test_F_0_3_8_compare_a_perfect_match(tf: ParityRun) -> None:
    c = compared(tf, window(tf))
    assert c.tv_trades == N and c.engine_trades == N
    assert c.by_reason() == {"match": N}
    assert c.matched_share == 1.0 and c.differences() == []


def test_F_0_3_8_compare_a_quantity_difference(tf: ParityRun) -> None:
    """Same bars and prices, a different size: classified, never a match (found on MR)."""
    rows = base_rows(tf)
    entry = next(r for r in rows if (r.trade, r.kind) == (3, "entry"))
    c = compared(tf, window(tf, edit(rows, 3, "entry", quantity=entry.quantity + 1.0)))
    assert c.by_reason() == {"match": N - 1, "quantity": 1}
    (diff,) = c.differences()
    assert diff.reason == "quantity" and diff.tv_index == 2
    assert "quantity" in diff.detail
    # half a step is the tolerance: a float-noise difference is still a match
    tiny = compared(tf, window(tf, edit(rows, 3, "entry", quantity=entry.quantity + 1e-9)))
    assert tiny.by_reason() == {"match": N}


def test_F_0_3_8_compare_a_missing_trade(tf: ParityRun) -> None:
    """A TradingView trade on a bar where the engine did not enter."""
    rows = base_rows(tf)
    first, second = (next(r for r in rows if (r.trade, r.kind) == (k, "entry")) for k in (4, 5))
    # a bar strictly between trade 4's exit and trade 5's entry, where the engine is flat
    exit4 = next(r for r in rows if (r.trade, r.kind) == (4, "exit"))
    gap_bars = (second.when - exit4.when) // dt.timedelta(hours=1)
    assert gap_bars >= 3, "trades 4 and 5 are too close for a hand-built missing trade"
    when = exit4.when + dt.timedelta(hours=1)
    fake = [
        dataclasses.replace(first, trade=99, when=when),
        dataclasses.replace(exit4, trade=99, when=when + dt.timedelta(hours=1)),
    ]
    c = compared(tf, window(tf, rows + fake))
    assert c.by_reason() == {"match": N, "missing_in_engine": 1}
    (diff,) = c.differences()
    assert diff.engine_index is None and diff.tv_index is not None


def test_F_0_3_8_compare_an_extra_trade(tf: ParityRun) -> None:
    """An engine trade inside the covered range that TradingView does not have."""
    rows = [r for r in base_rows(tf) if r.trade != 5]  # trade 5 is inside the range
    c = compared(tf, window(tf, rows))
    assert c.tv_trades == N - 1 and c.engine_trades == N
    assert c.by_reason() == {"match": N - 1, "extra_in_engine": 1}
    (diff,) = c.differences()
    assert diff.tv_index is None and diff.engine_index is not None
    # P-47: an extra engine trade does not lower D-011's trade share as it is defined today
    assert c.matched_share == 1.0


def test_F_0_3_8_compare_a_one_bar_entry_shift(tf: ParityRun) -> None:
    """TradingView entering one bar later is a missing trade *and* an extra one, side by side."""
    rows = base_rows(tf)
    entry = next(r for r in rows if (r.trade, r.kind) == (6, "entry"))
    shifted = edit(rows, 6, "entry", when=entry.when + dt.timedelta(hours=1))
    c = compared(tf, window(tf, shifted))
    assert c.by_reason() == {"match": N - 1, "missing_in_engine": 1, "extra_in_engine": 1}
    missing = next(p for p in c.pairs if p.reason == "missing_in_engine")
    extra = next(p for p in c.pairs if p.reason == "extra_in_engine")
    assert missing.entry_bar == extra.entry_bar + 1  # the shift is visible in the report


def test_F_0_3_8_compare_an_exit_on_another_bar(tf: ParityRun) -> None:
    """Same entry, a different exit bar: the intrabar path is the named suspect (D-335)."""
    rows = base_rows(tf)
    exit7 = next(r for r in rows if (r.trade, r.kind) == (7, "exit"))
    moved = edit(rows, 7, "exit", when=exit7.when + dt.timedelta(hours=1), price=exit7.price + 5)
    c = compared(tf, window(tf, moved))
    assert c.by_reason() == {"match": N - 1, "intrabar_path": 1}


def test_F_0_3_8_compare_a_sub_tick_exit_price(tf: ParityRun) -> None:
    """An exit price within one tick is a rounding difference, not a different decision."""
    rows = base_rows(tf)
    exit8 = next(r for r in rows if (r.trade, r.kind) == (8, "exit"))
    tick = tf.config.pine.tick_size
    c = compared(tf, window(tf, edit(rows, 8, "exit", price=exit8.price + tick)))
    assert c.by_reason() == {"match": N - 1, "sub_tick_level": 1}
    far = compared(tf, window(tf, edit(rows, 8, "exit", price=exit8.price + 50 * tick)))
    assert far.by_reason() == {"match": N - 1, "unexplained": 1}


def test_F_0_3_8_compare_the_opposite_direction(tf: ParityRun) -> None:
    rows = base_rows(tf)
    flipped = [dataclasses.replace(r, direction=-1) if r.trade == 2 else r for r in rows]
    c = compared(tf, window(tf, flipped))
    assert c.by_reason() == {"match": N - 1, "unexplained": 1}
    (diff,) = c.differences()
    assert diff.detail == "opposite direction"
