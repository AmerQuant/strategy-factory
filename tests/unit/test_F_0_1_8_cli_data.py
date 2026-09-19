"""F-0.1.8: `sfac data list` and `sfac data show`."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.bars import make_bars, make_meta
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.store import write_snapshot

runner = CliRunner()


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    monkeypatch.chdir(tmp_path)
    return root


def test_F_0_1_8_cli_list_empty(data_root: Path) -> None:
    result = runner.invoke(app, ["data", "list"])
    assert result.exit_code == 0, result.output
    assert "catalog is empty" in result.output


def test_F_0_1_8_cli_list_and_show(data_root: Path) -> None:
    cat = Catalog()
    a = cat.register(write_snapshot(make_bars(5), make_meta()))
    b = cat.register(write_snapshot(make_bars(3), make_meta(symbol="SPY", source_symbol="SPY")))
    cat.set_reference("TEST", "1D", a.snapshot_hash or "")

    result = runner.invoke(app, ["data", "list"])
    assert result.exit_code == 0, result.output
    assert "TEST" in result.output and "SPY" in result.output
    assert (a.snapshot_hash or "")[:12] in result.output
    assert "2 snapshot(s)" in result.output

    filtered = runner.invoke(app, ["data", "list", "--symbol", "SPY"])
    assert (b.snapshot_hash or "")[:12] in filtered.output
    assert "1 snapshot(s)" in filtered.output

    show = runner.invoke(app, ["data", "show", "TEST", "1D"])
    assert show.exit_code == 0, show.output
    assert f"snapshot_hash  : {a.snapshot_hash}" in show.output
    assert "row_count      : 5" in show.output
    assert "first_ts" in show.output and "last_ts" in show.output


def test_F_0_1_8_cli_show_without_reference_fails(data_root: Path) -> None:
    Catalog().register(write_snapshot(make_bars(), make_meta()))
    result = runner.invoke(app, ["data", "show", "TEST", "1D"])
    assert result.exit_code == 1
    assert "no reference" in result.output


def test_F_0_1_8_cli_list_without_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SFAC_DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["data", "list"])
    assert result.exit_code == 1
    assert "SFAC_DATA_ROOT is not set" in result.output
