"""F-X.9: `sfac --version` and `sfac info` via Typer's CliRunner."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest
from typer.testing import CliRunner

from strategy_factory import __version__
from strategy_factory.cli import app

runner = CliRunner()


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run in an empty directory (no .env) with the SFAC_* roots unset."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SFAC_DATA_ROOT", raising=False)
    monkeypatch.delenv("SFAC_ARTIFACTS_ROOT", raising=False)
    return tmp_path


def test_F_X_9_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"sfac {__version__}"


def test_F_X_9_info_reports_not_set(clean_env: Path) -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.output
    assert __version__ in result.output
    assert platform.python_version() in result.output
    assert platform.system() in result.output
    assert "SFAC_DATA_ROOT" in result.output
    assert "SFAC_ARTIFACTS_ROOT" in result.output
    assert result.output.count("not set") == 2


def test_F_X_9_info_resolves_env_and_dotenv(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (clean_env / ".env").write_text(
        "# comment\nSFAC_ARTIFACTS_ROOT='/tmp/sfac art'\nSFAC_DATA_ROOT=/from/dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SFAC_DATA_ROOT", "/from/env")  # environment wins over .env
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.output
    assert "/from/env  (from environment)" in result.output
    assert "/tmp/sfac art  (from .env)" in result.output
    assert "/from/dotenv" not in result.output
    assert "not set" not in result.output


def test_F_X_9_global_log_level_option(clean_env: Path) -> None:
    assert runner.invoke(app, ["--log-level", "DEBUG", "info"]).exit_code == 0
    assert runner.invoke(app, ["--log-level", "warning", "info"]).exit_code == 0
    bad = runner.invoke(app, ["--log-level", "LOUD", "info"])
    assert bad.exit_code != 0
