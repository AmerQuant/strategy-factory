"""F-0.5.4: yearly and monthly tables on the hand fixture; monthly sum = yearly sum = total."""

from __future__ import annotations

import math

import pytest
from fixtures.metrics_runs import hand_run

from strategy_factory.metrics.tables import monthly_table, yearly_table


def test_F_0_5_4_yearly_table_hand_fixture() -> None:
    rows = yearly_table(hand_run())
    assert [r.year for r in rows] == [2021, 2022, 2023]
    assert [r.profit_usd for r in rows] == [2000.0, 8000.0, 1000.0]
    assert [r.profit_pct for r in rows] == [2.0, 8.0, 1.0]
    assert [r.dd_ystart_pct for r in rows] == [3.0, 4.0, 1.0]
    assert [r.dd_peak_pct for r in rows] == [3.0, 5.5, 1.0]
    # trades are counted in their exit year: T1 (2021-10 -> 2022-03) belongs to 2022
    assert [r.n_trades for r in rows] == [0, 1, 1]
    assert math.isnan(rows[0].win_rate)
    assert rows[1].win_rate == 0.0 and rows[2].win_rate == 1.0
    assert [r.profitable_month_share for r in rows] == pytest.approx([1 / 3, 0.5, 1 / 3])
    assert [r.covered_fraction for r in rows] == pytest.approx(
        [183 / 365.25, 365 / 365.25, 182 / 365.25]
    )


def test_F_0_5_4_trade_spanning_year_end_mtm_split() -> None:
    # T1 is open over 2021-12-31: its marked P&L at the 2021 close (+2,000) is 2021 profit,
    # the rest (-2,500 to its exit) lands in 2022 although the trade is counted in 2022.
    rows = {r.year: r for r in yearly_table(hand_run())}
    months = {(m.year, m.month): m for m in monthly_table(hand_run())}
    assert rows[2021].profit_usd == 2000.0
    assert months[(2022, 3)].profit_usd == -2500.0
    assert months[(2022, 3)].n_trades == 1


def test_F_0_5_4_monthly_table_hand_fixture() -> None:
    rows = monthly_table(hand_run())
    assert [(r.year, r.month, r.profit_usd, r.n_trades) for r in rows] == [
        (2021, 7, 0.0, 0),
        (2021, 10, 5000.0, 0),
        (2021, 12, -3000.0, 0),
        (2022, 3, -2500.0, 1),
        (2022, 6, 8500.0, 0),
        (2022, 9, -4000.0, 0),
        (2022, 12, 6000.0, 0),
        (2023, 2, -1000.0, 1),
        (2023, 4, 3000.0, 0),
        (2023, 7, -1000.0, 0),
    ]


def test_F_0_5_4_monthly_sum_equals_yearly_equals_total() -> None:
    run = hand_run()
    years = yearly_table(run)
    months = monthly_table(run)
    for y in years:
        assert sum(m.profit_usd for m in months if m.year == y.year) == y.profit_usd
        assert sum(m.n_trades for m in months if m.year == y.year) == y.n_trades
    total = run.equity.equity_mtm[-1] - run.equity.initial_capital
    assert sum(y.profit_usd for y in years) == total
    assert sum(y.n_trades for y in years) == len(run.trades)
