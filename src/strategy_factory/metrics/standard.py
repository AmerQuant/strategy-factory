"""Team standard metrics (F-0.5.1) and the :class:`MetricsReport` (F-0.5.1, F-0.5.2).

All metrics are after costs. Percentages (``*_pct``) are in percent units (``12.5`` means
12.5 %) **of initial capital**, except ``expectancy_pct`` which is of the per-trade notional.
Drawdowns are positive money amounts / percentages.

Definitions
-----------
* ``years`` = (last ts - first ts) / 365.25 days; partial years count fractionally.
* ``avg_annual_profit_usd`` = (final equity - initial capital) / ``years`` (final equity is
  mark-to-market, so a position open at the end is included and ``open_position_marked``
  is set); ``avg_annual_profit_pct`` = that / initial capital * 100.
* Annual drawdown, per calendar year (UTC), two versions:
  (a) ``ystart`` - the running peak starts at the equity at the end of the previous year
  (initial capital for the first year): **the gate/target basis**;
  (b) ``peak`` - the running peak is the all-time peak; the year's value is the largest
  drawdown observed on that year's bars.
  ``avg_annual_dd_*`` is the mean of the yearly values weighted by each year's covered
  fraction of the span (see :mod:`strategy_factory.metrics._calendar`).
* ``profit_dd_ratio`` = ``avg_annual_profit_pct / avg_annual_dd_ystart_pct`` (target
  metric); ``inf`` with flag ``inf_ratio`` when the denominator is 0.
* ``exposure`` = share of bars with an open position (fraction 0..1);
  ``return_per_exposure`` = ``avg_annual_profit_pct / exposure`` (NaN when exposure is 0).
* Trade statistics use closed trades only: ``profit_factor`` = gross wins / |gross losses|
  of ``pnl_net`` (``inf`` with no loss, NaN with no trade or all-zero P&L), ``win_rate`` =
  share with ``pnl_net > 0``, ``avg_bars_held``, ``expectancy_usd`` = mean ``pnl_net``,
  ``expectancy_pct`` = mean ``pnl_net / notional * 100``, ``expectancy_atr`` = mean
  ``pnl_net / (qty * atr_at_entry)``. All are NaN with no closed trade.
* ``n_position_entries`` counts flat -> in-position transitions of ``in_position``; this is
  what the grid batch path reports as ``n_trades`` (it includes a position open at the end
  and merges an exit and re-entry at the same open).
* Risk metrics: see :mod:`strategy_factory.metrics.risk`.

Gate names (``MetricsReport.as_gate_dict()``)
---------------------------------------------
``years, total_net_profit_usd, avg_annual_profit_usd, avg_annual_profit_pct,
avg_annual_dd_ystart_usd, avg_annual_dd_ystart_pct, avg_annual_dd_peak_usd,
avg_annual_dd_peak_pct, profit_dd_ratio, exposure, return_per_exposure, n_trades,
n_position_entries, profit_factor, win_rate, avg_bars_held, expectancy_usd, expectancy_pct,
expectancy_atr, sharpe, sortino, max_dd_pct, ulcer_index, max_underwater_bars,
max_underwater_days, trade_return_skew, trade_return_excess_kurtosis`` plus the flags
``inf_ratio, open_position_marked, cost_placeholder`` (as 0.0 / 1.0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from strategy_factory.metrics import _kernels, risk
from strategy_factory.metrics._calendar import YearCalendar, year_calendar
from strategy_factory.metrics.config import MetricsConfig
from strategy_factory.metrics.containers import EquityCurve, RunResult, TradeLog

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class CoreMetrics:
    """The metrics shared with the grid batch path (bit-identical to it)."""

    avg_annual_profit_usd: float
    avg_annual_profit_pct: float
    avg_annual_dd_ystart_usd: float
    avg_annual_dd_ystart_pct: float
    profit_dd_ratio: float
    exposure: float
    n_position_entries: int


@dataclass(frozen=True)
class YearlyDrawdowns:
    years: NDArray[np.int64]  # calendar year labels
    weights: FloatArray  # covered fraction of each year
    dd_ystart_usd: FloatArray
    dd_peak_usd: FloatArray


def _core_from_arrays(
    equity: FloatArray,
    in_position: NDArray[np.bool_],
    cal: YearCalendar,
    capital: float,
) -> CoreMetrics:
    r = _kernels.core_one(equity, in_position, cal.year_id, cal.weights, capital, cal.years)
    return CoreMetrics(
        avg_annual_profit_usd=float(r[0]),
        avg_annual_profit_pct=float(r[1]),
        avg_annual_dd_ystart_usd=float(r[2]),
        avg_annual_dd_ystart_pct=float(r[3]),
        profit_dd_ratio=float(r[4]),
        exposure=float(r[5]),
        n_position_entries=int(r[6]),
    )


def core_metrics(curve: EquityCurve) -> CoreMetrics:
    """Single-run core metrics (same kernel as :func:`metrics.batch.core_metrics_batch`)."""
    return _core_from_arrays(
        np.ascontiguousarray(curve.equity_mtm),
        np.ascontiguousarray(curve.in_position),
        year_calendar(curve.ts),
        curve.initial_capital,
    )


def yearly_drawdowns(curve: EquityCurve) -> YearlyDrawdowns:
    """Per calendar year: max drawdown from year start (a) and against all-time peak (b)."""
    cal = year_calendar(curve.ts)
    dd_ys, dd_pk = _kernels.yearly_drawdowns(
        np.ascontiguousarray(curve.equity_mtm),
        cal.year_id,
        cal.labels.size,
        curve.initial_capital,
    )
    return YearlyDrawdowns(
        years=cal.labels,
        weights=cal.weights,
        dd_ystart_usd=np.asarray(dd_ys, dtype=np.float64),
        dd_peak_usd=np.asarray(dd_pk, dtype=np.float64),
    )


def avg_annual_dd_peak_usd(curve: EquityCurve) -> float:
    ydd = yearly_drawdowns(curve)
    return float(_kernels.weighted_mean(ydd.dd_peak_usd, ydd.weights))


def profit_factor(pnl_net: FloatArray) -> float:
    wins = float(pnl_net[pnl_net > 0].sum())
    losses = float(-pnl_net[pnl_net < 0].sum())
    if losses == 0.0:
        return math.inf if wins > 0.0 else math.nan
    return wins / losses


def _mean_or_nan(values: FloatArray) -> float:
    return float(np.mean(values)) if values.size else math.nan


def trade_stats(trades: TradeLog, notional: float) -> dict[str, float]:
    n = len(trades)
    pnl = trades.pnl_net
    return {
        "n_trades": float(n),
        "profit_factor": profit_factor(pnl) if n else math.nan,
        "win_rate": float(np.mean(pnl > 0)) if n else math.nan,
        "avg_bars_held": _mean_or_nan(trades.bars_held.astype(np.float64)),
        "expectancy_usd": _mean_or_nan(pnl),
        "expectancy_pct": _mean_or_nan(pnl / notional * 100.0),
        "expectancy_atr": _mean_or_nan(pnl / (trades.qty * trades.atr_at_entry)),
    }


class MetricsReport(BaseModel):
    """All standard, risk and distribution metrics of one run, plus flags."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # F-0.5.1
    years: float
    total_net_profit_usd: float
    avg_annual_profit_usd: float
    avg_annual_profit_pct: float
    avg_annual_dd_ystart_usd: float
    avg_annual_dd_ystart_pct: float
    avg_annual_dd_peak_usd: float
    avg_annual_dd_peak_pct: float
    profit_dd_ratio: float
    exposure: float
    return_per_exposure: float
    n_trades: int
    n_position_entries: int
    profit_factor: float
    win_rate: float
    avg_bars_held: float
    expectancy_usd: float
    expectancy_pct: float
    expectancy_atr: float
    # F-0.5.2
    sharpe: float
    sortino: float
    max_dd_pct: float
    ulcer_index: float
    max_underwater_bars: int
    max_underwater_days: float
    trade_return_skew: float
    trade_return_excess_kurtosis: float
    # flags
    inf_ratio: bool
    open_position_marked: bool
    cost_placeholder: bool

    def as_gate_dict(self) -> dict[str, float]:
        """Metric name -> value for the gate engine (flags as 0.0 / 1.0)."""
        return {name: float(value) for name, value in self.model_dump().items()}


def compute_metrics(
    result: RunResult,
    *,
    calendar: str,
    config: MetricsConfig | None = None,
) -> MetricsReport:
    """Compute the full :class:`MetricsReport` of a run.

    ``calendar`` selects the Sharpe/Sortino annualisation from ``config.periods_per_year``
    (e.g. ``us_equity`` or ``24x5``).
    """
    cfg = config if config is not None else MetricsConfig()
    periods = cfg.annualisation(calendar)
    curve, trades = result.equity, result.trades
    capital = curve.initial_capital
    cal = year_calendar(curve.ts)
    core = _core_from_arrays(
        np.ascontiguousarray(curve.equity_mtm),
        np.ascontiguousarray(curve.in_position),
        cal,
        capital,
    )
    dd_peak_usd = avg_annual_dd_peak_usd(curve)
    stats = trade_stats(trades, curve.notional)
    daily = risk.daily_returns(curve)
    uw_bars, uw_days = risk.longest_underwater(curve)
    skew, kurt = risk.trade_return_moments(trades.pnl_net, curve.notional)
    exposure = core.exposure
    return MetricsReport(
        years=cal.years,
        total_net_profit_usd=float(curve.equity_mtm[-1] - capital),
        avg_annual_profit_usd=core.avg_annual_profit_usd,
        avg_annual_profit_pct=core.avg_annual_profit_pct,
        avg_annual_dd_ystart_usd=core.avg_annual_dd_ystart_usd,
        avg_annual_dd_ystart_pct=core.avg_annual_dd_ystart_pct,
        avg_annual_dd_peak_usd=dd_peak_usd,
        avg_annual_dd_peak_pct=dd_peak_usd / capital * 100.0,
        profit_dd_ratio=core.profit_dd_ratio,
        exposure=exposure,
        return_per_exposure=(core.avg_annual_profit_pct / exposure if exposure > 0.0 else math.nan),
        n_trades=len(trades),
        n_position_entries=core.n_position_entries,
        profit_factor=stats["profit_factor"],
        win_rate=stats["win_rate"],
        avg_bars_held=stats["avg_bars_held"],
        expectancy_usd=stats["expectancy_usd"],
        expectancy_pct=stats["expectancy_pct"],
        expectancy_atr=stats["expectancy_atr"],
        sharpe=risk.sharpe(daily, periods),
        sortino=risk.sortino(daily, periods),
        max_dd_pct=risk.max_drawdown_pct(curve),
        ulcer_index=risk.ulcer_index(curve),
        max_underwater_bars=uw_bars,
        max_underwater_days=uw_days,
        trade_return_skew=skew,
        trade_return_excess_kurtosis=kurt,
        inf_ratio=math.isinf(core.profit_dd_ratio),
        open_position_marked=result.open_position_marked,
        cost_placeholder=result.meta.cost_status == "placeholder",
    )
