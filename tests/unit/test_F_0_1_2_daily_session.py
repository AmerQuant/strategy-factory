"""F-0.1.2 (T04i, D-033): daily-vs-RTH breach detection and classification."""

from __future__ import annotations

import datetime as dt

import polars as pl

from strategy_factory.data.daily_session import (
    EXTENDED_HOURS,
    INCOMPLETE_HOURLY_DAY,
    NO_RAW_HOURS,
    UNEXPLAINED,
    breaches,
    compared_days,
    covered_years,
    expected_bars,
    raw_extremes,
    rth_extremes,
    with_atr,
)

NY = "America/New_York"
DAY = dt.date(2024, 7, 2)


def _hourly(highs: list[float], lows: list[float], first_hour: int = 9) -> pl.DataFrame:
    """Canonical hourly bars on ``DAY``, starting at ``first_hour`` New York."""
    ts = [
        dt.datetime.combine(
            DAY, dt.time(first_hour + i), tzinfo=dt.timezone(dt.timedelta(hours=-4))
        ).astimezone(dt.UTC)
        for i in range(len(highs))
    ]
    return pl.DataFrame({"ts": ts, "high": highs, "low": lows}).with_columns(
        pl.col("ts").dt.replace_time_zone("UTC")
    )


def _raw(hours: list[int], highs: list[float], lows: list[float]) -> pl.DataFrame:
    """Raw hourly rows (RFC-3339 ``t``, ``h``, ``l``) at the given New-York hours."""
    ts = [
        dt.datetime.combine(DAY, dt.time(h), tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        .astimezone(dt.UTC)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
        for h in hours
    ]
    return pl.DataFrame({"t": ts, "h": highs, "l": lows})


def _daily(high: float, low: float, close: float) -> pl.DataFrame:
    ts = dt.datetime.combine(DAY, dt.time(0), tzinfo=dt.UTC)
    return pl.DataFrame({"ts": [ts], "high": [high], "low": [low], "close": [close]})


def test_F_0_1_2_no_breach_when_the_daily_range_is_inside_rth() -> None:
    rth = rth_extremes(_hourly([101.0, 102.0], [99.0, 98.0]), NY)
    raw = raw_extremes(_raw([9, 10], [101.0, 102.0], [99.0, 98.0]), NY)
    assert breaches(_daily(102.0, 98.0, 100.0), rth, raw, "TEST").height == 0


def test_F_0_1_2_breach_explained_by_a_pre_market_bar_is_extended_hours() -> None:
    """The adapter drops the 08:00 bar; the raw file still has it."""
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    raw = raw_extremes(_raw([8, 9], [105.0, 102.0], [98.0, 98.0]), NY)
    out = breaches(_daily(105.0, 98.0, 100.0), rth, raw, "TEST")
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["breach_class"] == EXTENDED_HOURS
    assert round(row["breach_high_bps"]) == 300  # 3.00 of a 100.00 close
    assert row["breach_low_bps"] <= 0


def test_F_0_1_2_breach_no_hourly_bar_reaches_is_unexplained() -> None:
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    raw = raw_extremes(_raw([8, 9, 17], [102.5, 102.0, 102.5], [97.9, 98.0, 98.0]), NY)
    out = breaches(_daily(110.0, 98.0, 100.0), rth, raw, "TEST")
    assert out.row(0, named=True)["breach_class"] == UNEXPLAINED


def test_F_0_1_2_low_breach_is_detected_and_classified_separately() -> None:
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    raw = raw_extremes(_raw([9, 18], [102.0, 99.0], [98.0, 95.0]), NY)
    out = breaches(_daily(102.0, 95.0, 100.0), rth, raw, "TEST").row(0, named=True)
    assert out["breach_class"] == EXTENDED_HOURS
    assert round(out["breach_low_bps"]) == 300
    assert out["breach_high_bps"] <= 0


def test_F_0_1_2_day_without_raw_hours_cannot_be_classified() -> None:
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    empty = raw_extremes(_raw([], [], []), NY)
    out = breaches(_daily(105.0, 98.0, 100.0), rth, empty, "TEST")
    assert out.row(0, named=True)["breach_class"] == NO_RAW_HOURS


def test_F_0_1_2_float_noise_is_not_a_breach() -> None:
    """A difference below the epsilon is a rounding artefact, not a price level."""
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    raw = raw_extremes(_raw([9], [102.0], [98.0]), NY)
    assert breaches(_daily(102.0 + 1e-9, 98.0, 100.0), rth, raw, "TEST").height == 0


def test_F_0_1_2_only_dates_in_both_timeframes_are_compared() -> None:
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    other = dt.datetime(2024, 7, 5, tzinfo=dt.UTC)
    daily = pl.concat(
        [
            _daily(102.0, 98.0, 100.0),
            pl.DataFrame({"ts": [other], "high": [9.0], "low": [1.0], "close": [5.0]}),
        ]
    )
    assert compared_days(daily, rth) == 1
    assert breaches(daily, rth, raw_extremes(_raw([9], [102.0], [98.0]), NY), "TEST").height == 0


def test_F_0_1_2_covered_years_reports_the_hourly_coverage() -> None:
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)
    assert covered_years(rth) == [2024]
    assert covered_years(rth.clear()) == []


def test_F_0_1_2_expected_bars_from_the_calendar() -> None:
    sessions = {DAY: ("09:30", "16:00"), dt.date(2024, 7, 3): ("09:30", "13:00")}
    got = dict(expected_bars(sessions, "09:00").iter_rows())
    assert got == {DAY: 7, dt.date(2024, 7, 3): 4}


def test_F_0_1_2_partial_hourly_day_is_not_evidence_of_anything() -> None:
    """A day the hourly download has only partly filled must not read as a bad print."""
    rth = rth_extremes(_hourly([102.0], [98.0]), NY)  # 1 bar where the calendar implies 7
    raw = raw_extremes(_raw([9], [102.0], [98.0]), NY)
    expected = expected_bars({DAY: ("09:30", "16:00")}, "09:00")
    out = breaches(_daily(110.0, 98.0, 100.0), rth, raw, "TEST", expected=expected)
    assert out.row(0, named=True)["breach_class"] == INCOMPLETE_HOURLY_DAY
    # without the calendar the same day is reported as unexplained
    assert (
        breaches(_daily(110.0, 98.0, 100.0), rth, raw, "TEST").row(0, named=True)["breach_class"]
        == UNEXPLAINED
    )


def test_F_0_1_2_complete_day_still_classifies_normally() -> None:
    rth = rth_extremes(_hourly([102.0] * 7, [98.0] * 7), NY)
    raw = raw_extremes(_raw([8, *range(9, 16)], [105.0, *([102.0] * 7)], [98.0] * 8), NY)
    expected = expected_bars({DAY: ("09:30", "16:00")}, "09:00")
    out = breaches(_daily(105.0, 98.0, 100.0), rth, raw, "TEST", expected=expected)
    assert out.row(0, named=True)["breach_class"] == EXTENDED_HOURS


def test_F_0_1_2_breach_is_also_reported_against_the_bar_atr() -> None:
    """The task asks for the breach as a fraction of the day's range, not only in bps."""
    days = 20
    ts = [
        dt.datetime.combine(DAY, dt.time(0), tzinfo=dt.UTC) - dt.timedelta(days=days - 1 - i)
        for i in range(days)
    ]
    daily = with_atr(
        pl.DataFrame(
            {
                "ts": ts,
                "high": [101.0] * days,
                "low": [99.0] * days,
                "close": [100.0] * days,
            }
        )
    )
    assert daily["atr"][-1] == 2.0  # high - low on every bar

    rth = rth_extremes(_hourly([100.5] * 7, [99.5] * 7), NY)
    raw = raw_extremes(_raw(list(range(9, 16)), [100.5] * 7, [99.5] * 7), NY)
    out = breaches(daily, rth, raw, "TEST")  # only DAY exists on both sides
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["high_side"] is True and row["low_side"] is True
    assert round(row["breach_atr_frac"], 3) == round((101.0 - 100.5) / 2.0, 3)
