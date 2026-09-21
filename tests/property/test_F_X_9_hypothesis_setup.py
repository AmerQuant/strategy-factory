"""F-X.9: Hypothesis is installed and runs under the active profile."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


@given(st.integers(), st.integers())
def test_F_X_9_hypothesis_runs(a: int, b: int) -> None:
    assert a + b == b + a


def test_F_X_9_hypothesis_profile_loaded() -> None:
    assert settings.get_current_profile_name() in {"dev", "ci", "weekly"}


# -- D-368: the CI profiles and the weekly budget -------------------------------------------
def test_F_X_9_d368_the_per_pr_profile_is_derandomized_and_the_weekly_one_is_not() -> None:
    assert settings.get_profile("ci").derandomize is True
    weekly = settings.get_profile("weekly")
    assert weekly.derandomize is False
    assert weekly.database is None  # nothing persists on a runner; the pin is the memory
    assert weekly.print_blob is True


def test_F_X_9_d368_every_budget_goes_through_examples() -> None:
    """A literal budget (a number written straight into `@settings`) would override the weekly
    profile and silently keep that test at its per-PR budget in the weekly job."""
    import re
    from pathlib import Path

    tests = Path(__file__).resolve().parents[1]
    literal = re.compile(r"max_examples\s*=\s*\d")
    offenders = [
        f"{p.relative_to(tests)}:{i}"
        for p in sorted(tests.rglob("*.py"))
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if literal.search(line)
    ]
    assert offenders == [], offenders


def test_F_X_9_d368_the_budget_multiplier(monkeypatch) -> None:
    from fixtures.hypothesis_budget import MULTIPLIER_ENV, examples

    monkeypatch.delenv(MULTIPLIER_ENV, raising=False)
    assert examples(150) == 150  # per PR and on a laptop: unchanged
    monkeypatch.setenv(MULTIPLIER_ENV, "20")
    assert examples(150) == 3000
    monkeypatch.setenv(MULTIPLIER_ENV, "0")
    import pytest

    with pytest.raises(ValueError):
        examples(150)


def test_F_X_9_d368_the_weekly_job_is_scheduled_and_does_not_gate() -> None:
    """The workflow: a weekly cron runs the randomized profile with a multiplied budget, and the
    job runs on no pull request, so a failure reports without blocking a merge."""
    from pathlib import Path

    import yaml

    repo = Path(__file__).resolve().parents[2]
    wf = yaml.safe_load((repo / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML reads the key `on` as True
    crons = [c["cron"] for c in triggers["schedule"]]
    job = wf["jobs"]["weekly-hypothesis"]
    assert job["env"]["HYPOTHESIS_PROFILE"] == "weekly"
    assert int(job["env"]["HYPOTHESIS_BUDGET_MULTIPLIER"]) > 1
    weekly_cron = next(c for c in crons if c in job["if"])
    assert weekly_cron.split()[4] != "*", "the weekly job's cron must name a weekday"
    assert "pull_request" not in job["if"]
    assert "continue-on-error" not in job  # a failure must show; it gates nothing anyway
    # and the per-PR job neither runs on the schedule nor changes profile
    assert "schedule" in wf["jobs"]["checks"]["if"]
    assert wf["env"]["HYPOTHESIS_PROFILE"] == "ci"
