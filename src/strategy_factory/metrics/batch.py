"""Core metrics for a whole parameter grid in one Numba call (stages 2/3).

Each column of ``equity_matrix`` / ``in_position_matrix`` is one configuration run on the
same bars ``ts``. Every column goes through the same kernel as the single-run
:func:`strategy_factory.metrics.standard.core_metrics`, so results are bit-identical.

Returned keys (arrays of length ``n_configs``): ``avg_annual_profit_usd``,
``avg_annual_profit_pct``, ``avg_annual_dd_ystart_usd``, ``avg_annual_dd_ystart_pct``,
``profit_dd_ratio``, ``exposure``, ``n_trades``. ``n_trades`` here is the number of position
entries (flat -> in-position transitions of ``in_position``), i.e.
``MetricsReport.n_position_entries``: a position open at the end counts, and an exit plus
re-entry at the same open counts once.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from strategy_factory.metrics import _kernels
from strategy_factory.metrics._calendar import year_calendar


def core_metrics_batch(
    equity_matrix: NDArray[np.float64],
    in_position_matrix: NDArray[np.bool_],
    ts: NDArray[np.datetime64],
    initial_capital: float,
) -> dict[str, NDArray[Any]]:
    equity = np.asfortranarray(equity_matrix, dtype=np.float64)
    in_pos = np.asfortranarray(in_position_matrix, dtype=np.bool_)
    if equity.ndim != 2 or equity.shape != in_pos.shape:
        raise ValueError("equity_matrix and in_position_matrix must have the same 2-D shape")
    if equity.shape[0] != np.asarray(ts).shape[0]:
        raise ValueError("ts length must equal the number of bars (rows)")
    if not np.all(np.isfinite(equity)):
        raise ValueError("equity_matrix contains non-finite values")
    cal = year_calendar(ts)
    out = _kernels.core_batch(
        equity, in_pos, cal.year_id, cal.weights, float(initial_capital), cal.years
    )
    names = (
        "avg_annual_profit_usd",
        "avg_annual_profit_pct",
        "avg_annual_dd_ystart_usd",
        "avg_annual_dd_ystart_pct",
        "profit_dd_ratio",
        "exposure",
        "n_trades",
    )
    return dict(zip(names, out, strict=True))
