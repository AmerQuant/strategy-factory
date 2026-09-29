"""F-0.1.3 (T04j, D-386 copied, P-62): the Dukascopy coverage report and the gate before the ingest.

A gap is a required month without a file on either side (the adapter refuses one-sided bars); a
month before the instrument's own start (its universe notes) and the current month are never
required; the latest version of a month counts. The verdict rests on the files present, never on a
manifest field (D-711). The ingest never writes an instrument with a gap; since D-657 the gate is
per instrument, so a complete instrument is ingested while a gapped one waits.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner, Result

from strategy_factory.cli import app
from strategy_factory.data import cli_dukascopy
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.coverage import (
    Window,
    dukascopy_coverage_frame,
    dukascopy_gaps,
    dukascopy_windows,
    is_settled,
)
from strategy_factory.data.download.dukascopy import Instrument, month_dir, raw_pairs

TODAY = dt.date(2011, 3, 15)  # 2010-01 .. 2011-02 complete, 2011-03 current
START = dt.date(2010, 1, 1)
EURUSD = Instrument("eurusd", "EURUSD", "fx", "EUR/USD; h1 from 2003-05-04; m1 from 2003-05-04")
LATE = Instrument("ussc2000idxusd", "USSC2000IDXUSD", "index_cfd", "h1 from 2010-08-08;")


def _month(root: Path, inst: Instrument, side: str, month: str, version: int = 1) -> None:
    folder = month_dir(root, "h1", inst.instrument_id, side)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{month}.csv.gz" if version == 1 else f"{month}.v{version}.csv.gz"
    (folder / name).write_bytes(
        gzip.compress(b"timestamp,open,high,low,close,volume\n1262563200000,1,1,1,1,1\n")
    )
    (folder / f"{name}.manifest.json").write_text(json.dumps({"row_count": 1}), encoding="utf-8")


def _months(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _full(root: Path, inst: Instrument, first: str = "2010-01", last: str = "2011-02") -> None:
    for month in _months(first, last):
        for side in ("bid", "ask"):
            _month(root, inst, side, month)


def _gaps(root: Path, *insts: Instrument) -> dict[str, list[str]]:
    return dukascopy_gaps(dukascopy_coverage_frame(root, "h1", list(insts), START, TODAY))


def test_F_0_1_3_T04j_a_complete_set_passes_and_the_current_month_is_not_required(
    tmp_path: Path,
) -> None:
    _full(tmp_path, EURUSD)
    frame = dukascopy_coverage_frame(tmp_path, "h1", [EURUSD], START, TODAY)
    assert _gaps(tmp_path, EURUSD) == {}
    assert frame.height == 14 and "2011-03" not in frame["month"].to_list()


def test_F_0_1_3_T04j_a_month_on_one_side_only_is_a_gap(tmp_path: Path) -> None:
    _full(tmp_path, EURUSD)
    (month_dir(tmp_path, "h1", "eurusd", "ask") / "2010-06.csv.gz").unlink()
    assert _gaps(tmp_path, EURUSD) == {"EURUSD": ["2010-06"]}


def test_F_0_1_3_T04j_months_before_the_instrument_start_are_not_required(tmp_path: Path) -> None:
    _full(tmp_path, LATE, first="2010-08")
    assert _gaps(tmp_path, LATE) == {}
    _full(tmp_path, EURUSD, first="2010-08")  # EURUSD lists in 2003: Jan-Jul 2010 are missing
    assert _gaps(tmp_path, EURUSD)["EURUSD"] == _months("2010-01", "2010-07")


def test_F_0_1_3_T04j_the_latest_version_of_a_month_counts(tmp_path: Path) -> None:
    _full(tmp_path, EURUSD)
    ask = month_dir(tmp_path, "h1", "eurusd", "ask")
    (ask / "2010-06.csv.gz").unlink()
    _month(tmp_path, EURUSD, "ask", "2010-06", version=2)
    assert _gaps(tmp_path, EURUSD) == {}


def test_F_0_1_3_T04j_the_verdict_ignores_manifest_fields(tmp_path: Path) -> None:
    """D-711: no manifest field decides coverage -- a manifest alone does not make a missing month
    present, and a manifest claiming no rows does not make a present month a gap. Only the
    manifest's existence counts, as the write-completion marker (D-661: the download runs
    alongside; a data file without its manifest is still being written)."""
    _full(tmp_path, EURUSD)
    bid = month_dir(tmp_path, "h1", "eurusd", "bid")
    manifest = bid / "2010-03.csv.gz.manifest.json"
    manifest.write_text(json.dumps({"row_count": 0, "complete": False}), encoding="utf-8")
    (bid / "2010-04.csv.gz").unlink()  # its manifest stays behind
    (bid / "2010-05.csv.gz.manifest.json").unlink()  # data written, manifest not yet
    assert _gaps(tmp_path, EURUSD) == {"EURUSD": ["2010-04", "2010-05"]}


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw = tmp_path / "raw"
    universe = tmp_path / "dukascopy.csv"
    universe.write_text(
        "instrument_id,symbol,asset_class,notes\neurusd,EURUSD,fx,h1 from 2003-05-04;\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "dukascopy.yaml"
    today = dt.datetime.now(dt.UTC).date()
    first = dt.date(today.year - 1, today.month, 1)  # a short span keeps the fixture small
    cfg.write_text(
        f"h1_start: {first.isoformat()}\nuniverse_file: {universe.as_posix()}\n", encoding="utf-8"
    )
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(tmp_path / "store"))
    return tmp_path


def _invoke(env: Path, *args: str) -> Result:
    return CliRunner().invoke(app, ["data", *args, "--config", str(env / "dukascopy.yaml")])


def test_F_0_1_3_T04j_the_ingest_refuses_a_gapped_set_and_writes_nothing(cli_env: Path) -> None:
    out = _invoke(cli_env, "ingest", "dukascopy")
    assert out.exit_code == 1
    assert "nothing ingested" in out.output and "EURUSD" in out.output
    assert not (cli_env / "store").exists()
    assert (
        "allow-gaps"
        not in CliRunner().invoke(app, ["data", "ingest", "dukascopy", "--help"]).output
    )


def test_F_0_1_3_T04j_the_coverage_command_reports_and_exits_on_a_gap(cli_env: Path) -> None:
    out = _invoke(cli_env, "coverage", "dukascopy")
    assert out.exit_code == 1 and "GAPS" in out.output and "complete: 0 of 1" in out.output
    report = cli_env / "raw" / "_reports" / "dukascopy_coverage_h1.csv"
    assert report.is_file() and "EURUSD" in report.read_text(encoding="utf-8")


INGEST_TODAY = dt.date(2024, 6, 15)  # required: 2024-01 .. 2024-05


def _synthetic_month(root: Path, inst: Instrument, side: str, month: str) -> None:
    """Weekday hourly bars of ``month``, the ask 2 pips above the bid, plus the manifest."""
    y, m = map(int, month.split("-"))
    ts = dt.datetime(y, m, 1, tzinfo=dt.UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    k = 0
    while ts.month == m:
        if ts.weekday() < 5:
            px = 1.1 + 0.0001 * (k % 50) + (0.0002 if side == "ask" else 0.0)
            lines.append(f"{int(ts.timestamp() * 1000)},{px},{px + 0.0005},{px - 0.0005},{px},1000")
            k += 1
        ts += dt.timedelta(hours=1)
    folder = month_dir(root, "h1", inst.instrument_id, side)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{month}.csv.gz").write_bytes(gzip.compress("\n".join(lines).encode("utf-8")))
    (folder / f"{month}.csv.gz.manifest.json").write_text("{}", encoding="utf-8")


def _synthetic(root: Path, inst: Instrument, skip: tuple[tuple[str, str], ...] = ()) -> None:
    for month in _months("2024-01", "2024-05"):
        for side in ("bid", "ask"):
            if (month, side) not in skip:
                _synthetic_month(root, inst, side, month)


GBPUSD = Instrument("gbpusd", "GBPUSD", "fx", "h1 from 2003-05-04;")


@pytest.fixture
def ingest_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """EURUSD complete 2024-01 .. 2024-05; GBPUSD missing its last month (no window). The D-008
    check is stubbed to pass (five months cannot split); ``_real_d008`` restores it."""
    raw = tmp_path / "raw"
    _synthetic(raw, EURUSD)
    _synthetic(raw, GBPUSD, skip=(("2024-05", "bid"),))
    universe = tmp_path / "dukascopy.csv"
    universe.write_text(
        "instrument_id,symbol,asset_class,notes\n"
        "eurusd,EURUSD,fx,h1 from 2003-05-04;\n"
        "gbpusd,GBPUSD,fx,h1 from 2003-05-04;\n",
        encoding="utf-8",
    )
    (tmp_path / "dukascopy.yaml").write_text(
        f"h1_start: 2024-01-01\nuniverse_file: {universe.as_posix()}\n", encoding="utf-8"
    )
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(cli_dukascopy, "_today", lambda: INGEST_TODAY)
    monkeypatch.setattr(cli_dukascopy, "d008_short", lambda *a: None)
    return tmp_path


def _snapshots(store: Path) -> list[tuple[Path, int]]:
    return sorted(
        (p.relative_to(store), p.stat().st_mtime_ns)
        for p in store.rglob("*.parquet")
        if not p.name.startswith("catalog")
    )


def test_F_0_1_3_T04j_D657_a_complete_instrument_is_ingested_while_one_without_window_waits(
    ingest_env: Path,
) -> None:
    out = _invoke(ingest_env, "ingest", "dukascopy", "--set-reference")
    assert out.exit_code == 0, out.output
    assert "waiting (not ingested, D-661)" in out.output
    assert "GBPUSD no complete window (2024-05 missing)" in out.output
    ref = Catalog().get_reference("EURUSD", "1H")
    assert ref.hash_version == 2 and "D-661" not in ref.notes  # complete: no window note
    assert Catalog().table()["symbol"].unique().to_list() == ["EURUSD"]  # nothing for GBPUSD


def test_F_0_1_3_T04j_D657_a_waiting_instrument_named_alone_is_refused_and_writes_nothing(
    ingest_env: Path,
) -> None:
    out = _invoke(ingest_env, "ingest", "dukascopy", "--instruments", "gbpusd")
    assert out.exit_code == 1
    assert "nothing ingested" in out.output and "GBPUSD" in out.output
    assert not (ingest_env / "store").exists()


def test_F_0_1_3_T04j_D657_a_rerun_of_an_ingested_instrument_writes_nothing(
    ingest_env: Path,
) -> None:
    assert _invoke(ingest_env, "ingest", "dukascopy", "--set-reference").exit_code == 0
    store = ingest_env / "store"
    before, rows = _snapshots(store), Catalog().table().height
    assert _invoke(ingest_env, "ingest", "dukascopy", "--set-reference").exit_code == 0
    assert before and _snapshots(store) == before and Catalog().table().height == rows


def test_F_0_1_3_T04j_D661_a_gapped_instrument_is_ingested_over_its_window_only(
    ingest_env: Path,
) -> None:
    (month_dir(ingest_env / "raw", "h1", "eurusd", "bid") / "2024-02.csv.gz").unlink()
    out = _invoke(ingest_env, "ingest", "dukascopy", "--set-reference")
    assert out.exit_code == 0, out.output
    assert "window=2024-03..2024-05 (D-661)" in out.output
    ref = Catalog().get_reference("EURUSD", "1H")
    assert ref.first_ts is not None and ref.first_ts.strftime("%Y-%m") == "2024-03"
    assert ref.last_ts is not None and ref.last_ts.strftime("%Y-%m") == "2024-05"
    assert "D-661 window 2024-03..2024-05: 1 month(s) missing before it, the latest 2024-02" in (
        ref.notes
    )


def test_F_0_1_3_T04j_D661_a_window_shorter_than_D008_waits_and_writes_nothing(
    ingest_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real D-008 check: five months cannot hold an 18-month holdout
    monkeypatch.setenv("SFAC_RAW_ROOT", str(ingest_env / "raw"))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(ingest_env / "store"))
    monkeypatch.setattr(cli_dukascopy, "_today", lambda: INGEST_TODAY)
    out = _invoke(ingest_env, "ingest", "dukascopy", "--instruments", "eurusd")
    assert out.exit_code == 1
    assert "EURUSD window 2024-01..2024-05 (0.42 y) shorter than D-008 on 1H, 1D" in out.output
    assert not (ingest_env / "store").exists()


def test_F_0_1_3_T04j_D661_a_closed_gap_re_derives_a_new_versioned_snapshot(
    ingest_env: Path,
) -> None:
    raw = ingest_env / "raw"
    (month_dir(raw, "h1", "eurusd", "bid") / "2024-02.csv.gz").unlink()
    (month_dir(raw, "h1", "eurusd", "bid") / "2024-02.csv.gz.manifest.json").unlink()
    assert _invoke(ingest_env, "ingest", "dukascopy", "--set-reference").exit_code == 0
    old = Catalog().get_reference("EURUSD", "1H")
    before = _snapshots(ingest_env / "store")
    _synthetic_month(raw, EURUSD, "bid", "2024-02")  # a later download closes the gap
    out = _invoke(ingest_env, "ingest", "dukascopy", "--set-reference")
    assert out.exit_code == 0, out.output
    assert "window=2024-01..2024-05 (reference)" in out.output  # complete now: no D-661 mark
    new = Catalog().get_reference("EURUSD", "1H")
    assert new.snapshot_hash != old.snapshot_hash
    assert new.first_ts is not None and new.first_ts.strftime("%Y-%m") == "2024-01"
    after = _snapshots(ingest_env / "store")
    assert set(before) <= set(after) and len(after) == len(before) + 1  # nothing overwritten
    hashes = Catalog().table().filter(pl.col("symbol") == "EURUSD")["snapshot_hash"].to_list()
    assert {old.snapshot_hash, new.snapshot_hash} <= set(hashes)


# -- D-661: the complete window; reading alongside a running download --------------------------


def _windows(root: Path, *insts: Instrument) -> dict[str, Window]:
    return dukascopy_windows(dukascopy_coverage_frame(root, "h1", list(insts), START, TODAY))


def test_F_0_1_3_T04j_D661_the_window_ends_at_the_last_complete_month_after_the_last_gap(
    tmp_path: Path,
) -> None:
    _full(tmp_path, EURUSD)
    for month in ("2010-03", "2010-07"):  # two gaps: the later one bounds the window
        (month_dir(tmp_path, "h1", "eurusd", "bid") / f"{month}.csv.gz").unlink()
    w = _windows(tmp_path, EURUSD)["EURUSD"]
    assert (w.first, w.last, w.months, w.bounding_gap, w.missing_before) == (
        "2010-08",
        "2011-02",
        7,
        "2010-07",
        2,
    )
    assert not w.complete


def test_F_0_1_3_T04j_D661_a_missing_last_month_leaves_no_window(tmp_path: Path) -> None:
    _full(tmp_path, EURUSD)
    (month_dir(tmp_path, "h1", "eurusd", "ask") / "2011-02.csv.gz").unlink()
    w = _windows(tmp_path, EURUSD)["EURUSD"]
    assert w.first is None and w.months == 0 and w.bounding_gap == "2011-02"


def test_F_0_1_3_T04j_D661_a_complete_instrument_has_the_whole_span(tmp_path: Path) -> None:
    _full(tmp_path, LATE, first="2010-08")
    w = _windows(tmp_path, LATE)["USSC2000IDXUSD"]
    assert w.complete and (w.first, w.months, w.missing_before) == ("2010-08", 7, 0)


@pytest.mark.parametrize("unfinished", ["data.partial", "no manifest", "manifest.partial"])
def test_F_0_1_3_T04j_a_month_still_being_written_is_not_counted(
    tmp_path: Path, unfinished: str
) -> None:
    """The download runs alongside: the writer links the data file, then its manifest; a month
    counts only once both exist and no ``.partial`` is left."""
    _full(tmp_path, EURUSD)
    folder = month_dir(tmp_path, "h1", "eurusd", "ask")
    data = folder / "2010-05.csv.gz"
    manifest = folder / "2010-05.csv.gz.manifest.json"
    if unfinished == "data.partial":
        (folder / "2010-05.csv.gz.partial").write_bytes(b"")
    elif unfinished == "no manifest":
        manifest.unlink()
    else:
        (folder / "2010-05.csv.gz.manifest.json.partial").write_text("{}", encoding="utf-8")
    assert data.is_file()
    assert _gaps(tmp_path, EURUSD) == {"EURUSD": ["2010-05"]}
    assert not is_settled(data)


def test_F_0_1_3_T04j_the_ingest_reads_only_settled_months(tmp_path: Path) -> None:
    """``raw_pairs`` (what the ingest reads) skips a month whose manifest is not written yet."""
    _full(tmp_path, EURUSD)
    (month_dir(tmp_path, "h1", "eurusd", "bid") / "2010-05.csv.gz.manifest.json").unlink()
    bid, ask = raw_pairs(tmp_path, "h1", "eurusd")
    assert "2010-05.csv.gz" not in [p.name for p in bid]
    assert "2010-05.csv.gz" in [p.name for p in ask] and len(bid) == len(ask) - 1
