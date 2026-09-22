"""F-0.1.2 / F-0.1.8 (T04l, D-708, D-709, D-713): re-used tickers decided by CUSIP.

The decision per boundary and the plan per symbol (pure), then the pass end to end on a store: a
proven re-use is trimmed, an unsettled one gets a research-window snapshot and the full history
keeps a marker, a same-issuer break is kept, 1H follows 1D, references move only when asked, and a
re-run derives from the base -- never from its own output.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl
import pytest
from fixtures.bars import make_meta
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_reuse import REUSE_DIR, SUMMARY, T04L_TAG
from strategy_factory.data.cusip_evidence import Event, SplitRecord, classify
from strategy_factory.data.reuse import (
    KEEP,
    NO_BREAK,
    SPLIT,
    SPLIT_MATCH,
    SPLIT_UNEXPLAINED,
    TRIM,
    UNSETTLED,
    Boundary,
    Decision,
    decide,
    long_gaps,
    plan,
    split_test,
)
from strategy_factory.data.store import SnapshotStore

W = 7


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------------------------- pure


def test_F_0_1_2_D_708_every_long_gap_is_a_candidate_whatever_the_price() -> None:
    ts = pl.Series(
        [
            dt.datetime(2020, 1, 2, tzinfo=dt.UTC),
            dt.datetime(2020, 1, 3, tzinfo=dt.UTC),
            dt.datetime(2021, 3, 1, tzinfo=dt.UTC),
        ]
    )
    assert long_gaps(ts, 200) == [(_d("2021-03-01"), 423)]
    assert long_gaps(ts, 500) == []


def _decision(resumes: str, action: str) -> Decision:
    ev = classify([], _d(resumes), W)
    boundary = Boundary(_d(resumes), "long gap 1D")
    return Decision(boundary, action, "cusip_none", ev)  # type: ignore[arg-type]


def test_F_0_1_2_D_709_the_actions() -> None:
    b = Boundary(_d("2021-10-04"), "T04k kept", "one_name")
    diff = classify(
        [
            Event("name_changes", "away", "020764106", "2021-02-04"),
            Event("name_changes", "into", "127097103", "2021-10-04"),
        ],
        b.resumes,
        W,
    )
    assert decide(b, diff) == (TRIM, "")
    same_company = Boundary(b.resumes, "T04k kept", "same_company")
    assert decide(same_company, diff) == (UNSETTLED, "cusip_disagrees_with_name")
    same = classify(
        [
            Event("reverse_splits", "id_before", "00901B105", "2021-10-04"),
            Event("reverse_splits", "id", "00901B303", "2021-10-04"),
        ],
        b.resumes,
        W,
    )
    assert decide(b, classify([], b.resumes, W)) == (UNSETTLED, "cusip_none")
    re_use = Boundary(b.resumes, "T04k kept", "re_use")
    assert decide(re_use, same, NO_BREAK) == (UNSETTLED, "cusip_disagrees_with_name")


def test_F_0_1_2_D_709_the_same_cusip_across_a_halt_keeps() -> None:
    b = Boundary(_d("2023-05-15"), "long gap 1D", None, 400)
    halt = classify(
        [
            Event("cash_dividends", "id", "268648102", "2021-03-01"),
            Event("cash_dividends", "id", "268648102", "2023-08-01"),
        ],
        b.resumes,
        W,
        b.break_start,
    )
    assert halt.relation == "same_cusip"
    assert decide(b, halt, NO_BREAK) == (KEEP, "")


def test_F_0_1_2_D_709_a_split_test_that_cannot_tell_is_never_no_split() -> None:
    """Reviewer B1: every outcome of the known-split test other than 'no break' is not a keep."""
    b = Boundary(_d("2025-06-17"), "T04k kept", "ambiguous")
    same = classify(
        [
            Event("reverse_splits", "id_before", "00901B105", "2025-06-12"),
            Event("reverse_splits", "id", "00901B303", "2025-06-12"),
        ],
        b.resumes,
        W,
    )
    assert decide(b, same, SPLIT_UNEXPLAINED) == (UNSETTLED, "same_issuer_split_unsettled")
    assert decide(b, same, SPLIT_MATCH) == (SPLIT, "unadjusted_split")
    assert decide(b, same, None) == (UNSETTLED, "same_issuer_split_unsettled")
    assert decide(b, same, NO_BREAK) == (KEEP, "")


def test_F_0_1_2_D_709_the_known_split_test() -> None:
    ev = classify(
        [
            Event("reverse_splits", "id_before", "00901B105", "2025-06-12"),
            Event("reverse_splits", "id", "00901B303", "2025-06-12"),
        ],
        _d("2025-06-17"),
        W,
    )
    split = SplitRecord("2025-06-12", 100.0, ("00901B105", "00901B303"), "AIMID")
    a, b = _d("2025-06-10"), _d("2025-06-17")
    assert split_test(1.1, a, b, ev, [split], 0.40, 0.02)[0] == NO_BREAK
    assert split_test(100.5, a, b, ev, [split], 0.40, 0.02)[0] == SPLIT_MATCH
    assert split_test(107.0, a, b, ev, [split], 0.40, 0.02)[0] == SPLIT_UNEXPLAINED
    assert split_test(100.0, a, b, ev, [], 0.40, 0.02)[0] == SPLIT_UNEXPLAINED  # none recorded
    other = SplitRecord("2025-06-12", 100.0, ("99999Z101",), "OTHER")  # another issuer's split
    assert split_test(100.0, a, b, ev, [other], 0.40, 0.02)[0] == SPLIT_UNEXPLAINED


def test_F_0_1_2_D_709_mixed_evidence_is_unsettled() -> None:
    ev = classify(
        [
            Event("reverse_splits", "id_before", "74841Q100", "2022-08-12"),
            Event("stock_mergers", "id", "74841Q407", "2026-06-01"),
            Event("stock_mergers", "id", "G73264114", "2026-06-02"),
        ],
        _d("2026-05-29"),
        W,
    )
    assert decide(Boundary(_d("2026-05-29"), "T04k kept"), ev) == (UNSETTLED, "cusip_mixed")


def test_F_0_1_2_D_713_the_series_starts_at_the_last_cut() -> None:
    p = plan([_decision("2019-01-02", TRIM), _decision("2022-05-02", UNSETTLED)])
    assert p.kind == "research_window" and p.start == _d("2022-05-02")
    assert [d.boundary.resumes for d in p.marked] == [_d("2022-05-02")]
    p = plan([_decision("2019-01-02", UNSETTLED), _decision("2022-05-02", TRIM)])
    assert p.kind == "trim" and p.start == _d("2022-05-02") and p.marked == ()
    assert plan([_decision("2019-01-02", KEEP)]).kind == "none"
    p = plan([_decision("2019-01-02", TRIM), _decision("2020-01-02", SPLIT)])
    assert p.kind == SPLIT and [d.boundary.resumes for d in p.marked] == [_d("2020-01-02")]


def test_F_0_1_2_D_713_the_window_marker_names_only_its_own_boundary() -> None:
    """Reviewer: a boundary the window already cut away is not on the window's marker (FIG)."""
    p = plan([_decision("2022-05-17", UNSETTLED), _decision("2025-07-31", UNSETTLED)])
    assert [d.boundary.resumes for d in p.marked] == [_d("2022-05-17"), _d("2025-07-31")]
    assert [d.boundary.resumes for d in p.window] == [_d("2025-07-31")]


# ------------------------------------------------------------------------------- end to end


def _bars(dates: list[dt.datetime], price: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": dates,
            "open": [price] * len(dates),
            "high": [price + 0.5] * len(dates),
            "low": [price - 0.5] * len(dates),
            "close": [price] * len(dates),
            "volume": [100.0] * len(dates),
        }
    )


def _days(start: str, n: int) -> list[dt.datetime]:
    d0 = dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC)
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _spliced(first: str, second: str, tf: str = "1D") -> pl.DataFrame:
    """Two stretches at a similar price (no level break) with a long gap between them."""
    a, b = _days(first, 60), _days(second, 60)
    if tf == "1H":
        a = [d.replace(hour=14) for d in a]
        b = [d.replace(hour=14) for d in b]
    return pl.concat([_bars(a, 40.0), _bars(b, 42.0)])


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    store_root, raw = tmp_path / "store", tmp_path / "raw"
    (raw / "reference" / "alpaca" / "corporate_actions").mkdir(parents=True)
    monkeypatch.setenv("SFAC_DATA_ROOT", str(store_root))
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    return store_root, raw


def _register(root: Path, symbol: str, df: pl.DataFrame, tf: str = "1D") -> str:
    store, catalog = SnapshotStore(root), Catalog(root)
    meta = make_meta(
        source="alpaca", source_symbol=symbol, symbol=symbol, session="exchange", timeframe=tf
    )
    stored = catalog.register(store.write_snapshot(df, meta))
    catalog.set_reference(symbol, tf, stored.snapshot_hash or "", note="raw")
    return stored.snapshot_hash or ""


def _actions(raw: Path, name: str, rows: list[dict[str, str]]) -> None:
    folder = raw / "reference" / "alpaca" / "corporate_actions"
    (folder / f"{name}_20260921.json").write_text(json.dumps(rows), encoding="utf-8")


def _run(*args: str) -> str:
    out = CliRunner().invoke(app, ["data", "reuse", *args])
    assert out.exit_code == 0, out.output
    return out.output


def _world(env: tuple[Path, Path]) -> dict[str, str]:
    root, raw = env
    hashes = {
        "REUSE": _register(root, "REUSE", _spliced("2017-01-02", "2021-01-04")),
        "UNS": _register(root, "UNS", _spliced("2017-01-02", "2021-01-04")),
        "UNS1H": _register(root, "UNS", _spliced("2017-01-02", "2021-01-04", "1H"), "1H"),
        "SAME": _register(root, "SAME", _spliced("2017-01-02", "2021-01-04")),
    }
    _actions(
        raw,
        "name_changes",
        [
            {
                "old_symbol": "REUSE",
                "old_cusip": "111111101",
                "new_symbol": "GONE",
                "new_cusip": "111111101",
                "process_date": "2017-06-01",
            }
        ],
    )
    _actions(
        raw,
        "cash_dividends",
        [
            {"symbol": "REUSE", "cusip": "G99999105", "process_date": "2021-06-01"},
            {"symbol": "SAME", "cusip": "222222101", "process_date": "2017-02-01"},
            {"symbol": "SAME", "cusip": "222222309", "process_date": "2021-06-01"},
        ],
    )
    return hashes


def test_F_0_1_8_T04l_decisions_and_derived_snapshots(env: tuple[Path, Path]) -> None:
    root, _ = env
    h = _world(env)
    _run()
    summary = pl.read_csv(root / REUSE_DIR / SUMMARY)
    kinds = {(s, tf): k for s, tf, k in summary.select("symbol", "timeframe", "kind").rows()}
    assert kinds == {
        ("REUSE", "1D"): "trim",
        ("UNS", "1D"): "research_window",
        ("UNS", "1H"): "research_window",
    }  # SAME: same issuer, kept -- nothing derived
    catalog = Catalog(root)
    # references have NOT moved without --set-reference
    assert catalog.get_reference("UNS", "1D").snapshot_hash == h["UNS"]
    new = summary.filter((pl.col("symbol") == "UNS") & (pl.col("timeframe") == "1D")).row(
        0, named=True
    )
    meta = catalog.get(
        catalog.get_reference("UNS", "1D")
        .key()
        .model_copy(update={"snapshot_hash": new["new_hash"]})
    )
    assert meta.derived_from is not None and meta.derived_from.snapshot_hash == h["UNS"]
    assert T04L_TAG in meta.notes and "research window from 2021-01-04" in meta.notes
    assert new["new_bars"] == 60 and new["removed_bars"] == 60
    # the full history keeps its marker; the window says where it starts
    base = catalog.get_reference("UNS", "1D")
    marker = catalog.splices(base.key())
    assert [s.role for s in marker] == ["full_history"]  # one break, seen in 1D and in 1H
    assert "long gap 1D+long gap 1H" in marker[0].evidence
    assert catalog.splices(meta.key())[0].role == "research_window"
    assert catalog.splices(meta.key())[0].reason == "cusip_none"
    # log + provenance beside the snapshot; replaying the log reproduces it
    folder = root / REUSE_DIR / "1D" / "UNS"
    prov = json.loads((folder / f"{new['new_hash']}.json").read_text(encoding="utf-8"))
    assert prov["derived_from"] == h["UNS"] and prov["start"] == "2021-01-04"
    store = SnapshotStore(root)
    base_bars = store.read_snapshot("alpaca", "UNS", "1D", h["UNS"])
    replay = base_bars.filter(pl.col("ts").dt.date() >= dt.date.fromisoformat(prov["start"]))
    assert replay.equals(store.read_snapshot("alpaca", "UNS", "1D", new["new_hash"]))


def test_F_0_1_8_T04l_set_reference_moves_and_a_rerun_derives_from_the_base(
    env: tuple[Path, Path],
) -> None:
    root, _ = env
    h = _world(env)
    _run("--set-reference")
    catalog = Catalog(root)
    moved = catalog.get_reference("UNS", "1D")
    assert moved.snapshot_hash != h["UNS"] and moved.derived_from is not None
    assert catalog.get_reference("UNS", "1H").snapshot_hash != h["UNS1H"]
    assert catalog.get_reference("SAME", "1D").snapshot_hash == h["SAME"]
    before = catalog.table().height
    events = catalog.events().filter(pl.col("event") != "quality").height
    _run("--set-reference")  # the input is the base, not the window: nothing new
    assert catalog.table().height == before
    # only the quality checks run again (as in T04k); no register, reference or splice event
    after = catalog.events().filter(pl.col("event") != "quality")
    assert after.height == events  # REUSE and UNS share bars (one hash): the base is found by key
    assert catalog.get_reference("UNS", "1D").snapshot_hash == moved.snapshot_hash


def test_F_0_1_8_T04l_an_hourly_gap_is_dated_as_the_daily_break_it_belongs_to() -> None:
    """PCL: the hourly series resumes six weeks after the daily one -- one break, the daily date."""
    from strategy_factory.data.cli_reuse import _same_break

    daily = [(_d("2025-08-01"), 300)]  # daily gap 2024-10-05 .. 2025-08-01
    assert _same_break(_d("2025-09-12"), 400, daily, []) == _d("2025-08-01")  # overlaps
    kept = [Boundary(_d("2021-10-04"), "T04k kept")]
    assert _same_break(_d("2021-10-06"), 300, [], kept) == _d("2021-10-04")  # contains it
    assert _same_break(_d("2019-01-02"), 250, daily, kept) == _d("2019-01-02")  # its own break


# ------------------------------------------------------------ the fixes of the acceptance review


def test_F_0_1_8_T04l_1d_is_rederived_from_raw_and_names_its_base(env: tuple[Path, Path]) -> None:
    """D-713 'exactly as T04k': the 1D snapshot is derived from raw with every arm; the T04k clean
    reference it replaces is its base (named in the notes), which keeps the marker."""
    root, _ = env
    store, catalog = SnapshotStore(root), Catalog(root)
    raw_meta = make_meta(source="alpaca", source_symbol="UNS", symbol="UNS", session="exchange")
    raw = catalog.register(store.write_snapshot(_spliced("2017-01-02", "2021-01-04"), raw_meta))
    clean_bars = _spliced("2017-01-02", "2021-01-04").with_columns(pl.col("high") + 0.01)
    clean_meta = raw_meta.model_copy(
        update={"derived_from": raw.key(), "notes": "T04k clean daily (test)"}
    )
    clean = catalog.register(store.write_snapshot(clean_bars, clean_meta))
    catalog.set_reference("UNS", "1D", clean.snapshot_hash or "")
    _run()
    row = pl.read_csv(root / REUSE_DIR / SUMMARY).row(0, named=True)
    assert row["derived_from"] == raw.snapshot_hash and row["base_hash"] == clean.snapshot_hash
    new = catalog.get(clean.key().model_copy(update={"snapshot_hash": row["new_hash"]}))
    assert new.derived_from == raw.key()
    assert f"Base snapshot {clean.snapshot_hash}" in new.notes
    assert [s.role for s in catalog.splices(clean.key())] == ["full_history"]
    assert catalog.splices(raw.key()) == ()  # the raw snapshot is not the base here


def test_F_0_1_8_T04l_stale_notes_are_never_made_a_reference(env: tuple[Path, Path]) -> None:
    """D-392: identical bars return the first writer's notes; such a snapshot is not moved to."""
    root, _ = env
    h = _register(root, "UNS", _spliced("2017-01-02", "2021-01-04"))
    store, catalog = SnapshotStore(root), Catalog(root)
    window = store.read_snapshot("alpaca", "UNS", "1D", h).filter(
        pl.col("ts").dt.date() >= dt.date(2021, 1, 4)
    )
    old = make_meta(
        source="alpaca", source_symbol="UNS", symbol="UNS", session="exchange", notes="old notes"
    )
    catalog.register(store.write_snapshot(window, old))  # an earlier writer of the same bars
    _run("--set-reference")
    row = pl.read_csv(root / REUSE_DIR / SUMMARY).row(0, named=True)
    assert row["metadata_stale"] is True and row["reference_moved"] is False
    assert "NOT moved" in row["note"]
    assert catalog.get_reference("UNS", "1D").snapshot_hash == h


def test_F_0_1_8_T04l_new_evidence_that_settles_a_break_undoes_the_move(
    env: tuple[Path, Path],
) -> None:
    root, raw = env
    h = _register(root, "UNS", _spliced("2017-01-02", "2021-01-04"))
    _run("--set-reference")
    catalog = Catalog(root)
    assert catalog.get_reference("UNS", "1D").snapshot_hash != h
    folder = raw / "reference" / "alpaca" / "corporate_actions"
    (folder / "cash_dividends_20260922.json").write_text(  # later evidence: one security
        json.dumps(
            [
                {"symbol": "UNS", "cusip": "555555101", "process_date": "2017-02-01"},
                {"symbol": "UNS", "cusip": "555555101", "process_date": "2021-06-01"},
            ]
        ),
        encoding="utf-8",
    )
    _run("--set-reference")
    assert catalog.get_reference("UNS", "1D").snapshot_hash == h
    assert catalog.splices(catalog.get_reference("UNS", "1D").key()) == ()


def test_F_0_1_8_T04l_data_show_prints_the_marker(env: tuple[Path, Path]) -> None:
    root, _ = env
    _register(root, "UNS", _spliced("2017-01-02", "2021-01-04"))
    _run("--set-reference")
    out = CliRunner().invoke(app, ["data", "show", "UNS", "1D"])
    assert out.exit_code == 0, out.output
    assert "research_window 2021-01-04 cusip_none" in out.output


def test_F_0_1_8_T04l_an_unadjusted_split_is_marked_and_derives_nothing(
    env: tuple[Path, Path],
) -> None:
    """D-709 change 1 / D-397: a same-issuer break whose jump matches a recorded split."""
    root, raw = env
    a, b = _days("2017-01-02", 60), _days("2021-01-04", 60)
    h = _register(root, "SPL", pl.concat([_bars(a, 4.0), _bars(b, 40.0)]))
    _actions(
        raw,
        "reverse_splits",
        [
            {
                "symbol": "SPL",
                "old_cusip": "777777101",
                "new_cusip": "777777309",
                "old_rate": 10,
                "new_rate": 1,
                "process_date": "2020-12-01",
            }
        ],
    )
    _actions(
        raw,
        "cash_dividends",
        [
            {"symbol": "SPL", "cusip": "777777101", "process_date": "2017-02-01"},
            {"symbol": "SPL", "cusip": "777777309", "process_date": "2021-06-01"},
        ],
    )
    _run("--set-reference")
    catalog = Catalog(root)
    row = pl.read_csv(root / REUSE_DIR / SUMMARY).row(0, named=True)
    assert row["kind"] == "unadjusted_split" and "--refresh" in row["note"]
    assert catalog.get_reference("SPL", "1D").snapshot_hash == h  # nothing derived
    marker = catalog.splices(catalog.get_reference("SPL", "1D").key())
    assert [(s.role, s.reason) for s in marker] == [("full_history", "unadjusted_split")]
