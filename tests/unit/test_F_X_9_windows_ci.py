"""D-800 (P-54): a Windows job on every pull request -- the fast suite only, nothing else.

The scope is a supervisor decision with a cost ceiling, so it is pinned here: widening the job
(a database, parity/oracle/leakage, benchmarks, or running on every push too) is a change to
D-800, not a quiet edit of the workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def job() -> dict[str, Any]:
    workflow = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    jobs: dict[str, Any] = workflow["jobs"]
    return jobs["windows-fast"]  # type: ignore[no-any-return]


def test_F_X_9_d800_the_job_runs_on_windows_on_every_pull_request(job: dict[str, Any]) -> None:
    assert job["runs-on"] == "windows-latest"
    condition = job["if"]
    assert "github.event_name == 'pull_request'" in condition
    # not on every push as well: that would run it twice per PR and double its cost
    assert "'push'" not in condition and "schedule" not in condition


def test_F_X_9_d800_the_job_runs_the_fast_suite_only(job: dict[str, Any]) -> None:
    assert "services" not in job and "SFAC_DB_URL" not in str(job.get("env", {}))
    commands = [step["run"] for step in job["steps"] if "run" in step]
    pytest_runs = [c for c in commands if "pytest" in c]
    assert len(pytest_runs) == 1
    command = pytest_runs[0]
    assert '-m "not slow and not db"' in command
    for folder in ("tests/parity", "tests/oracle", "tests/leakage"):
        assert f"--ignore={folder}" in command, folder
    everything = " ".join(commands)
    for absent in ("bench", "alembic", "ruff", "mypy", "streams check"):
        assert absent not in everything, absent
