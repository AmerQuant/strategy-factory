"""D-355 / D-357: the three stream guards — path ownership, ID discipline, one Alembic head."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import ConfigError
from strategy_factory.core.streams import (
    DEFAULT_OWNERSHIP,
    Ownership,
    alembic_heads,
    check_all,
    check_ids,
    check_paths,
    check_single_head,
    load_ownership,
    parse_ids,
    read_migrations,
)

REPO = Path(__file__).resolve().parents[2]
ALEMBIC = REPO / "src" / "strategy_factory" / "registry" / "alembic" / "versions"


@pytest.fixture
def rules() -> Ownership:
    return load_ownership(REPO / DEFAULT_OWNERSHIP)


def migration(revision: str, down: str | None) -> str:
    down_line = "None" if down is None else f'"{down}"'
    return f'revision: str = "{revision}"\ndown_revision: str | None = {down_line}\n'


# -- the repo's own ownership file -----------------------------------------------------------
def test_F_X_9_repo_ownership_file_is_valid(rules: Ownership) -> None:
    assert set(rules.streams) == {"A", "B"}
    assert rules.supervisor is not None and rules.supervisor.decisions == (355, 359)
    assert rules.streams["A"].branch_prefix == "a/" and rules.streams["B"].branch_prefix == "b/"
    assert rules.streams["A"].decisions == (360, 379) and rules.streams["A"].pending == (40, 59)
    assert rules.streams["B"].decisions == (380, 399) and rules.streams["B"].pending == (60, 79)
    assert rules.append_only == (
        "docs/decisions/decisions_log.md",
        "docs/decisions/pending.md",
    )
    # the stream-A-only paths of D-357 (2)
    for path in (
        "HANDOFF.md",
        "CLAUDE.md",
        "docs/STANDING_PROMPT.md",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "uv.lock",
        "src/strategy_factory/registry/alembic/versions/0001_initial.py",
        "configs/universe.yaml",
        "src/strategy_factory/components/base.py",
    ):
        assert rules.owner_of(path) == "A", path
    assert rules.owner_of("configs/universe/us_equity_daily.csv") == "B"
    for shared in ("docs/tasks/T11_tradingview_parity.md", "tests/unit/x.py", "src/x.py"):
        assert rules.owner_of(shared) is None, shared


def test_F_X_9_longest_prefix_wins(rules: Ownership) -> None:
    """`configs/universe/` is B's, `configs/universe.yaml` is A's (D-394)."""
    assert rules.owner_of("configs/universe.yaml") == "A"
    assert rules.owner_of("configs/universe/dukascopy.csv") == "B"
    assert rules.owner_of("configs/costs/moneta/mapping.yaml") is None


def test_F_X_9_invalid_ownership_files_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "ownership.yaml"
    base: dict[str, Any] = {
        "streams": {
            "A": {"name": "a", "branch_prefix": "a/", "decisions": [1, 9], "pending": [1, 9]}
        },
        "owners": {},
    }
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    assert load_ownership(path).streams["A"].name == "a"
    with pytest.raises(ConfigError, match="not found"):
        load_ownership(tmp_path / "missing.yaml")
    bad = {**base, "owners": {"x": "Z"}}
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown streams"):
        load_ownership(path)
    inverted = {
        "streams": {
            "A": {"name": "a", "branch_prefix": "a/", "decisions": [9, 1], "pending": [1, 9]}
        },
        "owners": {},
    }
    path.write_text(yaml.safe_dump(inverted), encoding="utf-8")
    with pytest.raises(ConfigError, match="inverted"):
        load_ownership(path)


# -- guard 1: path ownership -----------------------------------------------------------------
def test_F_X_9_guard_paths_refuses_the_other_streams_paths(rules: Ownership) -> None:
    problems = check_paths("B", ["HANDOFF.md", "docs/tasks/x.md"], rules)
    assert len(problems) == 1
    assert "HANDOFF.md" in problems[0] and "owned by stream A" in problems[0]
    assert "P- question" in problems[0]
    assert check_paths("A", ["HANDOFF.md", "configs/universe.yaml"], rules) == []
    assert len(check_paths("A", ["configs/universe/dukascopy.csv"], rules)) == 1
    assert check_paths("A", ["tests/unit/x.py", "src/strategy_factory/engine/api.py"], rules) == []


def test_F_X_9_guard_paths_skips_grandfathered_branches(rules: Ownership) -> None:
    """Branches without a prefix predate D-357 and are not checked."""
    assert rules.stream_of_branch("feat/T06b-moneta-costs") is None
    assert rules.stream_of_branch("docs/batch3-data") is None
    assert rules.stream_of_branch("a/T11-parity") == "A"
    assert rules.stream_of_branch("b/T04f-alpaca-reference") == "B"
    assert check_paths(None, ["HANDOFF.md", "configs/universe/x.csv"], rules) == []


# -- guard 2: ID discipline ------------------------------------------------------------------
def test_F_X_9_parse_ids() -> None:
    rows = [
        "| D-357 | Stream protocol | accepted |",
        "|P-40 | blocking | open |",
        "| D-9999 | far future | accepted |",
        "not a row",
        "| something | else |",
    ]
    assert parse_ids(rows) == [("D", 357), ("P", 40), ("D", 9999)]


def test_F_X_9_guard_ids_range_and_duplicates(rules: Ownership) -> None:
    existing = ["| D-356 | x |", "| P-38 | y |"]
    assert check_ids("A", ["| D-360 | new |", "| P-40 | new |"], existing, rules) == []
    out_of_range = check_ids("A", ["| D-380 | wrong stream |"], existing, rules)
    assert len(out_of_range) == 1 and "outside stream A's range" in out_of_range[0]
    assert "D-360" in out_of_range[0].replace("D-380", "")  # the range is named
    b_ok = check_ids("B", ["| D-380 | right stream |", "| P-60 | right |"], existing, rules)
    assert b_ok == []
    dup = check_ids("A", ["| D-356 | duplicate |"], existing, rules)
    assert any("duplicate id" in p for p in dup)
    twice = check_ids("A", ["| D-360 | a |", "| D-360 | b |"], existing, rules)
    assert any("duplicate id" in p for p in twice)
    # a grandfathered branch is checked for duplicates only
    assert check_ids(None, ["| D-380 | any range |"], existing, rules) == []
    assert check_ids(None, ["| D-356 | duplicate |"], existing, rules) != []


def test_F_X_9_supervisor_decisions_are_allowed_from_any_stream(rules: Ownership) -> None:
    """D-355 keeps D-355 … D-359 for the supervisor; whichever stream carries one may add it."""
    existing = ["| D-354 | x |"]
    for stream in ("A", "B"):
        for number in (355, 357, 359):
            assert check_ids(stream, [f"| D-{number} | supervisor |"], existing, rules) == []
    # the range is decisions only: P-357 is still judged against the stream's pending range
    assert check_ids("A", ["| P-357 | not a decision |"], existing, rules) != []
    # just outside it, the stream range applies again
    out = check_ids("A", ["| D-354 | too low |"], [], rules)
    assert len(out) == 1 and "the supervisor's range is D-355 … D-359" in out[0]
    # and a supervisor id is still checked for duplicates
    assert check_ids("A", ["| D-357 | dup |"], ["| D-357 | already |"], rules) != []


# -- guard 3: one Alembic head ---------------------------------------------------------------
def test_F_X_9_guard_alembic_single_head() -> None:
    one = {"0001.py": migration("0001_initial", None)}
    assert alembic_heads(one) == ["0001_initial"]
    assert check_single_head(one) == []
    chain = {**one, "0002.py": migration("0002_next", "0001_initial")}
    assert alembic_heads(chain) == ["0002_next"]
    assert check_single_head(chain) == []
    forked = {**chain, "0002b.py": migration("0002_other", "0001_initial")}
    assert alembic_heads(forked) == ["0002_next", "0002_other"]
    problems = check_single_head(forked)
    assert len(problems) == 1 and "2 heads" in problems[0] and "in parallel" in problems[0]
    assert check_single_head({}) == ["no Alembic migrations found"]
    with pytest.raises(ConfigError, match="no `revision"):
        alembic_heads({"broken.py": "nothing here"})


def test_F_X_9_repo_migrations_have_one_head() -> None:
    migrations = read_migrations(ALEMBIC)
    assert migrations, "the repo must have migrations"
    assert check_single_head(migrations) == []
    assert alembic_heads(migrations) == ["0001_initial"]


def test_F_X_9_repo_alembic_heads_matches_alembic_itself() -> None:
    """The guard's parser must agree with Alembic (the guard runs without a database)."""
    out = subprocess.run(
        ["uv", "run", "alembic", "heads"], cwd=REPO, capture_output=True, text=True, timeout=180
    )
    assert out.returncode == 0, out.stderr
    reported = [line.split()[0] for line in out.stdout.splitlines() if line.strip()]
    assert reported == alembic_heads(read_migrations(ALEMBIC))


# -- all three, and the CLI ------------------------------------------------------------------
def test_F_X_9_check_all_reports_every_guard(rules: Ownership) -> None:
    results = check_all(
        "b/T04f-alpaca-reference",
        ["HANDOFF.md"],
        ["| D-360 | wrong range for B |"],
        ["| D-356 | x |"],
        read_migrations(ALEMBIC),
        rules,
    )
    assert set(results) == {"paths", "ids", "alembic"}
    assert results["paths"] and results["ids"] and results["alembic"] == []


def test_F_X_9_streams_check_cli_on_this_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    result = CliRunner().invoke(app, ["streams", "check", "--base", "HEAD"])
    assert result.exit_code == 0, result.output
    assert "path ownership" in result.output and "single Alembic head" in result.output


def test_F_X_9_streams_check_cli_fails_on_a_foreign_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `b/` branch that changed HANDOFF.md must fail the CLI, not just the function."""
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(
        "strategy_factory.core.cli_streams.changed_paths", lambda base: ["HANDOFF.md"]
    )
    result = CliRunner().invoke(
        app, ["streams", "check", "--base", "HEAD", "--branch", "b/whatever"]
    )
    assert result.exit_code == 1
    assert "FAIL path ownership" in result.output and "HANDOFF.md" in result.output
