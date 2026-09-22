# RUNBOOK — T12: stage 1, edge discovery (stream A)

One task, **critical (D-402)**: it adds a gate criterion and builds the first stage. Task file:
`docs/tasks/T12_stage1_edge_discovery.md` (§1 … §11 supervisor's, §12 supervisor's additions,
§13 planning notes). Decisions: D-601 … D-612, D-802, and the answers to **P-55 … P-59**.
Features: F-1.1 … F-1.6, F-1.8, F-1.9; F-1.7 reserved (P1); touches F-0.7.1 … F-0.7.3, F-0.8.1,
F-0.9.1.

## Branches

| step | branch | base | stop |
|---|---|---|---|
| plan | `a/docs-T12-plan` | `main` | **"Plan approved"** (D-403) |
| 1 … 9 | `a/T12-edge-discovery` (one task, one review file) | `main` after the plan | after the pilot, only on a §11 trigger; after the review, **"Approved"** (D-402) |

Stream A works in the main folder. `src/strategy_factory/data/` stays stream B's in practice. If
a data-layer change is needed (for example a quality-status accessor on `DataAccess`), stop and
raise it; the stage reads the catalog read-only through `RunContext` instead.

## Before starting (preconditions)

1. P-55 … P-59 answered, or their proposals accepted with "Plan approved".
2. The D-802 PR (#44) merged, so `HANDOFF.md` v7 and `docs/streams/A.md` are on `main`.
3. `main` green; `uv sync` after any entry-point change (D-379).
4. **Stream A's pending range is used up with P-59.** Any question raised during execution
   needs a second pending range from the supervisor first.

## Order of work

0. **Scope, measured.** Repeat the `configs/universe.yaml` check (§12.1) and regenerate if a
   stream-B merge made it stale (D-394). Count the resolved scope: broker universe (D-603) ∩
   references ∩ D-008 split possible, per timeframe, with the `ok` / `warning` split. These
   counts go in the review; none is hard-coded.
1. **Statistics helpers** (`stats/`): percentile (strictly below, ×100), empirical p with the
   1/1001 floor, Benjamini–Hochberg q-values, the two-proportion z-test. Tests: hand cases, a
   worked BH example, the boundaries.
2. **Config and metrics.**
   - `configs/stages/s01_edge.yaml` with a Pydantic model: probe list and groups, the
     applicable groups (D-233), the baseline count (1000), the draw attempts, the ESS constants
     (D-606), `consistency_min_trades_per_year`, BH q.
   - `metrics/ess.py`: four components with raw values and points, and the total.
   - `metrics/names.py`: register `probe_q_value` and the stage-1 statistics; re-describe `ess`
     as the 0–100 edge strength score (§13).
   - `configs/gates/default.yaml`: `probe_q_value <= 0.1` under `s01_probe`.
   - Tests: every ESS component at its boundaries; a weight change in config moves ESS
     (F-1.6); a threshold change moves the gate (F-0.8.1).
3. **Probe exits** (F-1.3, P-56). MR `close > high[i-1]` (long) and `close < low[i-1]` (short) as
   registered exit rules in `components/exits/`; the TF reverse signal from the probe's own
   opposite signal; time caps 5 / 50; the 3-ATR disaster stop on every probe.
   - The parity harness switches to the shared MR rule, and **the parity gate must still pass
     unchanged** (rule 9).
   - Tests: unit cases per exit; truncation (leakage) tests.
4. **Zero costs and the baseline** (F-1.4, P-57).
   - A zero-cost `CostInputs` factory.
   - `baseline/random_entries.py`: allowed bars; the exact count; an exact permutation of the
     probe's `bars_held`; no overlap; D-607 seeds (sha256 of run seed, symbol, timeframe,
     probe, direction).
   - The run path: `simulate` per simulation (measured, §13).
   - Tests: the matched properties are equal by construction; no overlap; the same seed gives
     the same draws; order and chunking change no number.
5. **Stage framework** (P-58).
   - `RunContext` (config, `DataAccess`, a read-only reference-info view, registry writer,
     executor, gates, seed; **no `SplitManager`**), `Stage`, `StageResult`.
   - `stages/edge_profile.py`: `EdgeProfile` with its JSON schema, `schema_version`, the
     D-610 caveats and the reserved `complementary_stats` (P-59).
   - The artifacts writer under `SFAC_ARTIFACTS_ROOT`.
   - `symbols: broker` resolved by `resolve_config`.
6. **The stage** `stages/edge.py`, and a minimal `sfac run --config` for `s01_edge` only.
   - One work unit per (symbol, timeframe, edge type, direction).
   - The parent writes candidates, trials (one per probe × direction, `family_id` = edge type),
     `gate_results` through `GateEngine`, and artifacts.
   - `summary.json` per profile; `trades.parquet` only for the accepted probes of passing
     profiles (D-608); `index.parquet` for the universe (P-59).
7. **Tests** (§9 of the task, plus the D-354 grep tests).
   - Unit tests for each part.
   - Random-walk and planted-edge fixtures, slow-marked where they are heavy.
   - Stage-level leakage: truncation of the statistics.
   - A static holdout test: no `SplitManager` or `open_holdout` in the stage modules.
   - Serial vs parallel runs bit-identical (D-607).
   - Every gate criterion failed in turn, named in the result.
   - `probes_run` equals the trial rows.
8. **Pilot** (§7, §10): 10 symbols chosen to cover 1D and 1H, `ok` and `warning`, and one research
   window.
   - Measure the per-probe cost and project the full run.
   - Run it twice and compare: identical numbers.
   - **Checkpoint to the supervisor only on a §11 trigger:** the projected compute exceeds a few
     hours, ESS constants look badly placed, or a probe falls systematically below the 1H
     minimum. Otherwise continue.
9. **Full run and control.** The MVP scope, then the random-walk control at the same scale
   (P-57). The review reports:
   - profiles and passes;
   - the ESS distribution;
   - failing-criterion counts;
   - the `probes_run` total;
   - **the pass rate by quality status for 1D and for 1H, with the z-test** (§12.2);
   - the 1H pass rate separately (B_data_state item 3);
   - **the random-walk pass count, the headline**. If it is not small, stop and take it to the
     supervisor before anything builds on it.
10. **Close.**
    - Acceptance commands: fast suite, parity/leakage/oracle, db with 0 skipped, ruff, format,
      mypy, `sfac streams check`.
    - The `acceptance-reviewer` subagent.
    - `docs/reviews/T12_review.md`, stating D-802's open gap and the D-336 research default.
    - Push, PR, **stop for "Approved"** (D-402).

## Rules for this task

- No threshold, weight or constant in code (rule 1): all in `s01_edge.yaml` or the gate YAML.
- Development data only; the stage never holds a `SplitManager` (rule 2, D-306).
- No look-ahead: every new signal, exit and statistic gets a truncation test (rule 3).
- Costs: probes and baseline at zero; PF with the full Moneta profile (D-602, rule 4).
- Every probe × direction evaluated is a trial; baseline simulations are not (rule 5, D-012).
- The engine is not changed (§13). If that turns out wrong, stop: an engine change is critical.
- No new dependency: stats in NumPy (`math.erfc` for the z-test).
- Stream-A paths: `stages/`, `baseline/`, `metrics/`, `components/`, `configs/gates/`,
  `configs/stages/` (D-611, D-612); `stats/`, `core/` and `tests/` are shared; `data/` is not
  touched.
