"""F-0.1.2 (T04i): frozen stretches, re-used tickers and their boundary (D-383, D-398)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from strategy_factory.data.config import AlpacaConfig, RelistingConfig, load_alpaca_config
from strategy_factory.data.relisting import (
    CLEAN,
    DEFAULT_FROZEN_SESSIONS,
    DEFAULT_GAP_DAYS,
    EXCLUDE,
    FROZEN_ONLY,
    TRIM,
    analyse_series,
    frozen_stretches,
    looks_like_reverse_split,
    relisting_candidates,
)

START = dt.date(2016, 1, 4)
JUMP = 0.40  # configs/data/alpaca.yaml split_check.jump_threshold


def _series(
    spec: list[tuple[int, float]], gap_after: dict[int, int] | None = None
) -> tuple[list[dt.date], list[float], list[float], list[float]]:
    """``spec`` = [(n_bars, close), ...]; ``gap_after`` inserts calendar days after a segment.

    Every bar gets a real high and low, so nothing is frozen by accident.
    """
    dates: list[dt.date] = []
    closes: list[float] = []
    day = START
    for seg, (n, close) in enumerate(spec):
        for k in range(n):
            dates.append(day)
            closes.append(close + k * 1e-4)
            day += dt.timedelta(days=1)
        day += dt.timedelta(days=(gap_after or {}).get(seg, 0))
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    return dates, highs, lows, closes


def _padded(
    before: float, frozen: float, after: float, n: int = 749, lead: int = 300, tail: int = 300
) -> tuple[list[dt.date], list[float], list[float], list[float]]:
    """A real stretch, ``n`` padded bars (``high == low == close``), then a real stretch."""
    dates: list[dt.date] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    day = START
    for count, close, pad in ((lead, before, False), (n, frozen, True), (tail, after, False)):
        for _ in range(count):
            dates.append(day)
            closes.append(close)
            highs.append(close if pad else close * 1.01)
            lows.append(close if pad else close * 0.99)
            day += dt.timedelta(days=1)
    return dates, highs, lows, closes


# --- the two fingerprints -------------------------------------------------------------------


def test_F_0_1_2_trading_gap_with_a_level_break_is_a_candidate() -> None:
    dates, highs, lows, closes = _series([(300, 200.0), (300, 40.0)], gap_after={0: 1100})
    got = relisting_candidates("FBLIKE", dates, highs, lows, closes, JUMP)
    assert len(got) == 1
    assert got[0]["reason"] == "trading_gap"
    assert got[0]["gap_days"] > 1000
    assert got[0]["ratio"] < 0.4


def test_F_0_1_2_a_long_gap_without_a_level_break_is_not_a_candidate() -> None:
    """A trading halt that resumes at the same price is not a re-used ticker."""
    dates, highs, lows, closes = _series([(300, 100.0), (300, 101.0)], gap_after={0: 1100})
    assert relisting_candidates("HALTED", dates, highs, lows, closes, JUMP) == []


def test_F_0_1_2_a_known_split_inside_the_gap_explains_the_break() -> None:
    dates, highs, lows, closes = _series([(300, 200.0), (300, 20.0)], gap_after={0: 1100})
    split = dates[300] - dt.timedelta(days=10)
    assert relisting_candidates("SPLIT", dates, highs, lows, closes, JUMP, frozenset({split})) == []
    assert relisting_candidates("SPLIT", dates, highs, lows, closes, JUMP, frozenset()) != []


def test_F_0_1_2_a_frozen_stretch_with_a_level_break_is_a_stale_run() -> None:
    """`PX`: Praxair, 749 bars at exactly 164.50, then RPC Inc. -- no gap at all."""
    dates, highs, lows, closes = _padded(165.49, 164.50, 12.08)
    got = relisting_candidates("PX", dates, highs, lows, closes, JUMP)
    assert [r["reason"] for r in got] == ["stale_run"]
    assert got[0]["stale_bars"] == 749


def test_F_0_1_2_a_frozen_stretch_without_a_level_break_is_padding_only() -> None:
    dates, highs, lows, closes = _padded(3.00, 3.00, 3.10, n=315)
    got = relisting_candidates("FI", dates, highs, lows, closes, JUMP)
    assert [r["reason"] for r in got] == ["padding_only"]


def test_F_0_1_2_a_frozen_stretch_at_the_start_is_pre_listing_padding() -> None:
    dates, highs, lows, closes = _padded(1.0, 1.0, 30.0, n=570, lead=0)
    got = relisting_candidates("GRAB", dates, highs, lows, closes, JUMP)
    assert [r["reason"] for r in got] == ["pre_listing_padding"]


# --- D-398 (1): zero true range, and the configured threshold -------------------------------


def test_F_0_1_2_D_398_a_frozen_stretch_needs_zero_true_range() -> None:
    """Identical closes with a real high and low are a quiet market, not feed padding."""
    dates, highs, lows, closes = _padded(165.49, 164.50, 12.08)
    highs = [c * 1.01 for c in closes]  # same closes, but every bar has a range
    lows = [c * 0.99 for c in closes]
    assert frozen_stretches(highs, lows, closes) == []
    assert [r["reason"] for r in relisting_candidates("PX", dates, highs, lows, closes, JUMP)] == []


def test_F_0_1_2_D_398_the_frozen_threshold_is_ten_sessions_by_default() -> None:
    dates, highs, lows, closes = _padded(100.0, 100.0, 100.0, n=10, lead=20, tail=20)
    assert frozen_stretches(highs, lows, closes) == [(20, 29)]
    assert frozen_stretches(highs, lows, closes, min_sessions=11) == []
    assert analyse_series("PAD", dates, highs, lows, closes, JUMP).verdict == FROZEN_ONLY


def test_F_0_1_2_D_398_two_frozen_stretches_at_different_levels_stay_apart() -> None:
    closes = [50.0] * 5 + [10.0] * 12 + [20.0] * 15 + [50.0] * 5
    highs = [c if 5 <= i < 32 else c * 1.01 for i, c in enumerate(closes)]
    lows = [c if 5 <= i < 32 else c * 0.99 for i, c in enumerate(closes)]
    assert frozen_stretches(highs, lows, closes) == [(5, 16), (17, 31)]


# --- D-398 (2)/(3)/(4): the boundary ---------------------------------------------------------


def test_F_0_1_2_D_398_a_re_used_ticker_is_trimmed_to_its_boundary_not_excluded() -> None:
    dates, highs, lows, closes = _padded(165.49, 164.50, 12.08)
    got = analyse_series("PX", dates, highs, lows, closes, JUMP)
    assert got.verdict == TRIM
    assert got.boundary_reason == "stale_run"
    assert got.boundary_date == dates[300 + 749].isoformat()
    assert got.dropped_bars == 300 + 749
    assert (got.dropped_from, got.dropped_to) == (dates[0].isoformat(), dates[1048].isoformat())
    assert got.kept_bars == 300
    assert got.kept_from == dates[1049].isoformat()


def test_F_0_1_2_D_398_a_trading_gap_sets_the_boundary_too() -> None:
    dates, highs, lows, closes = _series([(300, 200.0), (300, 40.0)], gap_after={0: 1100})
    got = analyse_series("FBLIKE", dates, highs, lows, closes, JUMP)
    assert got.verdict == TRIM
    assert got.boundary_reason == "trading_gap"
    assert got.boundary_date == dates[300].isoformat()
    assert got.dropped_bars == 300
    assert got.kept_bars == 300


def test_F_0_1_2_D_398_leading_padding_is_trimmed_and_the_symbol_stays() -> None:
    dates, highs, lows, closes = _padded(1.0, 1.0, 30.0, n=570, lead=0)
    got = analyse_series("GRAB", dates, highs, lows, closes, JUMP)
    assert got.verdict == TRIM
    assert got.boundary_reason == "leading_padding"
    assert got.boundary_date == dates[570].isoformat()
    assert got.dropped_bars == 570
    assert got.kept_bars == 300


def test_F_0_1_2_D_398_interior_padding_is_cut_without_moving_the_boundary() -> None:
    dates, highs, lows, closes = _padded(3.00, 3.00, 3.10, n=315)
    got = analyse_series("FI", dates, highs, lows, closes, JUMP)
    assert got.verdict == FROZEN_ONLY
    assert got.boundary_date == ""
    assert got.frozen_bars_cut == 315
    assert got.kept_bars == 600
    assert got.kept_from == dates[0].isoformat()


def test_F_0_1_2_D_398_a_series_that_is_all_padding_is_an_exclusion() -> None:
    """Nothing ever trades, so no boundary can be read off the series (D-398 (4))."""
    dates, highs, lows, closes = _padded(1.0, 1.0, 1.0, n=300, lead=0, tail=0)
    got = analyse_series("DEAD", dates, highs, lows, closes, JUMP)
    assert got.verdict == EXCLUDE
    assert got.boundary_date == ""
    assert got.dropped_bars == len(closes)


def test_F_0_1_2_D_398_a_break_followed_only_by_padding_is_an_exclusion() -> None:
    """The ticker was re-used and the new series never prints a real bar."""
    dates: list[dt.date] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    day = START
    for count, close, pad in ((300, 200.0, False), (300, 20.0, True)):
        for _ in range(count):
            dates.append(day)
            closes.append(close)
            highs.append(close if pad else close * 1.01)
            lows.append(close if pad else close * 0.99)
            day += dt.timedelta(days=1)
        day += dt.timedelta(days=1100)
    got = analyse_series("HALFDEAD", dates, highs, lows, closes, JUMP)
    assert got.verdict == EXCLUDE
    assert got.boundary_reason == "trading_gap"
    assert got.boundary_date == ""
    assert got.dropped_bars == len(closes)


def test_F_0_1_2_D_398_a_series_that_ends_in_padding_keeps_its_real_history() -> None:
    """A dead listing padded to the end is not a re-use: the pad is cut, the symbol stays."""
    dates, highs, lows, closes = _padded(165.49, 164.50, 0.0, n=749, tail=0)
    got = analyse_series("DELISTED", dates, highs, lows, closes, JUMP)
    assert got.verdict == FROZEN_ONLY
    assert [r["reason"] for r in got.rows] == ["padding_only"]
    assert got.frozen_bars_cut == 749
    assert got.kept_bars == 300


def test_F_0_1_2_D_398_a_clean_series_has_no_rows_and_no_boundary() -> None:
    dates, highs, lows, closes = _series([(600, 100.0)])
    got = analyse_series("CLEAN", dates, highs, lows, closes, JUMP)
    assert (got.verdict, got.rows, got.boundary_date) == (CLEAN, [], "")


def test_F_0_1_2_D_398_the_last_break_wins_when_a_ticker_was_re_used_twice() -> None:
    dates: list[dt.date] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    day = START
    for count, close, pad in (
        (100, 200.0, False),
        (40, 200.0, True),
        (100, 20.0, False),
        (40, 20.0, True),
        (100, 300.0, False),
    ):
        for _ in range(count):
            dates.append(day)
            closes.append(close)
            highs.append(close if pad else close * 1.01)
            lows.append(close if pad else close * 0.99)
            day += dt.timedelta(days=1)
    got = analyse_series("TWICE", dates, highs, lows, closes, JUMP)
    assert got.verdict == TRIM
    assert got.boundary_date == dates[280].isoformat()
    assert got.dropped_bars == 280
    assert got.kept_bars == 100
    assert got.frozen_stretches == 2


def test_F_0_1_2_D_398_the_per_symbol_row_carries_the_boundary() -> None:
    dates, highs, lows, closes = _padded(165.49, 164.50, 12.08)
    row = analyse_series("PX", dates, highs, lows, closes, JUMP).as_row()
    assert row["symbol"] == "PX"
    assert row["verdict"] == TRIM
    assert row["boundary_date"] == dates[1049].isoformat()
    assert row["dropped_bars"] == 1049
    assert row["kept_bars"] == 300


# --- rule 1: the thresholds live in config, not in code -------------------------------------


def test_F_0_1_2_D_398_the_thresholds_come_from_the_shipped_config() -> None:
    """`CLAUDE.md` rule 1: the numbers are in YAML, and the model's defaults are the same ones."""
    cfg = load_alpaca_config(Path("configs") / "data" / "alpaca.yaml")
    assert (cfg.relisting.frozen_min_sessions, cfg.relisting.gap_days) == (10, 200)
    assert RelistingConfig().frozen_min_sessions == DEFAULT_FROZEN_SESSIONS
    assert RelistingConfig().gap_days == DEFAULT_GAP_DAYS


def test_F_0_1_2_D_398_a_configured_threshold_reaches_the_detector() -> None:
    cfg = AlpacaConfig.model_validate({"relisting": {"frozen_min_sessions": 400}})
    _, highs, lows, closes = _padded(165.49, 164.50, 12.08, n=300)
    assert frozen_stretches(highs, lows, closes, cfg.relisting.frozen_min_sessions) == []


# --- P-74: the reverse-split flag on the evidence artefact ----------------------------------


def test_F_0_1_2_P_74_an_upward_round_multiple_is_a_reverse_split_suspect() -> None:
    assert looks_like_reverse_split(10.0)
    assert looks_like_reverse_split(150.2)  # SMRT 0.0739 -> 11.1
    assert looks_like_reverse_split(19.4)  # within 5 % of 20


def test_F_0_1_2_P_74_a_downward_or_unround_break_is_not() -> None:
    assert not looks_like_reverse_split(0.1)  # a forward split or a collapse
    assert not looks_like_reverse_split(1.0)
    assert not looks_like_reverse_split(37.0)  # no reverse split has this ratio
