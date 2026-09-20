"""F-0.1.2 (T04i, D-383): re-used-ticker detection — trading gaps and frozen stretches."""

from __future__ import annotations

import datetime as dt

from strategy_factory.data.relisting import relisting_candidates

START = dt.date(2016, 1, 4)
JUMP = 0.40  # configs/data/alpaca.yaml split_check.jump_threshold


def _series(
    spec: list[tuple[int, float]], gap_after: dict[int, int] | None = None
) -> tuple[list[dt.date], list[float]]:
    """``spec`` = [(n_bars, close), ...]; ``gap_after`` inserts calendar days after a segment."""
    dates: list[dt.date] = []
    closes: list[float] = []
    day = START
    for seg, (n, close) in enumerate(spec):
        for k in range(n):
            dates.append(day)
            closes.append(close + k * 1e-4)  # move a little so nothing is stale by accident
            day += dt.timedelta(days=1)
        day += dt.timedelta(days=(gap_after or {}).get(seg, 0))
    return dates, closes


def test_F_0_1_2_trading_gap_with_a_level_break_is_a_candidate() -> None:
    dates, closes = _series([(300, 200.0), (300, 40.0)], gap_after={0: 1100})
    got = relisting_candidates("FBLIKE", dates, closes, JUMP)
    assert len(got) == 1
    row = got[0]
    assert row["reason"] == "trading_gap"
    assert row["gap_days"] > 1000
    assert row["ratio"] < 0.4


def test_F_0_1_2_a_long_gap_without_a_level_break_is_not_a_candidate() -> None:
    """A trading halt that resumes at the same price is not a re-used ticker."""
    dates, closes = _series([(300, 100.0), (300, 101.0)], gap_after={0: 1100})
    assert relisting_candidates("HALTED", dates, closes, JUMP) == []


def test_F_0_1_2_a_known_split_inside_the_gap_explains_the_break() -> None:
    dates, closes = _series([(300, 200.0), (300, 20.0)], gap_after={0: 1100})
    split = dates[300] - dt.timedelta(days=10)
    assert relisting_candidates("SPLIT", dates, closes, JUMP, frozenset({split})) == []
    assert relisting_candidates("SPLIT", dates, closes, JUMP, frozenset()) != []


def _frozen(before: float, frozen: float, after: float, n: int = 749) -> tuple[list, list]:
    dates: list[dt.date] = []
    closes: list[float] = []
    day = START
    for count, close in ((300, before), (n, frozen), (300, after)):
        for _ in range(count):
            dates.append(day)
            closes.append(close)
            day += dt.timedelta(days=1)
    return dates, closes


def test_F_0_1_2_a_frozen_stretch_without_a_level_break_is_not_a_d383_candidate() -> None:
    """D-383 is about a ticker re-used by another company; padding alone is not that."""
    dates, closes = _frozen(2.94, 2.94, 3.15, n=315)  # the FI shape
    got = relisting_candidates("FILIKE", dates, closes, JUMP)
    assert got, "the frozen stretch must still be reported"
    assert not [r for r in got if r["reason"] in ("stale_run", "trading_gap")]
    assert {r["reason"] for r in got} <= {"padding_only", "pre_listing_padding"}


def test_F_0_1_2_a_frozen_stretch_is_a_candidate_even_without_a_gap() -> None:
    """The PX shape: the feed pads the dead years with the last price, so there is no gap."""
    dates, closes = _frozen(165.0, 164.5, 12.0)  # the PX shape
    got = [
        r for r in relisting_candidates("PXLIKE", dates, closes, JUMP) if r["reason"] == "stale_run"
    ]
    frozen = [r for r in got if r["stale_bars"] == 749]
    assert frozen, [r["stale_bars"] for r in got]
    assert frozen[0]["close_after"] == 12.0


def test_F_0_1_2_a_short_flat_stretch_is_not_a_candidate() -> None:
    dates, _ = _series([(300, 100.0)])
    flat_dates = dates[:50]
    assert relisting_candidates("QUIET", flat_dates, [7.5] * 50, JUMP) == []


def test_F_0_1_2_the_stale_threshold_is_a_parameter() -> None:
    dates, closes = _frozen(100.0, 5.0, 100.0, n=100)
    assert relisting_candidates("F", dates, closes, JUMP, stale_days=400) == []
    assert relisting_candidates("F", dates, closes, JUMP, stale_days=60) != []


def test_F_0_1_2_a_clean_series_yields_nothing() -> None:
    dates, closes = _series([(2500, 100.0)])
    assert relisting_candidates("AAPL", dates, closes, JUMP) == []
