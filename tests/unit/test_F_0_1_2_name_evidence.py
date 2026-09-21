"""F-0.1.2 (T04k, D-700): the company-name discriminator for a re-used ticker.

D-700 amends D-399: the price series cannot tell a re-use from a halt, so the evidence is the
**company name** in the Alpaca assets file, linked across the break by the `NAME_CHANGE` feed.
Exact identity only. One name, or a rename that does not agree with the boundary: keep everything.
"""

from __future__ import annotations

import datetime as dt

from strategy_factory.data.name_evidence import (
    AMBIGUOUS,
    DISAGREES,
    ONE_NAME,
    RE_USE,
    SAME_COMPANY,
    NameChange,
    settle_by_name,
)

BREAK = dt.date(2022, 6, 8)  # the last real bar before the break (FB: Meta's last day as FB)
BOUNDARY = dt.date(2025, 6, 26)  # the first bar of the new holder
WINDOW = 7

ASSETS = {
    "FB": "ProShares S&P 500 Dynamic Buffer ETF",
    "META": "Meta Platforms, Inc. Class A Common Stock",
    "AMR": "Alpha Metallurgical Resources, Inc.",
    "SAMEA": "Acme Corp",
    "SAMEB": "Acme Corp",
    "LOOKALIKE": "Acme Corp.",
}


def _chg(old: str, new: str, day: dt.date) -> NameChange:
    return NameChange(old_symbol=old, new_symbol=new, process_date=day)


def test_F_0_1_2_D_700_an_unrelated_company_across_the_break_is_a_re_use() -> None:
    """`FB`: Meta renamed away to `META` at the break; the ticker now belongs to a ProShares ETF."""
    got = settle_by_name(
        "FB", BREAK, BOUNDARY, ASSETS, [_chg("FB", "META", dt.date(2022, 6, 9))], WINDOW
    )
    assert got.verdict == RE_USE and got.may_trim
    assert "Meta Platforms" in got.evidence and "ProShares" in got.evidence


def test_F_0_1_2_D_700_the_same_company_under_both_names_is_not_a_re_use() -> None:
    got = settle_by_name(
        "SAMEA", BREAK, BOUNDARY, ASSETS, [_chg("SAMEA", "SAMEB", dt.date(2022, 6, 9))], WINDOW
    )
    assert got.verdict == SAME_COMPANY and not got.may_trim


def test_F_0_1_2_D_700_matching_is_exact_identity_not_similarity() -> None:
    """`Acme Corp` vs `Acme Corp.` is a different string, so the feed calls it a different name.

    That is the stated failure mode of exact identity (D-700 (4)): it errs towards *different*,
    so the review must say which trims rest on a near-identical pair.
    """
    got = settle_by_name(
        "SAMEA", BREAK, BOUNDARY, ASSETS, [_chg("SAMEA", "LOOKALIKE", dt.date(2022, 6, 9))], WINDOW
    )
    assert got.verdict == RE_USE
    assert got.near_identical  # flagged for the review, never silently merged


def test_F_0_1_2_D_700_a_ticker_with_only_one_name_keeps_its_history() -> None:
    """No rename away from the ticker: the file knows only today's holder (D-700 (2))."""
    got = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, [], WINDOW)
    assert got.verdict == ONE_NAME and not got.may_trim


def test_F_0_1_2_D_700_a_ticker_missing_from_the_assets_file_has_one_name_at_most() -> None:
    got = settle_by_name(
        "CTRA", BREAK, BOUNDARY, ASSETS, [_chg("CTRA", "AMR", dt.date(2022, 6, 9))], WINDOW
    )
    assert got.verdict == ONE_NAME and not got.may_trim
    assert "CTRA" in got.evidence


def test_F_0_1_2_D_700_a_rename_that_does_not_agree_with_the_boundary_keeps_the_history() -> None:
    """`PX`: the feed renames PX -> RPC in 2026, years after the 2021 boundary (D-700 (2))."""
    got = settle_by_name(
        "FB", BREAK, BOUNDARY, ASSETS, [_chg("FB", "META", dt.date(2026, 2, 11))], WINDOW
    )
    assert got.verdict == DISAGREES and not got.may_trim


def test_F_0_1_2_D_700_the_window_opens_a_few_days_before_the_break() -> None:
    """`CTRA`: Contura renamed away one day before the first padded bar."""
    early = BREAK - dt.timedelta(days=WINDOW)
    got = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, [_chg("FB", "META", early)], WINDOW)
    assert got.verdict == RE_USE
    too_early = BREAK - dt.timedelta(days=WINDOW + 1)
    got = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, [_chg("FB", "META", too_early)], WINDOW)
    assert got.verdict == DISAGREES


def test_F_0_1_2_D_700_two_renames_away_inside_the_window_are_ambiguous() -> None:
    changes = [_chg("FB", "META", dt.date(2022, 6, 9)), _chg("FB", "AMR", dt.date(2022, 7, 1))]
    got = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, changes, WINDOW)
    assert got.verdict == AMBIGUOUS and not got.may_trim


def test_F_0_1_2_D_700_a_rename_into_the_ticker_is_recorded_but_does_not_decide() -> None:
    """`COG -> CTRA` says who arrived, not who left; only a rename *away* gives the old name."""
    changes = [_chg("COG", "FB", BOUNDARY), _chg("FB", "META", dt.date(2022, 6, 9))]
    got = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, changes, WINDOW)
    assert got.verdict == RE_USE
    assert "arrived from COG" in got.evidence
    alone = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, [_chg("COG", "FB", BOUNDARY)], WINDOW)
    assert alone.verdict == ONE_NAME


def test_F_0_1_2_D_700_a_destination_renamed_again_is_not_evidence() -> None:
    """`PTN`: Palatin went PTN -> PTNT and came back PTNT -> PTN; an ETF then took PTNT.

    Comparing PTN's name with PTNT's *current* name calls Palatin a re-use of itself. The
    destination changed hands after the rename, so its name no longer identifies who left.
    """
    assets = {
        "PTN": "Palatin Technologies, Inc. Common Stock",
        "PTNT": "Corgi IP Licensing & Royalties ETF",
    }
    away = _chg("PTN", "PTNT", dt.date(2022, 6, 9))
    back = _chg("PTNT", "PTN", dt.date(2025, 11, 12))
    index = {"PTN": [away, back], "PTNT": [away, back]}
    got = settle_by_name("PTN", BREAK, BOUNDARY, assets, [away, back], WINDOW, index)
    assert got.verdict == AMBIGUOUS and not got.may_trim
    assert "renamed again" in got.evidence
    # without the index the same evidence would have trimmed -- which is the bug this prevents
    naive = settle_by_name("PTN", BREAK, BOUNDARY, assets, [away, back], WINDOW)
    assert naive.verdict == RE_USE


def test_F_0_1_2_D_700_a_destination_that_stayed_put_is_still_evidence() -> None:
    away = _chg("FB", "META", dt.date(2022, 6, 9))
    index = {"FB": [away], "META": [away]}
    got = settle_by_name("FB", BREAK, BOUNDARY, ASSETS, [away], WINDOW, index)
    assert got.verdict == RE_USE
