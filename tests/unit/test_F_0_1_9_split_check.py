"""F-0.1.9: split consistency check between the ingested series and the cross-check."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
from fixtures.alpaca_helpers import make_config

from strategy_factory.data.config import KnownSplit
from strategy_factory.data.split_check import check_splits, warning_note, write_report

SPLIT = dt.date(2020, 8, 31)
KNOWN = [KnownSplit(symbol="AAPL", date=SPLIT, ratio=4, source="test")]
CFG = make_config().split_check
DATES = [dt.date(2020, 8, d) for d in (26, 27, 28, 31)] + [dt.date(2020, 9, 1)]


def closes(values: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"date": DATES, "close": values})


ADJUSTED = closes([126.5, 125.0, 124.8, 129.0, 134.2])
UNADJUSTED = closes([506.0, 500.0, 499.2, 129.0, 134.2])


def verdicts(rows: list[dict[str, object]]) -> dict[str, object]:
    return {str(r["date"]): r["verdict"] for r in rows}


def test_F_0_1_9_adjusted_split_passes() -> None:
    rows = check_splits("AAPL", "1D", ADJUSTED, ADJUSTED, KNOWN, CFG)
    assert verdicts(rows) == {"2020-08-31": "adjusted"}
    assert warning_note(rows) == ""


def test_F_0_1_9_synthetic_unadjusted_split_is_detected() -> None:
    rows = check_splits("AAPL", "1D", UNADJUSTED, ADJUSTED, KNOWN, CFG)
    assert verdicts(rows) == {"2020-08-31": "unadjusted"}
    assert "SPLIT-CHECK WARNING (1)" in warning_note(rows)


def test_F_0_1_9_unknown_split_jump_only_in_ingested_is_unexplained() -> None:
    rows = check_splits("MSFT", "1D", UNADJUSTED, ADJUSTED, KNOWN, CFG)
    assert verdicts(rows) == {"2020-08-31": "unexplained_ingested"}


def test_F_0_1_9_jump_only_in_crosscheck_is_reported() -> None:
    rows = check_splits("MSFT", "1D", ADJUSTED, UNADJUSTED, KNOWN, CFG)
    assert verdicts(rows) == {"2020-08-31": "unexplained_crosscheck"}


def test_F_0_1_9_real_move_in_both_sources_is_explained() -> None:
    crash = closes([100.0, 100.0, 100.0, 50.0, 51.0])
    rows = check_splits("XYZ", "1D", crash, crash, [], CFG)
    assert verdicts(rows) == {"2020-08-31": "market_move_both"}
    assert warning_note(rows) == ""


def test_F_0_1_9_report_merges_per_symbol(tmp_path: Path) -> None:
    path = tmp_path / "check.csv"
    write_report(path, "AAPL", check_splits("AAPL", "1D", UNADJUSTED, ADJUSTED, KNOWN, CFG))
    write_report(path, "MSFT", check_splits("MSFT", "1D", UNADJUSTED, ADJUSTED, KNOWN, CFG))
    write_report(path, "AAPL", check_splits("AAPL", "1D", ADJUSTED, ADJUSTED, KNOWN, CFG))
    df = pl.read_csv(path)
    assert df.select("symbol", "verdict").rows() == [
        ("AAPL", "adjusted"),
        ("MSFT", "unexplained_ingested"),
    ]
