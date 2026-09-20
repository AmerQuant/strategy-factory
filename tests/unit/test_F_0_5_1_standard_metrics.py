"""F-0.5.1: team standard metrics on hand-computed fixtures (answers known in advance).

Hand fixture (tests/fixtures/metrics_runs.py): 10 daily bars 2021-07-02 .. 2023-07-02
(730 days, partial first and last year), capital 100,000.

* years = 730 / 365.25; covered days per year 2021/2022/2023 = 183 / 365 / 182.
* total net profit = 111,000 - 100,000 = 11,000 (includes +2,000 open P&L of T3).
* dd from year start: 2021 3,000 (105,000 -> 102,000); 2022 4,000 (108,000 -> 104,000;
  99,500 is only 2,500 below the 102,000 year start); 2023 1,000.
* dd against the all-time peak: 2021 3,000; 2022 5,500 (105,000 -> 99,500); 2023 1,000.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from fixtures.metrics_runs import (
    CAPITAL,
    HAND_TS,
    NOTIONAL,
    hand_run,
    meta,
    rising_run,
    trade_log,
)

from strategy_factory.metrics.containers import EquityCurve, RunResult
from strategy_factory.metrics.standard import (
    compute_metrics,
    core_metrics,
    profit_factor,
    yearly_drawdowns,
)

YEARS = 730 / 365.25
PROFIT_USD = 11_000 / YEARS
DD_YSTART_USD = (183 * 3000 + 365 * 4000 + 182 * 1000) / 730
DD_PEAK_USD = (183 * 3000 + 365 * 5500 + 182 * 1000) / 730


def _approx(x: float) -> object:
    return pytest.approx(x, rel=1e-12, abs=1e-12)


def test_F_0_5_1_fractional_years_and_yearly_weights() -> None:
    ydd = yearly_drawdowns(hand_run().equity)
    assert ydd.years.tolist() == [2021, 2022, 2023]
    np.testing.assert_allclose(ydd.weights, np.array([183, 365, 182]) / 365.25, rtol=1e-14)
    assert ydd.weights.sum() == _approx(YEARS)


def test_F_0_5_1_both_drawdown_versions_per_year() -> None:
    ydd = yearly_drawdowns(hand_run().equity)
    assert ydd.dd_ystart_usd.tolist() == [3000.0, 4000.0, 1000.0]
    assert ydd.dd_peak_usd.tolist() == [3000.0, 5500.0, 1000.0]


def test_F_0_5_1_hand_fixture_report() -> None:
    m = compute_metrics(hand_run(), calendar="us_equity")
    assert m.years == _approx(YEARS)
    assert m.total_net_profit_usd == 11_000.0
    assert m.avg_annual_profit_usd == _approx(PROFIT_USD)
    assert m.avg_annual_profit_pct == _approx(PROFIT_USD / 1000)
    # weighted by covered fraction; drawdowns relative to initial capital
    assert m.avg_annual_dd_ystart_usd == _approx(DD_YSTART_USD)
    assert m.avg_annual_dd_ystart_pct == _approx(DD_YSTART_USD / 1000)
    assert m.avg_annual_dd_peak_usd == _approx(DD_PEAK_USD)
    assert m.avg_annual_dd_peak_pct == _approx(DD_PEAK_USD / 1000)
    assert m.profit_dd_ratio == _approx(PROFIT_USD / DD_YSTART_USD)
    assert not m.inf_ratio
    assert m.exposure == 0.7
    assert m.return_per_exposure == _approx(PROFIT_USD / 1000 / 0.7)
    assert m.n_trades == 2
    assert m.n_entries == 3
    assert m.profit_factor == 19.0  # 9,500 / 500
    assert m.win_rate == 0.5
    assert m.avg_bars_held == 2.5  # (2 + 3) / 2
    assert m.expectancy_usd == 4500.0
    assert m.expectancy_pct == 4.5
    assert m.expectancy_atr == _approx((-500 / (1000 * 2) + 9500 / (1000 * 5)) / 2)  # 0.825
    assert not m.cost_placeholder


def test_F_0_5_1_open_position_at_end_is_marked() -> None:
    run = hand_run()
    m = compute_metrics(run, calendar="us_equity")
    assert m.open_position_marked
    # the open P&L (+2,000) is in the profit but T3 is not a closed trade
    assert m.total_net_profit_usd == float(run.trades.pnl_net.sum()) + 2000.0
    assert m.n_trades == 2


def test_F_0_5_1_zero_drawdown_gives_inf_ratio_and_flag() -> None:
    m = compute_metrics(rising_run(), calendar="us_equity")
    assert m.avg_annual_dd_ystart_pct == 0.0
    assert math.isinf(m.profit_dd_ratio) and m.profit_dd_ratio > 0
    assert m.inf_ratio
    assert m.cost_placeholder
    assert not m.open_position_marked
    assert math.isinf(m.profit_factor)  # no losing trade


def test_F_0_5_1_as_gate_dict_names() -> None:
    gate = compute_metrics(hand_run(), calendar="us_equity").as_gate_dict()
    expected = {
        "years",
        "total_net_profit_usd",
        "avg_annual_profit_usd",
        "avg_annual_profit_pct",
        "avg_annual_dd_ystart_usd",
        "avg_annual_dd_ystart_pct",
        "avg_annual_dd_peak_usd",
        "avg_annual_dd_peak_pct",
        "profit_dd_ratio",
        "exposure",
        "return_per_exposure",
        "n_trades",
        "n_entries",
        "profit_factor",
        "win_rate",
        "avg_bars_held",
        "expectancy_usd",
        "expectancy_pct",
        "expectancy_atr",
        "sharpe",
        "sortino",
        "max_dd_pct",
        "ulcer_index",
        "max_underwater_bars",
        "max_underwater_days",
        "trade_return_skew",
        "trade_return_excess_kurtosis",
        "inf_ratio",
        "open_position_marked",
        "cost_placeholder",
        # T08 additions (run-meta counters and flags)
        "n_skipped_min_volume",
        "min_volume_skip_flag",
        "volume_step_assumed",
        "contracts_fixed",
        "fx_peg",
    }
    assert set(gate) == expected
    assert all(isinstance(v, float) for v in gate.values())
    assert gate["open_position_marked"] == 1.0


def test_F_0_5_1_back_to_back_trades_merge_in_entries() -> None:
    ts = HAND_TS[:6]
    # T1 bars 1..2 (exit at open of 3), T2 enters at the same open of bar 3, exits at 5
    equity = np.array([0, 100, 200, 300, 400, 500], dtype=float) + CAPITAL
    in_pos = np.array([0, 1, 1, 1, 1, 0], dtype=bool)
    realized = np.array([0, 0, 0, 250, 250, 500], dtype=float)
    curve = EquityCurve(
        ts=ts,
        equity_mtm=equity,
        in_position=in_pos,
        realized_pnl=realized,
        initial_capital=CAPITAL,
        notional=NOTIONAL,
    )
    trades = trade_log(
        [
            {"entry_idx": 1, "exit_idx": 3, "entry_ts": ts[1], "exit_ts": ts[3], "pnl_net": 250.0},
            {"entry_idx": 3, "exit_idx": 5, "entry_ts": ts[3], "exit_ts": ts[5], "pnl_net": 250.0},
        ]
    )
    run = RunResult(trades=trades, equity=curve, meta=meta())
    m = compute_metrics(run, calendar="us_equity")
    assert m.n_trades == 2
    assert m.n_entries == 1
    assert core_metrics(curve).n_entries == 1


def test_F_0_5_1_profit_factor_edge_cases() -> None:
    assert profit_factor(np.array([100.0, -50.0])) == 2.0
    assert math.isinf(profit_factor(np.array([100.0])))
    assert math.isnan(profit_factor(np.array([0.0])))


def test_F_0_5_1_no_trades_gives_nan_trade_stats() -> None:
    curve = EquityCurve(
        ts=HAND_TS,
        equity_mtm=np.full(10, CAPITAL),
        in_position=np.zeros(10, dtype=bool),
        realized_pnl=np.zeros(10),
        initial_capital=CAPITAL,
        notional=NOTIONAL,
    )
    run = RunResult(trades=trade_log([]), equity=curve, meta=meta())
    m = compute_metrics(run, calendar="us_equity")
    assert m.n_trades == 0 and m.exposure == 0.0
    assert math.isnan(m.win_rate) and math.isnan(m.expectancy_usd)
    assert math.isnan(m.return_per_exposure)
    assert m.inf_ratio  # 0 / 0: denominator is 0 -> inf per the team convention
