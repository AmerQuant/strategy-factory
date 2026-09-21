"""Shared pytest configuration: Hypothesis profiles."""

from __future__ import annotations

import os

from fixtures.hypothesis_budget import examples
from hypothesis import settings

# `ci`: no per-example deadline (shared runners are slow and noisy) and derandomized so a
# CI failure reproduces exactly. Selected with HYPOTHESIS_PROFILE=ci (set in the workflow).
settings.register_profile("ci", deadline=None, derandomize=True)
# `weekly` (D-368): the scheduled job's search for NEW falsifying examples -- randomized, a
# budget multiplied by HYPOTHESIS_BUDGET_MULTIPLIER (the default budget here, and every test's
# own through `examples()`), no example database (the runner keeps none), and a reproduction
# blob printed with any failure. A failure found this way is pinned as an `@example` on its
# test, which is what makes the per-PR `ci` profile see it from then on.
settings.register_profile(
    "weekly", deadline=None, derandomize=False, database=None, print_blob=True,
    max_examples=examples(100),
)  # fmt: skip
settings.register_profile("dev")
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
