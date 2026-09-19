# T10b — Executor and metric-name registry

**Features:** F-0.3.7 (batch and parallel execution), F-0.8.1 (gate engine: metric names validated), F-0.6.1 (holdout only from stage 6) · **Priority:** MVP · **Depends on:** T08 (grid kernel), T09 (metrics), T10a (gates), T05 (split manager)

Read first: `CLAUDE.md`, `docs/design.md` §4 (`RunContext`, `Executor`), §10 (two-level parallelism), ADR-005, `docs/reviews/T09_review.md` (`as_gate_dict()` names, `core_metrics_batch`), `docs/reviews/T10a_review.md` (gate table, open questions), `docs/reviews/T05_review.md` (open question 1), `docs/reviews/T08_review.md`, and decisions **D-012, D-301, D-306, D-308, D-309**, plus pending answers **P-20, P-22, P-23**.

## Scope

### 1. Executor (F-0.3.7, `pipeline/executor.py`)
- `Executor` Protocol (design §4, ADR-005): `map(fn, work_units) -> list[result]`, results in **input order**, deterministic.
- `SerialExecutor` (reference) and `ProcessPoolExecutor`-based `LocalExecutor`. Work unit = (symbol, timeframe, stage) (design §10). The start method is `spawn` on every platform, so Windows and Ubuntu behave the same.
- **Thread budget (P-23):** `workers × numba_threads ≤ os.cpu_count()`; both come from `configs/pipeline/executor.yaml` (defaults: `workers: auto`, `numba_threads: auto`), set in each worker with `numba.set_num_threads` before any kernel runs.
- **Grid chunking (P-20):** `run_grid(bars, cost_arrays, signal_matrix, params, chunk_cols)` splits configurations into column chunks so `n_bars × chunk_cols × 8 bytes × 2` stays under `max_grid_bytes` (config); chunk results are concatenated in order. Output = T09 `core_metrics_batch` input per chunk → one metrics table per grid.
- **Seeds:** every work unit gets a seed derived from the run seed and the unit key (sha256), never from the worker id, so parallel = serial.
- **Registry writes (D-012, P-23):** workers return results; only the parent writes trials through the batched `RegistryWriter` (COPY). One trial per evaluated configuration; the trial count equals the number of configurations (F-0.7.1).
- Errors in a worker are re-raised in the parent with the unit key; completed units are not lost.

### 2. Metric-name registry (D-309, `metrics/names.py`)
- One registry: `MetricName(name, unit, description, producer)` where `producer` is `metrics.core`, `metrics.batch` or a stage id (`s01_probe`, `s02_screen`, …) for stage-level metrics that later stages will compute.
- The core names are exactly `MetricsReport.as_gate_dict()` keys (including the T08 additions `n_skipped_min_volume`, `min_volume_skip_flag`, `volume_step_assumed` from D-313/D-314) and the `core_metrics_batch` keys; a test asserts both producers emit only registered names and all of them.
- The stage-level names used in `configs/gates/default.yaml` are registered now with their producer stage (P-22), so the YAML validates.
- `GateConfig` validation: **an unknown metric in the YAML is an error at load time** (every stage and every override).
- **Reconciliation of the gate YAML (P-22):**
  - `min_trades` → `n_trades` (closed trades, D-301) in `s01_probe` and its 1H override;
  - `mc_dd95_within_tolerance == 1` → `mc_max_dd_p95_pct <= 25` (D-308; % of initial capital, the 25 in YAML);
  - any other mismatch found is listed in the review.

### 3. Holdout stage guard (D-306, F-0.6.1)
- `SplitManager.open_holdout(candidate_id, symbol, timeframe, *, stage)`: any `stage` other than `s06_robust` raises `HoldoutAccessError` **before** the ledger is touched. The allowed stage name comes from config, not a literal in the method.
- All existing callers and tests are updated; the one-shot rule is unchanged.

## Tests
- **F-0.3.7:** a grid of ≥ 200 configurations on synthetic bars: `LocalExecutor` (2 and 4 workers) gives results **identical** to `SerialExecutor` (metrics `==`, order, seeds, registry rows); chunked grid = unchunked grid; a failing unit reports its key; thread budget respected (mock `cpu_count`).
- Registry: trial count = number of configurations (DB test); only the parent writes.
- **D-309:** unknown metric in base or override → load error; all names in `default.yaml` registered; `as_gate_dict()` and batch keys ⊆ registry and equal to the `metrics.core` / `metrics.batch` sets.
- **D-308:** the renamed MC criterion evaluates correctly (`24.9` pass, `25.1` fail).
- **D-306 / F-0.6.1:** `open_holdout` from any stage other than stage 6 raises and writes nothing to the ledger; from stage 6 it works once and the second call raises (DB test, 0 skipped).

## Acceptance
- ruff, format, mypy (strict for `gates`, `core`, `data`; `pipeline/executor.py` typed), fast suite, parity + leakage, `pytest -m db` 0 skipped.
- **Scalability report** (F-0.3.7 acceptance): wall time of the same grid with 1, 2, 4, … workers up to the core count on the development machine, as a table in the review, plus speed-up and efficiency. No threshold.

## Review summary
`docs/reviews/T10b_review.md`: executor design, thread budget, chunking rule, scalability table, the full metric-name registry (name, unit, producer), the YAML changes, the holdout guard, deviations, open questions.
