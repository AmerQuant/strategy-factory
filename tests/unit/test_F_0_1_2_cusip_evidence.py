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
    NONE,
    SAME_CUSIP,
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


def test_F_0_1_2_D_712_without_rule_1_ctra_would_have_read_same_cusip() -> None:
    """The dangerous direction D-712 guards against: drop the rename-into row and the re-keyed
    dividends are no longer recognised -- the break reads as one security."""
    without_into = [e for e in _ctra() if e.role != "into"]
    ev = classify(without_into, dt.date(2021, 10, 4), W)
    assert ev.relation == SAME_CUSIP


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
