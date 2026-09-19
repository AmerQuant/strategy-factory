"""F-0.5.2: risk and distribution metrics on the hand fixture, vs independent formulas.

The reference implementation here is the Python standard library (``statistics``) applied
to the hand-derived daily returns, not the NumPy code under test.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import numpy as np
import pytest
from fixtures.metrics_runs import CAPITAL, NOTIONAL, hand_run

from strategy_factory.core.errors import ConfigError
from strategy_factory.metrics import risk
from strategy_factory.metrics.config import MetricsConfig, load_metrics_config
from strategy_factory.metrics.containers import EquityCurve
from strategy_factory.metrics.standard import compute_metrics

# daily equity changes of the hand fixture (one bar per UTC date), / initial capital
HAND_DAILY = [0, 5000, -3000, -2500, 8500, -4000, 6000, -1000, 3000, -1000]
HAND_R = [x / 100_000 for x in HAND_DAILY]


def test_F_0_5_2_daily_returns_last_equity_per_utc_date() -> None:
    np.testing.assert_allclose(risk.daily_returns(hand_run().equity), HAND_R, rtol=0, atol=1e-15)


def test_F_0_5_2_daily_returns_collapse_intraday_bars() -> None:
    ts = np.array(
        ["2024-01-02T14:00", "2024-01-02T20:00", "2024-01-03T14:00", "2024-01-03T23:00"],
        dtype="datetime64[ns]",
    )
    curve = EquityCurve(
        ts=ts,
        equity_mtm=np.array([100_500.0, 101_000.0, 100_800.0, 100_600.0]),
        in_position=np.array([True, True, True, True]),
        realized_pnl=np.zeros(4),
        initial_capital=CAPITAL,
        notional=NOTIONAL,
        open_pnl_end=600.0,
    )
    np.testing.assert_allclose(risk.daily_returns(curve), [0.01, -0.004], rtol=1e-12)


@pytest.mark.parametrize(("calendar", "periods"), [("us_equity", 252), ("24x5", 260)])
def test_F_0_5_2_sharpe_sortino_reference(calendar: str, periods: int) -> None:
    m = compute_metrics(hand_run(), calendar=calendar)
    mean = statistics.fmean(HAND_R)
    ref_sharpe = mean / statistics.stdev(HAND_R) * math.sqrt(periods)
    downside = math.sqrt(statistics.fmean([min(r, 0.0) ** 2 for r in HAND_R]))
    ref_sortino = mean / downside * math.sqrt(periods)
    assert m.sharpe == pytest.approx(ref_sharpe, rel=1e-12)
    assert m.sortino == pytest.approx(ref_sortino, rel=1e-12)


def test_F_0_5_2_max_dd_ulcer_underwater() -> None:
    m = compute_metrics(hand_run(), calendar="us_equity")
    assert m.max_dd_pct == 5.5
    # dd % of capital per bar: 0 0 3 5.5 0 4 0 1 0 1
    assert m.ulcer_index == pytest.approx(math.sqrt((9 + 30.25 + 16 + 1 + 1) / 10), rel=1e-14)
    # longest stretch: bars 2-3 (2 bars); peak 2021-10-01 -> recovery 2022-06-01 = 243 days
    assert m.max_underwater_bars == 2
    assert m.max_underwater_days == 243.0


def test_F_0_5_2_underwater_not_recovered_runs_to_last_bar() -> None:
    ts = np.array(["2024-01-01", "2024-01-02", "2024-01-10", "2024-01-20"], dtype="datetime64[ns]")
    curve = EquityCurve(
        ts=ts,
        equity_mtm=np.array([100_000.0, 101_000.0, 100_500.0, 100_200.0]),
        in_position=np.array([True, True, True, True]),
        realized_pnl=np.zeros(4),
        initial_capital=CAPITAL,
        notional=NOTIONAL,
        open_pnl_end=200.0,
    )
    assert risk.longest_underwater(curve) == (2, 18.0)


def test_F_0_5_2_trade_return_moments_reference() -> None:
    m = compute_metrics(hand_run(), calendar="us_equity")
    # two trades, r = -0.005 and 0.095: symmetric -> skew 0, excess kurtosis 1 - 3 = -2
    assert m.trade_return_skew == pytest.approx(0.0, abs=1e-12)
    assert m.trade_return_excess_kurtosis == pytest.approx(-2.0, rel=1e-12)
    rng = np.random.default_rng(7)
    pnl = rng.normal(100, 900, size=200) + rng.exponential(500, size=200)
    r = pnl / NOTIONAL
    mu = statistics.fmean(r)
    m2 = statistics.fmean([(x - mu) ** 2 for x in r])
    m3 = statistics.fmean([(x - mu) ** 3 for x in r])
    m4 = statistics.fmean([(x - mu) ** 4 for x in r])
    skew, kurt = risk.trade_return_moments(pnl, NOTIONAL)
    assert skew == pytest.approx(m3 / m2**1.5, rel=1e-9)
    assert kurt == pytest.approx(m4 / m2**2 - 3, rel=1e-9)


def test_F_0_5_2_degenerate_inputs_are_nan() -> None:
    assert math.isnan(risk.sharpe(np.array([0.01]), 252))
    assert math.isnan(risk.sharpe(np.array([0.01, 0.01]), 252))
    assert math.isinf(risk.sortino(np.array([0.01, 0.02]), 252))
    assert math.isnan(risk.sortino(np.array([0.0, 0.0]), 252))
    assert all(math.isnan(x) for x in risk.trade_return_moments(np.array([5.0]), NOTIONAL))


def test_F_0_5_2_periods_per_year_from_config(tmp_path: Path) -> None:
    assert load_metrics_config().periods_per_year == {"us_equity": 252, "24x5": 260}
    assert MetricsConfig().annualisation("24x5") == 260
    cfg_path = tmp_path / "m.yaml"
    cfg_path.write_text("periods_per_year:\n  us_equity: 250\n", encoding="utf-8")
    cfg = load_metrics_config(cfg_path)
    m250 = compute_metrics(hand_run(), calendar="us_equity", config=cfg)
    m252 = compute_metrics(hand_run(), calendar="us_equity")
    assert m250.sharpe == pytest.approx(m252.sharpe * math.sqrt(250 / 252), rel=1e-12)
    with pytest.raises(ConfigError):
        cfg.annualisation("24x5")
    with pytest.raises(ConfigError):
        load_metrics_config(tmp_path / "missing.yaml")
