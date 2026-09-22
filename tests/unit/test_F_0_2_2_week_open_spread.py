"""F-0.2.2 / D-716: the bar that opens the trading week is its own spread key.

Measured on the Dukascopy 1H set (T04j): the Sunday open is 4.0-5.4x the median spread for FX,
while the hour-21 bucket that used to hold it averages it with weekday 21:00s (about 3x). Under
D-010 that bar is also the open of Monday's daily bar, so every daily next-open entry on a Monday
lands on it. The table keeps it separate, and a bar that opens the week is charged that value.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pytest

from strategy_factory.costs.arrays import (
    broker_scaled_table,
    build_cost_arrays,
    hourly_spread_table,
    resolve_from_data,
    week_open_mask,
)
from strategy_factory.costs.profile import CostProfile, SpreadHourly, profile_content_hash

EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
HOUR = dt.timedelta(hours=1)
SUNDAY = dt.datetime(2024, 1, 7, 21, tzinfo=dt.UTC)  # a Sunday, 21:00 UTC


def us(t: dt.datetime) -> int:
    return (t - EPOCH) // dt.timedelta(microseconds=1)


def fx_week(sunday_open: dt.datetime) -> list[dt.datetime]:
    """One 24x5 week: the Sunday open to Friday 20:00 UTC, every hour."""
    end = sunday_open + dt.timedelta(days=4, hours=23)
    out, t = [], sunday_open
    while t <= end:
        out.append(t)
        t += HOUR
    return out


def weeks(n: int) -> list[dt.datetime]:
    return [t for w in range(n) for t in fx_week(SUNDAY + dt.timedelta(weeks=w))]


def spreads(ts: list[dt.datetime], week_open: float, h21: float, base: float) -> np.ndarray:
    first = {t for i, t in enumerate(ts) if i == 0 or t - ts[i - 1] > HOUR}  # after a weekend
    return np.array(
        [week_open if t in first else h21 if t.hour == 21 else base for t in ts], dtype=float
    )


def arrays(ts: list[dt.datetime], **extra: Any) -> dict[str, np.ndarray]:
    n = len(ts)
    out = {
        "ts": np.array([us(t) for t in ts], dtype=np.int64),
        "open": np.full(n, 1.1),
        "close": np.full(n, 1.1),
    }
    out.update({k: np.asarray(v) for k, v in extra.items()})
    return out


def profile(spread: dict[str, Any]) -> CostProfile:
    return CostProfile.model_validate(
        {
            "name": "t",
            "status": "placeholder",
            "spread": spread,
            "commission": {"model": "none"},
            "swap": {"model": "none"},
        }
    )


def test_F_0_2_2_week_open_mask_marks_the_first_sunday_bar_of_each_week() -> None:
    ts = weeks(3)
    mask = week_open_mask(np.array([us(t) for t in ts], dtype=np.int64), "1H")
    opened = [t for t, m in zip(ts, mask, strict=True) if m]
    assert opened == [SUNDAY + dt.timedelta(weeks=w) for w in range(3)]
    # a later week that opens at 22:00 (the other DST half): that bar, not 21:00
    late = fx_week(SUNDAY + dt.timedelta(weeks=5, hours=1))
    lmask = week_open_mask(np.array([us(t) for t in late], dtype=np.int64), "1H")
    assert [t for t, m in zip(late, lmask, strict=True) if m] == [late[0]]
    assert late[0].hour == 22 and late[0].weekday() == 6


def test_F_0_2_2_week_open_mask_needs_a_sunday_or_the_monday_daily_bar() -> None:
    # US equities: the week starts Monday 14:30 UTC -- no week-open bar at 1H
    eq = [dt.datetime(2024, 1, 8, 14, 30, tzinfo=dt.UTC) + d * HOUR for d in range(7)]
    assert not week_open_mask(np.array([us(t) for t in eq], dtype=np.int64), "1H").any()
    # a series that starts mid-week has no week open in that first week
    mid = [dt.datetime(2024, 1, 10, tzinfo=dt.UTC) + d * HOUR for d in range(30)]
    assert not week_open_mask(np.array([us(t) for t in mid], dtype=np.int64), "1H").any()
    # 1D under D-010: the Monday bar carries the Sunday open; Tue-Fri do not
    days = [dt.datetime(2024, 1, 8, tzinfo=dt.UTC) + dt.timedelta(days=d) for d in range(12)]
    days = [d for d in days if d.weekday() < 5]
    dmask = week_open_mask(np.array([us(t) for t in days], dtype=np.int64), "1D")
    assert [d for d, m in zip(days, dmask, strict=True) if m] == [days[0], days[5]]
    assert all(d.weekday() == 0 for d, m in zip(days, dmask, strict=True) if m)


def test_F_0_2_2_the_week_open_is_not_averaged_into_hour_21() -> None:
    """The failure D-716 names: with the week open inside hour 21, that bucket would read ~3x
    where the Sunday open is 5x. Separate, weekday 21:00 reads 2x and the week open 5x."""
    ts = weeks(4)
    sp = spreads(ts, week_open=5.0, h21=2.0, base=1.0)
    t = hourly_spread_table(np.array([us(x) for x in ts], dtype=np.int64), sp, 1.0, None)
    assert t.full_spread[21] == pytest.approx(2.0)
    assert t.week_open == pytest.approx(5.0) and t.week_open_count == 4
    assert int(t.counts.sum()) + t.week_open_count == len(ts)


def test_F_0_2_2_broker_scaling_weights_the_week_open_by_its_bars() -> None:
    ts = weeks(4)
    sp = spreads(ts, week_open=5.0, h21=2.0, base=1.0)
    table, scale = broker_scaled_table(np.array([us(x) for x in ts], dtype=np.int64), sp, 3e-5)
    assert table.bar_weighted_mean() == pytest.approx(3e-5, rel=1e-12)
    assert table.week_open == pytest.approx(5.0 * scale)
    assert table.full_spread[21] == pytest.approx(2.0 * scale)


def test_F_0_2_2_a_bar_that_opens_the_week_is_charged_the_week_open() -> None:
    dev = weeks(4)
    sp = spreads(dev, week_open=5e-4, h21=2e-4, base=1e-4)
    resolved, _ = resolve_from_data(
        profile({"mode": "broker_scaled", "broker_spread": 1.2e-4}), arrays(dev, spread=sp)
    )
    assert isinstance(resolved.spread, SpreadHourly) and resolved.spread.week_open is not None
    assert "week open" in resolved.source_note
    wk, h21 = resolved.spread.week_open, resolved.spread.hourly[21]
    # 1H: the Sunday open vs a weekday 21:00
    later = fx_week(SUNDAY + dt.timedelta(weeks=10))
    a = build_cost_arrays(arrays(later), resolved, timeframe="1H")
    assert a.half_spread[0] == pytest.approx(wk / 2)
    tue21 = later.index(SUNDAY + dt.timedelta(weeks=10, days=2))
    assert a.half_spread[tue21] == pytest.approx(h21 / 2)
    # 1D (D-010): Monday's daily bar opens at the Sunday open; Tuesday at hour 0
    days = [dt.datetime(2024, 3, 18, tzinfo=dt.UTC) + dt.timedelta(days=d) for d in range(5)]
    d = build_cost_arrays(arrays(days), resolved, timeframe="1D")
    assert d.half_spread[0] == pytest.approx(wk / 2)
    assert d.half_spread[1] == pytest.approx(resolved.spread.hourly[0] / 2)


def test_F_0_2_2_no_sunday_hours_no_week_open_and_the_hash_is_unchanged() -> None:
    hourly = tuple(float(h) for h in range(24))
    plain = profile({"mode": "hourly_profile", "hourly": hourly})
    assert set(plain.spread.model_dump()) == {"mode", "hourly", "unit"}  # the pre-D-716 dump
    same = profile({"mode": "hourly_profile", "hourly": hourly, "week_open": None})
    assert profile_content_hash(plain) == profile_content_hash(same)
    keyed = profile({"mode": "hourly_profile", "hourly": hourly, "week_open": 30.0})
    assert profile_content_hash(keyed) != profile_content_hash(plain)
    assert keyed.spread.model_dump()["week_open"] == 30.0
    # equities-like development bars (no Sunday): the resolved table has no week-open key
    eq = [dt.datetime(2024, 1, 8, tzinfo=dt.UTC) + d * HOUR for d in range(24 * 5)]
    resolved, table = resolve_from_data(
        profile({"mode": "from_data"}), arrays(eq, spread=np.full(len(eq), 0.01))
    )
    assert table.week_open is None and "week_open" not in resolved.spread.model_dump()
    one = build_cost_arrays(arrays(eq[:24]), resolved, timeframe="1H")
    assert np.allclose(one.half_spread, 0.005)
