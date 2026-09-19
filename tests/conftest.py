"""Shared pytest configuration: Hypothesis profiles and marker-selection behaviour."""

from __future__ import annotations

import os

import pytest
from hypothesis import settings

# `ci`: no per-example deadline (shared runners are slow and noisy) and derandomized so a
# CI failure reproduces exactly. Selected with HYPOTHESIS_PROFILE=ci (set in the workflow).
settings.register_profile("ci", deadline=None, derandomize=True)
settings.register_profile("dev")
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A marker selection that matches no tests (e.g. the nightly `-m slow` run before any
    slow tests exist) counts as a pass instead of pytest's exit code 5."""
    if exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED and session.config.option.markexpr:
        session.exitstatus = pytest.ExitCode.OK
