"""F-0.1.2 (T04l, D-709, D-712): the CUSIP on each side of a break.

The two re-keying rules of D-712 with its worked example (``CTRA``), the issuer relation, and that
absence is never evidence.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from strategy_factory.data.cusip_evidence import (
    AFTER_ONLY,
    BEFORE_ONLY,
    BOTH,
    DIFFERENT_ISSUER,
    MIXED,
    NONE,
    SAME_ISSUER,
    Event,
    classify,
    load_events,
)

W = 7  # relisting.rename_window_days


def _ctra() -> list[Event]:
    """D-712's worked example, as the feed files it."""
    return [
        Event("name_changes", "away", "020764106", "2021-02-04"),  # Contura/Alpha leaves CTRA
        Event("cash_dividends", "id", "127097103", "2021-05-27"),  # Cabot (then COG), re-keyed
        Event("cash_dividends", "id", "127097103", "2021-08-26"),  # Cabot (then COG), re-keyed
        Event("name_changes", "into", "127097103", "2021-10-04"),  # COG -> CTRA
        Event("cash_dividends", "id", "127097103", "2021-10-22"),
    ]


def test_F_0_1_2_D_712_ctra_reads_a_different_issuer_not_a_clean_series() -> None:
    ev = classify(_ctra(), dt.date(2021, 10, 4), W)
    assert ev.coverage == BOTH and ev.relation == DIFFERENT_ISSUER
    assert ev.before == ("020764106",) and ev.after == ("127097103",)
    assert ev.dropped_rekeyed == 2


def test_F_0_1_2_D_712_without_rule_1_ctra_is_never_read_as_one_security() -> None:
    """The dangerous direction D-712 guards against: drop the rename-into row and the re-keyed
    dividends are no longer recognised. Before the mixed-issuer rule this read ``same_cusip``; now
    the before side holds two issuers and the break reads ``mixed`` -- unsettled, never clean."""
    without_into = [e for e in _ctra() if e.role != "into"]
    ev = classify(without_into, dt.date(2021, 10, 4), W)
    assert ev.relation == MIXED


def test_F_0_1_2_D_712_the_arriving_holder_counts_after_within_the_window() -> None:
    events = [
        Event("name_changes", "away", "111111111", "2020-01-10"),
        Event("stock_mergers", "id", "222222222", "2021-09-30"),  # acquirer row, days before
    ]
    ev = classify(events, dt.date(2021, 10, 4), W)
    assert ev.after == ("222222222",) and ev.relation == DIFFERENT_ISSUER
    far = [events[0], Event("stock_mergers", "id", "222222222", "2021-06-01")]
    assert classify(far, dt.date(2021, 10, 4), W).coverage == BEFORE_ONLY


def test_F_0_1_2_D_709_same_issuer_is_a_new_cusip_of_the_same_issuer() -> None:
    events = [
        Event("reverse_splits", "id_before", "00901B105", "2025-06-17"),
        Event("reverse_splits", "id", "00901B303", "2025-06-17"),
        Event("cash_dividends", "id", "00901B303", "2025-09-01"),
    ]
    ev = classify(events, dt.date(2025, 6, 17), W)
    assert ev.relation == SAME_ISSUER


def test_F_0_1_2_D_712_absence_is_never_evidence() -> None:
    assert classify([], dt.date(2017, 10, 20), W).coverage == NONE
    only_after = [Event("cash_dividends", "id", "G1234X100", "2021-01-05")]
    assert classify(only_after, dt.date(2020, 9, 16), W).coverage == AFTER_ONLY


def test_F_0_1_2_D_709_a_cessation_before_the_break_is_recorded_not_decisive() -> None:
    events = [Event("cash_mergers", "ceased", "729251108", "2016-02-22")]
    ev = classify(events, dt.date(2025, 8, 1), W)
    assert ev.coverage == BEFORE_ONLY and ev.ceased_before == ("cash_mergers",)


def test_F_0_1_2_D_710_rows_without_a_cusip_are_not_evidence(tmp_path: Path) -> None:
    folder = tmp_path
    (folder / "cash_dividends_20260921.v2.json").write_text(
        json.dumps(
            [
                {"symbol": "AAA", "cusip": "", "process_date": "2017-01-02"},
                {"symbol": "AAA", "cusip": "123456789", "process_date": "2022-01-03"},
            ]
        ),
        encoding="utf-8",
    )
    (folder / "cash_dividends_20260921.json").write_text("[]", encoding="utf-8")  # truncated v1
    events, no_cusip = load_events(folder)
    assert events["AAA"] == [Event("cash_dividends", "id", "123456789", "2022-01-03")]
    assert no_cusip == {"cash_dividends": 1}


def test_F_0_1_2_D_712_a_cessation_on_the_resumption_day_is_the_old_holder_leaving() -> None:
    """GORO: the merger that ends the old CUSIP is dated on the day the new one resumes."""
    events = [
        Event("stock_mergers", "ceased", "38068T105", "2026-07-20"),
        Event("name_changes", "into", "38141A602", "2026-07-20"),
    ]
    ev = classify(events, dt.date(2026, 7, 20), W)
    assert ev.before == ("38068T105",) and ev.after == ("38141A602",)
    assert ev.relation == DIFFERENT_ISSUER and ev.ceased_before == ("stock_mergers",)


def test_F_0_1_2_D_709_mixed_issuers_are_a_disagreement_not_the_same_company() -> None:
    """QH: the after side holds the old issuer's CUSIP and a different issuer's."""
    events = [
        Event("reverse_splits", "id_before", "74841Q100", "2022-08-12"),
        Event("stock_mergers", "id", "74841Q407", "2026-06-01"),
        Event("stock_mergers", "id", "G73264114", "2026-06-02"),
    ]
    ev = classify(events, dt.date(2026, 5, 29), W)
    assert ev.relation == MIXED


def test_F_0_1_2_D_712_rule_1_spares_the_arriving_holder_inside_the_window() -> None:
    """A reverse split days before the rename into the ticker is the arriving holder's own."""
    events = [
        Event("name_changes", "away", "11111A101", "2020-01-02"),
        Event("reverse_splits", "id", "22222B202", "2026-09-02"),
        Event("name_changes", "into", "22222B202", "2026-09-07"),
    ]
    ev = classify(events, dt.date(2026, 9, 14), W)
    assert ev.dropped_rekeyed == 0 and "reverse_splits" in ev.types_after


def test_F_0_1_2_D_712_the_arriving_window_never_reaches_before_the_break() -> None:
    """A break shorter than the window: the old holder's last row stays on the before side."""
    events = [
        Event("cash_dividends", "id", "33333C103", "2021-10-01"),
        Event("cash_dividends", "id", "44444D104", "2021-10-10"),
    ]
    resumes, start = dt.date(2021, 10, 4), dt.date(2021, 10, 2)
    assert classify(events, resumes, W).coverage == "after_only"  # without the break start
    ev = classify(events, resumes, W, break_start=start)
    assert ev.before == ("33333C103",) and ev.relation == DIFFERENT_ISSUER
