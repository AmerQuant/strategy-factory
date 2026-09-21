"""F-0.1.9 (T04k, D-399): settling an ambiguous re-use signature against MS-US-1D.

A trim is never applied on an ambiguous signature. The all-adjusted series is continuous across a
corporate action and discontinuous where the company actually changed — the test that settled AVGO.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from strategy_factory.data.crosscheck import (
    HALT,
    RE_USE,
    UNADJUSTED_SPLIT,
    UNSETTLED,
    settle_boundary,
)

BEFORE = dt.date(2021, 5, 18)
AFTER = dt.date(2021, 10, 21)
JUMP = 0.40
TOL = 0.02


def _cross(pairs: list[tuple[dt.date, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {"date": [p[0] for p in pairs], "close": [p[1] for p in pairs]},
        schema={"date": pl.Date(), "close": pl.Float64()},
    )


def test_F_0_1_9_D_399_a_continuous_crosscheck_is_an_unadjusted_split() -> None:
    """The ingested series multiplies by 10; the all-adjusted one does not move."""
    cross = _cross([(BEFORE, 50.0), (AFTER, 50.5)])
    got = settle_boundary("RSPLIT", BEFORE, AFTER, 10.0, cross, TOL, JUMP)
    assert got.verdict == UNADJUSTED_SPLIT and not got.may_trim
    assert "all-adjusted 1.0100" in got.evidence


def test_F_0_1_9_T04k_a_shared_break_does_not_settle_a_re_use() -> None:
    """Measured on `PX`: MS-US-1D is ticker-keyed too, so it splices a re-used ticker identically.

    A break in both feeds proves the break is in the data, never what caused it. D-399 (4) then
    applies: keep the whole history and list the symbol.
    """
    cross = _cross([(BEFORE, 50.0), (AFTER, 10.0)])
    got = settle_boundary("SHARED", BEFORE, AFTER, 0.2, cross, TOL, JUMP)
    assert got.verdict == UNSETTLED and not got.may_trim
    assert "both feeds break alike" in got.evidence
    assert "cannot separate a re-use from a halt" in got.evidence


def test_F_0_1_9_T04k_feeds_breaking_by_different_factors_are_unsettled_too() -> None:
    cross = _cross([(BEFORE, 50.0), (AFTER, 150.0)])
    got = settle_boundary("DIFFERENT", BEFORE, AFTER, 0.2, cross, TOL, JUMP)
    assert got.verdict == UNSETTLED and not got.may_trim
    assert "different factors" in got.evidence


def test_F_0_1_9_D_399_no_crosscheck_file_is_unsettled_and_never_trims() -> None:
    got = settle_boundary("NOFILE", BEFORE, AFTER, 0.2, None, TOL, JUMP)
    assert got.verdict == UNSETTLED and not got.may_trim
    assert "no MS-US-1D cross-check file" in got.evidence


def test_F_0_1_9_D_399_no_overlapping_bar_is_unsettled() -> None:
    cross = _cross([(dt.date(2019, 1, 2), 50.0)])
    got = settle_boundary("NOOVERLAP", BEFORE, AFTER, 0.2, cross, TOL, JUMP)
    assert got.verdict == UNSETTLED and not got.may_trim


def test_F_0_1_9_D_399_a_nearby_bar_is_used_when_the_exact_date_is_missing() -> None:
    """The two feeds' calendars differ by a day here and there; a week's window absorbs that."""
    cross = _cross([(BEFORE - dt.timedelta(days=2), 50.0), (AFTER + dt.timedelta(days=1), 50.5)])
    got = settle_boundary("NEAR", BEFORE, AFTER, 10.0, cross, TOL, JUMP)
    assert got.verdict == UNADJUSTED_SPLIT


def test_F_0_1_9_D_399_this_test_never_returns_a_trimmable_verdict() -> None:
    """Only `re_use` may trim, and nothing this test can see proves a re-use (T04k finding)."""
    cases = [
        (10.0, _cross([(BEFORE, 50.0), (AFTER, 50.5)]), UNADJUSTED_SPLIT),
        (0.2, _cross([(BEFORE, 50.0), (AFTER, 10.0)]), UNSETTLED),
        (0.2, _cross([(BEFORE, 50.0), (AFTER, 150.0)]), UNSETTLED),
        (0.2, None, UNSETTLED),
    ]
    for ratio, cross, expected in cases:
        got = settle_boundary("X", BEFORE, AFTER, ratio, cross, TOL, JUMP)
        assert got.verdict == expected
        assert not got.may_trim
    # the constants D-399 names are still defined, for a future discriminator
    assert RE_USE and HALT


# --- the three shapes that produced false `unadjusted_split` verdicts on the real data -------


def test_F_0_1_9_T04k_a_crosscheck_with_no_bar_before_the_break_is_unsettled() -> None:
    """`AMLX`/`ATAI`: MS-US-1D starts at the IPO; the two sides must never collapse onto it."""
    ipo = dt.date(2022, 1, 7)
    cross = _cross([(ipo, 18.07), (ipo + dt.timedelta(days=3), 16.72)])
    got = settle_boundary("AMLX", dt.date(2021, 12, 31), ipo, 18.07 / 9.61, cross, TOL, JUMP)
    assert got.verdict == UNSETTLED
    assert "no bar near 2021-12-31" in got.evidence


def test_F_0_1_9_T04k_an_ingested_series_that_does_not_break_is_unsettled() -> None:
    """`NRGZ`: both feeds move 0.693, which is not a break at a 0.40 threshold."""
    cross = _cross([(BEFORE, 41.83), (AFTER, 28.99)])
    got = settle_boundary("NRGZ", BEFORE, AFTER, 28.99 / 41.83, cross, TOL, JUMP)
    assert got.verdict == UNSETTLED
    assert "does not break" in got.evidence


def test_F_0_1_9_T04k_the_bars_on_each_side_are_distinct_and_ordered() -> None:
    """A nearest-bar fallback may only look on its own side of the break."""
    only_after = _cross([(AFTER, 50.0), (AFTER + dt.timedelta(days=1), 50.2)])
    got = settle_boundary("X", BEFORE, AFTER, 10.0, only_after, TOL, JUMP)
    assert got.verdict == UNSETTLED


def test_F_0_1_9_T04k_one_bar_between_close_dates_cannot_serve_both_sides() -> None:
    """S2: with a short gap, one cross-check bar strictly between the two dates used to satisfy
    both windows and report a 1.0 ratio -- the AMLX failure in another shape."""
    before, after = dt.date(2021, 6, 10), dt.date(2021, 6, 18)
    cross = _cross([(dt.date(2021, 6, 14), 50.0)])  # between the two dates, nothing else
    got = settle_boundary("SHORTGAP", before, after, 10.0, cross, TOL, JUMP)
    assert got.verdict == UNSETTLED


def test_F_0_1_9_T04k_the_window_comes_from_the_caller() -> None:
    far = _cross([(BEFORE - dt.timedelta(days=10), 50.0), (AFTER, 50.5)])
    assert settle_boundary("W", BEFORE, AFTER, 10.0, far, TOL, JUMP, 7).verdict == UNSETTLED
    assert settle_boundary("W", BEFORE, AFTER, 10.0, far, TOL, JUMP, 14).verdict == UNADJUSTED_SPLIT
