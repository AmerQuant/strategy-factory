"""F-0.1.2 (T04l, D-710): the corporate-action evidence fetch -- no network (a fake client).

One immutable JSON per answer key with a manifest; a second run writes a new version, never an
overwrite; an unknown type is refused before any request; a TLS failure is reported as such and
never worked around (D-031); an HTTP error is permanent.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
import requests

from strategy_factory.core.errors import ConfigError
from strategy_factory.data.download.alpaca import Credentials
from strategy_factory.data.download.alpaca_reference import (
    EVIDENCE_ACTION_TYPES,
    check_truncation,
    fetch_corporate_actions,
)
from strategy_factory.data.download.ratelimit import PermanentError, TLSVerificationError

CREDS = Credentials("k", "s")
MERGER = {"acquiree_symbol": "PCL", "acquiree_cusip": "729251108", "process_date": "2016-02-22"}
REMOVAL = {"symbol": "OLD", "cusip": "123456789", "process_date": "2017-05-01"}


class FakeClient:
    def __init__(self, answer: dict[str, Any] | Exception) -> None:
        self.answer = answer
        self.requests: list[Any] = []

    def get_corporate_actions(self, req: Any) -> dict[str, Any]:
        self.requests.append(req)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _fetch(tmp_path: Path, client: FakeClient, types: tuple[str, ...] = EVIDENCE_ACTION_TYPES):
    return fetch_corporate_actions(
        CREDS, types, dt.date(2016, 1, 1), dt.date(2017, 12, 31), tmp_path, client=client
    )


def test_F_0_1_2_T04l_one_immutable_file_per_answer_key_with_a_manifest(tmp_path: Path) -> None:
    client = FakeClient({"stock_mergers": [MERGER], "worthless_removals": [REMOVAL]})
    paths = _fetch(tmp_path, client)
    assert len(client.requests) == 2  # one request per year
    names = sorted(p.name.rsplit("_", 1)[0] for p in paths)
    assert names == ["stock_mergers", "worthless_removals"]
    merger = next(p for p in paths if p.name.startswith("stock_mergers"))
    assert json.loads(merger.read_text(encoding="utf-8")) == [MERGER, MERGER]  # both years
    manifest = json.loads((merger.parent / (merger.name + ".manifest.json")).read_text("utf-8"))
    assert manifest["rows"] == 2 and manifest["answer_key"] == "stock_mergers"
    assert "worthless_removal" in manifest["source"] and "name_change" not in manifest["source"]
    assert manifest["sha256"]


def test_F_0_1_2_T04l_a_second_run_writes_a_new_version_never_an_overwrite(
    tmp_path: Path,
) -> None:
    first = _fetch(tmp_path, FakeClient({"stock_mergers": [MERGER]}))[0]
    before = first.read_bytes()
    second = _fetch(tmp_path, FakeClient({"stock_mergers": [MERGER, MERGER]}))[0]
    assert second != first and ".v2" in second.name
    assert first.read_bytes() == before


def test_F_0_1_2_T04l_an_unknown_type_is_refused_before_any_request(tmp_path: Path) -> None:
    client = FakeClient({})
    with pytest.raises(ConfigError, match="unknown corporate-action type"):
        _fetch(tmp_path, client, ("stock_merger", "no_such_action"))
    assert client.requests == []


def test_F_0_1_2_T04l_a_tls_failure_is_reported_as_such(tmp_path: Path) -> None:
    """D-031: never worked around -- the error names the TLS failure, nothing is written."""
    client = FakeClient(requests.exceptions.SSLError("certificate verify failed"))
    with pytest.raises(TLSVerificationError, match="certificate verify failed"):
        _fetch(tmp_path, client)
    assert not any(tmp_path.rglob("*.json"))


def test_F_0_1_2_T04l_an_http_error_is_permanent(tmp_path: Path) -> None:
    class Forbidden(Exception):
        status_code = 403

    with pytest.raises(PermanentError, match="HTTP 403"):
        _fetch(tmp_path, FakeClient(Forbidden("forbidden")))


def test_F_0_1_2_T04l_the_evidence_types_are_every_type_but_name_change() -> None:
    from alpaca.data.enums import CorporateActionsType

    offered = {t.value for t in CorporateActionsType}
    assert set(EVIDENCE_ACTION_TYPES) == offered - {"name_change"}


def test_F_0_1_2_T04l_the_request_has_no_row_cap(tmp_path: Path) -> None:
    """alpaca-py's default limit (1,000) caps the TOTAL rows: the first real run lost everything
    after the first page of each year. The request must ask for all of them."""
    client = FakeClient({"stock_mergers": [MERGER]})
    _fetch(tmp_path, client)
    assert all(req.limit is None for req in client.requests)


def test_F_0_1_2_T04l_a_full_page_year_is_flagged_in_the_manifest(tmp_path: Path) -> None:
    client = FakeClient({"cash_dividends": [REMOVAL] * 1000})
    path = _fetch(tmp_path, client)[0]
    manifest = json.loads((path.parent / (path.name + ".manifest.json")).read_text("utf-8"))
    assert manifest["rows_per_year_all_types"] == {"2016": 1000, "2017": 1000}
    assert manifest["suspect_truncation"] == ["2016", "2017"]


# ------------------------------------------------ the truncation guard itself (D-711)


def _write(folder: Path, name: str, rows: list[dict[str, Any]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(rows), encoding="utf-8")


def _rows(year: int, n: int) -> list[dict[str, Any]]:
    return [{"symbol": "X", "cusip": "1", "process_date": f"{year}-03-01"}] * n


def test_F_0_1_2_T04l_the_guard_reads_what_the_fetch_writes(tmp_path: Path) -> None:
    """Round trip, no field name in between: a capped answer (1,000 rows a year) is SUSPECT,
    a full one is OK -- counted from the rows the fetch wrote."""
    folder = tmp_path / "reference" / "alpaca" / "corporate_actions"
    _fetch(tmp_path, FakeClient({"cash_dividends": _rows(2016, 1000)}))
    capped = check_truncation(folder)
    assert not capped.ok and capped.suspect_years == ["2016"]
    _fetch(tmp_path, FakeClient({"cash_dividends": _rows(2016, 1234)}))  # writes .v2
    full = check_truncation(folder)
    assert full.ok and full.rows_per_year == {"2016": 2468}  # two yearly requests, 1234 each
    assert full.files["cash_dividends"].name.endswith(".v2.json")


def test_F_0_1_2_T04l_the_guard_never_mixes_a_truncated_older_file_in(tmp_path: Path) -> None:
    """The PowerShell summary crashed because it read the old v1 file; the guard takes the
    latest version of each key and ignores name changes."""
    _write(tmp_path, "cash_dividends_20260921.json", _rows(2016, 1000))
    _write(tmp_path, "cash_dividends_20260921.v2.json", _rows(2016, 1500))
    _write(tmp_path, "stock_mergers_20260921.json", _rows(2016, 7))
    _write(tmp_path, "name_changes_20260920.json", _rows(2016, 993))
    check = check_truncation(tmp_path)
    assert sorted(p.name for p in check.files.values()) == [
        "cash_dividends_20260921.v2.json",
        "stock_mergers_20260921.json",
    ]
    assert check.rows_per_year == {"2016": 1507} and check.ok


def test_F_0_1_2_T04l_no_file_is_not_a_pass(tmp_path: Path) -> None:
    assert not check_truncation(tmp_path / "missing").ok


def test_F_0_1_2_T04l_the_check_command_fails_loudly_on_a_suspect_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from strategy_factory.cli import app

    folder = tmp_path / "reference" / "alpaca" / "corporate_actions"
    _write(folder, "cash_mergers_20260921.json", _rows(2020, 2000))
    monkeypatch.setenv("SFAC_RAW_ROOT", str(tmp_path))
    out = CliRunner().invoke(app, ["data", "reference", "alpaca-corporate-actions-check"])
    assert out.exit_code == 1 and "SUSPECT" in out.output and "2020:2000" in out.output
    _write(folder, "cash_mergers_20260921.v2.json", _rows(2020, 2001))
    ok = CliRunner().invoke(app, ["data", "reference", "alpaca-corporate-actions-check"])
    assert ok.exit_code == 0 and "TRUNCATION CHECK: OK" in ok.output


def test_F_0_1_2_T04l_the_fetch_command_runs_the_guard_after_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard is part of the fetch, in the same process -- not a summary that may crash."""
    from typer.testing import CliRunner

    from strategy_factory.cli import app
    from strategy_factory.data import cli_alpaca

    def fake_fetch(creds, types, start, end, raw_root, client=None):
        return fetch_corporate_actions(
            creds,
            types,
            start,
            end,
            raw_root,
            client=FakeClient({"cash_dividends": _rows(2016, 1000)}),
        )

    monkeypatch.setattr(cli_alpaca, "fetch_corporate_actions", fake_fetch)
    monkeypatch.setattr(cli_alpaca, "load_credentials", lambda: CREDS)
    monkeypatch.setenv("SFAC_RAW_ROOT", str(tmp_path))
    out = CliRunner().invoke(
        app,
        [
            "data",
            "reference",
            "alpaca-corporate-actions",
            "--start",
            "2016-01-01",
            "--end",
            "2016-12-31",
        ],
    )
    assert out.exit_code == 1 and "TRUNCATION CHECK: SUSPECT" in out.output


def test_F_0_1_2_T04l_the_user_script_delegates_the_verdict_to_the_tested_command() -> None:
    """No verdict logic in PowerShell: the script calls the check command and fails on its exit."""
    script = Path("scripts/pilots/T04l_corporate_actions.ps1").read_text(encoding="utf-8")
    assert "sfac data reference alpaca-corporate-actions-check" in script
    assert "rows_per_year_all_types" not in script and "suspect_truncation" not in script
