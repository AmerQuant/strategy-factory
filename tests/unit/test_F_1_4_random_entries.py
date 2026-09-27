"""F-1.4 (D-102, D-607, D-615): the matched random baseline.

The matched properties are equal **by construction** (direction, trade count, the exact
multiset of holding periods), placements never overlap, only allowed bars are used, and the
same seed gives the same draws.
"""

from __future__ import annotations

import numpy as np
from fixtures.executor import bars as walk

from strategy_factory.baseline.random_entries import (
    allowed_range,
    atr_returns,
    baseline_seed,
    baseline_signals,
    draw_placements,
    frictionless_costs,
    frictionless_sizing,
    run_baseline,
)
from strategy_factory.engine.api import ExitParams, MarketArrays, simulate


def test_F_1_4_placements_match_count_and_holdings_exactly() -> None:
    rng = np.random.default_rng(1)
    holdings = np.array([3, 1, 5, 5, 2, 8])
    for _ in range(200):
        starts, held = draw_placements(rng, holdings, lo=10, hi=200)
        assert starts is not None
        assert len(starts) == len(holdings)
        assert sorted(held.tolist()) == sorted(holdings.tolist())  # the exact multiset


def test_F_1_4_placements_never_overlap_and_stay_on_allowed_bars() -> None:
    rng = np.random.default_rng(2)
    holdings = rng.integers(1, 20, size=30)
    for _ in range(200):
        starts, held = draw_placements(rng, holdings, lo=37, hi=900)
        assert starts is not None
        assert starts[0] >= 37 and (starts + held).max() <= 900
        # the next signal comes after the previous trade's exit signal bar
        assert (starts[1:] >= starts[:-1] + held[:-1] + 1).all()


def test_F_1_4_a_tight_fit_is_still_exact_and_an_impossible_one_is_refused() -> None:
    rng = np.random.default_rng(3)
    holdings = np.array([4, 4, 4])  # three blocks of 5 signal bars = 15
    starts, _ = draw_placements(rng, holdings, lo=0, hi=14)  # exactly 15 bars
    assert starts is not None and starts.tolist() == [0, 5, 10]
    assert draw_placements(rng, holdings, lo=0, hi=13) == (None, None)


def test_F_1_4_placements_cover_the_allowed_range() -> None:
    """Uniform in position: over many draws the first and last allowed bars are both used."""
    rng = np.random.default_rng(4)
    firsts, lasts = set(), set()
    for _ in range(3000):
        starts, held = draw_placements(rng, np.array([2]), lo=5, hi=20)
        assert starts is not None
        firsts.add(int(starts[0]))
        lasts.add(int(starts[0] + held[0]))
    assert min(firsts) == 5 and max(lasts) == 20


def test_F_1_4_zero_holdings_are_clamped_to_one_bar() -> None:
    """A probe trade stopped on its entry bar has bars_held 0; a scheduled baseline exit needs
    at least one bar (D-300), so it is drawn as 1 and counted."""
    rng = np.random.default_rng(5)
    starts, held = draw_placements(rng, np.array([0, 2]), lo=0, hi=50)
    assert starts is not None and sorted(held.tolist()) == [1, 2]


def test_F_1_4_the_same_seed_gives_the_same_draws() -> None:
    holdings = np.array([3, 7, 2, 9])
    a = draw_placements(np.random.default_rng(42), holdings, lo=0, hi=500)
    b = draw_placements(np.random.default_rng(42), holdings, lo=0, hi=500)
    c = draw_placements(np.random.default_rng(43), holdings, lo=0, hi=500)
    assert a[0] is not None and b[0] is not None and c[0] is not None
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])
    assert not np.array_equal(a[0], c[0])


def test_F_1_4_d607_seed_depends_on_every_key_part() -> None:
    base = baseline_seed(42, "SPY", "1D", "mr_rsi2_below_10", "long")
    assert base == baseline_seed(42, "SPY", "1D", "mr_rsi2_below_10", "long")
    for other in (
        baseline_seed(43, "SPY", "1D", "mr_rsi2_below_10", "long"),
        baseline_seed(42, "QQQ", "1D", "mr_rsi2_below_10", "long"),
        baseline_seed(42, "SPY", "1H", "mr_rsi2_below_10", "long"),
        baseline_seed(42, "SPY", "1D", "mr_rsi5_below_30", "long"),
        baseline_seed(42, "SPY", "1D", "mr_rsi2_below_10", "short"),
    ):
        assert other != base


def test_F_1_4_allowed_range_starts_after_the_warmup_and_a_valid_atr() -> None:
    atr = np.array([np.nan] * 13 + [1.0] * 87)
    assert allowed_range(100, warmup=5, atr=atr) == (13, 98)  # the ATR is the later
    assert allowed_range(100, warmup=40, atr=atr) == (40, 98)  # the probe is the later


# -- the engine runs the placements exactly --------------------------------------------------
def market(n: int, seed: int) -> MarketArrays:
    b = walk(n, seed)
    return MarketArrays(b["open"], b["high"], b["low"], b["close"], b["atr"])


def test_F_1_4_the_engine_holds_each_baseline_trade_exactly_its_drawn_bars() -> None:
    n = 400
    m = market(n, 7)
    starts, held = draw_placements(
        np.random.default_rng(8), np.array([1, 4, 9, 2]), lo=20, hi=n - 2
    )
    assert starts is not None
    entry, exit_ = baseline_signals(n, starts, held)
    # a huge disaster multiple keeps the stop out of the way, so every exit is scheduled
    sim = simulate(
        m,
        entry,
        exit_,
        1,
        ExitParams(disaster_atr=1e9),
        frictionless_costs(n),
        frictionless_sizing(100_000.0, 100_000.0),
        1,
    )
    np.testing.assert_array_equal(sim.entry_idx, starts + 1)
    np.testing.assert_array_equal(sim.exit_idx - sim.entry_idx, held)
    r = atr_returns(sim, 1)
    expected = (sim.exit_price - sim.entry_price) / sim.atr_at_entry
    np.testing.assert_allclose(r, expected)


def test_F_1_4_run_baseline_matches_count_and_is_reproducible() -> None:
    n = 600
    m = market(n, 9)
    holdings = np.array([2, 5, 1, 7, 3])
    ts = (np.arange(n) * 86_400_000_000).astype(np.int64)  # daily, from 1970
    kw = dict(direction=1, holdings=holdings, lo=20, hi=n - 2, simulations=50)
    a = run_baseline(m, ts, notional=1e5, initial_capital=1e5, rng=np.random.default_rng(11), **kw)  # type: ignore[arg-type]
    b = run_baseline(m, ts, notional=1e5, initial_capital=1e5, rng=np.random.default_rng(11), **kw)  # type: ignore[arg-type]
    assert a.sim_means.shape == (50,) and a.infeasible == 0
    np.testing.assert_array_equal(a.sim_means, b.sim_means)
    assert a.trades_per_sim.min() == a.trades_per_sim.max() == len(holdings)
    assert a.pooled_returns.shape[0] == a.pooled_years.shape[0] == 50 * len(holdings)
    assert np.isfinite(a.sim_means).all()


def test_F_1_4_run_baseline_counts_an_impossible_fit() -> None:
    n = 60
    res = run_baseline(
        market(n, 1),
        np.arange(n, dtype=np.int64),
        direction=-1,
        holdings=np.array([40, 40]),
        lo=10,
        hi=n - 2,
        simulations=5,
        notional=1e5,
        initial_capital=1e5,
        rng=np.random.default_rng(0),
    )
    assert res.infeasible == 5 and np.isnan(res.sim_means).all()


def test_F_1_4_the_direction_is_matched() -> None:
    """Same seed, stop out of the way: the short baseline's trades are the long ones negated."""
    n = 300
    kw = dict(holdings=np.array([3, 3, 6]), lo=20, hi=n - 2, simulations=4)
    ts = np.arange(n, dtype=np.int64)
    up = run_baseline(
        market(n, 2),
        ts,
        direction=1,
        notional=1e5,
        initial_capital=1e5,
        rng=np.random.default_rng(1),
        **kw,
    )  # type: ignore[arg-type]
    down = run_baseline(
        market(n, 2),
        ts,
        direction=-1,
        notional=1e5,
        initial_capital=1e5,
        rng=np.random.default_rng(1),
        **kw,
    )  # type: ignore[arg-type]
    assert up.direction == 1 and down.direction == -1
    np.testing.assert_allclose(down.pooled_returns, -up.pooled_returns)
    assert np.abs(up.pooled_returns).sum() > 0


def test_F_1_4_the_holding_order_is_a_random_permutation() -> None:
    """Every holding period appears first in some draw: the order is shuffled, not kept."""
    rng = np.random.default_rng(6)
    holdings = np.array([1, 2, 3, 4, 5])
    firsts = {int(draw_placements(rng, holdings, lo=0, hi=200)[1][0]) for _ in range(500)}  # type: ignore[index]
    assert firsts == {1, 2, 3, 4, 5}


def test_F_1_4_d618_baseline_trades_hold_exactly_their_drawn_periods() -> None:
    """D-618 (amends D-615): no second disaster stop in the baseline. On violent bars, where a
    3-ATR stop would certainly fire, every baseline trade still holds its drawn period."""
    n = 800
    rng = np.random.default_rng(12)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.05, n)))  # 5 % bars, huge relative to ATR
    open_ = np.concatenate(([100.0], close[:-1]))
    m = MarketArrays(
        open_,
        np.maximum(open_, close) * 1.03,
        np.minimum(open_, close) * 0.97,
        close,
        np.full(n, 0.5),
    )  # a tiny ATR: a 3-ATR stop is 1.5 price units away
    holdings = np.array([12, 30, 7, 45, 20])
    res = run_baseline(
        m,
        np.arange(n, dtype=np.int64),
        direction=1,
        holdings=holdings,
        lo=20,
        hi=n - 2,
        simulations=30,
        notional=1e5,
        initial_capital=1e5,
        rng=np.random.default_rng(3),
    )
    assert res.infeasible == 0
    np.testing.assert_array_equal(np.sort(res.pooled_bars_held), np.sort(np.tile(holdings, 30)))
