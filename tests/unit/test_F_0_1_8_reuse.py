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
from strategy_factory.data.cusip_evidence import Event, classify
from strategy_factory.data.reuse import (
    KEEP,
    SPLIT,
    TRIM,
    UNSETTLED,
    Boundary,
    Decision,
    decide,
    long_gaps,
    plan,
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
    assert decide(b, diff) == TRIM
    same_company = Boundary(b.resumes, "T04k kept", "same_company")
    assert decide(same_company, diff) == UNSETTLED  # CUSIP and names disagree
    same = classify(
        [
            Event("reverse_splits", "id_before", "00901B105", "2021-10-04"),
            Event("reverse_splits", "id", "00901B303", "2021-10-04"),
        ],
        b.resumes,
        W,
    )
    assert decide(b, same, "unsettled") == KEEP
    assert decide(b, same, "unadjusted_split") == SPLIT
    assert decide(b, classify([], b.resumes, W)) == UNSETTLED


def test_F_0_1_2_D_713_the_series_starts_at_the_last_cut() -> None:
    p = plan([_decision("2019-01-02", TRIM), _decision("2022-05-02", UNSETTLED)])
    assert p.kind == "research_window" and p.start == _d("2022-05-02")
    assert [d.boundary.resumes for d in p.unsettled] == [_d("2022-05-02")]
    p = plan([_decision("2019-01-02", UNSETTLED), _decision("2022-05-02", TRIM)])
    assert p.kind == "trim" and p.start == _d("2022-05-02") and p.unsettled == ()
    assert plan([_decision("2019-01-02", KEEP)]).kind == "none"
    assert plan([_decision("2019-01-02", TRIM), _decision("2020-01-02", SPLIT)]).kind == SPLIT


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
