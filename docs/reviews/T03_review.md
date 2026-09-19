# T03 review — Registry (PostgreSQL)

**Features:** F-0.7.1, F-0.7.2, F-0.7.3, F-0.7.4 (partial) · **Branch:** `feat/T03-registry` (worktree `StrategyFactory_T03`, based on `7ddd838`) · **Status:** done

## Dependencies (pinned in `uv.lock`)
| package | version | pulled in |
|---|---|---|
| sqlalchemy | 2.0.54 | greenlet 3.5.6 |
| psycopg[binary] | 3.3.6 | psycopg-binary 3.3.6 |
| alembic | 1.20.0 | mako 1.4.1, markupsafe 3.0.3 |
Nothing else was added.

## Files
| file | content |
|---|---|
| `src/strategy_factory/registry/tables.py` | the 10 tables (SQLAlchemy Core `MetaData` with a naming convention) |
| `src/strategy_factory/registry/alembic/{env.py,script.py.mako,versions/0001_initial.py}` + `alembic.ini` | first migration (explicit `op.create_table`, not generated from `tables.py` at run time); `env.py` takes the URL from `SFAC_DB_URL` or an injected connection, never from the ini |
| `src/strategy_factory/registry/engine.py` | `make_engine` / `check_connection` / `db_url`; `RegistryError` without the URL |
| `src/strategy_factory/registry/writer.py` | `RegistryWriter` + frozen record models (`CandidateRecord`, `TrialRecord`, `GateResultRecord`, `SplitRecord`) |
| `src/strategy_factory/registry/queries.py` | `trial_count`, `trials_by_family`, `candidate_lineage`, `gate_history`, `reproduction_plan`, `format_plan` |
| `src/strategy_factory/registry/migrations.py` | `upgrade`, `downgrade`, `current_revision`, `head_revision`, `row_counts` |
| `src/strategy_factory/registry/cli.py` (+3 lines in `cli.py`) | `sfac db upgrade`, `sfac db status`, `sfac reproduce --trial <id>` |
| `.github/workflows/ci.yml` | `postgres:16` service, `SFAC_DB_URL`, `alembic upgrade head`, db tests, skip check |
| `pyproject.toml` | `db` pytest marker; mypy excludes the Alembic script folder (not importable modules) |
| `.env.example` | one comment line (port clash hint); no new variables |
| tests | `tests/fixtures/registry_db.py`, `tests/unit/conftest.py`, `test_F_0_7_1_registry.py` (8), `test_F_0_7_2_trial_counts.py` (1), `test_F_0_7_3_gates_holdout_decisions.py` (3), `test_F_0_7_4_reproduce.py` (1) — 11 of 13 are `@pytest.mark.db` |

## Tables
All columns from the task are present with these types: ids `uuid` (runs), `text` (candidate content hash), `bigint GENERATED … AS IDENTITY` (all other surrogate keys); timestamps `timestamptz` with `DEFAULT now()`; JSON columns `jsonb`; metrics `double precision`.

| table | constraints / indexes (beyond the task's column list) |
|---|---|
| pipeline_runs | `CHECK status IN (running, done, failed, aborted)`; `status` default `running`, `notes` default `''` |
| data_snapshots | pk `snapshot_hash`; `is_reference` default false |
| splits | `UNIQUE(symbol, timeframe, snapshot_hash)`; **FK `snapshot_hash → data_snapshots`**; `CHECK embargo_bars >= 0` |
| candidates | FK `parent_id → candidates.id`, FK `run_id`; `CHECK direction IN (long, short)`; `CHECK status IN (active, rejected, approved, retired)`; **`CHECK parent_id <> id`** |
| trials | FKs `run_id`, `candidate_id` (nullable); indexes `(run_id, stage)`, `(candidate_id)`, `(family_id)` |
| gate_results | FKs; `CHECK op IN (>=, <=, >, <, ==)`; index `(candidate_id)`; `critical` default false, `reason` default `''` |
| artifacts | FKs (`candidate_id` nullable); index `(candidate_id)` |
| holdout_access | **`UNIQUE(candidate_id)`**; `consumed` default true |
| reports | FK `candidate_id` |
| decisions | `CHECK decision IN (approve, reject, return)`; `CHECK length(btrim(reason)) > 0`; **`CHECK analyst <> ''`**; **`CHECK decision <> 'return' OR return_to_stage IS NOT NULL`** |

Differences from the task (additions only): the bold constraints above; `edge_type` has **no** CHECK (the edge-type list is still growing — addendum v0.1 adds PB/VS/FB/IM/OR); `data_snapshots` has no FK to files (as specified).

## Behaviour
- **Engine:** URL from `SFAC_DB_URL` (env or `.env`), `hide_parameters=True`, `pool_pre_ping`, `connect_timeout` 10 s (fail fast instead of hanging). Missing variable, invalid URL and unreachable DB each give a `RegistryError` naming only the variable and the failure class — never the URL or password.
- **start_run:** `config_hash` = sha256 of canonical JSON (sorted keys); `code_version` = `git rev-parse HEAD` of the package's checkout, `"unknown"` otherwise (or an explicit value).
- **add_trials:** rows (`TrialRecord` or plain mappings, validated for required/unknown fields) are buffered and written with one psycopg `COPY trials (...) FROM STDIN` per flush — at `batch_size` rows (default 5000), on `flush()`, `finish_run()`, `close()` and context exit. `params`/`extra` go through as `jsonb`.
- **record_holdout_access:** the insert hits `UNIQUE(candidate_id)`; SQLSTATE 23505 → `HoldoutAccessError` (stage `holdout`, names the candidate). Holds across connections/processes because the database enforces it.
- **add_decision:** empty/blank reason → `RegistryError` before the DB; the DB CHECK rejects it too.
- **trial_count:** recursive CTE over `parent_id` (the candidate + all ancestors); `include_lineage=False` counts only the candidate. Stage-1 probe trials without a candidate are not attributed to any candidate.
- **sfac reproduce --trial:** prints run id/status, stage, family, candidate/instrument, `config_hash`, `code_version`, `seed`, `spec_hash`, `params`, and every `*snapshot_hash` found in the stored run config (with its JSON path) — clearly labelled **"partial - execution after T08"**.

## COPY timing (100k synthetic trials, batch 5000, local Docker Postgres 16 on Windows)
**2.61 s ≈ 38,300 rows/s** (row count 100,000 = rows written, asserted).

## Acceptance
| command | result |
|---|---|
| `docker compose up -d` | ✅ (see "Local environment" below) |
| `uv run sfac db upgrade` | ✅ `registry schema: empty -> 0001_initial` |
| `uv run sfac db status` | ✅ revision `0001_initial (head: 0001_initial)` + 10 row counts |
| `ruff check` / `ruff format --check` | ✅ all passed / 134 files formatted |
| `mypy src` | ✅ 56 files, strict for `strategy_factory.registry` |
| `pytest` | ✅ **230 passed** (13 new; 11 db tests ran, none skipped) in ≈ 13 s |
| CI steps simulated locally | ✅ `uv run alembic upgrade head` via `alembic.ini`; `pytest -m db --junitxml` → skip check "db tests skipped: 0" |

## How each criterion is tested
| criterion | test |
|---|---|
| F-0.7.1 round trip of each table | `test_F_0_7_1_round_trip_every_table` (all 10 tables written and read back field by field, candidate upsert updates stage, run finish; final row count = 1 per table) |
| COPY of 100k trials, time + count | `test_F_0_7_1_copy_100k_trials` (prints the timing) |
| buffer flushes on close | `test_F_0_7_1_buffer_flushes_at_batch_size_and_on_close` (batch 10: 25 rows → 20 flushed automatically, 5 on `close()`) |
| trial rows validated; config hash; git sha | `_trial_rows_are_validated`, `_config_hash_and_git_sha` |
| F-0.7.2 three generations, with/without lineage | `test_F_0_7_2_three_generation_lineage_counts` (G1 40, G2 16, G3 64 trials + unrelated branch + candidate-less probes: G3 alone 64, with lineage 120; lineage order root→leaf) |
| F-0.7.3 gate results with all fields | `test_F_0_7_3_gate_results_stored_with_all_fields` (every field incl. `metric_value=None`, critical, reason) |
| second holdout access raises, from a separate connection | `test_F_0_7_3_second_holdout_access_raises_even_from_another_connection` (second engine/pool → `HoldoutAccessError`; a raw INSERT also fails → proves the DB constraint) |
| empty decision reason rejected | `test_F_0_7_3_decision_needs_a_reason` (empty and blank in Python; blank via raw INSERT → CHECK violation; `return` without stage) |
| F-0.7.4 reproduce plan | `test_F_0_7_4_reproduce_prints_plan` (CLI output contains config hash, code version, seed, spec hash, params, snapshot hash + path; unknown trial → exit 1) |
| migrations up → down → up | `test_F_0_7_1_migrations_up_down_up_and_match_tables` (+ `compare_metadata` = no diff between migration and `tables.py`) |
| secrets | `test_F_0_7_1_db_password_never_in_errors_or_logs` (fake URL with a password: exception text, repr, cause/context and all log records are free of password and host:port), `_missing_db_url_is_a_clear_error` |
| isolation / cleanup | every db test gets its own schema (`search_path` via psycopg `options`), migrated with Alembic, dropped with CASCADE afterwards |
| skip locally, fail in CI | fixture skips with a clear reason when the DB is unreachable (checked once per session); CI step fails if the JUnit report of `pytest -m db` shows any skipped test |

## Local environment (needed a change — approved by the user)
- A **native Windows PostgreSQL 17 service** (`postgresql-x64-17`) listens on `0.0.0.0:5432`, shadowing Docker's `sfac-postgres` on IPv4; and the password inside `SFAC_DB_URL` in this worktree's `.env` did not match `SFAC_DB_PASSWORD` (the one the container was created with).
- With your approval, in **`StrategyFactory_T03/.env` only**: `SFAC_DB_PORT=5433` and `SFAC_DB_URL` rebuilt from `SFAC_DB_USER/PASSWORD/NAME` on port 5433; `docker compose up -d` recreated `sfac-postgres` (data volume kept; it was empty). The PG17 service and other folders were not touched. `.env.example` got a one-line hint; its defaults are unchanged (CI uses 5432).

## Deviations
- Extra writer methods `register_snapshot` and `add_split` (needed for the `data_snapshots` and `splits` round trips).
- `make_engine(connect_timeout=10)` added after the first run showed a 130 s hang per connection attempt to a closed port on Windows.
- mypy excludes `src/strategy_factory/registry/alembic/` (the migration file name `0001_initial.py` is not a valid module name); ruff still checks it.
- Test fixtures are exposed via `tests/unit/conftest.py`.

## Open questions
1. `data_snapshots.snapshot_hash` is the sole primary key (as specified), while the T02 catalog key is (source, symbol, timeframe, hash): identical content under two sources/symbols would collide. Keep, or use a composite key?
2. Should the run config be required to contain the data snapshot hash(es) (e.g. validated when `start_run` is called)? Today `sfac reproduce` reports "NOT RECORDED" if absent.
3. Merge note: another branch (T04e) also changed `pyproject.toml`, `uv.lock`, `cli.py` and `.env.example`; T03's edits there are additive (3 dependencies, one marker, one mypy exclude, 3 CLI lines, one comment).
