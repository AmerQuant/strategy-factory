"""F-0.1.2 (T04e): Alpaca calendar and symbol-change processing (offline, raw API shapes)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl
import pytest

from strategy_factory.core.errors import ConfigError
from strategy_factory.data.download.alpaca_reference import (
    build_sessions_csv,
    build_symbol_changes,
    current_symbol,
    load_sessions,
    read_changes_csv,
)

# shape of GET /v2/calendar (raw_data=True)
CALENDAR = [
    {
        "date": "2024-11-27",
        "open": "09:30",
        "close": "16:00",
        "session_open": "0400",
        "session_close": "2000",
    },
    {
        "date": "2024-11-29",
        "open": "09:30",
        "close": "13:00",
        "session_open": "0400",
        "session_close": "1700",
    },
    {
        "date": "2024-12-24",
        "open": "09:30",
        "close": "13:00",
        "session_open": "0400",
        "session_close": "1700",
    },
    {
        "date": "2024-12-26",
        "open": "09:30",
        "close": "16:00",
        "session_open": "0400",
        "session_close": "2000",
    },
]
# shape of GET /v1/corporate-actions name_changes (raw_data=True)
NAME_CHANGES = [
    {
        "old_symbol": "FB",
        "old_cusip": "30303M102",
        "new_symbol": "META",
        "new_cusip": "30303M102",
        "process_date": "2022-06-09",
    },
    {
        "old_symbol": "ANTM",
        "old_cusip": "036752103",
        "new_symbol": "ELV",
        "new_cusip": "036752103",
        "process_date": "2022-06-28",
    },
    {
        "old_symbol": "ZZZ",
        "old_cusip": "1",
        "new_symbol": "YYY",
        "new_cusip": "2",
        "process_date": "2023-01-03",
    },
]


def test_F_0_1_2_sessions_csv_from_raw_calendar(tmp_path: Path) -> None:
    raw = tmp_path / "cal.json"
    raw.write_text(json.dumps(CALENDAR), encoding="utf-8")
    out = tmp_path / "nyse_sessions.csv"
    assert build_sessions_csv(raw, out) == 4
    sessions = load_sessions(out)
    assert sessions[dt.date(2024, 11, 29)] == ("09:30", "13:00")
    assert dt.date(2024, 11, 28) not in sessions  # Thanksgiving: no session
    with pytest.raises(ConfigError, match="alpaca-calendar"):
        load_sessions(tmp_path / "missing.csv")


def test_F_0_1_2_symbol_changes_for_pit_tickers_with_manual_override(tmp_path: Path) -> None:
    raw = tmp_path / "nc.json"
    raw.write_text(json.dumps(NAME_CHANGES), encoding="utf-8")
    manual = tmp_path / "manual.csv"
    manual.write_text(
        "old_symbol,new_symbol,effective_date,source\nANTM,ELV,2022-06-28,manual check\n",
        encoding="utf-8",
    )
    out = tmp_path / "symbol_changes.csv"
    n = build_symbol_changes(raw, ["FB", "ANTM", "AAPL"], manual, out)
    rows = pl.read_csv(out).rows(named=True)
    assert n == 2
    assert {(r["old_symbol"], r["new_symbol"], r["effective_date"]) for r in rows} == {
        ("FB", "META", "2022-06-09"),
        ("ANTM", "ELV", "2022-06-28"),
    }
    assert {r["old_symbol"]: r["source"] for r in rows} == {
        "FB": "alpaca_corporate_actions",
        "ANTM": "manual check",  # manual row wins
    }


def test_F_0_1_2_current_symbol_follows_chain_after_membership() -> None:
    changes = [
        {"old_symbol": "A1", "new_symbol": "B1", "effective_date": "2018-01-02"},
        {"old_symbol": "B1", "new_symbol": "C1", "effective_date": "2020-01-02"},
        {"old_symbol": "X", "new_symbol": "Y", "effective_date": "2012-01-02"},  # before membership
    ]
    assert current_symbol("A1", changes, dt.date(2016, 1, 1)) == "C1"
    assert current_symbol("X", changes, dt.date(2016, 1, 1)) == "X"
    assert current_symbol("AAPL", changes) == "AAPL"


def test_F_0_1_2_manual_changes_file_starts_empty() -> None:
    repo = Path(__file__).resolve().parents[2]
    manual = repo / "configs" / "universe" / "symbol_changes_manual.csv"
    assert manual.read_text(encoding="utf-8").splitlines() == [
        "old_symbol,new_symbol,effective_date,source"
    ]
    assert read_changes_csv(manual) == []
