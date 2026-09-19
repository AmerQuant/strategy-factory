# T03 — Registry (PostgreSQL)

**Features:** F-0.7.1 (trial registry), F-0.7.2 (trial counts per search family), F-0.7.3 (gates, holdout, decisions), F-0.7.4 (reproducibility record — partial) · **Priority:** MVP · **Depends on:** T01 (on `main`)

**Parallel-work note:** this task runs in a separate git worktree while another session works on T04a–T04c. Touch only what this task needs. Expect later merge conflicts only in `pyproject.toml`, `uv.lock`, `cli.py` and `.env.example`; keep your changes there minimal and additive.

Read first: `CLAUDE.md`, `docs/design.md` §2 (ADR-004), §4, §7, and F-0.7.1–F-0.7.4 in `docs/features.md`.

## Decisions (fixed, ADR-004)
- PostgreSQL 16 in Docker (`docker-compose.yml` from T01).
- **SQLAlchemy Core** (not ORM), **psycopg 3**, **Alembic** for all schema changes.
- Bulk inserts of trials go through **COPY**.
- The connection string comes from `SFAC_DB_URL`. Never log it; it contains a password.

## Scope

### 1. Dependencies
Add `sqlalchemy`, `psycopg[binary]` and `alembic` (pinned in `uv.lock`). Nothing else without asking.

### 2. Schema (`registry/tables.py` + first Alembic migration)
The tables from design §7. Minimum columns:

- **`pipeline_runs`:** `id (uuid pk), config (jsonb), config_hash, code_version (git sha), seed, started_at, finished_at, status (running|done|failed|aborted), notes`
- **`data_snapshots`:** `snapshot_hash (pk), source, symbol, timeframe, is_reference, meta (jsonb), registered_at` — mirrors the catalog; no FK to files.
- **`splits`:** `id, symbol, timeframe, snapshot_hash, dev_start, dev_end, embargo_bars, holdout_start, holdout_end, expected_holdout_trades, created_at`; unique (symbol, timeframe, snapshot_hash).
- **`candidates`:** `id (text pk, content hash), parent_id (nullable, FK self), run_id (FK), symbol, timeframe, direction, edge_type, spec (jsonb), spec_hash, current_stage, status (active|rejected|approved|retired), created_at`
- **`trials`:** `id (bigserial), run_id (FK), stage, candidate_id (FK, nullable for stage-1 probes), family_id (text), spec_hash, params (jsonb), n_trades, net_profit, avg_annual_profit, avg_annual_dd_ystart, avg_annual_dd_peak, profit_dd_ratio, exposure, return_per_exposure, profit_factor, win_rate, expectancy_atr, extra (jsonb), created_at`
  - Indexes: `(run_id, stage)`, `(candidate_id)`, `(family_id)`.
- **`gate_results`:** `id, run_id, candidate_id, stage, criterion, metric_value, op, threshold, passed, critical, reason, created_at`
- **`artifacts`:** `id, run_id, candidate_id, stage, kind, path, schema_version, sha256, created_at`
- **`holdout_access`:** `id, candidate_id (unique), accessed_at, result (jsonb), consumed (bool, default true)`
- **`reports`:** `id, candidate_id, docx_path, prompt_version, spec_version, verify_passed, verify_result (jsonb), created_at`
- **`decisions`:** `id, candidate_id, analyst, decision (approve|reject|return), return_to_stage (nullable), reason (not null, non-empty), created_at`

Use `CHECK` constraints for the enumerations and for the non-empty `reason`.

### 3. Access layer (`registry/`)
- `engine.py`: create the SQLAlchemy engine from `SFAC_DB_URL`, with a clear `RegistryError` if the variable is missing or the DB is unreachable. The message must not contain the URL.
- `writer.py` — `RegistryWriter`:
  - `start_run(config, seed) -> run_id` (computes `config_hash`, reads the git SHA; `"unknown"` if not a git checkout), `finish_run(run_id, status)`
  - `upsert_candidate(candidate)`
  - `add_trials(rows)`: buffered; flushes at N rows (default 5000, configurable) or on `close()`/context exit, using psycopg COPY
  - `add_gate_results(...)`, `add_artifact(...)`, `add_report(...)`, `add_decision(...)` (rejects an empty reason)
  - `record_holdout_access(candidate_id, result)`: the **second call for the same candidate raises `HoldoutAccessError`**, enforced by the unique constraint in the DB, not only in Python
- `queries.py`:
  - `trial_count(candidate_id, include_lineage=True)` — F-0.7.2: counts the trials of the candidate **and all its ancestors** via a recursive CTE over `parent_id`
  - `trials_by_family(family_id)`
  - `candidate_lineage(candidate_id)`
  - `gate_history(candidate_id)`

### 4. Reproducibility record (F-0.7.4 — partial)
- Every trial must be traceable to `run_id` → (`config`, `config_hash`, `code_version`, `seed`) + `spec_hash` + `params` + the data snapshot hash (take it from `config`).
- `sfac reproduce --trial <id>`: loads everything needed and **prints the reproduction plan**. Actually re-running needs the engine (T08); mark this clearly as "partial — execution after T08".

### 5. CLI
- `sfac db upgrade`: `alembic upgrade head`.
- `sfac db status`: current revision, and row counts per table.

### 6. CI
Add a `postgres:16` **service container** to the CI job, set `SFAC_DB_URL` for tests, and run `alembic upgrade head` before pytest.

## Tests
- Mark DB tests `@pytest.mark.db`.
  - Locally they need `docker compose up -d`. If the DB is unreachable, skip them with a clear skip reason.
  - In CI they must run: add a CI step that fails the build if any `db` test was skipped.
- Each test runs in its own schema or transaction and cleans up after itself.

Cover each feature:
- **F-0.7.1:**
  - Round trip of each table.
  - COPY batch of 100k synthetic trials: report the time, and the row count must match.
  - The buffer flushes on `close()`.
- **F-0.7.2:** a lineage of 3 generations with trials at each level gives the correct counts, with and without lineage.
- **F-0.7.3:**
  - Gate results are stored with all fields.
  - A second holdout access raises `HoldoutAccessError`, even from a **separate connection** (proves the DB constraint).
  - A decision with an empty reason is rejected.
- **F-0.7.4:** `sfac reproduce --trial` prints a plan that contains config hash, code version, seed, spec hash, params and snapshot hash.
- **Migrations:** `upgrade head` → `downgrade base` → `upgrade head` works.
- **Secrets:** no log line and no exception message contains the DB password (use a fake URL).

## Acceptance
```
docker compose up -d
uv run sfac db upgrade
uv run sfac db status
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src ; uv run pytest
```
All must pass locally; CI green with the Postgres service. mypy strict clean for `strategy_factory.registry`. Report the 100k-trial COPY timing.

## Review summary
Write it to `docs/reviews/T03_review.md` on the branch. Include:
- the tables, with anything that differs from this task;
- the dependency versions;
- the COPY timing;
- how each acceptance criterion is tested;
- open questions.
