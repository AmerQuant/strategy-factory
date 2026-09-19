"""F-X.9: Hypothesis is installed and runs under the active profile."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


@given(st.integers(), st.integers())
def test_F_X_9_hypothesis_runs(a: int, b: int) -> None:
    assert a + b == b + a


def test_F_X_9_hypothesis_profile_loaded() -> None:
    assert settings.get_current_profile_name() in {"dev", "ci"}
