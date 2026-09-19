"""Yearly and monthly tables (F-0.5.4).

Periods are UTC calendar years / months of the bar ``ts``; only periods that contain bars
appear. A period's profit is the change of mark-to-market equity from the end of the
previous period (initial capital before the first bar) to its last bar, so monthly profits
sum to the yearly profit and yearly profits sum to the total net profit (final equity -
initial capital). Trades are counted in the period of their ``exit_ts``; a position still
open at the end is not a trade. ``profitable_month_share`` = months with profit > 0 / months
with bars in that year.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from strategy_factory.metrics._calendar import month_keys
from strategy_factory.metrics.containers import RunResult
from strategy_factory.metrics.standard import yearly_drawdowns


class YearRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int
    covered_fraction: float
    profit_usd: float
    profit_pct: float
    dd_ystart_pct: float
    dd_peak_pct: float
    n_trades: int
    win_rate: float  # NaN when no trade closed in the year
    profitable_month_share: float


class MonthRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int
    month: int
    profit_usd: float
    profit_pct: float
    n_trades: int


def _period_profits(
    keys: NDArray[np.int64], equity: NDArray[np.float64], capital: float
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Unique period keys (ascending, ts is increasing) and their equity change."""
    last = np.flatnonzero(np.append(keys[1:] != keys[:-1], True))
    end_equity = equity[last]
    return keys[last], np.diff(end_equity, prepend=capital)


def monthly_table(result: RunResult) -> list[MonthRow]:
    curve, trades = result.equity, result.trades
    capital = curve.initial_capital
    months, profits = _period_profits(month_keys(curve.ts), curve.equity_mtm, capital)
    exit_months = month_keys(trades.exit_ts)
    rows = []
    for key, profit in zip(months.tolist(), profits.tolist(), strict=True):
        rows.append(
            MonthRow(
                year=1970 + key // 12,
                month=key % 12 + 1,
                profit_usd=profit,
                profit_pct=profit / capital * 100.0,
                n_trades=int(np.count_nonzero(exit_months == key)),
            )
        )
    return rows


def yearly_table(result: RunResult) -> list[YearRow]:
    curve, trades = result.equity, result.trades
    capital = curve.initial_capital
    year_keys = curve.ts.astype("datetime64[Y]").astype(np.int64) + 1970
    years, profits = _period_profits(year_keys, curve.equity_mtm, capital)
    ydd = yearly_drawdowns(curve)
    months = monthly_table(result)
    exit_years = trades.exit_ts.astype("datetime64[Y]").astype(np.int64) + 1970
    rows = []
    for i, (year, profit) in enumerate(zip(years.tolist(), profits.tolist(), strict=True)):
        in_year = exit_years == year
        n = int(np.count_nonzero(in_year))
        year_months = [m for m in months if m.year == year]
        rows.append(
            YearRow(
                year=year,
                covered_fraction=float(ydd.weights[i]),
                profit_usd=profit,
                profit_pct=profit / capital * 100.0,
                dd_ystart_pct=float(ydd.dd_ystart_usd[i]) / capital * 100.0,
                dd_peak_pct=float(ydd.dd_peak_usd[i]) / capital * 100.0,
                n_trades=n,
                win_rate=float(np.mean(trades.pnl_net[in_year] > 0)) if n else math.nan,
                profitable_month_share=(
                    sum(m.profit_usd > 0 for m in year_months) / len(year_months)
                ),
            )
        )
    return rows
