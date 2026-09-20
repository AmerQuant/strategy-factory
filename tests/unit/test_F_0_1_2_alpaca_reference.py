"""F-0.1.2 (T04e): Alpaca calendar and symbol-change processing (offline, raw API shapes)."""

from __future__ import annotations

import csv
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


def test_F_0_1_2_rejected_rename_keeps_the_old_symbol(tmp_path: Path) -> None:
    """D-383: an empty ``new_symbol`` in the manual file rejects a NAME_CHANGE row."""
    raw = tmp_path / "nc.json"
    raw.write_text(json.dumps(NAME_CHANGES), encoding="utf-8")
    manual = tmp_path / "manual.csv"
    manual.write_text(
        "old_symbol,new_symbol,effective_date,source\nFB,,2022-06-09,rejected: different company\n",
        encoding="utf-8",
    )
    out = tmp_path / "symbol_changes.csv"
    n = build_symbol_changes(raw, ["FB", "ANTM", "AAPL"], manual, out)
    rows = pl.read_csv(out).rows(named=True)
    # the rejected row is not written and does not override the API row's effect on the chain
    assert n == 1
    assert {(r["old_symbol"], r["new_symbol"]) for r in rows} == {("ANTM", "ELV")}
    # and the chain stops: FB keeps its own row in the universe
    assert current_symbol("FB", read_changes_csv(out), dt.date(2016, 1, 1)) == "FB"


def test_F_0_1_2_rejection_stops_a_chain_at_the_rejected_hop(tmp_path: Path) -> None:
    """A later hop is still followed; only the rejected hop is cut."""
    raw = tmp_path / "nc.json"
    raw.write_text(
        json.dumps(
            [
                {"old_symbol": "A1", "new_symbol": "B1", "process_date": "2018-01-02"},
                {"old_symbol": "B1", "new_symbol": "C1", "process_date": "2020-01-02"},
            ]
        ),
        encoding="utf-8",
    )
    manual = tmp_path / "manual.csv"
    manual.write_text(
        "old_symbol,new_symbol,effective_date,source\nB1,,2020-01-02,rejected: ticker re-used\n",
        encoding="utf-8",
    )
    out = tmp_path / "symbol_changes.csv"
    build_symbol_changes(raw, ["A1"], manual, out)
    changes = read_changes_csv(out)
    assert [(r["old_symbol"], r["new_symbol"]) for r in changes] == [("A1", "B1")]
    assert current_symbol("A1", changes, dt.date(2016, 1, 1)) == "B1"


def test_F_0_1_2_current_symbol_ignores_an_empty_new_symbol() -> None:
    """Defensive: a hand-edited file with an empty ``new_symbol`` never derails the chain."""
    changes = [
        {"old_symbol": "A1", "new_symbol": "", "effective_date": "2018-01-02"},
        {"old_symbol": "A1", "new_symbol": "B1", "effective_date": "2019-01-02"},
    ]
    assert current_symbol("A1", changes, dt.date(2016, 1, 1)) == "B1"


def test_F_0_1_2_current_symbol_follows_chain_after_membership() -> None:
    changes = [
        {"old_symbol": "A1", "new_symbol": "B1", "effective_date": "2018-01-02"},
        {"old_symbol": "B1", "new_symbol": "C1", "effective_date": "2020-01-02"},
        {"old_symbol": "X", "new_symbol": "Y", "effective_date": "2012-01-02"},  # before membership
    ]
    assert current_symbol("A1", changes, dt.date(2016, 1, 1)) == "C1"
    assert current_symbol("X", changes, dt.date(2016, 1, 1)) == "X"
    assert current_symbol("AAPL", changes) == "AAPL"


def test_F_0_1_2_manual_changes_file_is_only_rejections(tmp_path: Path) -> None:
    """T04f (D-383): every committed manual row is a rejection, with a documented reason."""
    repo = Path(__file__).resolve().parents[2]
    rows = read_changes_csv(repo / "configs" / "universe" / "symbol_changes_manual.csv")
    assert rows, "the T04f rejections must be committed"
    for r in rows:
        assert r["new_symbol"] == "", f"{r['old_symbol']} is not a rejection"
        assert r["source"].startswith("rejected: "), f"{r['old_symbol']} has no reason"
    # the rejected renames must not reach the generated file
    auto = repo / "configs" / "universe" / "symbol_changes.csv"
    generated = {r["old_symbol"] for r in read_changes_csv(auto)}
    assert generated.isdisjoint({r["old_symbol"] for r in rows})


def test_F_0_1_2_committed_nyse_calendar_is_usable(tmp_path: Path) -> None:
    """T04f (D-025): the generated calendar is the file the adapter and quality read."""
    repo = Path(__file__).resolve().parents[2]
    sessions = load_sessions(repo / "configs" / "calendars" / "nyse_sessions.csv")
    assert dt.date(2016, 1, 4) in sessions
    assert max(sessions) >= dt.date(dt.date.today().year, 12, 1)
    assert {o for o, _ in sessions.values()} == {"09:30"}  # NYSE opens at 09:30 throughout
    early = {d for d, (_, c) in sessions.items() if c != "16:00"}
    assert early, "the calendar must carry the 13:00 half-days"
    assert {c for d, (_, c) in sessions.items() if d in early} == {"13:00"}
    # the hand-written list this file replaced (T04e section 6) is gone
    assert not (repo / "configs" / "calendars" / "nyse_early_closes.yaml").exists()


def test_F_0_1_2_us_equity_schedule_is_not_skipped_with_the_committed_calendar() -> None:
    """Without the calendar both schedule checks are skipped and the snapshot still reads 'ok'."""
    from strategy_factory.data.config import load_quality_config
    from strategy_factory.data.schedule import expected_schedule

    repo = Path(__file__).resolve().parents[2]
    calendar = repo / "configs" / "calendars" / "nyse_sessions.csv"
    ny = dt.timezone(dt.timedelta(hours=-4))
    ts = pl.Series(
        "ts",
        [
            dt.datetime.combine(dt.date(2024, 7, 2), dt.time(h), tzinfo=ny).astimezone(dt.UTC)
            for h in range(9, 16)
        ],
    )
    sched = expected_schedule(ts, "us_equity", "1H", load_quality_config(), "", calendar)
    assert sched.starts is not None, sched.reason
    assert "calendar not found" not in sched.reason


def test_F_0_1_2_rejection_with_a_date_cuts_only_that_hop(tmp_path: Path) -> None:
    """A ticker the feed renames twice keeps the hop that was not rejected."""
    raw = tmp_path / "nc.json"
    raw.write_text(
        json.dumps(
            [
                {"old_symbol": "A1", "new_symbol": "WRONG", "process_date": "2018-01-02"},
                {"old_symbol": "A1", "new_symbol": "RIGHT", "process_date": "2020-01-02"},
            ]
        ),
        encoding="utf-8",
    )
    manual = tmp_path / "manual.csv"
    manual.write_text(
        "old_symbol,new_symbol,effective_date,source\nA1,,2018-01-02,rejected: ticker re-used\n",
        encoding="utf-8",
    )
    out = tmp_path / "symbol_changes.csv"
    build_symbol_changes(raw, ["A1"], manual, out)
    changes = read_changes_csv(out)
    assert [(r["old_symbol"], r["new_symbol"]) for r in changes] == [("A1", "RIGHT")]
    assert current_symbol("A1", changes, dt.date(2016, 1, 1)) == "RIGHT"


def test_F_0_1_2_committed_hourly_universe_applies_the_exclusion_rule() -> None:
    """T04f (D-383): the committed universe, not a fixture."""
    repo = Path(__file__).resolve().parents[2]
    with (repo / "configs" / "universe" / "us_equity_hourly.csv").open(encoding="utf-8") as fh:
        rows = {r["symbol"]: r for r in csv.DictReader(fh)}
    assert "pit_symbol" in next(iter(rows.values()))
    # confirmed rename: the old ticker is gone and the survivor records it
    assert "FB" not in rows
    assert "FB" in rows["META"]["pit_symbol"].split("|")
    # rejected renames keep their own row (D-383), including the two Moneta targets (D-388)
    rejected = [
        r["old_symbol"]
        for r in read_changes_csv(repo / "configs" / "universe" / "symbol_changes_manual.csv")
        if not r["new_symbol"]
    ]
    assert rejected, "the T04f rejections must be committed"
    assert set(rejected) <= set(rows), f"rejected but missing: {sorted(set(rejected) - set(rows))}"
    for target in ("EQR", "IR"):
        assert target in rows, f"{target} is a Moneta mapping target and is kept under D-388"
