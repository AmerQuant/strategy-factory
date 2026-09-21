"""F-0.1.6 / F-0.1.8 (T04k): the two daily checks and the derived clean daily series.

D-396 (cap an unsupported extreme, clip a wick), D-398 (cut frozen stretches, trim to a re-use
boundary) and D-399 (never trim on an ambiguous signature), plus the supervisor's rule of
2026-09-21: **a short hourly day is not evidence**, so it neither corrects a bar nor clears one.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import polars as pl
import pytest
from fixtures.bars import make_meta

from strategy_factory.data.clean_daily import (
    ARM_BOUNDARY_TRIM,
    ARM_EXTREME_CAP,
    ARM_FROZEN_CUT,
    ARM_WICK_CLIP,
    clean_daily,
    wick_outliers,
)
from strategy_factory.data.config import DailyWickOutlierConfig, QualityConfig
from strategy_factory.data.daily_session import (
    EXTENDED_HOURS,
    INCOMPLETE_HOURLY_DAY,
    NO_RAW_HOURS,
    UNEXPLAINED,
)
from strategy_factory.data.quality import (
    check_daily_extreme_unsupported,
    check_daily_wick_outlier,
)
from strategy_factory.data.relisting import TRIM, SeriesVerdict
from strategy_factory.data.schema import SeriesMetadata

CFG = QualityConfig()
START = dt.datetime(2020, 1, 2, tzinfo=dt.UTC)
Bar = tuple[float, float, float, float]


def _daily(rows: list[Bar], start: dt.datetime = START) -> pl.DataFrame:
    """``rows`` = [(open, high, low, close), ...], one bar per calendar day."""
    return pl.DataFrame(
        {
            "ts": [start + dt.timedelta(days=i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [1000.0] * len(rows),
        }
    )


def _calm(n: int, price: float = 100.0) -> list[Bar]:
    """``n`` ordinary bars with a 1-point range, so ATR(14) settles at 1.0."""
    return [(price, price + 0.5, price - 0.5, price) for _ in range(n)]


def _date(i: int) -> dt.date:
    return (START + dt.timedelta(days=i)).date()


def _breaches(rows: list[dict[str, object]]) -> pl.DataFrame:
    schema = {
        "symbol": pl.Utf8(),
        "session_date": pl.Date(),
        "breach_class": pl.Utf8(),
        "breach_bps": pl.Float64(),
        "rth_high": pl.Float64(),
        "rth_low": pl.Float64(),
        "rth_bars": pl.UInt32(),
        "expected_bars": pl.UInt32(),
    }
    return pl.DataFrame(rows, schema=schema)


# --------------------------------------------------------------------- daily_wick_outlier


def test_F_0_1_6_D_396_a_bad_print_exceeds_both_thresholds_and_flags() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 100.0)  # 60 % above the body, 60 x ATR
    flagged = wick_outliers(_daily(rows), CFG.daily_wick_outlier)
    assert flagged.filter(pl.col("flag_high"))["idx"].to_list() == [20]


def test_F_0_1_6_D_396_a_wide_but_real_day_is_not_flagged() -> None:
    """It clears the percentage and not the ATR multiple, so requiring both keeps it."""
    rows = [(100.0, 112.0, 88.0, 100.0) for _ in range(30)]  # every day is 24 % wide
    flagged = wick_outliers(_daily(rows), CFG.daily_wick_outlier)
    assert not any(flagged["flag_high"].to_list())
    assert not any(flagged["flag_low"].to_list())


def test_F_0_1_6_D_396_a_large_atr_multiple_alone_is_not_enough() -> None:
    """A quiet series makes ATR tiny; a 2 % wick is many ATRs but is not a bad print."""
    rows = [(100.0, 100.01, 99.99, 100.0) for _ in range(30)]
    rows[20] = (100.0, 102.0, 99.99, 100.0)  # ~200 x ATR, only 2 %
    flagged = wick_outliers(_daily(rows), CFG.daily_wick_outlier)
    assert not any(flagged["flag_high"].to_list())


def test_F_0_1_6_D_396_the_wick_thresholds_come_from_config() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 102.0, 99.5, 100.0)  # 2 % above the body
    loose = wick_outliers(_daily(rows), DailyWickOutlierConfig(k1_atr=1.0, k2_pct=1.0))
    assert loose.filter(pl.col("flag_high"))["idx"].to_list() == [20]
    strict = wick_outliers(_daily(rows), DailyWickOutlierConfig(k1_atr=1.0, k2_pct=50.0))
    assert not any(strict["flag_high"].to_list())


def test_F_0_1_6_D_396_a_low_wick_flags_too() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 100.5, 40.0, 100.0)
    flagged = wick_outliers(_daily(rows), CFG.daily_wick_outlier)
    assert flagged.filter(pl.col("flag_low"))["idx"].to_list() == [20]


# ------------------------------------------------------------------------------ wick_clip


def test_F_0_1_6_D_396_a_flagged_wick_is_clipped_to_the_body() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 101.0)
    clean, log = clean_daily(_daily(rows), "BAD", CFG)
    assert clean["high"][20] == 101.0  # max(open, close)
    assert clean["low"][20] == 99.5  # untouched
    assert log.height == 1
    row = log.row(0, named=True)
    assert row["arm"] == ARM_WICK_CLIP and row["field"] == "high"
    assert (row["old"], row["new"]) == (160.0, 101.0)
    assert "x ATR(14)" in row["evidence"] and "% beyond the body" in row["evidence"]


def test_F_0_1_6_D_396_open_close_and_volume_are_never_changed() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 40.0, 101.0)
    raw = _daily(rows)
    clean, log = clean_daily(raw, "BAD", CFG)
    assert log.height == 2  # both wicks
    for column in ("open", "close", "volume", "ts"):
        assert clean[column].to_list() == raw[column].to_list()


# ---------------------------------------------------------------------------- extreme_cap


def test_F_0_1_6_D_396_an_unsupported_extreme_is_capped_to_the_rth_range() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 130.0, 99.5, 100.0)
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": UNEXPLAINED,
                "breach_bps": 3000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 7,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["high"][20] == 101.0
    assert log.filter(pl.col("arm") == ARM_EXTREME_CAP).height == 1
    assert "RTH hourly range" in log.row(0, named=True)["evidence"]


def test_F_0_1_6_D_396_an_extended_hours_extreme_is_capped_too() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 100.5, 90.0, 100.0)
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": EXTENDED_HOURS,
                "breach_bps": 900.0,
                "rth_high": 100.6,
                "rth_low": 99.0,
                "rth_bars": 7,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["low"][20] == 99.0
    assert log.row(0, named=True)["field"] == "low"


# --- the supervisor's rule: a short hourly day is not evidence ---------------------------


def test_F_0_1_6_T04k_a_short_hourly_day_never_caps_a_bar() -> None:
    """`incomplete_hourly_day`: one bar of seven says nothing, so the daily bar is left alone."""
    rows = _calm(30)
    rows[20] = (100.0, 130.0, 99.5, 100.0)
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": INCOMPLETE_HOURLY_DAY,
                "breach_bps": 3000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 1,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["high"][20] == 130.0  # untouched
    assert log.height == 0


def test_F_0_1_6_T04k_a_short_hourly_day_is_not_wick_clipped_either() -> None:
    """The bar would otherwise be a wick outlier; a short hourly day must not silently clean it."""
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 101.0)  # a wick the clip arm would take
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": INCOMPLETE_HOURLY_DAY,
                "breach_bps": 5000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 1,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["high"][20] == 160.0
    assert log.height == 0


def test_F_0_1_6_T04k_a_short_hourly_day_that_agrees_is_still_not_evidence() -> None:
    """The surviving bar contains the daily range -- agreement with one bar is not agreement."""
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 101.0)
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": INCOMPLETE_HOURLY_DAY,
                "breach_bps": 1.0,
                "rth_high": 200.0,  # "agrees": it contains the daily high
                "rth_low": 1.0,
                "rth_bars": 1,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["high"][20] == 160.0  # not corrected ...
    assert log.height == 0  # ... and not recorded as clean either


def test_F_0_1_6_T04k_a_day_with_no_raw_hours_is_left_alone() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 101.0)
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": NO_RAW_HOURS,
                "breach_bps": 5000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 0,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["high"][20] == 160.0 and log.height == 0


def test_F_0_1_6_T04k_a_symbol_without_hourly_data_still_gets_its_wicks_clipped() -> None:
    """No breach frame at all: every flagged wick goes to the clip arm (only 826 have hourly)."""
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 101.0)
    clean, log = clean_daily(_daily(rows), "NOHOURLY", CFG, breaches=None)
    assert clean["high"][20] == 101.0
    assert log.row(0, named=True)["arm"] == ARM_WICK_CLIP


# ------------------------------------------------------------------- frozen_cut, boundary


def _padded(lead: int, frozen: int, tail: int, level: float = 50.0) -> list[Bar]:
    rows = _calm(lead)
    rows += [(level, level, level, level)] * frozen
    rows += _calm(tail, 100.0)
    return rows


def test_F_0_1_6_D_398_a_frozen_stretch_is_cut_and_logged_per_bar() -> None:
    rows = _padded(20, 15, 20)
    raw = _daily(rows)
    clean, log = clean_daily(raw, "PAD", CFG)
    assert clean.height == raw.height - 15
    cut = log.filter(pl.col("arm") == ARM_FROZEN_CUT)
    assert cut.height == 15
    assert all(r["field"] == "bar" and r["new"] is None for r in cut.iter_rows(named=True))
    assert "padded sessions" in cut.row(0, named=True)["evidence"]


def test_F_0_1_6_D_398_the_history_starts_at_the_boundary_when_one_is_given() -> None:
    rows = _calm(40)
    verdict = SeriesVerdict(
        symbol="REUSED",
        verdict=TRIM,
        boundary_date=_date(25).isoformat(),
        boundary_reason="stale_run",
        dropped_from=_date(0).isoformat(),
        dropped_to=_date(24).isoformat(),
        dropped_bars=25,
    )
    clean, log = clean_daily(_daily(rows), "REUSED", CFG, verdict=verdict)
    assert clean.height == 15
    assert clean["ts"][0].date() == _date(25)
    trim = log.filter(pl.col("arm") == ARM_BOUNDARY_TRIM)
    assert trim.height == 25
    assert "D-398 (stale_run)" in trim.row(0, named=True)["evidence"]


def test_F_0_1_6_D_399_an_ambiguous_signature_keeps_the_whole_history() -> None:
    """The cross-check could not settle it, so `apply_boundary=False` and nothing is trimmed."""
    rows = _calm(40)
    verdict = SeriesVerdict(
        symbol="SUSPECT",
        verdict=TRIM,
        boundary_date=_date(25).isoformat(),
        boundary_reason="stale_run",
        dropped_from=_date(0).isoformat(),
        dropped_to=_date(24).isoformat(),
        dropped_bars=25,
    )
    clean, log = clean_daily(_daily(rows), "SUSPECT", CFG, verdict=verdict, apply_boundary=False)
    assert clean.height == 40
    assert log.filter(pl.col("arm") == ARM_BOUNDARY_TRIM).height == 0


def test_F_0_1_6_D_398_a_bar_is_never_logged_by_two_arms() -> None:
    """Padding ahead of the boundary is trimmed, not trimmed *and* cut."""
    rows = _padded(20, 15, 20)
    verdict = SeriesVerdict(
        symbol="BOTH",
        verdict=TRIM,
        boundary_date=_date(35).isoformat(),
        boundary_reason="stale_run",
        dropped_from=_date(0).isoformat(),
        dropped_to=_date(34).isoformat(),
        dropped_bars=35,
    )
    clean, log = clean_daily(_daily(rows), "BOTH", CFG, verdict=verdict)
    assert clean.height == 20
    removed = log.filter(pl.col("field") == "bar")
    assert removed.height == 35
    assert removed["session_date"].n_unique() == 35


# ------------------------------------------------------------------------------- the log


def test_F_0_1_6_T04k_every_log_row_names_its_arm_and_its_evidence() -> None:
    rows = _padded(20, 15, 20)
    rows[50] = (100.0, 160.0, 99.5, 101.0)
    _clean, log = clean_daily(_daily(rows), "MIXED", CFG)
    assert log.height > 0
    for row in log.iter_rows(named=True):
        assert row["arm"] in {ARM_BOUNDARY_TRIM, ARM_FROZEN_CUT, ARM_EXTREME_CAP, ARM_WICK_CLIP}
        assert row["evidence"] and row["evidence"].strip()
        assert row["field"] in {"bar", "high", "low"}


def test_F_0_1_6_T04k_replaying_the_log_reproduces_the_clean_bars() -> None:
    """The log accounts for every difference between raw and clean (acceptance criterion)."""
    rows = _padded(20, 15, 20)
    rows[50] = (100.0, 160.0, 99.5, 101.0)
    rows[52] = (100.0, 100.5, 40.0, 99.0)
    raw = _daily(rows)
    clean, log = clean_daily(raw, "MIXED", CFG)

    replay = raw.with_row_index("i")
    by_date = {
        r["session_date"]: r
        for r in raw.with_columns(pl.col("ts").dt.date().alias("session_date")).iter_rows(
            named=True
        )
    }
    dropped = {
        r["session_date"] for r in log.filter(pl.col("field") == "bar").iter_rows(named=True)
    }
    edits = {
        (r["session_date"], r["field"]): r["new"]
        for r in log.filter(pl.col("field") != "bar").iter_rows(named=True)
    }
    expected_rows = []
    for day, row in by_date.items():
        if day.isoformat() in dropped:
            continue
        out = dict(row)
        for field in ("high", "low"):
            if (day.isoformat(), field) in edits:
                out[field] = edits[(day.isoformat(), field)]
        expected_rows.append(out)
    assert len(expected_rows) == clean.height
    assert [r["high"] for r in expected_rows] == clean["high"].to_list()
    assert [r["low"] for r in expected_rows] == clean["low"].to_list()
    assert replay.height == raw.height  # raw itself is untouched


def test_F_0_1_6_T04k_a_clean_series_produces_an_empty_log() -> None:
    clean, log = clean_daily(_daily(_calm(40)), "CLEAN", CFG)
    assert clean.height == 40 and log.height == 0
    assert log.columns == ["symbol", "session_date", "arm", "field", "old", "new", "evidence"]


def test_F_0_1_6_T04k_an_empty_frame_is_handled() -> None:
    empty = _daily([]).clear()
    clean, log = clean_daily(empty, "EMPTY", CFG)
    assert clean.height == 0 and log.height == 0


# ------------------------------------------------------------------- the two quality checks


def _meta(**over: object) -> SeriesMetadata:
    return make_meta(**{"timeframe": "1D", **over})


def test_F_0_1_6_D_396_the_wick_check_reports_counts_per_symbol_and_per_date() -> None:
    rows = _calm(30)
    rows[20] = (100.0, 160.0, 99.5, 101.0)
    rows[25] = (100.0, 100.5, 40.0, 99.0)
    res = check_daily_wick_outlier(_daily(rows), _meta(), CFG)
    assert res.status == "fail" and res.count == 2
    assert res.details["high_side"] == 1 and res.details["low_side"] == 1
    assert _date(20).isoformat() in res.details["dates"]


def test_F_0_1_6_D_396_the_wick_check_runs_without_hourly_data() -> None:
    """826 of 6,707 symbols have hourly data; this arm must work for the other 5,881."""
    assert check_daily_wick_outlier(_daily(_calm(30)), _meta(), CFG).status == "pass"


def test_F_0_1_6_D_396_the_wick_check_is_skipped_on_an_hourly_series() -> None:
    res = check_daily_wick_outlier(_daily(_calm(30)), _meta(timeframe="1H"), CFG)
    assert res.status == "skipped"


def test_F_0_1_6_D_396_the_extreme_check_is_skipped_without_hourly_data() -> None:
    res = check_daily_extreme_unsupported(_daily(_calm(30)), _meta(), CFG, None)
    assert res.status == "skipped"
    assert "no hourly series" in str(res.message) + str(res.details)


def test_F_0_1_6_T04k_the_extreme_check_never_counts_a_short_hourly_day_as_a_defect() -> None:
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": INCOMPLETE_HOURLY_DAY,
                "breach_bps": 3000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 1,
                "expected_bars": 7,
            }
        ]
    )
    res = check_daily_extreme_unsupported(_daily(_calm(30)), _meta(), CFG, br)
    assert res.status == "pass"  # not a defect ...
    assert res.details["not_evidence_days"] == 1  # ... but visibly not checked either
    assert _date(20).isoformat() in res.details["not_evidence_dates"]


def test_F_0_1_6_D_396_the_extreme_check_counts_a_real_breach() -> None:
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": UNEXPLAINED,
                "breach_bps": 3000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 7,
                "expected_bars": 7,
            },
            {
                "symbol": "EQ",
                "session_date": _date(21),
                "breach_class": INCOMPLETE_HOURLY_DAY,
                "breach_bps": 900.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 2,
                "expected_bars": 7,
            },
        ]
    )
    res = check_daily_extreme_unsupported(_daily(_calm(30)), _meta(), CFG, br)
    assert res.status == "fail" and res.count == 1  # the short day is not counted
    assert res.details["not_evidence_days"] == 1
    assert "unexplained 1" in (res.message or "")


def test_F_0_1_6_T04k_a_cap_never_moves_an_extreme_past_the_body() -> None:
    """The open and the close really traded, so `low <= open, close <= high` must survive a cap.

    Found by the store refusing 5 of 7 smoke-test symbols with `ohlc_outside_range`: the RTH
    hourly range can sit entirely inside the daily body when the hourly feed missed the move.
    """
    rows = _calm(30)
    rows[20] = (100.0, 130.0, 70.0, 125.0)  # the close is above the hourly high
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(20),
                "breach_class": UNEXPLAINED,
                "breach_bps": 3000.0,
                "rth_high": 101.0,
                "rth_low": 99.0,
                "rth_bars": 7,
                "expected_bars": 7,
            }
        ]
    )
    clean, log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    assert clean["high"][20] == 125.0  # max(open, close), not the 101.0 hourly high
    assert clean["low"][20] == 99.0  # the low may still be capped
    assert all(
        lo <= min(o, c) and max(o, c) <= hi
        for o, hi, lo, c in zip(
            clean["open"], clean["high"], clean["low"], clean["close"], strict=True
        )
    )
    assert "bounded by the body" in log.row(0, named=True)["evidence"]


def test_F_0_1_6_T04k_the_clean_frame_always_satisfies_the_ohlc_invariant() -> None:
    """Whatever the arms do, every bar still has `low <= open, close <= high`."""
    rows = _padded(20, 15, 20)
    rows[50] = (100.0, 160.0, 40.0, 101.0)
    rows[52] = (100.0, 100.5, 40.0, 99.0)
    br = _breaches(
        [
            {
                "symbol": "EQ",
                "session_date": _date(51),
                "breach_class": UNEXPLAINED,
                "breach_bps": 3000.0,
                "rth_high": 100.2,
                "rth_low": 100.1,
                "rth_bars": 7,
                "expected_bars": 7,
            }
        ]
    )
    clean, _log = clean_daily(_daily(rows), "EQ", CFG, breaches=br)
    for o, hi, lo, c in zip(
        clean["open"], clean["high"], clean["low"], clean["close"], strict=True
    ):
        assert lo <= min(o, c) and max(o, c) <= hi


# ------------------------------------ D-398/D-008: short history fails the split, raw untouched


def test_F_0_1_6_D_398_a_trimmed_history_too_short_fails_the_split_not_the_universe() -> None:
    """D-398/D-008: a too-short trimmed history is not excluded; `SplitManager` refuses it."""
    from strategy_factory.data.config import SplitConfig
    from strategy_factory.data.split import HistoryTooShortError, compute_split

    rows = _calm(400)
    verdict = SeriesVerdict(
        symbol="SHORT",
        verdict=TRIM,
        boundary_date=_date(300).isoformat(),
        boundary_reason="stale_run",
        dropped_from=_date(0).isoformat(),
        dropped_to=_date(299).isoformat(),
        dropped_bars=300,
    )
    clean, _log = clean_daily(_daily(rows), "SHORT", CFG, verdict=verdict)
    assert clean.height == 100  # the clean series exists -- nothing excluded it
    key = make_meta(symbol="SHORT", snapshot_hash="c" * 64).key()
    with pytest.raises(HistoryTooShortError):
        compute_split(clean["ts"], key, SplitConfig())


def test_F_0_1_8_T04k_writing_the_clean_snapshot_leaves_the_raw_one_untouched(
    tmp_path: pathlib.Path,
) -> None:
    """Rule 10: the clean snapshot is new; the raw parquet keeps its bytes and its mtime."""
    import hashlib

    from strategy_factory.data.catalog import Catalog
    from strategy_factory.data.store import SnapshotStore

    store, catalog = SnapshotStore(tmp_path), Catalog(tmp_path)
    rows = _calm(60)
    rows[40] = (100.0, 160.0, 99.5, 101.0)
    raw = _daily(rows)
    raw_meta = catalog.register(store.write_snapshot(raw, make_meta(symbol="EQ")))
    raw_path, _ = store.paths("test", "EQ", "1D", raw_meta.snapshot_hash or "")
    before = (hashlib.sha256(raw_path.read_bytes()).hexdigest(), raw_path.stat().st_mtime_ns)

    clean, log = clean_daily(raw, "EQ", CFG)
    assert log.height == 1
    derived = raw_meta.model_copy(
        update={"snapshot_hash": None, "derived_from": raw_meta.key(), "notes": "T04k"}
    )
    stored = catalog.register(store.write_snapshot(clean, derived))

    assert stored.snapshot_hash != raw_meta.snapshot_hash
    assert stored.derived_from == raw_meta.key()
    after = (hashlib.sha256(raw_path.read_bytes()).hexdigest(), raw_path.stat().st_mtime_ns)
    assert after == before  # raw bytes and mtime unchanged
    assert catalog.list_snapshots(symbol="EQ").height == 2  # raw still in the catalog
