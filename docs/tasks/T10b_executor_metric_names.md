# T10b — Executor and metric-name registry

**Features:** F-0.3.7 (batch and parallel execution), F-0.8.1 (gate engine: metric names validated), F-0.6.1 (holdout only from stage 6) · **Priority:** MVP · **Depends on:** T08 (grid kernel), T09 (metrics), T10a (gates), T05 (split manager)

**Critical parts (D-339, D-402):** the `SplitManager.open_holdout` change (§4) and the gate-YAML changes (§2) are marked **CRITICAL** in the review and in the PR description, for supervisor review. The rest of the task is not critical. **Stop after the review and wait for "Approved".**

**Plan approved 2026-09-20 with three changes** (recorded in `HANDOFF.md` §5); they are folded into §3 (a), §4 (b) and §5 (c) below. Everything else in this file stands.

Read first: `CLAUDE.md`, `docs/design.md` §4 (`RunContext`, `Executor`), §10 (two-level parallelism), ADR-005, `docs/reviews/T09_review.md` (`as_gate_dict()` names, `core_metrics_batch`), `docs/reviews/T10a_review.md` (gate table, open questions), `docs/reviews/T05_review.md` (open question 1), `docs/reviews/T08_review.md`, and decisions **D-012, D-301, D-306, D-308, D-309, D-316, D-331, D-333, D-334, D-339, D-343,
D-344, D-345, D-347**.

## Scope

### 1. Executor (F-0.3.7, `pipeline/executor.py`)
- `Executor` Protocol (design §4, ADR-005): `map(fn, work_units) -> list[result]`, results in **input order**, deterministic.
- `SerialExecutor` (reference) and `ProcessPoolExecutor`-based `LocalExecutor`. Work unit = (symbol, timeframe, stage) (design §10). The start method is `spawn` on every platform, so Windows and Ubuntu behave the same.
- **Thread budget (D-334):** `workers × numba_threads ≤ os.cpu_count()`; both come from `configs/pipeline/executor.yaml` (defaults: `workers: auto`, `numba_threads: auto`), set in each worker with `numba.set_num_threads` before any kernel runs.
- **Grid chunking (D-331):** `run_grid(bars, cost_arrays, signal_matrix, params, chunk_cols)` splits configurations into column chunks so `n_bars × chunk_cols × 8 bytes × 2` stays under `max_grid_bytes` (config); chunk results are concatenated in order. Output = T09 `core_metrics_batch` input per chunk → one metrics table per grid.
- **Seeds:** every work unit gets a seed derived from the run seed and the unit key (sha256), never from the worker id, so parallel = serial.
- **Registry writes (D-012, D-334):** workers return results; only the parent writes trials through the batched `RegistryWriter` (COPY). One trial per evaluated configuration; the trial count equals the number of configurations (F-0.7.1).
- Errors in a worker are re-raised in the parent with the unit key; completed units are not lost.

### 2. Metric-name registry (D-309, `metrics/names.py`)
- One registry: `MetricName(name, unit, description, producer)` where `producer` is `metrics.core`, `metrics.batch` or a stage id (`s01_probe`, `s02_screen`, …) for stage-level metrics that later stages will compute.
- The core names are exactly `MetricsReport.as_gate_dict()` keys and the `core_metrics_batch` keys; a test asserts both producers emit only registered names and all of them.
- **The T08 names must be registered (D-333, D-345):** `n_skipped_min_volume` (count, D-313), `min_volume_skip_flag` (flag, D-313), `volume_step_assumed` (flag, D-314), `contracts_fixed` (flag, D-329) and `fx_peg` (flag, D-307). Each gets its unit, description and producer (`metrics.core`), and the test that compares the registry with `as_gate_dict()` covers them, so a future addition cannot slip through unregistered.
- The stage-level names used in `configs/gates/default.yaml` are registered now with their producer stage (D-333), so the YAML validates.
- `GateConfig` validation: **an unknown metric in the YAML is an error at load time** (every stage and every override).
- **Reconciliation of the gate YAML (D-333) — CRITICAL (D-339):**
  - `min_trades` → `n_trades` (closed trades, D-301) in `s01_probe` and its 1H override;
  - `mc_dd95_within_tolerance == 1` → `mc_max_dd_p95_pct <= 25` (D-308; % of initial capital, the 25 in YAML);
  - any other mismatch found is listed in the review.

### 3. Run-level config hash (D-344, D-343, D-347, F-0.8.2)
The T08 `BacktestSpec.spec_hash` covers the strategy spec only, so two runs that differ in
engine settings hash alike. The **run** config must close that gap (CLAUDE.md rule 8):

- `PipelineConfig` gains an **`engine` section** holding the `EngineConfig` values that decide
  a result: `initial_capital`, `notional`, `disaster_stop_atr`, `atr_length` (D-343),
  `futures_contracts` and `parity_qty_step` (D-347). It is validated by the same Pydantic model
  as `configs/engine/default.yaml`, so a config file and a run agree by construction.
- `intrabar_mode` is already in `PipelineConfig`; `config_hash` must cover it **and** the new
  `engine` section (it hashes the canonical JSON, so this follows once the fields are there —
  the task is to prove it).
- **(a) `config_hash` must also cover the cost inputs** (approved 2026-09-20). Costs decide
  every result (CLAUDE.md rule 4), so `resolve_config` fills a **`cost_inputs` section**:
  - the **resolved cost-profile content hash per symbol** — sha256 of the canonical JSON of the
    profile as `resolve_profile` returns it (assignment overrides included), so a changed
    spread, commission, swap or volume step changes the run hash;
  - the **Moneta spec SHA-256** (`configs/costs/moneta/moneta_spec.csv.meta.json: sha256`, the
    broker xlsx hash of D-340), or `null` when no Moneta profile is used;
  - **`configs/data/fx_conversion.yaml`**: the pairs and the pegs (D-307), canonicalized;
  - the **conversion pairs' snapshot hashes**, resolved from the catalog like `data_snapshots`,
    for exactly the pairs the run's symbols need (D-316).
  - **Tests:** regenerating a profile with a different spread changes `config_hash` (and
    nothing else about the run does); a changed peg, a changed `moneta_spec` sha and a changed
    conversion snapshot each change it; key order does not. `sfac reproduce --trial <id>`
    **fails loudly** when a stored cost hash no longer matches what the configs resolve to
    today, naming the symbol and both hashes — it never silently reproduces with other costs.
- **Parity runs** (`intrabar_mode: tradingview`) are refused at config validation when
  `engine.parity_qty_step` is missing, with the same message as `run_backtest` (D-347), and the
  Pine ATR length must be set explicitly rather than inherited from the default.
- `start_run` stores the resolved config, so the registry row carries the engine and cost
  settings; and `sfac reproduce --trial <id>` rebuilds them from that row (F-0.7.4).
- **Tests:** changing `atr_length`, `parity_qty_step`, `disaster_stop_atr` or `intrabar_mode`
  changes `config_hash`; reordering keys does not; a `tradingview` config without
  `parity_qty_step` is refused; a resolved config round-trips through the registry and gives a
  bit-identical rerun.

### 4. Holdout stage guard (D-306, F-0.6.1) — CRITICAL (D-339)
- `SplitManager.open_holdout(candidate_id, symbol, timeframe, *, stage)`: any `stage` other than `s06_robust` raises `HoldoutAccessError` **before** the ledger is touched.
- **(b) The allowed stage is a single constant in code**, not a config value (approved
  2026-09-20; D-306 says *enforced in code*): one module-level `HOLDOUT_STAGE = "s06_robust"` in
  `data/split.py`, used by `open_holdout` and `open_holdout_with_conversion`. It is **not** a
  field of any Pydantic config model and is not read from YAML.
  - **Test:** no config can change it — a `PipelineConfig` / `SplitConfig` with an extra
    `holdout_stage` key is rejected (`extra="forbid"`), and `open_holdout(..., stage="s05_filter")`
    still raises with such a config present; a search asserts that no YAML under `configs/`
    defines the allowed stage.
- All existing callers and tests are updated; the one-shot rule is unchanged. The D-316 conversion path (T08) does not go through `open_holdout` and is unaffected; a test confirms it.

### 5. Code version on the run row (c)
`pipeline_runs.code_version` already stores the git commit (`registry.writer.git_sha`). It must
also record whether the checkout was **dirty**: `git_sha()` gains a dirty flag
(`<sha>-dirty` / `{"commit": ..., "dirty": ...}`, one shape, documented), **stored, not
hashed** — `config_hash` must not change when the working tree is dirty.

- **Tests:** a clean checkout and a dirty one give different `code_version` but the **same**
  `config_hash`; `sfac reproduce` prints the dirty marker and warns that a dirty checkout is
  not reproducible; a checkout without git still yields `unknown` (no crash).

## Tests
- **F-0.3.7:** a grid of ≥ 200 configurations on synthetic bars: `LocalExecutor` (2 and 4 workers) gives results **identical** to `SerialExecutor` (metrics `==`, order, seeds, registry rows); chunked grid = unchunked grid; a failing unit reports its key; thread budget respected (mock `cpu_count`). The engine settings travel with the work unit, so a worker cannot silently fall back to the defaults (a run with a non-default `atr_length` gives the same result serially and in parallel).
- Registry: trial count = number of configurations (DB test); only the parent writes.
- **D-309:** unknown metric in base or override → load error; all names in `default.yaml` registered; `as_gate_dict()` and batch keys ⊆ registry and equal to the `metrics.core` / `metrics.batch` sets.
- **D-308:** the renamed MC criterion evaluates correctly (`24.9` pass, `25.1` fail).
- **D-306 / F-0.6.1:** `open_holdout` from any stage other than stage 6 raises and writes nothing to the ledger; from stage 6 it works once and the second call raises (DB test, 0 skipped). `open_holdout_with_conversion` (D-316) takes the same `stage` argument and refuses the same callers. **(b)** No config can change the allowed stage.
- **Config hash (§3):** the tests listed there, including the cost inputs **(a)** and the
  `sfac reproduce` cost-hash mismatch.
- **Code version (§5, c):** dirty flag stored, not hashed.

## Acceptance
- ruff, format, mypy (strict for `gates`, `core`, `data`; `pipeline/executor.py` typed), fast suite, parity + leakage, `pytest -m db` 0 skipped.
- **Scalability report** (F-0.3.7 acceptance): wall time of the same grid with 1, 2, 4, … workers up to the core count on the development machine, as a table in the review, plus speed-up and efficiency. No threshold.

## Review summary
`docs/reviews/T10b_review.md`: a **CRITICAL** section first (the `open_holdout` diff and the gate-YAML diff, with their tests), then executor design, thread budget, chunking rule, scalability table, the full metric-name registry (name, unit, producer, including the five T08 names), the run-config hash (what it now covers — engine **and** cost inputs — and the proof), the code-version change, the YAML changes, the holdout guard, deviations, open questions.
