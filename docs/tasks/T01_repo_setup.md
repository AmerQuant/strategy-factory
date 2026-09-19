# T01 — Repository bootstrap

**Features:** F-X.9 (repo, CLAUDE.md, automated tests), F-X.10 (logging & errors) · **Priority:** MVP · **Depends on:** —

Read `CLAUDE.md`, `docs/design.md` §2, §3, §10, §12 and the two features in `docs/features.md` first.

## Scope

Create the skeleton only. **No domain logic** (no adapters, engine, registry tables). Those are later tasks.

### 1. Project & environment
- `uv init` style project, **src layout**, package `strategy_factory`, Python pinned to 3.12 (`.python-version`, `requires-python = ">=3.12,<3.13"`).
- Runtime dependencies (only these for now): `typer`, `pydantic`, `pyyaml`.
- Dev dependencies: `pytest`, `hypothesis`, `ruff`, `mypy`, `types-PyYAML`.
- Console script: `sfac = "strategy_factory.cli:app"`.

### 2. Package skeleton
Create the sub-packages from design §3, each with an `__init__.py` containing a one-line docstring describing its responsibility:
`core, data (with adapters/), costs, engine, components (indicators/, entries/, exits/, filters/, sizing/), metrics, baseline, diagnostics, robustness, stats, registry, gates, stages, pipeline, reports, evidence`.
`strategy_factory/__init__.py` exposes `__version__ = "0.1.0"`.

### 3. CLI (`cli.py`, Typer)
- `sfac --version` → prints version.
- `sfac info` → prints Python version, package version, platform, and resolved `SFAC_DATA_ROOT` / `SFAC_ARTIFACTS_ROOT` (from environment or `.env`; say "not set" if missing).
- Global `--log-level` option.

### 4. Logging & errors (F-X.10)
- `strategy_factory/core/logging.py`: stdlib `logging` setup with a consistent format that includes timestamp (UTC), level, logger name; a `get_logger(name)` helper.
- `strategy_factory/core/errors.py`: base exception `SfacError` and subclasses `ConfigError`, `DataError`, `HoldoutAccessError`, `RegistryError`. Messages must say which stage / symbol / config caused them when those are known (constructor accepts optional `stage`, `symbol`, `config_path`).

### 5. Configuration files
- `.env.example` with `SFAC_DATA_ROOT`, `SFAC_ARTIFACTS_ROOT`, `SFAC_DB_URL` (postgres URL matching docker-compose).
- `configs/` with empty placeholder folders and a `README.md` in each: `costs/`, `gates/`, `pipeline/`, plus `universe.yaml` containing only a comment header.
- `.gitignore`: `.venv/`, `__pycache__/`, `.env`, `data/`, `artifacts/`, `*.parquet`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.hypothesis/`.

### 6. Docker (registry DB only)
- `docker-compose.yml` with a single `postgres:16` service, named volume, port 5432, credentials from `.env` (with sensible defaults), healthcheck.
- Do **not** create tables (that is T03).

### 7. Quality tooling (in `pyproject.toml`)
- **ruff:** line length 100, target py312, rule sets `E, F, W, I, B, UP, SIM, RUF`; formatter enabled.
- **mypy:** `strict = true` for `strategy_factory.core`, `.data`, `.registry`, `.gates`; normal checking elsewhere; `ignore_missing_imports` only per-module where needed.
- **pytest:** `testpaths = ["tests"]`, markers `slow`, `parity`, `leakage`, `oracle`; default run excludes `slow`.
- Hypothesis: a `ci` profile with `deadline=None` and a fixed derandomization for CI.

### 8. Tests
- Folder structure from design §12: `tests/unit, property, parity, leakage, oracle, selftest, fixtures` (each with `__init__.py` or `conftest.py` as appropriate).
- `tests/unit/test_F_X_9_smoke.py`: package imports, `__version__` exists, every sub-package in §2 imports.
- `tests/unit/test_F_X_9_cli.py`: `sfac --version` and `sfac info` via Typer's `CliRunner`.
- `tests/unit/test_F_X_10_errors.py`: error messages include stage/symbol/config when given; `get_logger` returns configured logger.
- `tests/property/test_F_X_9_hypothesis_setup.py`: one trivial property test proving Hypothesis runs.

### 9. CI (`.github/workflows/ci.yml`)
- Trigger on push and pull_request. Ubuntu latest.
- Steps: checkout → `astral-sh/setup-uv` → `uv sync` → `ruff check` → `ruff format --check` → `mypy src` → `pytest -m "not slow"`.
- Separate nightly job (schedule) that runs `pytest -m slow` (it will have no tests yet — must still pass).

### 10. Docs
- `docs/adr/`: one file per ADR-001 … ADR-011 from design §14, each with Title / Status: Accepted / Decision (1–3 lines copied from the design table) / Date.
- `README.md` (English, short): what the project is, prerequisites (Windows: Git, uv, Docker Desktop), setup commands, pointer to `CLAUDE.md` and `docs/`.
- Do not modify `docs/spec`, `docs/design.*`, `docs/features.*` or `CLAUDE.md`.

### 11. Git
- `git init` if not already a repository; first commit on `main` with the existing docs + CLAUDE.md; then create branch `feat/T01-repo-setup` and commit the task work there. Do **not** push (the user adds the remote).

## Acceptance (all must pass locally on Windows)

```bash
uv sync
uv run sfac --version
uv run sfac info
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
docker compose config        # validates compose file (do not require the DB to be running)
```

## Review summary (end of task)

Report: files created (tree), dependencies added and why, output of each acceptance command (pass/fail + short excerpt), anything that differs from this task or the design, and open questions.
