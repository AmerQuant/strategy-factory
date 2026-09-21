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


def test_F_0_1_9_D_399_both_series_making_the_same_move_is_a_halt() -> None:
    """The price really did move across the gap, and both feeds agree it did."""
    cross = _cross([(BEFORE, 50.0), (AFTER, 10.0)])
    got = settle_boundary("HALTED", BEFORE, AFTER, 0.2, cross, TOL, JUMP)
    assert got.verdict == HALT and not got.may_trim


def test_F_0_1_9_D_399_a_crosscheck_that_breaks_differently_is_a_re_use() -> None:
    """The all-adjusted series breaks too, and by a different factor: a different company."""
    cross = _cross([(BEFORE, 50.0), (AFTER, 150.0)])
    got = settle_boundary("REUSED", BEFORE, AFTER, 0.2, cross, TOL, JUMP)
    assert got.verdict == RE_USE and got.may_trim


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


def test_F_0_1_9_D_399_only_re_use_may_trim() -> None:
    cross_by_verdict = {
        UNADJUSTED_SPLIT: _cross([(BEFORE, 50.0), (AFTER, 50.5)]),
        HALT: _cross([(BEFORE, 50.0), (AFTER, 10.0)]),
        RE_USE: _cross([(BEFORE, 50.0), (AFTER, 150.0)]),
    }
    for expected, cross in cross_by_verdict.items():
        ratio = 10.0 if expected is UNADJUSTED_SPLIT else 0.2
        got = settle_boundary("X", BEFORE, AFTER, ratio, cross, TOL, JUMP)
        assert got.verdict == expected
        assert got.may_trim is (expected == RE_USE)
