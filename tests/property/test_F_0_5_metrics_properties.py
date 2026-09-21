"""F-0.5.1 / F-0.5.4: metric invariants on random but contract-consistent runs (Hypothesis)."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest
from fixtures.hypothesis_budget import examples
from fixtures.metrics_runs import CAPITAL, STEPS_NS, RunSpec, build_run, run_specs
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from strategy_factory.metrics.batch import core_metrics_batch
from strategy_factory.metrics.standard import (
    avg_annual_dd_peak_usd,
    compute_metrics,
    core_metrics,
    yearly_drawdowns,
)
from strategy_factory.metrics.tables import monthly_table, yearly_table

# Numba compiles on first use; no per-example deadline.
PROPS = settings(deadline=None, max_examples=examples(150))

# -- pinned falsifying examples (D-368) --------------------------------------------------------
# The per-PR CI profile is derandomized and `.hypothesis/` is git-ignored, so an example found
# on a laptop never reaches CI by itself. Every example that has ever falsified a property here
# is therefore pinned with `@example` next to the property, where it runs under ANY profile.
# Keep them: they are regression tests for a bug that CI could not otherwise see.

#: Found by Hypothesis on 2026-09-21 and shrunk (P-44). Trade 11 is a short whose gross P&L is
#: +10,000 at qty 100; when `scaled` multiplied the P&L but not the position, k = 10 moved the
#: derived exit price from 900 to exactly 0 and `TradeLog` refused the run.
FOUND_P44 = RunSpec(
    start=np.datetime64("2018-05-11", "ns"),
    steps=("1d",) * 226,
    trades=((1, 0),) * 5
    + ((1, 5), (1, 6), (1, 8), (4, 12), (13, 12), (15, 4), (15, 4))
    + ((1, 0),) * 6,
    increments=(0.0,) * 102 + (1362.0, 0.0, 2638.0, 3000.0, 3000.0) + (0.0,) * 120,
    costs=(0.0,) * 18,
)
#: The same boundary, small enough to check by hand: one long trade losing 10,000 at qty 100
#: moves the price from 1000 to 900; scaling the loss by 10 at a fixed qty would reach 0.
BOUNDARY_P44 = RunSpec(
    start=np.datetime64("2020-01-01", "ns"),
    steps=("1d",) * 5,
    trades=((1, 4),),
    increments=(0.0, -2500.0, -2500.0, -2500.0, -2500.0, 0.0),
    costs=(0.0,),
)
#: every pinned example, for the count the review reports and for the fixture test below
PINNED_EXAMPLES = ((FOUND_P44, 10.0), (BOUNDARY_P44, 10.0))


@PROPS
@given(run_specs())
def test_F_0_5_4_table_sums_consistent(spec) -> None:
    run = build_run(spec)
    years = yearly_table(run)
    months = monthly_table(run)
    tol = 1e-6
    for y in years:
        month_sum = math.fsum(m.profit_usd for m in months if m.year == y.year)
        assert month_sum == pytest.approx(y.profit_usd, abs=tol)
        assert sum(m.n_trades for m in months if m.year == y.year) == y.n_trades
    total = run.equity.equity_mtm[-1] - CAPITAL
    assert math.fsum(y.profit_usd for y in years) == pytest.approx(total, abs=tol)
    assert sum(y.n_trades for y in years) == len(run.trades)


@PROPS
@given(run_specs())
def test_F_0_5_1_drawdowns_non_negative_and_ystart_le_peak(spec) -> None:
    run = build_run(spec)
    ydd = yearly_drawdowns(run.equity)
    assert np.all(ydd.dd_ystart_usd >= 0)
    assert np.all(ydd.dd_ystart_usd <= ydd.dd_peak_usd)
    m = compute_metrics(run, calendar="us_equity")
    assert m.avg_annual_dd_ystart_pct >= 0
    assert m.avg_annual_dd_ystart_pct <= m.avg_annual_dd_peak_pct + 1e-12
    assert m.avg_annual_dd_peak_pct <= m.max_dd_pct + 1e-12
    assert m.ulcer_index >= 0 and m.max_dd_pct >= 0
    assert 0.0 <= m.exposure <= 1.0
    assert ydd.weights.sum() == pytest.approx(m.years, rel=1e-12)


@PROPS
@given(run_specs(), st.sampled_from([0.25, 0.5, 2.0, 3.0, 10.0]))
@example(FOUND_P44, 10.0)
@example(BOUNDARY_P44, 10.0)
def test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio(spec, k: float) -> None:
    base = core_metrics(build_run(spec).equity)
    scaled_run = build_run(spec.scaled(k))
    scaled = core_metrics(scaled_run.equity)
    rel = 1e-9
    abs_tol = 1e-6
    assert scaled.avg_annual_profit_usd == pytest.approx(
        k * base.avg_annual_profit_usd, rel=rel, abs=abs_tol
    )
    assert scaled.avg_annual_dd_ystart_usd == pytest.approx(
        k * base.avg_annual_dd_ystart_usd, rel=rel, abs=abs_tol
    )
    assert avg_annual_dd_peak_usd(scaled_run.equity) == pytest.approx(
        k * avg_annual_dd_peak_usd(build_run(spec).equity), rel=rel, abs=abs_tol
    )
    if base.avg_annual_dd_ystart_usd > 1.0:  # away from the 0-denominator (inf) edge
        assert scaled.profit_dd_ratio == pytest.approx(base.profit_dd_ratio, rel=1e-7, abs=1e-9)
    elif base.avg_annual_dd_ystart_usd == 0.0:
        assert math.isinf(scaled.profit_dd_ratio) and math.isinf(base.profit_dd_ratio)


@PROPS
@given(run_specs(), st.data())
def test_F_0_5_1_adding_cost_never_increases_profit(spec, data) -> None:
    run = build_run(spec)
    assume(len(run.trades) > 0)
    trade = data.draw(st.integers(0, len(run.trades) - 1))
    cost = data.draw(st.integers(1, 5000).map(float))
    costlier = build_run(spec.with_extra_cost(trade, cost))
    before = core_metrics(run.equity)
    after = core_metrics(costlier.equity)
    assert after.avg_annual_profit_usd <= before.avg_annual_profit_usd
    assert after.avg_annual_profit_pct <= before.avg_annual_profit_pct
    assert costlier.trades.pnl_net.sum() <= run.trades.pnl_net.sum()


@PROPS
@given(st.data())
def test_F_0_5_1_batch_equals_single(data) -> None:
    n = data.draw(st.integers(min_value=2, max_value=150))
    steps = tuple(
        data.draw(st.lists(st.sampled_from(sorted(STEPS_NS)), min_size=n - 1, max_size=n - 1))
    )
    specs = data.draw(st.lists(run_specs(n=n, steps=steps), min_size=1, max_size=8))
    start = specs[0].start
    runs = [build_run(replace(s, start=start)) for s in specs]
    eq = np.column_stack([r.equity.equity_mtm for r in runs])
    pos = np.column_stack([r.equity.in_position for r in runs])
    closed = np.array([len(r.trades) for r in runs], dtype=np.int64)
    out = core_metrics_batch(eq, pos, closed, runs[0].equity.ts, CAPITAL)
    for j, run in enumerate(runs):
        single = core_metrics(run.equity)
        assert out["avg_annual_profit_usd"][j] == single.avg_annual_profit_usd
        assert out["avg_annual_profit_pct"][j] == single.avg_annual_profit_pct
        assert out["avg_annual_dd_ystart_usd"][j] == single.avg_annual_dd_ystart_usd
        assert out["avg_annual_dd_ystart_pct"][j] == single.avg_annual_dd_ystart_pct
        assert out["profit_dd_ratio"][j] == single.profit_dd_ratio
        assert out["exposure"][j] == single.exposure
        assert out["n_entries"][j] == single.n_entries
        assert out["n_trades"][j] == len(run.trades)
        # the full report agrees with the core path
        report = compute_metrics(run, calendar="24x5")
        assert report.profit_dd_ratio == single.profit_dd_ratio
        assert report.n_trades == out["n_trades"][j]
        assert report.n_entries == out["n_entries"][j]
        # entries miss same-bar trades and count an open position (gaps >= 1: no merges)
        multi_bar = int(np.count_nonzero(run.trades.bars_held > 0))
        assert single.n_entries == multi_bar + int(run.open_position_marked)


def _reference_core(run) -> tuple[float, float, float]:
    """Plain-Python reference: (avg annual profit $, weighted avg dd-from-year-start $,
    exposure), written from the definitions without the Numba kernels."""
    ts = [np.datetime64(t, "ns") for t in run.equity.ts]
    eq = [float(x) for x in run.equity.equity_mtm]
    day = np.timedelta64(1, "D").astype("timedelta64[ns]")
    years = ((ts[-1] - ts[0]) / day) / 365.25
    profit = (eq[-1] - CAPITAL) / years
    by_year: dict[int, float] = {}
    start_equity, peak, current = CAPITAL, CAPITAL, None
    for t, e in zip(ts, eq, strict=True):
        y = int(str(t)[:4])
        if y != current:
            current, peak = y, start_equity
        peak = max(peak, e)
        by_year[y] = max(by_year.get(y, 0.0), peak - e)
        start_equity = e
    weights = {}
    for y in by_year:
        lo = max(ts[0], np.datetime64(f"{y}-01-01", "ns"))
        hi = min(ts[-1], np.datetime64(f"{y + 1}-01-01", "ns"))
        weights[y] = ((hi - lo) / day) / 365.25
    dd = sum(weights[y] * by_year[y] for y in by_year) / sum(weights.values())
    exposure = sum(bool(p) for p in run.equity.in_position) / len(eq)
    return profit, dd, exposure


@PROPS
@given(run_specs())
def test_F_0_5_1_core_matches_plain_python_reference(spec) -> None:
    run = build_run(spec)
    got = core_metrics(run.equity)
    profit, dd, exposure = _reference_core(run)
    assert got.avg_annual_profit_usd == pytest.approx(profit, rel=1e-9, abs=1e-6)
    assert got.avg_annual_dd_ystart_usd == pytest.approx(dd, rel=1e-9, abs=1e-6)
    assert got.exposure == pytest.approx(exposure, rel=1e-12)


@pytest.mark.parametrize(("spec", "k"), PINNED_EXAMPLES, ids=["found_p44", "boundary_p44"])
def test_F_0_5_1_scaling_grows_the_position_not_the_price_level(spec: RunSpec, k: float) -> None:
    """D-368: `RunSpec.scaled(k)` is a k-times larger position. Every price is unchanged, and
    quantity, P&L and costs are k times the original -- so the scaling property tests what it
    says (a bigger position scales profit and drawdown), not a move in the price level."""
    base = build_run(spec).trades
    big = build_run(spec.scaled(k)).trades
    assert base.qty.size == big.qty.size > 0
    np.testing.assert_array_equal(big.entry_price, base.entry_price)
    np.testing.assert_allclose(big.exit_price, base.exit_price, rtol=1e-12)
    np.testing.assert_allclose(big.qty, k * base.qty, rtol=1e-12)
    np.testing.assert_allclose(big.pnl_gross, k * base.pnl_gross, rtol=1e-12)
    np.testing.assert_allclose(big.cost_commission, k * base.cost_commission, rtol=1e-12)
    assert (big.exit_price > 0).all()
