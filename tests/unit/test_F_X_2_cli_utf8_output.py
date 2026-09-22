"""D-379 (P-53): the ``sfac`` entry point writes stdout and stderr as UTF-8.

Redirected to a file or a pipe, Python writes with the locale codec -- cp1252 on Windows --
and ``sfac`` output with ``→``, ``≤`` or ``₁₀`` crashed the command. The PowerShell scripts
log ``sfac`` to a file, which is exactly that case. Every test here forces the child's
standard streams to cp1252 with ``PYTHONIOENCODING``, so it fails without the fix on any
platform, CI's UTF-8 Ubuntu included.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from strategy_factory import cli

REPO = Path(__file__).resolve().parents[2]


def run_child(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run Python with its standard streams forced to cp1252 and captured (a pipe)."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "COLUMNS": "200", "NO_COLOR": "1"}
    env.pop("PYTHONUTF8", None)
    return subprocess.run([sys.executable, *args], capture_output=True, env=env, timeout=120)


def test_F_X_2_d379_the_console_script_is_the_utf8_entry_point() -> None:
    """`sfac` must start at `run`, not at the bare Typer app, or nothing sets the encoding."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"]["sfac"] == "strategy_factory.cli:run"


def test_F_X_2_d379_a_real_help_text_survives_a_cp1252_pipe() -> None:
    """`--rehash`'s help says 'rehash v1→v2'; `→` is not in cp1252 (reproduced crash)."""
    out = run_child(["-m", "strategy_factory.cli", "data", "ingest", "dukascopy", "--help"])
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    assert "rehash v1→v2" in out.stdout.decode("utf-8")


def test_F_X_2_d379_stdout_and_stderr_both_carry_utf8() -> None:
    script = (
        "import typer\n"
        "from strategy_factory import cli\n"
        "demo = typer.Typer()\n"
        "@demo.command()\n"
        "def main() -> None:\n"
        "    typer.echo('out ≤ → log₁₀')\n"
        "    typer.echo('err ≤ → log₁₀', err=True)\n"
        "cli.app = demo\n"
        "cli.run()\n"
    )
    out = run_child(["-c", script])
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    assert out.stdout.decode("utf-8").strip() == "out ≤ → log₁₀"
    assert out.stderr.decode("utf-8").strip() == "err ≤ → log₁₀"


def test_F_X_2_d379_without_run_the_same_output_crashes() -> None:
    """The control: the bare app on a cp1252 pipe fails, so the tests above are not vacuous."""
    script = (
        "import typer\n"
        "demo = typer.Typer()\n"
        "@demo.command()\n"
        "def main() -> None:\n"
        "    typer.echo('≤')\n"
        "demo()\n"
    )
    out = run_child(["-c", script])
    assert out.returncode != 0
    assert b"UnicodeEncodeError" in out.stderr


def test_F_X_2_d379_a_stream_without_reconfigure_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A test runner's capture has no `reconfigure`; setting the encoding must not break it."""
    fake_out, fake_err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)
    cli.utf8_output()
    assert sys.stdout is fake_out and sys.stderr is fake_err
