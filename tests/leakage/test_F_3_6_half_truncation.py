"""Rule 3 for stage 3 (T14 §7): the halves are computed without reading bars beyond each half's
end (D-641, D-650 (c)).

``segment_runs`` -- the function the stage calls for every cell -- must give **identical** half-1
results whether or not the bars after half 1 exist, and identical half-2 and whole-window results
whether or not later bars exist. Half 2's indicators may read half 1 (earlier data, D-650).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from fixtures.edge_stage import flat_costs, synthetic_bars

from strategy_factory.core.config import EngineConfig
from strategy_factory.stages.optimize import EntryTask, halves, segment_runs
from strategy_factory.stages.optimize_config import load_s03_config
from strategy_factory.stages.optimize_grid import fine_grid
from strategy_factory.stages.screen import cell_signals, method_run

DATA = synthetic_bars(900, 11, phi=-0.25)
CASES = [
    ("mr_rsi", "long", "MR", [{"n": 3, "t": 20.0}]),
    ("mr_williams_confirm", "short", "MR", [{"n": 10, "t": 10.0, "confirm": "latched"}]),
    ("tf_ichimoku", "long", "TF", [{"conversion": 9, "base": 26, "span_b": 52}]),
]


def _task(bars: dict[str, Any], method: str, direction: str, edge: str, good: Any) -> EntryTask:
    return EntryTask(
        candidate_id="c",
        parent_id="p",
        method=method,
        symbol="SYN",
        timeframe="1D",
        direction=direction,  # type: ignore[arg-type]
        grid=fine_grid(method, good, good[0], max_cells=8),
        bars=bars,
        costs=flat_costs(int(bars["close"].shape[0]), 0.02),
        engine=EngineConfig(),
        exits=load_s03_config().exits[edge],
        min_trades=30,
        min_trades_half=30,
        ratio=0.8,
        failed_cell="worst0",
        spp_low=5,
        spp_high=95,
    )


def _head(bars: dict[str, Any], t: int) -> dict[str, Any]:
    return {k: v[:t] for k, v in bars.items()}


def _same(a: Any, b: Any) -> None:
    assert np.array_equal(a.trades.entry_idx, b.trades.entry_idx)
    assert np.array_equal(a.trades.exit_idx, b.trades.exit_idx)
    assert np.array_equal(a.trades.pnl_net, b.trades.pnl_net)
    assert np.array_equal(a.equity.equity_mtm, b.equity.equity_mtm)


@pytest.mark.parametrize(("method", "direction", "edge", "good"), CASES, ids=[c[0] for c in CASES])
def test_F_3_6_half_1_never_reads_half_2(method: str, direction: str, edge: str, good: Any) -> None:
    n = int(DATA["close"].shape[0])
    segs = halves(n)
    mid = segs["h1"][1]
    full = _task(DATA, method, direction, edge, good)
    cut = _task(_head(DATA, mid), method, direction, edge, good)  # half 2 does not exist
    for params in full.grid.cells():
        a = segment_runs(full, params, segs)
        b = segment_runs(cut, params, {"h1": (0, mid)})
        for leg in ("zero", "cost"):
            _same(a[("h1", leg)], b[("h1", leg)])


def _other_half2(bars: dict[str, Any], mid: int) -> dict[str, Any]:
    """The same series with every bar from ``mid`` on replaced by another path (same length)."""
    other = synthetic_bars(int(bars["close"].shape[0]), 99, phi=0.4, vol=0.03)
    out = {k: v.copy() for k, v in bars.items()}
    for k in ("open", "high", "low", "close"):
        out[k][mid:] = other[k][mid:] * (bars["close"][mid - 1] / other["open"][mid])
    return out


@pytest.mark.parametrize(("method", "direction", "edge", "good"), CASES, ids=[c[0] for c in CASES])
def test_F_3_6_half_1_is_unchanged_when_half_2_is_replaced(
    method: str, direction: str, edge: str, good: Any
) -> None:
    """Stronger than truncation: the arrays keep their length, so any use of half 2's bars in
    half 1 -- a global statistic, signals computed once on the whole series by a rule that is
    not causal -- changes half 1's result."""
    segs = halves(int(DATA["close"].shape[0]))
    mid = segs["h1"][1]
    a_task = _task(DATA, method, direction, edge, good)
    b_task = _task(_other_half2(DATA, mid), method, direction, edge, good)
    changed_h2 = 0
    for params in a_task.grid.cells():
        a = segment_runs(a_task, params, segs)
        b = segment_runs(b_task, params, segs)
        for leg in ("zero", "cost"):
            _same(a[("h1", leg)], b[("h1", leg)])
        changed_h2 += not np.array_equal(
            a[("h2", "cost")].equity.equity_mtm, b[("h2", "cost")].equity.equity_mtm
        )
    assert changed_h2  # the replacement is real: half 2 itself does change


@pytest.mark.parametrize(("method", "direction", "edge", "good"), CASES, ids=[c[0] for c in CASES])
def test_F_3_6_half_2_and_the_whole_window_never_read_later_bars(
    method: str, direction: str, edge: str, good: Any
) -> None:
    """Truncate the series after its first ``t`` bars: the segments ending at ``t`` computed on
    the short series equal the same segments computed on a longer one."""
    t = 700
    long_ = _task(DATA, method, direction, edge, good)
    short = _task(_head(DATA, t), method, direction, edge, good)
    segs = {"h2": (t // 2, t), "whole": (0, t)}
    for params in long_.grid.cells():
        a = segment_runs(long_, params, segs)
        b = segment_runs(short, params, segs)
        for k in a:
            _same(a[k], b[k])


def test_F_3_6_cell_signals_up_to_end_are_the_full_signals_prefix() -> None:
    exits = load_s03_config().exits["MR"]
    full = cell_signals(DATA, "mr_rsi", {"n": 3, "t": 20.0}, exits, "long", 14)
    for end in (200, 450, 899):
        part = cell_signals(DATA, "mr_rsi", {"n": 3, "t": 20.0}, exits, "long", 14, end)
        assert part.end == end
        assert np.array_equal(part.entry, full.entry[:end])
        assert np.array_equal(part.exit, full.exit[:end])
        assert np.array_equal(part.market.atr, full.market.atr[:end], equal_nan=True)


def test_F_3_6_method_run_whole_equals_the_unsegmented_run() -> None:
    """Stage 2's call (no segment) is unchanged by the segment arguments' defaults."""
    exits = load_s03_config().exits["MR"]
    eng = EngineConfig()
    a = method_run(DATA, "mr_rsi", {"n": 3, "t": 20.0}, exits, "long", eng)
    b = method_run(DATA, "mr_rsi", {"n": 3, "t": 20.0}, exits, "long", eng, None, 0, 900)
    assert np.array_equal(a.entry_idx, b.entry_idx) and np.array_equal(a.pnl_net, b.pnl_net)
