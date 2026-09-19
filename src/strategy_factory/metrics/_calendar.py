"""Calendar bookkeeping shared by the single-run and batch metric paths.

Calendar boundaries follow the bar ``ts`` date in UTC. The covered span is
``ts[-1] - ts[0]`` and ``years = span / 365.25 days``. A calendar year's weight is the part of
the span that falls inside it, also in units of 365.25 days, so the weights of all years sum
to ``years`` (partial years count fractionally).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

DAYS_PER_YEAR = 365.25  # the team's fractional-year convention (not a tunable threshold)
NS_PER_DAY = 86_400 * 1_000_000_000


@dataclass(frozen=True)
class YearCalendar:
    years: float  # covered span in years (365.25-day units)
    labels: NDArray[np.int64]  # calendar year of each group, e.g. 2021
    year_id: NDArray[np.int64]  # per bar: index into labels
    weights: NDArray[np.float64]  # per year: covered fraction (365.25-day units)


def as_ns(ts: NDArray[np.datetime64]) -> NDArray[np.int64]:
    return np.asarray(ts, dtype="datetime64[ns]").view(np.int64)


def span_days(ts: NDArray[np.datetime64]) -> float:
    ns = as_ns(ts)
    return float(ns[-1] - ns[0]) / NS_PER_DAY


def year_calendar(ts: NDArray[np.datetime64]) -> YearCalendar:
    ts_ns = np.asarray(ts, dtype="datetime64[ns]")
    if ts_ns.size < 2:
        raise ValueError("need at least 2 bars to annualise")
    years = span_days(ts_ns) / DAYS_PER_YEAR
    if years <= 0:
        raise ValueError("ts span must be positive")
    bar_year = ts_ns.astype("datetime64[Y]").astype(np.int64) + 1970
    labels, year_id = np.unique(bar_year, return_inverse=True)
    first, last = as_ns(ts_ns)[0], as_ns(ts_ns)[-1]
    starts = as_ns(np.array([f"{y}-01-01" for y in labels], dtype="datetime64[ns]"))
    ends = as_ns(np.array([f"{y + 1}-01-01" for y in labels], dtype="datetime64[ns]"))
    overlap_ns = np.minimum(ends, last) - np.maximum(starts, first)
    weights = np.maximum(overlap_ns, 0).astype(np.float64) / NS_PER_DAY / DAYS_PER_YEAR
    return YearCalendar(
        years=years,
        labels=labels.astype(np.int64),
        year_id=year_id.astype(np.int64),
        weights=weights,
    )


def month_keys(ts: NDArray[np.datetime64]) -> NDArray[np.int64]:
    """Months since 1970-01 of each timestamp (UTC)."""
    return np.asarray(ts, dtype="datetime64[ns]").astype("datetime64[M]").astype(np.int64)


def day_keys(ts: NDArray[np.datetime64]) -> NDArray[np.int64]:
    """Days since 1970-01-01 of each timestamp (UTC date)."""
    return np.asarray(ts, dtype="datetime64[ns]").astype("datetime64[D]").astype(np.int64)
