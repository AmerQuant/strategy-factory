"""The Hypothesis example budget, scaled for the weekly randomized job (D-368).

A test's own ``@settings(max_examples=...)`` overrides the active profile, so a profile alone
cannot give the weekly job a larger budget. Every property test therefore asks for its budget
through :func:`examples`, which multiplies it by ``HYPOTHESIS_BUDGET_MULTIPLIER`` -- 1 unless
the environment says otherwise, so a per-PR run and a laptop run are unchanged. The weekly job
sets it (``.github/workflows/ci.yml``); ``test_F_X_9_d368_every_budget_goes_through_examples`` keeps
a new test from escaping it with a literal.
"""

from __future__ import annotations

import os

MULTIPLIER_ENV = "HYPOTHESIS_BUDGET_MULTIPLIER"


def multiplier() -> int:
    raw = os.environ.get(MULTIPLIER_ENV, "1")
    value = int(raw)
    if value < 1:
        raise ValueError(f"{MULTIPLIER_ENV} must be a positive integer, got {raw!r}")
    return value


def examples(n: int) -> int:
    """``n`` examples, times the weekly multiplier (1 outside the weekly job)."""
    return n * multiplier()
