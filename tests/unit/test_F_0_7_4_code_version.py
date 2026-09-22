"""F-0.7.4 / T10b (c): the run row stores the code version with a dirty flag.

``code_version`` is ``<sha>``, ``<sha>-dirty`` or ``unknown``. It is **stored, not hashed**:
a dirty working tree does not change ``config_hash``, because the config did not change --
but the marker says the run cannot be reproduced from the commit alone.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from fixtures.registry_db import schema_url
from sqlalchemy import Engine, select
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.config import PipelineConfig, config_hash
from strategy_factory.registry import tables as T
from strategy_factory.registry.writer import (
    DIRTY_SUFFIX,
    DIRTY_UNTRACKED_PATHS,
    RegistryWriter,
    code_version,
    git_dirty,
    git_sha,
)

CONFIG = {
    "pipeline": "t10b",
    "data_snapshots": {"SPY": {"1D": {"source": "alpaca", "snapshot_hash": "d" * 64}}},
}


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throw-away git checkout with one commit."""
    root = tmp_path / "checkout"
    root.mkdir()
    git("init", "-q", cwd=root)
    git("config", "user.email", "t@example.com", cwd=root)
    git("config", "user.name", "T", cwd=root)
    (root / "code.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "code.py", cwd=root)
    git("commit", "-qm", "first", cwd=root)
    return root


def test_F_0_7_4_clean_checkout_gives_the_bare_commit(repo: Path) -> None:
    sha = git_sha(repo)
    assert len(sha) == 40 and not git_dirty(repo)
    assert code_version(repo) == sha


def test_F_0_7_4_dirty_checkout_is_marked(repo: Path) -> None:
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    assert git_dirty(repo)
    assert code_version(repo) == f"{git_sha(repo)}{DIRTY_SUFFIX}"
    assert code_version(repo) != git_sha(repo)


@pytest.mark.parametrize("path", ["scratch.txt", "docs/note.md", "reports/out.html"])
def test_F_0_7_4_d352_untracked_files_outside_src_and_configs_are_clean(
    repo: Path, path: str
) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("notes\n", encoding="utf-8")
    assert not git_dirty(repo)
    assert code_version(repo) == git_sha(repo)


@pytest.mark.parametrize(
    "path",
    [
        "src/strategy_factory/components/entries/new_probe.py",
        "configs/costs/new_profile.yaml",
        "src/extra.py",
        "configs/nested/deep/thing.yaml",
    ],
)
def test_F_0_7_4_d352_untracked_files_under_src_or_configs_are_dirty(repo: Path, path: str) -> None:
    """D-352: component discovery and config loading read those, so they change results."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")
    assert git_dirty(repo)
    assert code_version(repo) == f"{git_sha(repo)}{DIRTY_SUFFIX}"


def test_F_0_7_4_d352_the_watched_paths_are_src_and_configs() -> None:
    assert DIRTY_UNTRACKED_PATHS == ("src/", "configs/")


def test_F_0_7_4_no_git_gives_unknown(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git_sha(plain) == "unknown"
    assert code_version(plain) == "unknown"


def test_F_0_7_4_the_dirty_flag_is_not_part_of_the_config_hash(tmp_path: Path) -> None:
    path = tmp_path / "u.yaml"
    path.write_text(yaml.safe_dump({"symbols": []}), encoding="utf-8")
    cfg = PipelineConfig.model_validate(
        {
            "universe": str(path),
            "symbols": ["SPY"],
            "timeframes": ["1D"],
            "stages": ["s01_edge"],
            "data_snapshots": CONFIG["data_snapshots"],
        }
    )
    canonical = cfg.canonical()
    assert "code_version" not in canonical  # stored on the run row, never hashed
    before = config_hash(cfg)
    assert config_hash(PipelineConfig.model_validate(canonical)) == before


@pytest.mark.db
def test_F_0_7_4_run_row_stores_the_code_version(
    registry_engine: Engine, monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    (repo / "code.py").write_text("x = 3\n", encoding="utf-8")
    dirty = code_version(repo)
    writer = RegistryWriter(registry_engine)
    given = writer.start_run(CONFIG, seed=1, code_version=dirty)
    default = writer.start_run(CONFIG, seed=1)
    with registry_engine.connect() as conn:
        rows = dict(
            conn.execute(select(T.pipeline_runs.c.id, T.pipeline_runs.c.code_version)).fetchall()  # type: ignore[arg-type]
        )
    assert rows[given] == dirty and rows[given].endswith(DIRTY_SUFFIX)
    # the default comes from this checkout: a sha, possibly marked dirty, never empty
    assert rows[default] == "unknown" or len(rows[default].removesuffix(DIRTY_SUFFIX)) == 40
    # the two runs share one config hash: the code version is not part of it
    with registry_engine.connect() as conn:
        hashes = set(conn.execute(select(T.pipeline_runs.c.config_hash)).scalars())
    assert len(hashes) == 1


@pytest.mark.db
def test_F_0_7_4_reproduce_marks_a_dirty_run(
    registry_engine: Engine, registry_schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = RegistryWriter(registry_engine)
    run_id = writer.start_run(CONFIG, seed=7, code_version=f"{'a' * 40}{DIRTY_SUFFIX}")
    with writer:
        writer.add_trials(
            [
                {
                    "run_id": run_id,
                    "stage": "s02_screen",
                    "family_id": "fam",
                    "spec_hash": "f" * 64,
                    "params": {"n": 1},
                }
            ]
        )
    with registry_engine.connect() as conn:
        trial_id = conn.execute(select(T.trials.c.id)).scalar_one()
    monkeypatch.setenv(
        "SFAC_DB_URL", schema_url(registry_schema).render_as_string(hide_password=False)
    )
    out = CliRunner().invoke(app, ["reproduce", "--trial", str(trial_id)])
    assert out.exit_code == 0, out.output
    assert "DIRTY checkout" in out.output
    assert "cost_inputs   : NOT RECORDED" in out.output  # this run predates the cost inputs


# -- P-52: git output is decoded as UTF-8, not with the locale codec -------------------------
def test_F_0_7_4_p52_git_output_is_decoded_as_utf8(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserted on the call, so it fails on CI's UTF-8 locale too, not only on Windows."""
    from strategy_factory.registry import writer

    seen: list[dict[str, Any]] = []
    real_run = subprocess.run

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(writer.subprocess, "run", spy)
    git_sha(repo)
    git_dirty(repo)
    assert len(seen) == 2
    for kwargs in seen:
        assert kwargs.get("encoding") == "utf-8" and kwargs.get("errors") == "replace"


def test_F_0_7_4_p52_a_non_ascii_untracked_path_still_marks_the_checkout_dirty(
    repo: Path,
) -> None:
    """The reproduced failure: `core.quotepath=false` and a Persian name under `src/`.

    UTF-8 for ``ف`` is D9 81; cp1252 has no character for 0x81, so on Windows the old
    decode failed in subprocess's reader thread and ``git_dirty`` returned ``False``.
    """
    git("config", "core.quotepath", "false", cwd=repo)
    (repo / "src").mkdir()
    (repo / "src" / "ف.py").write_text("x = 1\n", encoding="utf-8")
    assert git_dirty(repo)
    assert code_version(repo).endswith(DIRTY_SUFFIX)
