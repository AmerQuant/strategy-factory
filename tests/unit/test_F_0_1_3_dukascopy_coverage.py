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

import pytest
from typer.testing import CliRunner, Result

from strategy_factory.cli import app
from strategy_factory.data import cli_dukascopy
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.coverage import dukascopy_coverage_frame, dukascopy_gaps
from strategy_factory.data.download.dukascopy import Instrument, month_dir

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


def test_F_0_1_3_T04j_the_verdict_ignores_the_manifest(tmp_path: Path) -> None:
    """D-711: a missing manifest does not make a present month a gap, and a manifest alone does
    not make a missing month present."""
    _full(tmp_path, EURUSD)
    bid = month_dir(tmp_path, "h1", "eurusd", "bid")
    (bid / "2010-03.csv.gz.manifest.json").unlink()
    (bid / "2010-04.csv.gz").unlink()  # its manifest stays behind
    assert _gaps(tmp_path, EURUSD) == {"EURUSD": ["2010-04"]}


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


FIX = Path(__file__).resolve().parents[1] / "fixtures" / "dukascopy" / "h1" / "EURUSD"


@pytest.fixture
def two_instruments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """EURUSD complete (the real 2024-03 fixture month, both sides) and GBPUSD with no file; the
    only required month is 2024-03."""
    raw = tmp_path / "raw"
    for side in ("bid", "ask"):
        folder = month_dir(raw, "h1", "eurusd", side)
        folder.mkdir(parents=True)
        (folder / "2024-03.csv.gz").write_bytes((FIX / side / "2024-03.csv.gz").read_bytes())
    universe = tmp_path / "dukascopy.csv"
    universe.write_text(
        "instrument_id,symbol,asset_class,notes\n"
        "eurusd,EURUSD,fx,h1 from 2003-05-04;\n"
        "gbpusd,GBPUSD,fx,h1 from 2003-05-04;\n",
        encoding="utf-8",
    )
    (tmp_path / "dukascopy.yaml").write_text(
        # the fixture month has 1 one-sided bar of 73, as in test_F_0_1_3_dukascopy's adapt()
        f"h1_start: 2024-03-01\nmax_one_sided_share: 0.02\nuniverse_file: {universe.as_posix()}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(cli_dukascopy, "_today", lambda: dt.date(2024, 4, 15))
    return tmp_path


def test_F_0_1_3_T04j_D657_a_complete_instrument_is_ingested_while_a_gapped_one_waits(
    two_instruments: Path,
) -> None:
    out = _invoke(two_instruments, "ingest", "dukascopy", "--set-reference")
    assert out.exit_code == 0, out.output
    assert "waiting (not ingested, D-657)" in out.output
    assert "GBPUSD 1 month(s) (2024-03..2024-03)" in out.output
    catalog = Catalog()
    assert catalog.has_reference("EURUSD", "1H")
    assert catalog.get_reference("EURUSD", "1H").hash_version == 2
    assert catalog.table()["symbol"].unique().to_list() == ["EURUSD"]  # nothing for GBPUSD
    assert not (two_instruments / "store" / "dukascopy" / "GBPUSD").exists()


def test_F_0_1_3_T04j_D657_a_gapped_instrument_named_alone_is_refused_and_writes_nothing(
    two_instruments: Path,
) -> None:
    out = _invoke(two_instruments, "ingest", "dukascopy", "--instruments", "gbpusd")
    assert out.exit_code == 1
    assert "nothing ingested" in out.output and "GBPUSD" in out.output
    assert not (two_instruments / "store").exists()


def test_F_0_1_3_T04j_D657_a_rerun_of_an_ingested_instrument_writes_nothing(
    two_instruments: Path,
) -> None:
    assert _invoke(two_instruments, "ingest", "dukascopy", "--set-reference").exit_code == 0
    store = two_instruments / "store"
    before = sorted((p.relative_to(store), p.stat().st_mtime_ns) for p in store.rglob("*.parquet"))
    rows = Catalog().table().height
    assert _invoke(two_instruments, "ingest", "dukascopy", "--set-reference").exit_code == 0
    after = sorted((p.relative_to(store), p.stat().st_mtime_ns) for p in store.rglob("*.parquet"))
    assert Catalog().table().height == rows
    snapshots = [f for f, _ in before if "_catalog" not in str(f)]
    assert snapshots and [x for x in after if x[0] in snapshots] == [
        x for x in before if x[0] in snapshots
    ]
