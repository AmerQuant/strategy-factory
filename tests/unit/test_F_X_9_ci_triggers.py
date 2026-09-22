"""D-801: `checks` runs once per PR update -- on `pull_request`, plus pushes to `main` only.

A push to a PR branch fires both `push` and `pull_request`; with `push` unfiltered, `checks`
ran twice per update for the same commit. Pinned so the duplication cannot come back quietly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def workflow() -> dict[Any, Any]:
    text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    loaded: dict[Any, Any] = yaml.safe_load(text)
    return loaded


def triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    on: dict[str, Any] = workflow.get("on", workflow.get(True))  # YAML 1.1 reads `on` as True
    return on


def test_F_X_9_d801_push_runs_only_on_main(workflow: dict[Any, Any]) -> None:
    assert triggers(workflow)["push"] == {"branches": ["main"]}


def test_F_X_9_d801_every_pull_request_is_still_checked(workflow: dict[Any, Any]) -> None:
    on = triggers(workflow)
    assert "pull_request" in on
    assert on["pull_request"] is None or "branches" not in on["pull_request"]
    assert "schedule" in workflow["jobs"]["checks"]["if"]  # checks: every event but cron
