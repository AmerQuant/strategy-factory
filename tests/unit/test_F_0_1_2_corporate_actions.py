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
