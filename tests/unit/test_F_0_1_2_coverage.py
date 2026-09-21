"""F-0.1.2 (T04h, D-386, P-62): the raw coverage report and the gate in front of a 1H ingest.

A gap is a required year with no file or with an incomplete one; an empty file is present; the
current, partial year is never required; required years start at ``history_start`` (default) or at
the first year with a bar -- from config, not code, and 1H cannot be un-gated. The ingest refuses a
gapped set and writes nothing.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner, Result

from strategy_factory.cli import app
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import CoverageConfig
from strategy_factory.data.coverage import coverage_frame, coverage_gaps, describe_gaps
from strategy_factory.data.download.alpaca import write_chunk

REQ = {"feed": "sip", "adjustment": "split"}
START = dt.date(2016, 1, 1)
TODAY = dt.date(2020, 6, 1)  # years 2016..2019 complete, 2020 partial


def _bar(year: int) -> dict[str, object]:
    return {"t": f"{year}-03-02T15:00:00Z", "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.0, "v": 10.0}


def _years(
    raw: Path, symbol: str, full: list[int], empty: list[int] | None = None, complete: bool = True
) -> None:
    for y in full:
        write_chunk(raw, "1H", symbol, y, [_bar(y)], REQ, complete, "fake")
    for y in empty or []:
        write_chunk(raw, "1H", symbol, y, [], REQ, True, "fake")


def _gaps(raw: Path, symbols: list[str], cfg: CoverageConfig | None = None) -> dict[str, list[int]]:
    frame = coverage_frame(raw, "1H", symbols, START, cfg or CoverageConfig(), TODAY)
    return coverage_gaps(frame)


def test_F_0_1_2_T04h_a_complete_set_passes_and_the_partial_year_is_not_required(
    tmp_path: Path,
) -> None:
    _years(tmp_path, "AAA", [2016, 2017, 2018, 2019])  # no 2020 file: the year is partial
    frame = coverage_frame(tmp_path, "1H", ["AAA"], START, CoverageConfig(), TODAY)
    assert coverage_gaps(frame) == {}
    assert frame.filter(frame["year"] == 2020)["required"].to_list() == [False]
    assert frame["row_count"].to_list()[:4] == [1, 1, 1, 1]


def test_F_0_1_2_T04h_a_missing_year_is_a_gap(tmp_path: Path) -> None:
    _years(tmp_path, "AAA", [2016, 2017, 2019])
    gaps = _gaps(tmp_path, ["AAA"])
    assert gaps == {"AAA": [2018]}
    assert "AAA 2018" in describe_gaps(gaps)


def test_F_0_1_2_T04h_an_empty_file_is_present_not_a_gap(tmp_path: Path) -> None:
    """CCE: the feed had nothing, the download asked -- a file with row_count 0."""
    _years(tmp_path, "CCE", [], empty=[2016, 2017, 2018, 2019])
    frame = coverage_frame(tmp_path, "1H", ["CCE"], START, CoverageConfig(), TODAY)
    assert coverage_gaps(frame) == {}
    assert frame.filter(frame["required"])["row_count"].to_list() == [0, 0, 0, 0]


def test_F_0_1_2_T04h_a_later_listing_has_empty_files_and_passes(tmp_path: Path) -> None:
    """The downloader writes an empty file for a year before the listing."""
    _years(tmp_path, "NEW", [2018, 2019], empty=[2016, 2017])
    assert _gaps(tmp_path, ["NEW"]) == {}


def test_F_0_1_2_T04h_missing_leading_years_are_a_gap_by_default(tmp_path: Path) -> None:
    """An interrupted download that never wrote 2016/2017 is caught; ``first_data_year`` would not
    see it, which is why it is not the default."""
    _years(tmp_path, "OLD", [2018, 2019])
    assert _gaps(tmp_path, ["OLD"]) == {"OLD": [2016, 2017]}
    lenient = CoverageConfig(require_from="first_data_year")
    assert _gaps(tmp_path, ["OLD"], lenient) == {}


def test_F_0_1_2_T04h_an_incomplete_required_year_is_a_gap(tmp_path: Path) -> None:
    """A year downloaded while it was running (``complete: false``) and never refreshed."""
    _years(tmp_path, "AAA", [2016, 2017, 2018])
    _years(tmp_path, "AAA", [2019], complete=False)
    frame = coverage_frame(tmp_path, "1H", ["AAA"], START, CoverageConfig(), TODAY)
    assert coverage_gaps(frame) == {"AAA": [2019]}
    assert frame.filter(frame["year"] == 2019)["incomplete"].to_list() == [True]


def test_F_0_1_2_T04h_the_1h_gate_cannot_be_switched_off_in_config() -> None:
    with pytest.raises(ValidationError, match="must include 1H"):
        CoverageConfig(gate_timeframes=[])
    with pytest.raises(ValidationError, match="must include 1H"):
        CoverageConfig(gate_timeframes=["1D"])


def test_F_0_1_2_T04h_a_symbol_without_any_file_misses_every_year(tmp_path: Path) -> None:
    assert _gaps(tmp_path, ["GONE"]) == {"GONE": [2016, 2017, 2018, 2019]}


def test_F_0_1_2_T04h_the_latest_version_of_a_year_is_read(tmp_path: Path) -> None:
    _years(tmp_path, "AAA", [2016, 2017, 2018], empty=[2019])
    write_chunk(tmp_path, "1H", "AAA", 2019, [_bar(2019), _bar(2019)], REQ, True, "f", refresh=True)
    frame = coverage_frame(tmp_path, "1H", ["AAA"], START, CoverageConfig(), TODAY)
    row = frame.filter(frame["year"] == 2019).row(0, named=True)
    assert row["file"] == "2019.v2.parquet" and row["row_count"] == 2


def _invoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    monkeypatch.setenv("SFAC_RAW_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(tmp_path / "s"))
    return CliRunner().invoke(app, ["data", *args])


def test_F_0_1_2_T04h_the_1h_ingest_refuses_a_gapped_set_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P-62: there is no --allow-gaps; the refusal names the symbol and the year."""
    raw = tmp_path / "raw"
    _years(raw, "AAA", [2016, 2018])  # 2017 missing (and every year up to today's)
    out = _invoke(
        tmp_path, monkeypatch, "ingest", "alpaca", "--timeframe", "1H", "--symbols", "AAA"
    )
    assert out.exit_code == 1
    assert "AAA 2017" in out.output and "nothing ingested" in out.output
    assert not (tmp_path / "s").exists() or Catalog(tmp_path / "s").table().height == 0
    helped = _invoke(tmp_path, monkeypatch, "ingest", "alpaca", "--help")
    assert "allow-gaps" not in helped.output


def test_F_0_1_2_T04h_the_coverage_command_writes_the_report_and_exits_on_a_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    _years(raw, "AAA", [2016, 2018])
    out = _invoke(
        tmp_path, monkeypatch, "coverage", "alpaca", "--timeframe", "1H", "--symbols", "AAA"
    )
    assert out.exit_code == 1
    assert "GAPS" in out.output
    report = raw / "_reports" / "alpaca_coverage_1H.csv"
    assert report.is_file() and "AAA,2017" in report.read_text(encoding="utf-8")
