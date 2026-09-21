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
    check_session,
    check_single_head,
    load_ownership,
    parse_ids,
    read_migrations,
    stream_of_folder,
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
    assert rules.supervisor is not None
    assert rules.supervisor.decisions == ((355, 359), (600, 699))
    assert rules.streams["A"].branch_prefix == "a/" and rules.streams["B"].branch_prefix == "b/"
    assert rules.streams["A"].decisions == ((360, 379),)
    assert rules.streams["A"].pending == (40, 59)
    # D-372: stream B's first range is used up, so it holds two
    assert rules.streams["B"].decisions == ((380, 399), (700, 799))
    assert rules.streams["B"].pending == (60, 79)
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
    """D-355 keeps its ranges for the supervisor; whichever stream carries one may add it."""
    existing = ["| D-354 | x |"]
    for stream in ("A", "B"):
        for number in (355, 357, 359, 600, 650, 699):
            assert check_ids(stream, [f"| D-{number} | supervisor |"], existing, rules) == []
    # the ranges are decisions only: P-357 is still judged against the stream's pending range
    assert check_ids("A", ["| P-357 | not a decision |"], existing, rules) != []
    assert check_ids("A", ["| P-600 | not a decision |"], existing, rules) != []
    # just outside them, the stream range applies again
    for number in (354, 599, 700):
        out = check_ids("A", [f"| D-{number} | outside |"], [], rules)
        assert len(out) == 1, number
        assert "the supervisor's range is D-355 … D-359 and D-600 … D-699" in out[0]
    # and a supervisor id is still checked for duplicates
    assert check_ids("A", ["| D-357 | dup |"], ["| D-357 | already |"], rules) != []


def test_F_X_9_d600_range_accepts_from_either_stream_and_still_catches_duplicates(
    rules: Ownership,
) -> None:
    """The second supervisor range, added when D-355 … D-359 was used up."""
    existing = ["| D-600 | already taken |"]
    for stream in ("A", "B", None):
        assert check_ids(stream, ["| D-601 | new supervisor decision |"], [], rules) == []
        dup = check_ids(stream, ["| D-600 | same id again |"], existing, rules)
        assert len(dup) == 1 and "duplicate id" in dup[0], stream
    # twice within one branch is a duplicate too
    twice = check_ids("A", ["| D-605 | a |", "| D-605 | b |"], [], rules)
    assert any("duplicate id" in p for p in twice)


def test_F_X_9_supervisor_ranges_accept_one_pair_or_a_list(tmp_path: Path) -> None:
    """The YAML may give a single ``[lo, hi]`` pair or a list of them."""
    base: dict[str, Any] = {
        "streams": {
            "A": {"name": "a", "branch_prefix": "a/", "decisions": [1, 9], "pending": [1, 9]}
        },
        "owners": {},
    }
    path = tmp_path / "ownership.yaml"
    path.write_text(yaml.safe_dump({**base, "supervisor": {"decisions": [20, 29]}}), "utf-8")
    one = load_ownership(path)
    assert one.supervisor is not None and one.supervisor.decisions == ((20, 29),)
    assert one.supervisor.covers("D", 25) and not one.supervisor.covers("D", 30)
    path.write_text(
        yaml.safe_dump({**base, "supervisor": {"decisions": [[20, 29], [40, 49]]}}), "utf-8"
    )
    two = load_ownership(path)
    assert two.supervisor is not None and two.supervisor.decisions == ((20, 29), (40, 49))
    assert two.supervisor.covers("D", 45) and not two.supervisor.covers("D", 35)
    path.write_text(yaml.safe_dump({**base, "supervisor": {"decisions": [[29, 20]]}}), "utf-8")
    with pytest.raises(ConfigError, match="inverted"):
        load_ownership(path)
    path.write_text(yaml.safe_dump({**base, "supervisor": {"decisions": []}}), "utf-8")
    with pytest.raises(ConfigError, match="at least one decision range"):
        load_ownership(path)


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


# -- D-357 (1) amended: every session in its own worktree ------------------------------------
def test_F_X_9_d357_folders_are_recorded_for_both_streams(rules: Ownership) -> None:
    assert rules.streams["A"].folder == "StrategyFactory"
    assert rules.streams["B"].folder == "StrategyFactory_B"
    for path in ("D:/x/StrategyFactory", "/home/u/StrategyFactory", "StrategyFactory"):
        assert stream_of_folder(path, rules) == "A", path
    assert stream_of_folder("D:/x/StrategyFactory_B", rules) == "B"
    assert stream_of_folder("D:/x/StrategyFactory_T11", rules) is None  # an own worktree
    assert stream_of_folder("D:\\x\\StrategyFactory", rules) == "A"  # Windows separators


def test_F_X_9_d357_a_stream_in_its_own_folder_is_fine(rules: Ownership) -> None:
    assert check_session("D:/x/StrategyFactory", "a/T11-parity", rules, "A") == []
    assert check_session("D:/x/StrategyFactory_B", "b/T04i", rules, "B") == []
    # a grandfathered branch name is still fine in the right folder
    assert check_session("D:/x/StrategyFactory", "docs/batch3-parity", rules, "A") == []


def test_F_X_9_d357_a_session_may_not_sit_in_another_streams_folder(rules: Ownership) -> None:
    problems = check_session("D:/x/StrategyFactory_B", "a/T11-parity", rules, "A")
    assert len(problems) == 1
    assert "belongs to stream B" in problems[0] and "do not own" in problems[0]
    other = check_session("D:/x/StrategyFactory", "b/T04i", rules, "B")
    assert any("belongs to stream A" in p for p in other)


def test_F_X_9_d357_the_spawned_session_incident_is_caught(rules: Ownership) -> None:
    """The real 2026-09-21 case: a spawned session in stream A's folder on its own branch."""
    problems = check_session("D:/x/StrategyFactory", "a/fix-metrics-fixture-prices", rules, None)
    assert problems, "a spawned session in stream A's folder must fail the check"
    assert any("needs its own worktree" in p for p in problems)
    assert any("git worktree add" in p for p in problems)
    # the same session in a worktree of its own is fine
    assert check_session("D:/x/wt_fix", "a/fix-metrics-fixture-prices", rules, None) == []


def test_F_X_9_d357_a_scratch_worktree_is_allowed(rules: Ownership) -> None:
    """A folder no stream owns is a worktree of the session's own -- exactly what D-357 asks."""
    assert check_session("D:/x/wt_T11", "a/T11-parity", rules, "A") == []
    assert check_session("D:/x/somewhere_else", "b/T04i", rules, "B") == []


def test_F_X_9_d357_a_detached_head_is_caught(rules: Ownership) -> None:
    """`git checkout <sha>` in somebody else's folder leaves exactly this state."""
    for stream in ("A", None):
        problems = check_session("D:/x/wt_T11", "", rules, stream)
        assert any("detached HEAD" in p for p in problems), stream
    # and in a stream's own folder it is still wrong: a session works on its own branch
    assert any("detached HEAD" in p for p in check_session("D:/x/StrategyFactory", "", rules, "A"))


def test_F_X_9_d357_a_helper_that_names_its_stream_has_its_branch_checked(
    rules: Ownership,
) -> None:
    """Naming the stream buys the prefix check; it still does not open that stream's folder."""
    assert check_session("D:/x/wt_fix", "a/fix-metrics", rules, "A") == []
    foreign = check_session("D:/x/wt_fix", "b/T04i", rules, "A")
    assert len(foreign) == 1 and "belongs to stream B, not stream A" in foreign[0]
    assert any(
        "needs its own worktree" in p
        for p in check_session("D:/x/StrategyFactory", "a/fix-metrics", rules, None)
    )


def test_F_X_9_d357_branch_prefix_must_match_the_stream(rules: Ownership) -> None:
    problems = check_session("D:/x/StrategyFactory", "b/T04i", rules, "A")
    assert any("belongs to stream B, not stream A" in p for p in problems)
    assert check_session("D:/x/StrategyFactory", "a/T11", rules, "Z") == [
        "unknown stream 'Z'; known: ['A', 'B']"
    ]


def test_F_X_9_d357_session_cli_passes_in_its_own_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(
        "strategy_factory.core.cli_streams._git",
        lambda *a: "D:/x/StrategyFactory_T11\n" if a[0] == "rev-parse" else "a/T11-parity\n",
    )
    result = CliRunner().invoke(app, ["streams", "session"])
    assert result.exit_code == 0, result.output
    assert "own worktree" in result.output


def test_F_X_9_d357_session_cli_fails_in_another_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(
        "strategy_factory.core.cli_streams._git",
        lambda *a: "D:/x/StrategyFactory\n" if a[0] == "rev-parse" else "a/fix-something\n",
    )
    result = CliRunner().invoke(app, ["streams", "session"])
    assert result.exit_code == 1
    assert "FAIL session setup" in result.output
    assert "Do NOT switch branches" in result.output


def test_F_X_9_d357_protocol_states_the_worktree_rule() -> None:
    """The rule must be written down where a session reads it, not only in code."""
    protocol = (REPO / "docs" / "streams" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "own git worktree" in protocol
    assert "may never switch the checkout of a folder it does not own" in protocol
    assert "sfac streams session" in protocol  # the session-start check
    assert "git worktree add" in protocol
    log = (REPO / "docs" / "decisions" / "decisions_log.md").read_text(encoding="utf-8")
    d357 = next(line for line in log.splitlines() if line.startswith("| D-357 |"))
    assert "own git worktree" in d357 and "spawned" in d357


# -- D-369: an amendment in place is not a duplicate -----------------------------------------
def test_F_X_9_d369_an_amended_row_is_not_a_duplicate(rules: Ownership) -> None:
    existing = ["| D-357 | old text |", "| D-356 | x |"]
    amended = ["| D-357 | new text |"]
    removed = ["| D-357 | old text |"]
    assert check_ids("A", amended, existing, rules, removed) == []
    # without the removal it is still a second row with the same id
    assert any("duplicate id" in p for p in check_ids("A", amended, existing, rules))
    # an amendment still has to pass the range check: stream A may not rewrite a D-380 row
    foreign = check_ids(
        "A", ["| D-380 | rewritten |"], ["| D-380 | old |"], rules, ["| D-380 | old |"]
    )
    assert len(foreign) == 1 and "outside stream A's range" in foreign[0]


def test_F_X_9_d369_a_deleted_row_always_fails(rules: Ownership) -> None:
    problems = check_ids("A", [], ["| D-356 | x |"], rules, ["| D-356 | x |"])
    assert len(problems) == 1
    assert "removed from the log" in problems[0] and "never deleted" in problems[0]
    # a grandfathered branch may not delete rows either
    assert check_ids(None, [], ["| D-356 | x |"], rules, ["| D-356 | x |"]) != []


def test_F_X_9_d369_this_branch_amends_d357_and_passes_the_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must accept exactly what this branch does to D-357 (1)."""
    monkeypatch.chdir(REPO)
    old = "| D-357 | **Stream protocol** old text | accepted |"
    new = "| D-357 | **Stream protocol** amended text | accepted |"
    monkeypatch.setattr("strategy_factory.core.cli_streams.added_rows", lambda base, f: [new])
    monkeypatch.setattr("strategy_factory.core.cli_streams.removed_rows", lambda base, f: [old])
    monkeypatch.setattr("strategy_factory.core.cli_streams.base_rows", lambda base, f: [old])
    monkeypatch.setattr("strategy_factory.core.cli_streams.changed_paths", lambda base: [])
    result = CliRunner().invoke(
        app, ["streams", "check", "--base", "HEAD", "--branch", "a/protocol-worktrees"]
    )
    assert result.exit_code == 0, result.output
    assert "ok   decision / pending ids" in result.output


def test_F_X_9_d369_an_unprefixed_branch_may_not_amend(rules: Ownership) -> None:
    """No range check applies to a grandfathered branch, so an amendment there is unguarded."""
    problems = check_ids(
        None, ["| D-380 | rewritten |"], ["| D-380 | old |"], rules, ["| D-380 | old |"]
    )
    assert len(problems) == 1 and "may not amend" in problems[0]
    # it may still add a new row in any range, as before
    assert check_ids(None, ["| D-380 | new |"], ["| D-356 | x |"], rules) == []


def test_F_X_9_d369_a_stream_may_not_amend_another_streams_row(rules: Ownership) -> None:
    amend_b = check_ids(
        "A", ["| D-380 | rewritten |"], ["| D-380 | old |"], rules, ["| D-380 | old |"]
    )
    assert len(amend_b) == 1 and "outside stream A's range" in amend_b[0]
    amend_a = check_ids(
        "B", ["| P-44 | rewritten |"], ["| P-44 | old |"], rules, ["| P-44 | old |"]
    )
    assert len(amend_a) == 1 and "outside stream B's range" in amend_a[0]
    # its own rows are fine
    assert (
        check_ids("A", ["| D-360 | amended |"], ["| D-360 | old |"], rules, ["| D-360 | old |"])
        == []
    )


def test_F_X_9_d369_a_supervisor_row_may_be_amended_by_either_stream(rules: Ownership) -> None:
    """What this branch does to D-357. The guard allows it; the supervisor's word authorises it.

    Documented as a stated limit of D-369: the guard cannot tell an instructed amendment of a
    supervisor row from an uninstructed one, exactly as it cannot for a newly added one.
    """
    for stream in ("A", "B"):
        for number in (357, 600):
            row_old = [f"| D-{number} | old |"]
            row_new = [f"| D-{number} | amended |"]
            assert check_ids(stream, row_new, row_old, rules, row_old) == [], (stream, number)


def test_F_X_9_d369_removed_rows_reads_real_git_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git diff -U0` opens each file with `--- a/<path>`; that is a header, not a removed row.

    Built on a throw-away repository rather than on this one's history, so the test says the
    same thing whatever branch it runs on.
    """
    from strategy_factory.core.cli_streams import added_rows, removed_rows

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    def write(*rows: str) -> None:
        table.write_text("\n".join(rows) + "\n", encoding="utf-8")

    folder = tmp_path / "docs" / "decisions"
    folder.mkdir(parents=True)
    table = folder / "decisions_log.md"
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    write("| ID | Decision |", "| D-357 | old text |", "| D-358 | untouched |")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("branch", "base")
    # one amended row, one new row, one row left alone
    write(
        "| ID | Decision |",
        "| D-357 | amended text |",
        "| D-358 | untouched |",
        "| D-369 | new |",
    )
    git("add", "-A")
    git("commit", "-qm", "amend D-357, add D-369")

    monkeypatch.chdir(tmp_path)
    files = ("docs/decisions/decisions_log.md",)
    raw = subprocess.run(
        ["git", "diff", "-U0", "base..HEAD", "--", *files],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert any(line.startswith("--- ") for line in raw.splitlines()), "no file header to ignore"
    assert any(line.startswith("+++ ") for line in raw.splitlines())

    removed, added = removed_rows("base", files), added_rows("base", files)
    assert not any(line.startswith(("-", "+")) for line in removed + added)  # no header leaked
    assert parse_ids(removed) == [("D", 357)]
    assert parse_ids(added) == [("D", 357), ("D", 369)]
    # and the guard reads that as an amendment plus a new row, not as two duplicates
    rules = load_ownership(REPO / DEFAULT_OWNERSHIP)
    assert check_ids("A", added, ["| D-357 | old text |"], rules, removed) == []


# -- D-372: a stream's own second decision range ---------------------------------------------
def written(folder: Path, spec: dict[str, Any]) -> Ownership:
    """An ownership file built from ``spec``, loaded the way the guard loads the real one."""
    path = folder / "ownership.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return load_ownership(path)


def test_F_X_9_d372_stream_b_may_use_its_second_range(rules: Ownership) -> None:
    existing = ["| D-399 | the last of the first range |"]
    for number in (700, 750, 799):
        assert check_ids("B", [f"| D-{number} | stream B |"], existing, rules) == [], number
    # and the first range still works
    assert check_ids("B", ["| D-385 | still fine |"], existing, rules) == []


def test_F_X_9_d372_the_second_range_is_still_stream_bs_own(rules: Ownership) -> None:
    """The point of D-372: a second range is not a second *supervisor* range."""
    for number in (700, 750, 799):
        problems = check_ids("A", [f"| D-{number} | stream A reaching |"], [], rules)
        assert len(problems) == 1, number
        assert "outside stream A's range" in problems[0]
        # the message names every range stream A holds, and the supervisor's for contrast
        assert "D-360 … D-379" in problems[0]
        assert "D-600 … D-699" in problems[0]
    # ... while a supervisor number is still accepted from either stream
    for stream in ("A", "B"):
        assert check_ids(stream, ["| D-650 | supervisor |"], [], rules) == []


def test_F_X_9_d372_the_message_names_every_range_a_stream_holds(rules: Ownership) -> None:
    problems = check_ids("B", ["| D-500 | neither range |"], [], rules)
    assert len(problems) == 1
    assert "outside stream B's range D-380 … D-399 and D-700 … D-799" in problems[0]


def test_F_X_9_d372_pending_ranges_are_unchanged(rules: Ownership) -> None:
    """A `P-` number always belongs to the stream that raised the question, so P-700 is not one."""
    for stream in ("A", "B"):
        problems = check_ids(stream, ["| P-700 | not a pending number |"], [], rules)
        assert len(problems) == 1, stream
        assert "outside stream" in problems[0] and "P-" in problems[0]
    assert check_ids("B", ["| P-65 | stream B |"], [], rules) == []
    assert check_ids("A", ["| P-45 | stream A |"], [], rules) == []


def test_F_X_9_d372_duplicates_are_still_rejected_in_the_new_range(rules: Ownership) -> None:
    existing = ["| D-700 | already taken |"]
    dup = check_ids("B", ["| D-700 | again |"], existing, rules)
    assert any("duplicate id" in problem for problem in dup)
    twice = check_ids("B", ["| D-701 | a |", "| D-701 | b |"], [], rules)
    assert any("duplicate id" in problem for problem in twice)
    # an amendment in the second range still behaves like one (D-369)
    assert check_ids("B", ["| D-700 | amended |"], existing, rules, existing) == []
    assert any(
        "may not amend" in problem
        for problem in check_ids(None, ["| D-700 | amended |"], existing, rules, existing)
    )


def test_F_X_9_d372_one_pair_is_still_a_valid_range(tmp_path: Path) -> None:
    """Every ownership file written before D-372 keeps working: a bare `[lo, hi]` is one range."""
    rules = written(
        tmp_path,
        {
            "supervisor": {"decisions": [355, 359]},  # a single pair, the pre-D-600 form
            "streams": {
                "A": {
                    "name": "a",
                    "branch_prefix": "a/",
                    "decisions": [360, 379],
                    "pending": [40, 59],
                },
            },
            "owners": {},
        },
    )
    assert rules.supervisor is not None
    assert rules.supervisor.decisions == ((355, 359),)
    assert rules.streams["A"].decisions == ((360, 379),)
    assert check_ids("A", ["| D-365 | fine |"], [], rules) == []
    assert check_ids("A", ["| D-700 | not granted here |"], [], rules) != []


def test_F_X_9_d372_an_inverted_or_empty_range_is_refused(tmp_path: Path) -> None:
    def spec(decisions: Any) -> dict[str, Any]:
        return {
            "streams": {
                "A": {
                    "name": "a",
                    "branch_prefix": "a/",
                    "decisions": decisions,
                    "pending": [40, 59],
                }
            },
            "owners": {},
        }

    for bad in ([[700, 690]], [[380, 399], [799, 700]], []):
        with pytest.raises(ConfigError):
            written(tmp_path, spec(bad))
