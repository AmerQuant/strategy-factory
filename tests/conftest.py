"""Shared pytest configuration: Hypothesis profiles."""

from __future__ import annotations

import os

from hypothesis import settings

# `ci`: no per-example deadline (shared runners are slow and noisy) and derandomized so a
# CI failure reproduces exactly. Selected with HYPOTHESIS_PROFILE=ci (set in the workflow).
settings.register_profile("ci", deadline=None, derandomize=True)
settings.register_profile("dev")
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
