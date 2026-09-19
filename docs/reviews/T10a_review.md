# T10a review — Gate engine, pipeline config and universe

**Features:** F-0.8.1, F-0.8.2, F-0.9.1 · **Branch:** `feat/T10a-gates-config-universe` (stacked on T06) · **Status:** done, with open questions below

## What was built
| file | content |
|---|---|
| `gates/engine.py` | `GateConfig` (YAML: `borderline_tolerance`, `stages`, `overrides` by `asset_class`, `timeframe`, `combined` "fx/1H"); `GateEngine.criteria/evaluate`; `GateResult` / `CriterionResult`; `record()` → `RegistryWriter.add_gate_results` |
| `configs/gates/default.yaml` | all gate values (table below) |
| `core/config.py` | `PipelineConfig`, `SnapshotRef`, `load_pipeline_config`, `validate_config`, `resolve_config` (catalog references → `data_snapshots`), `require_resolved`, `start_run`, `config_hash` |
| `registry/writer.py` | `require_snapshots()`: `RegistryWriter.start_run` refuses a config without resolved `data_snapshots` (T03 open question 2) |
| `core/universe.py` | `UniverseEntry`, `Universe`, `generate_universe`, `write_universe`, `load_universe` (libyaml loader), `validate_universe` |
| `configs/universe.yaml` | generated, 6749 symbols |
| `configs/pipeline/{sample_h1,mvp_daily}.yaml` | sample configs |
| `core/cli.py` | `sfac config validate|resolve`, `sfac universe list|validate|generate` |

## Default gate table (as loaded from `configs/gates/default.yaml`)
Shares are fractions and percentiles are 0–100. `crit` marks a critical criterion, never borderline. Borderline tolerance: **0.10**.

| stage | metric | op | threshold | crit | spec source |
|---|---|---|---|---|---|
| **s01_probe** | min_trades | ≥ | 30 (1H: **100**) | | stage 1: min trades per probe, daily 30 / hourly 100 |
| | probe_percentile | ≥ | 90 | | probe percentile in the random baseline |
| | profit_factor | ≥ | 1.1 | | PF after costs |
| **s01_edge** | accepted_probe_groups | ≥ | 3 | | accepted probe groups |
| | ess | ≥ | 50 | | ESS |
| **s02_screen** | grid_median_target | > | 0 | | grid median positive after costs |
| | profitable_cell_share | ≥ | 0.60 | | profitable cells |
| | overlap_with_selected | ≤ | 0.60 | | overlap with selected candidates |
| | min_trades_good_cells | ≥ | 30 (1H: **100**) | | "as stage 1" |
| **s03_entry** | spp_median_target | > | 0 | | SPP median profitable |
| | stability_ratio | ≥ | 0.8 | | neighbourhood ratio |
| | plateau_area | ≥ | 0.10 | | plateau ≥ 10 % of the space |
| | selected_in_both_halves | == | 1 | | accepted in both halves |
| *s01s_seasonal (P1)* | q_value | ≤ | 0.1 | | BH q-value |
| | direction_stable_years_share | ≥ | 0.70 | | direction stable in 70 % of years |
| | shift_1h_effect_retained | ≥ | 0.60 | | ±1 h shift keeps 60 % |
| | profit_cost_x1_5 | > | 0 | | profit with cost stress 1.5 |
| *s04_exit (P1)* | exit_improvement | ≥ | 0.10 | | +10 % … |
| | exit_improvement_years_share | > | 0.5 | | … "in most years" |
| | exit_spp_median_target | > | 0 | | "as stage 3" |
| | exit_stability_ratio | ≥ | 0.8 | | "as stage 3" |
| | exit_plateau_area | ≥ | 0.10 | | "as stage 3" |
| | entry_still_in_plateau | == | 1 | | |
| | free_params_total | ≤ | 5 | | max 5 free parameters |
| *s05_filter (P1)* | filter_improvement_percentile | ≥ | 95 | | vs 1000 random removals |
| | trades_retained_share | ≥ | 0.60 | | |
| | years_improved_share | ≥ | 0.60 | | |
| | bucket_min_trades | ≥ | 30 | | |
| | bucket_q_value | ≤ | 0.1 | | |
| | bucket_direction_stable_years_share | ≥ | 0.70 | | |
| | bucket_stable_both_halves | == | 1 | | |
| | filter_count | ≤ | 2 | | |
| *s06_robust (P1)* | wf_efficiency | ≥ | 0.50 | ✔ | WFE |
| | wf_oos_profitable_share | ≥ | 0.60 | ✔ | profitable OOS windows |
| | wf_matrix_success_share | ≥ | 0.60 | ✔ | WF matrix cells |
| | profit_cost_x2 | > | 0 | ✔ | profit with 2× costs |
| | mc_dd95_within_tolerance | == | 1 | | MC 95th-pct drawdown "within the defined tolerance" |
| | holdout_band_percentile | ≥ | 5 | ✔ | holdout above the 5th percentile of the band |
| *s07_stats (P1)* | t_test_p | < | 0.05 | | |
| | bootstrap_ci_lower | > | 0 | | |
| | permutation_p | < | 0.05 | | |
| | dsr | ≥ | 0.95 | | DSR with the effective N |
| | pbo | ≤ | 0.25 | | |
| | spa_p | < | 0.05 | | Hansen SPA |
| | min_trl_ratio | < | 1 | | MinTRL < available data |

## Universe counts (`configs/universe.yaml`, `sfac universe validate`)
| asset class | symbols | source | timeframes | calendar | cost profile | tradable |
|---|---|---|---|---|---|---|
| us_equity | 6713 | alpaca | 1D (6711) + 1H (827, of which 2 hourly-only: CCE, VMRK) | nyse | us_equity_default | yes |
| fx | 15 | dukascopy | 1H, 1D | 24x5 | fx_default (JPY pairs pip 0.01) | yes |
| metal | 2 | dukascopy | 1H, 1D | 24x5 | metal_default | yes |
| index_cfd | 10 | dukascopy | 1H, 1D | 24x5 | index_cfd_default | yes |
| energy_cfd | 2 | dukascopy | 1H, 1D | 24x5 | energy_cfd_default | yes |
| aux | 7 | yahoo | 1D | nyse (DXY: 24x5) | — | **no** |
| **total** | **6749** | | | | | 6742 tradable |

`sfac universe validate` → ok. It also checks the three catalog references (Dukascopy pilots): each source is `dukascopy` and each asset class matches.

`sfac config resolve configs/pipeline/sample_h1.yaml` → EURUSD `899ac745…`, XAUUSD `4e135eb4…`, USA500IDXUSD `4cf2fab5…` (all dukascopy 1H); config_hash `a27c7aef…c2c9`. `mvp_daily.yaml` validates. Resolving it gives the expected error "no reference snapshot in the catalog for: SPY 1D, QQQ 1D, AAPL 1D" until the Alpaca daily ingest runs.

## How each criterion is tested
| criterion | test |
|---|---|
| F-0.8.1 each operator | `test_F_0_8_1_each_operator` (11 cases incl. boundaries and booleans) |
| overrides (asset class, timeframe, combined; replace and add) | `_overrides_by_asset_class_timeframe_and_combined` |
| missing metric = failure | `_missing_and_nan_metrics_fail` |
| borderline: one non-critical within 10 % → yes; two failures / critical / beyond 10 % → no | `_borderline_rule` (6 cases), `_borderline_tolerance_from_config_and_zero_threshold` |
| changing a threshold in config changes the result (acceptance) | `_changing_threshold_in_config_changes_result` |
| defaults as specified | `_default_gates_as_specified` |
| results written to the registry | `_results_written_to_registry` (`db`) |
| F-0.8.2 resolution picks the catalog references | `test_F_0_8_2_resolution_picks_catalog_references` |
| unresolved snapshot refused (config layer and writer) | `_unresolved_snapshot_is_refused`, `_registry_writer_requires_snapshots` |
| config_hash stable under key reordering (and equal to the registry's hash) | `_config_hash_stable_under_key_order`, `_config_hash_equals_registry_hash` |
| validation errors, source mismatch, critical quality refused | `_validation_errors`, `_source_mismatch_and_critical_quality` |
| CLI; repo sample configs valid | `_cli_resolve_and_validate`, `_repo_sample_configs_are_valid` |
| F-0.9.1 generation from existing universes; aux non-tradable | `test_F_0_9_1_generation_from_existing_universes` |
| each validation error | `_validation_errors` (duplicate symbol, wrong/missing cost profile, tradable without profile, unknown asset class, catalog source and asset-class mismatch, reference for an unknown symbol) |
| repo universe valid and complete | `_repo_universe_is_valid_and_complete` |
| CLI list/validate | `_cli_list_and_validate` |

## Acceptance
| command | result |
|---|---|
| `ruff check .` / `ruff format --check .` | ✅ / ✅ |
| `mypy src` (strict for `gates` and `core`) | ✅ 68 files |
| `pytest` | ✅ **343 passed** (37 new) |
| `pytest tests/parity tests/leakage` | ✅ 2 passed |
| `pytest -m db` | ✅ 15 passed, **0 skipped** |
| `sfac universe validate` | ✅ |
| `sfac config resolve configs/pipeline/sample_h1.yaml` | ✅ |

## Deviations
1. **Stage 1 is split into two gate sets, `s01_probe` and `s01_edge`.** The spec has probe-level criteria (trades, percentile, PF) and edge-level criteria (groups, ESS).
2. **Criteria that are not a single number are expressed as metrics with `== 1`** (e.g. `selected_in_both_halves`), or split ("≥ 10 % and in most years" → `exit_improvement` + `exit_improvement_years_share > 0.5`). Metric names are my choice; they are documented in the YAML and have to be produced under these names by the stages (T12+).
3. **Critical criteria are those the spec says are never borderline:** Walk-Forward (all three WF criteria), 2× cost stress and holdout. All others are non-critical.
4. **A threshold of 0 (`> 0`) has no relative 10 % distance,** so such a failure is never borderline.
5. **`start_run` now requires `data_snapshots`.** The existing T03 tests were updated to pass a resolved config (the fixture `RUN_CONFIG`). `sfac reproduce` finds the hashes under `config.data_snapshots.<SYM>.<TF>.snapshot_hash`.
6. **The universe is one YAML file of 1.1 MB** (one line per symbol) and loads with libyaml in about 1 s. `sfac universe generate` regenerates it; do not edit it by hand.
7. **Dukascopy symbols list `timeframes: [1H, 1D]`,** with 1D coming from resampling the 1H reference. 4H is not listed yet: it is not an MVP timeframe.
8. **Groups are the asset class for now** (`us_equity`, `fx`, `metal`, `index_cfd`, `energy_cfd`, `aux`). The aux calendar is `nyse` except for DXY (`24x5`).
9. **`resolve_config` also refuses a reference whose quality status is critical** (`ensure_usable`) or whose source differs from the universe's reference source.

## Open questions
1. **`mc_dd95_within_tolerance`:** the spec says "within the defined tolerance" but gives no number. Which tolerance, e.g. a multiple of the backtest's average annual drawdown?
2. **Stage 4 "improvement ≥ 10 % or keep the base exit":** keeping the base exit is stage logic (then there is no new exit to gate). OK?
3. **Groups for cross-symbol validation:** asset class as a placeholder. Should we have finer groups (e.g. US index CFDs vs European and Asian, USD majors vs crosses, US equity sectors)?
4. **Stage 0 (parity/quality/reproduction) and stage 8 (report checks) are not in the gate YAML:** they are not per-candidate metrics. They will be enforced by T11 (parity) and `sfac report verify`.
