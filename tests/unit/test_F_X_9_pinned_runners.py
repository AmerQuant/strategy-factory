"""D-806: every CI job names an explicit runner image; no job uses a ``-latest`` label.

``ubuntu-latest`` migrates to Ubuntu 26 on 2026-10-19 and the Windows label moves on after it.
An OS change under the suite is ours to make, on a day we can watch the run -- so the labels are
pinned and this test fails if any job drifts back to a floating one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"


def runners() -> dict[str, str]:
    """``job name -> runs-on`` over every workflow file."""
    out: dict[str, str] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        workflow: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in workflow["jobs"].items():
            out[f"{path.name}:{name}"] = job["runs-on"]
    return out


def test_F_X_9_d806_every_job_is_scanned() -> None:
    """The guard is worthless if it silently finds no jobs."""
    found = runners()
    assert len(found) >= 4, found
    assert any(job.endswith(":windows-fast") for job in found), found


@pytest.mark.parametrize("job", sorted(runners()))
def test_F_X_9_d806_no_job_runs_on_a_floating_label(job: str) -> None:
    label = runners()[job]
    assert isinstance(label, str), f"{job}: a matrix or list needs its own pin check"
    assert not label.endswith("-latest"), (
        f"{job} runs on {label!r}: pin the image (D-806), e.g. ubuntu-24.04 or windows-2025, "
        "so an OS migration happens by our decision and not on GitHub's date"
    )


def test_F_X_9_d806_the_pins_are_the_images_we_measured_on() -> None:
    """The exact pins, so a change is deliberate and reviewed (D-806)."""
    assert set(runners().values()) == {"ubuntu-24.04", "windows-2025"}
