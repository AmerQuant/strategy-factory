# T10b review — Executor, metric-name registry, run config hash, holdout stage guard

**Features:** F-0.3.7, F-0.8.1, F-0.8.2, F-0.6.1, F-0.7.1, F-0.7.4 · **Branch:** `feat/T10b-executor-metric-names` (stacked on `feat/T08-engine`) · **Status:** done. **Two parts are CRITICAL (D-339) — waiting for "Approved".**

**Decisions used:** D-002, D-004, D-008, D-012, D-130, D-301, D-306, D-307, D-308, D-309, D-313, D-314, D-316, D-329, D-331, D-333, D-334, D-339, D-340, D-343, D-344, D-345, D-347.

## Dependencies
None added.

---

# CRITICAL (D-339) — read these two sections first

## C1. Gate YAML reconciliation (§2, D-333, D-301, D-308)

`configs/gates/default.yaml`, three lines:

| before | after | why |
|---|---|---|
| `s01_probe: {metric: min_trades, op: ">=", threshold: 30}` | `{metric: n_trades, op: ">=", threshold: 30}` | D-301/D-333: the gate count is **closed trades**, the name the metrics module emits |
| `overrides.timeframe.1H.s01_probe: {metric: min_trades, op: ">=", threshold: 100}` | `{metric: n_trades, …, threshold: 100}` | same, the 1H override |
| `s06_robust: {metric: mc_dd95_within_tolerance, op: "==", threshold: 1}` | `{metric: mc_max_dd_p95_pct, op: "<=", threshold: 25}` | D-308: the p95 of the Monte-Carlo maximum drawdown, % of initial capital; the 25 is in the YAML, not in code |

**No threshold changed.** `min_trades_good_cells` (s02_screen) and `bucket_min_trades` (s05_filter) keep their names: they are stage-2/stage-5 metrics ("smallest closed-trade count among the good cells / per bucket"), not the run's `n_trades`. They are registered with their producing stage. That is the only other name that looked like a mismatch.

`mc_max_dd_p95_pct` stays **non-critical** (`critical: true` is unchanged on the five spec-mandated ones), because D-308 does not make it critical.

Tests: `test_F_0_8_1_d333_min_trades_renamed_to_n_trades` (base + 1H override, and the metrics report really emits `n_trades` = the closed-trade count), `test_F_0_8_1_d308_monte_carlo_drawdown_criterion` (0.0 / 24.9 / 25.0 pass, 25.1 / 99.0 fail; asserts the old name is gone and that op/threshold/critical are `<=` / 25 / false), `test_F_0_8_1_default_gates_as_specified` (the T10a table test, updated).

## C2. Holdout stage guard (§4, D-306, F-0.6.1)

```python
# data/split.py
HOLDOUT_STAGE = "s06_robust"          # a constant in code, never read from a config

def open_holdout(self, candidate_id, symbol, timeframe, *, stage) -> pl.DataFrame
def open_holdout_with_conversion(self, candidate_id, symbol, timeframe, pairs, *, stage)
```

Both call `_check_stage(stage)` **first**: before the reference snapshot is read, before the split is registered and before the ledger is touched. A refused caller therefore neither reads a bar nor spends the candidate's one-shot access — it can still open its holdout from stage 6 afterwards. `stage` is keyword-only, so every existing caller had to be updated and none could silently pass a positional value.

**(b) The allowed stage is a code constant, not config.** D-306 says "enforced in code". It is not a field of any Pydantic model, it is not read from YAML, and there is no environment override. Four tests prove it:

| test | proves |
|---|---|
| `test_F_0_6_1_d306_allowed_stage_is_stage_six` | the constant is `s06_robust` |
| `test_F_0_6_1_d306_no_config_model_accepts_a_holdout_stage_field` | `PipelineConfig` and `SplitConfig` reject a `holdout_stage` key (`extra="forbid"`) |
| `test_F_0_6_1_d306_a_config_with_a_holdout_stage_key_changes_nothing` | even with such a file on disk, `stage="s05_filter"` still raises and the ledger stays empty |
| `test_F_0_6_1_d306_no_repo_config_defines_the_allowed_stage` | no YAML under `configs/` mentions `holdout_stage` |

Other tests: `..._any_other_stage_is_refused_and_writes_nothing` (10 stages, including `""`, `"S06_ROBUST"` and `"s06_robust "` — the comparison is exact; asserts the ledger is empty **and** that no snapshot was read), `..._stage_six_works_once` (one-shot unchanged, D-008), `..._the_stage_argument_is_keyword_only`, `..._conversion_path_refuses_the_same_callers`, `..._development_access_needs_no_stage` (D-316: a development run's conversion arrays never go through `open_holdout`), and the DB test `..._registry_ledger_records_nothing_for_a_refused_stage` (0 rows after the refusal, 1 after stage 6, still 1 after the second call).

---

## What was built

| File | Content |
|---|---|
| `pipeline/executor.py` | `ExecutorConfig` + `resolve_budget` (D-334), `WorkUnit` / `seeded` / `unit_seed` (D-334), `Executor` Protocol, `SerialExecutor`, `LocalExecutor` (spawn), `chunk_columns` + `GridJob` + `run_grid` (D-331), `grid_trial_rows` (F-0.7.1, D-012). |
| `configs/pipeline/executor.yaml` | `workers`, `numba_threads` (both `auto`), `max_grid_bytes` 512 MiB. |
| `metrics/names.py` | The one registry: 78 `MetricName(name, unit, description, producers)` entries (D-309, D-333, D-345). |
| `gates/engine.py` | `metrics_used`, `validate_metric_names`; `load_gate_config` validates every stage and every override against the registry. |
| `configs/gates/default.yaml` | The three renamed lines (C1). |
| `core/config.py` | `EngineConfig` + `load_engine_config` moved here; `PipelineConfig.engine` and `PipelineConfig.cost_inputs`; `CostInputsRef`; `cost_profile_hashes`, `conversion_pairs_for`, `check_cost_inputs`; parity validation (D-347, D-343); `require_resolved` now requires the cost inputs too. |
| `pipeline/backtest.py` | Imports `EngineConfig` / `load_engine_config` / `DEFAULT_ENGINE_CONFIG` from `core.config` and re-exports them; the parity refusal uses the shared message. |
| `costs/profile.py` | `profile_content_hash`, `moneta_spec_sha256`, `moneta_profile_names`, `MONETA_SPEC_META`. |
| `registry/writer.py` | `git_dirty`, `code_version` (`<sha>` / `<sha>-dirty` / `unknown`); `RegistryWriter` refuses to be created in an executor worker (D-012). |
| `registry/queries.py`, `registry/cli.py` | The plan prints the engine and cost sections and a dirty warning; `sfac reproduce` exits 1 on a cost mismatch. |
| `core/env.py` | `EXECUTOR_WORKER_ENV`, `mark_executor_worker`, `in_executor_worker`. |
| `core/errors.py` | `ExecutorError` (carries `results` and `failed`). |
| `data/split.py` | `HOLDOUT_STAGE`, `_check_stage`, the `stage` argument (C2). |
| `scripts/bench_executor.py` | The scalability benchmark below. |

## Executor design (F-0.3.7, ADR-005, design §10)

- **Interface:** `Executor.map(fn, work_units) -> list` — results in **input order**, always. `SerialExecutor` is the reference; `LocalExecutor` is a `ProcessPoolExecutor` with `mp_context=spawn` on every platform (D-334), so Windows and Ubuntu behave the same. `make_executor` returns the serial one when the budget resolves to a single worker.
- **Work unit** = `(symbol, timeframe, stage)` plus a payload and a seed. Its `key` is `SYMBOL|TF|STAGE`.
- **Seeds (D-334):** `seeded(run_seed, units)` fills each unit's `seed` with `sha256(run_seed|key)` **in the parent**, so a worker never derives anything from its process; `unit_seed` is stable, distinct per unit and changes with the run seed.
- **Failures:** both executors run *every* unit and then raise one `ExecutorError` naming each failed key, carrying the finished results (`None` where a unit failed). Serial and parallel raise the identical message and results — asserted in the test, since the module claims "parallel equals serial".
- **Only the parent writes (D-012, D-334):** `_init_worker` sets `SFAC_EXECUTOR_WORKER`, and `RegistryWriter.__init__` raises a `RegistryError` when that is set. This is a mechanism, not a convention: a worker that tries to open a writer fails, and the test asserts the parent is never marked.

### Thread budget (D-334)

`workers x numba_threads <= os.cpu_count()`, both from `configs/pipeline/executor.yaml`. The `auto` rule (an assumption, **P-36**): both auto → `workers = floor(sqrt(cpu))`, `numba_threads = cpu // workers`; one given → the other is `max(1, cpu // given)`; both given and over the bound → `ConfigError`. Each worker calls `numba.set_num_threads`, clamped to Numba's own `NUMBA_NUM_THREADS` maximum so an environment that allows fewer threads lowers the budget instead of failing silently. Tested with a mocked `cpu_count` (6 cases) and by reading `numba.get_num_threads()` back out of a worker.

### Grid chunking (D-331)

`chunk_columns(n_bars, n_configs, max_grid_bytes) = max(1, min(n_configs, max_grid_bytes // (n_bars * 16)))` — 16 bytes per cell = the equity matrix plus the in-position matrix, the task's `8 bytes x 2`. `run_grid` slices the grid into column chunks, runs each through `simulate_grid` + `core_metrics_batch`, and concatenates. Only metrics survive a chunk; the matrices are dropped. `test_F_0_3_7_chunked_grid_equals_the_unchunked_grid` compares chunk sizes 1, 5, 8 and 100 against the whole grid of 23 configurations with `assert_array_equal` on every metric.

### Scalability report (F-0.3.7 acceptance)

`uv run python scripts/bench_executor.py` — 20 work units x 1,000 configurations x 5,000 bars = **20,000 configurations**, 20 cores. Every numbered row uses one Numba thread per worker, so the x-axis is pure process-level scaling; the last two rows let the kernel use all cores. No thresholds.

| workers | numba threads | wall (s) | speed-up | efficiency |
|---|---|---|---|---|
| 1 | 1 | 4.16 | 1.00 | 1.00 |
| 2 | 1 | 2.40 | 1.74 | 0.87 |
| 4 | 1 | 1.80 | 2.32 | 0.58 |
| 8 | 1 | 1.91 | 2.18 | 0.27 |
| 16 | 1 | 2.83 | 1.47 | 0.09 |
| 20 | 1 | 3.97 | 1.05 | 0.05 |
| serial | all | 1.92 | 2.17 | — |
| **4 (auto)** | **5** | **1.43** | **2.91** | **0.73** |

Speed-up and efficiency are relative to 1 worker x 1 thread. Reading it: process-level scaling is good to 4 workers and then goes backwards, because each spawned worker pays process start-up plus the per-unit array building. The `auto` budget (4 x 5) is the fastest row and beats both pure levels — which is the point of the two-level design (ADR-005). The benchmark asserts that every parallel result equals the serial one before printing.

## Metric-name registry (D-309, D-333, D-345)

`metrics/names.py` holds 78 entries: **35** with producer `metrics.core` (exactly the `MetricsReport.as_gate_dict()` keys, including the five T08 names of D-345), **8** also with `metrics.batch` (exactly the `core_metrics_batch` keys), and **43** stage-level names with their producing stage (`s01_probe`, `s01_edge`, `s01s_seasonal`, `s02_screen` … `s07_stats`).

```
MetricName(name, unit, description, producers)
units: usd, pct, share, ratio, count, flag, years, bars, days, percentile, p_value, index
```

`load_gate_config` validates the base stages **and every override layer** (asset class, timeframe, combined) against the registry; an unknown metric is a `ConfigError` naming the metric and where it is used. A `GateConfig` built in code is not checked, so the T10a tests keep their synthetic names (`a`, `b`, `trades`) — `validate_metric_names` is the check itself and is called by the loader.

Tests: `test_F_0_8_1_core_producer_equals_as_gate_dict` (set equality both ways, and `MetricsReport.model_fields == metrics.core`, so a new field cannot be added without registering it), `..._batch_producer_equals_the_batch_keys` (and that batch ⊂ core), `..._stage_metrics_have_their_producing_stage`, `..._every_metric_of_the_repo_gates_is_registered`, `..._unknown_metric_in_base_or_override_fails_at_load` (4 layers), `..._registry_entries_are_complete_and_unique`.

## Run-level config hash (§3, F-0.8.2)

`config_hash` = sha256 of the canonical JSON of the resolved `PipelineConfig`, which now carries:

1. **`engine`** — `EngineConfig` (`initial_capital`, `notional`, `disaster_stop_atr`, `atr_length` D-343, `futures_contracts` D-329, `parity_qty_step` D-347), validated by the same model as `configs/engine/default.yaml`;
2. **`intrabar_mode`** (already there, D-002);
3. **`data_snapshots`** (already there);
4. **(a) `cost_inputs`** — `profile_names` and `profiles` (sha256 of each symbol's **resolved** profile, overrides applied), `moneta_spec_sha256` (the broker xlsx hash from the import sidecar, D-340, `null` when no Moneta profile is used), `fx_conversion` (pairs and pegs of `configs/data/fx_conversion.yaml`, D-307) and `conversion_snapshots` (the pairs the run needs, per timeframe, D-316).

`resolve_config` fills 3 and 4; `require_resolved` now refuses a run whose cost inputs are missing or incomplete (costs are mandatory, CLAUDE.md rule 4), so `start_run` cannot record a run that `reproduce` could not verify.

**Parity validation:** a `tradingview` config is refused without `engine.parity_qty_step` (D-347, the same message as `run_backtest`) **and** without an explicit `engine.atr_length` (D-343: the ATR length of the Pine script being reproduced, never the research default — stating `14` explicitly is accepted, inheriting it is not).

**`sfac reproduce`** prints the engine section, the intrabar mode, one line per symbol's cost profile, the Moneta sha and the conversion snapshots, then verifies the cost inputs with `check_cost_inputs`: a changed profile, a changed Moneta sha, a changed `fx_conversion.yaml` or a changed set of conversion pairs each make it **exit 1** naming the symbol and both hashes. A run recorded before T10b prints a warning and exits 0.

| what changes | test |
|---|---|
| `atr_length`, `disaster_stop_atr`, capital, notional, futures contracts, `parity_qty_step` | `test_F_0_8_2_engine_setting_changes_the_config_hash` (6 cases) |
| `intrabar_mode` | `..._intrabar_mode_changes_the_config_hash` |
| key order (must **not** change it) | `..._config_hash_ignores_key_order` |
| **a different spread on the same profile** | `..._a_different_spread_changes_the_config_hash` (and asserts nothing else about the run differs) |
| peg, Moneta spec sha, conversion snapshot hash | `..._changing_the_peg_or_the_broker_spec_changes_the_hash`, `..._conversion_snapshot_hash_is_part_of_the_config` |
| Moneta sha recorded and verified | `..._moneta_spec_sha_is_recorded_when_a_moneta_profile_is_used` |
| `sfac reproduce` fails loudly | `..._reproduce_fails_loudly_when_a_cost_profile_changed` (db, exit 1), plus `check_cost_inputs` unit tests for a changed profile, fx config, conversion pair, missing cost inputs and an unresolvable profile |
| parity without step / without explicit ATR length | `..._parity_run_without_the_step_is_refused`, `..._parity_run_must_state_the_pine_atr_length`, `..._parity_config_message_equals_the_engine_message` |
| a run cannot start without resolved costs | `..._run_cannot_start_without_resolved_cost_inputs` |

## Code version (§5, c)

`registry.writer.code_version()` returns **one shape**: `<40-hex sha>`, `<sha>-dirty` or `unknown`. It is **stored on `pipeline_runs.code_version`, never hashed** — a dirty working tree does not change `config_hash`, because the config did not change. `sfac reproduce` prints `(DIRTY checkout: uncommitted changes; not reproducible from the commit)` instead of `(git checkout this commit)`.

Dirty = uncommitted **tracked** changes (`git status --porcelain --untracked-files=no`); untracked files do not count (assumption **P-37**). Tests: clean, dirty, untracked-only, no git at all, the hash is unchanged, and the DB test asserting two runs with different `code_version` share one `config_hash`.

## How each criterion is tested

| Criterion | Test |
|---|---|
| **F-0.3.7** ≥ 200 configurations, `LocalExecutor` (2 and 4 workers) == `SerialExecutor` | `test_F_0_3_7_parallel_equals_serial_on_a_grid_of_200_configurations` (4 units x 200 configs; metrics, seeds and order identical, only the pid differs) |
| F-0.3.7 results in input order, serial and parallel, empty input | `..._results_are_in_input_order_serial_and_parallel` |
| F-0.3.7 chunked grid == unchunked | `..._chunked_grid_equals_the_unchunked_grid`, `..._chunk_size_from_the_memory_budget` |
| F-0.3.7 a failing unit reports its key; finished units kept; serial == parallel on failure | `..._failing_unit_reports_its_key_and_keeps_the_finished_results` |
| D-334 thread budget (mocked `cpu_count`), refusal over the bound, worker thread count | `..._thread_budget_never_exceeds_the_core_count`, `..._explicit_budget_over_the_core_count_is_refused`, `..._budget_uses_os_cpu_count_when_not_given`, `..._worker_gets_the_configured_numba_thread_count` |
| D-334 seeds from (run seed, unit key), carried into the worker | `..._seeds_come_from_the_run_seed_and_the_unit_key`, `..._seeded_units_carry_their_seed_into_the_worker` |
| Engine settings travel with the work unit (no silent fallback) | `..._engine_settings_travel_with_the_work_unit` |
| **D-012** only the parent writes | `..._d012_only_the_parent_writes_to_the_registry` |
| **F-0.7.1** trial count = number of configurations | `..._one_trial_row_per_configuration`, `..._trial_count_equals_the_number_of_configurations` (db, 25 rows, chunked) |
| Executor config file, defaults, invalid values, the repo file | `..._executor_config_file_and_defaults`, `..._repo_executor_config_is_valid` |
| **D-309** registry vs `as_gate_dict` / batch; unknown metric at load | see "Metric-name registry" |
| **D-333 / D-301 / D-308** the renames | see C1 |
| **F-0.8.2 / §3(a)** the run hash covers engine, mode, snapshots and costs | see "Run-level config hash" |
| **D-306 / F-0.6.1** the stage guard, and that no config can change it | see C2 |
| **§5(c)** the dirty flag, stored not hashed | see "Code version" |
| Sample configs still validate; no engine section → the documented defaults | `..._repo_sample_configs_still_validate` |

## Acceptance

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | ✅ / ✅ 238 files |
| `mypy src` | ✅ 95 files |
| `pytest -m "not slow"` | ✅ **1141 passed** |
| `pytest tests/parity tests/leakage tests/oracle` | ✅ **283 passed**, 0 skipped |
| `pytest -m db -rs` | ✅ **21 passed, 0 skipped** |
| `python scripts/bench_executor.py` | ✅ table above; every parallel result equals the serial one |
| acceptance-reviewer subagent | run; findings fixed (below) |

### Reviewer findings and what was done

1. **Parity runs could inherit the default ATR length** (task §3, D-343) — `validate_config` now also requires an explicit `engine.atr_length` for `tradingview` runs; new test.
2. **"Only the parent writes" was a convention** — now enforced: `_init_worker` marks the process, `RegistryWriter` refuses to be created there; new test.
3. **No scalability numbers committed** — the table is in this review.
4. **Serial and parallel differed on failure** (serial aborted at the first failure) — `SerialExecutor` now runs every unit and raises the identical error; the test compares both messages and result lists.
5. **`set_num_threads` could fail silently** under a pre-set `NUMBA_NUM_THREADS` — the count is clamped to Numba's maximum and no exception is swallowed.
6. **The seed was only a convention** — `WorkUnit.seed` plus `seeded(run_seed, units)`; the worker reads the seed from its unit.
7. **`check_cost_inputs` ignored the conversion pairs** — it now compares the required pair set too; new test. The Moneta-sha branch got its own test.
8. **A run could start with `cost_inputs = None`** — `require_resolved` now refuses it (costs are mandatory).
9. **New assumptions not in the log** — recorded as **P-36** (the `auto` core split), **P-37** ("dirty" = tracked changes only) and **P-38** (a futures parity run has no quantity step).

## Deviations

1. **`MetricName.producers` is a tuple, not one `producer`.** The task writes `MetricName(name, unit, description, producer)`, but the eight batch metrics are produced by *both* `metrics.core` and `metrics.batch` and are bit-identical there (T09). A single field would have forced one of the two producer sets to be wrong. `MetricName.producer` still returns the first (the only one of every stage-level metric), and `by_producer()` gives exactly the `metrics.core` / `metrics.batch` sets the task asks the test to compare.
2. **`EngineConfig` moved to `core/config.py`** (from `pipeline/backtest.py`). A pipeline config must carry the engine section, and `core.config` may not import `pipeline.backtest`, which pulls in Numba. `pipeline/backtest.py` re-exports the three names, so T08's imports still work.
3. **All `EngineConfig` fields now have model defaults** (they were required in T08). CLAUDE.md rule 1 puts defaults in the config model, and `configs/engine/default.yaml` restates them with their decision ids. Consequence: an engine YAML that loses a key falls back to the documented default instead of failing. `parity_qty_step` still has no default, and a parity run must state both it and `atr_length`.
4. **`run_grid` takes a `GridJob`**, not the task's `run_grid(bars, cost_arrays, signal_matrix, params, chunk_cols)`: the T08 grid kernel needs the market arrays, both signal matrices, four per-column exit arrays, cost and sizing inputs, the mode and the conversion arrays. Bundling them in one frozen dataclass keeps the call readable and makes the column slice a method.
5. **`grid_trial_rows` fills only the five trial columns the batch path computes** (`n_trades`, `avg_annual_profit`, `avg_annual_dd_ystart`, `profit_dd_ratio`, `exposure`) plus `n_skipped_min_volume` in `extra`. The other trial columns stay `None`: the grid path does not compute them (D-331 keeps only metrics), and inventing them would be worse than a null.
6. **`executor.yaml` is not part of `config_hash`.** It decides how fast a run is, never what it computes; the identity tests prove that.

## Open questions

- **P-36** — the `auto` split of cores between processes and Numba threads (D-334 fixes only the product).
- **P-37** — "dirty" counts tracked changes only.
- **P-38** — a futures parity run has no quantity step: `run_backtest` exempts futures, `validate_config` cannot (a pipeline config has no futures flag until T04d).
- `resolve_config` now requires a conversion-pair snapshot for **every timeframe of the run**. That is right per D-316, but it is only tested for a single timeframe.
- F-0.7.4 remains partial: `sfac reproduce` prints and verifies the plan; a bit-identical **re-run** needs the stage wiring (`RunContext`), which is not in this task.
- `PipelineConfig.engine` is now hashed, but nothing yet passes it to `run_backtest`: the wiring arrives with the stage code (D-344, `StrategySpec`). Until then the hash describes settings a stage does not read yet.
