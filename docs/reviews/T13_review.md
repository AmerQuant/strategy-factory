# T13 — Stage 2: method screening (s02_screen) — review

Branch `a/T13-method-screening`, stacked on `a/T13-plan` (plan and decisions). Features F-2.1 …
F-2.7; decisions **D-622 … D-637** (T13 §2, the plan's answers, the pilot's answer). Plan:
`docs/tasks/T13_plan.md`; pilot: `docs/reviews/T13_pilot.md`. **Stopped for "Approved".**

> **Open parity gap (D-802).** D-335 and D-336 are unverified against TradingView (T11b is
> parked). **D-336 is the research default and shaped every MR run here**: an exit scheduled at
> a close may be followed by a re-entry at the same open. If T11b later shows an engine
> difference, these results may need re-running; every run records its `code_version`.

## 1. The headline: the control (D-629)

Stage 2 on the **same** 18 stage-1 passes with each symbol's returns reshuffled (D-615, T12's
seeds):

| | 1D control | 1H control |
|---|---|---|
| run id | `625a0f5c…` | `8246d5f7…` |
| methods screened (profiles) | 280 (14) | 60 (4) |
| **pass the gate** | **0** | **0** |
| stopped by `method_q_value` **alone** | **45** | **11** |
| lowest `method_q_value` of any method | 0.040 (it failed the target criteria) | 0.79 |

**No method passes on the control.** The number that says why is the second row: **45 daily
methods clear every other criterion** on the permuted series — on high-drift longs (AAPL, MSFT,
ETN, SHW, TMUS; GNRC and TXN once each) — and only the comparison with the matched random
baseline stops them. The gate as first specified had no such term and passed 43 of 266 in the
plan's measurement; D-629 added it.

## 2. The full run

| | 1D | 1H (all `unconfirmed`, D-621, D-628) |
|---|---|---|
| run id | `3c76a3fa…` | `4ded5d1b…` |
| stage-1 passes screened | 14 (13 symbols) | 4 |
| methods / cells run (= trials, D-160) | 280 / **4,256** | 60 / **1,008** |
| pass every criterion but the overlap | 111 | 45 |
| … stopped by the overlap (F-2.6) only | 86 | 39 |
| **selected** | **25** | **6** |
| profiles with **fewer than 3** (D-625) | **11 of 14** | **4 of 4** |
| wall time | 57 s | 20 s |

Criterion failures on 1D (a method can fail several): `overlap_with_selected` 202,
`profitable_cell_share` 141, `grid_median_target` 117, `method_q_value` 88. The pilot showed
the run reproduces byte for byte (pilot §2); every artifact records its config hash,
stage-config hash, seed and code version. The four run indexes are copied to
`docs/reviews/T13_index_{1D,1H,1D_control,1H_control}.csv`.

## 3. Per profile

Family score (zero cost, D-623), the grid median target zero cost → after costs, the
good-region median cell's q, and the cell. `pre` = methods passing every criterion but the
overlap.

**1D, long**

| profile | pre | selected (rank) | family | median, zero → after cost | q | median cell |
|---|---|---|---|---|---|---|
| MSFT | 18 | `mr_ibs_after_new_high` (1) | 100.0 | 1.41 → 1.05 | 0.031 | n 10, t 15 |
| | | `mr_zscore` (2) | 96.9 | 1.68 → 1.33 | 0.020 | n 20, t 1.0 |
| | | `mr_macd_hist_falling` (12) | 88.0 | 0.70 → 0.44 | 0.022 | k 2 |
| TXN | 19 | `mr_ema_slope_drop` (1) | 98.4 | 1.75 → 1.12 | 0.009 | n 8, p 0.5 |
| | | `mr_macd_hist_turn` (17) | 84.3 | 0.70 → 0.31 | 0.040 | k 2 |
| | | `mr_macd_hist_falling` (19) | 82.5 | 0.66 → 0.24 | 0.092 | k 3 |
| TMUS | 13 | `mr_down_closes` (1) | 96.2 | 1.09 → 0.24 | 0.083 | k 3 |
| | | `mr_n_day_low` (6) | 93.3 | 0.88 → 0.38 | 0.082 | n 20, low |
| | | `mr_williams_confirm` (15) | 82.7 | 0.77 → 0.35 | 0.082 | n 20, t 20, same_bar |
| AAPL | 9 | `mr_ibs_after_new_high` (1), `mr_down_closes` (2) | 100.0, 96.2 | 2.06 → 1.69, 1.52 → 1.11 | 0.020, 0.035 | |
| RTX | 6 | `mr_n_day_low` (2), `mr_candle_score` (9) | 86.5, 72.6 | 0.71 → 0.42, 0.45 → 0.16 | 0.033, 0.020 | |
| SHW | 11 | `mr_connors_rsi` (1) | 98.1 | 1.24 → 0.75 | 0.004 | rsi_len 2, t 30 |
| ETN | 5 | `mr_n_day_low` (1) | 96.0 | 1.17 → 0.55 | **0.092** | n 20, low |

**1D, short**

| profile | pre | selected (rank) | median, zero → after cost | q |
|---|---|---|---|---|
| K | 9 | `mr_stochastic_k` (1), `mr_macd_hist_falling` (3) | 0.97 → 0.48, 0.65 → 0.21 | 0.020, 0.038 |
| TXN | 5 | `mr_ema_slope_drop` (1), `mr_rsi_sum` (5) | 0.90 → 0.48, 0.68 → 0.23 | 0.004, 0.005 |
| TJX | 2 | `mr_rsi_sum` (1), `mr_macd_hist_falling` (2) | 0.75 → 0.34, 0.50 → 0.15 | 0.044, 0.095 |
| EEM | 10 | `mr_n_day_low` (1) | 1.00 → 0.67 | 0.017 |
| ADI | 1 | `mr_rsi_sum` (1) | 0.69 → 0.38 | 0.020 |
| GNRC | 1 | `mr_candle_score` (1) | 0.43 → 0.11 | 0.028 |
| LEN | 2 | `mr_stochastic_k` (1) | 0.68 → 0.37 | 0.063 |

**1H, long — `unconfirmed`, reported apart, never standing in for the daily MR finding (D-628)**

| profile | pre | selected (rank) | median, zero → after cost | q |
|---|---|---|---|---|
| TSLA | 15 | `tf_hma_turn` (1), `tf_ichimoku` (5) | 1.51 → 1.26, 1.47 → 1.36 | 0.003, 0.006 |
| ARKK | 15 | `tf_base_candle` (1), `tf_sma_cross` (14) | 1.47 → 1.13, 0.56 → 0.48 | 0.002, 0.038 |
| BAC | 9 | `tf_keltner_breakout` (1) | 1.51 → 0.88 | 0.038 |
| MRNA | 6 | `tf_ichimoku` (2) | 0.95 → 0.59 | 0.067 |

Readings, stated plainly:

- **Costs take a third to three quarters of the daily edge.** The median target after costs is
  typically 40–70 % of the zero-cost one on the selected daily methods (TMUS `mr_down_closes`
  keeps 22 %). Every selected method is still positive after costs across its grid (the gate).
- **ETN long keeps one method, `mr_n_day_low`, at q 0.092 — just inside 0.1.** The plan's
  measurement (approximate warm-ups, the pre-split library, the task grid for `mr_n_day_low`)
  gave ETN none. Five methods pass every criterion but the overlap, **all at the same q, 0.092**
  (the BH step-up gives several methods one q), and the next ones sit at 0.109–0.128. On this
  evidence ETN's daily edge is weak: it clears the baseline test only at the edge of the
  threshold, and a drift-dominated stock is exactly where that is expected.
- **The short profiles are thin**: ADI, GNRC and LEN each have a single method that passes at all;
  their stage-1 edges rest on one rule each.
- **The four hourly profiles pass heavily and not on the control** (0 of 60). They stay
  `unconfirmed`: stage 2 cannot separate a trend edge from the D-621 caveats (uncleaned hourly
  layer, residual TF bias).

## 4. The diversity rule and the fixed exit (D-637)

**11 of 14 daily profiles and all 4 hourly ones end with fewer than 3 candidates**, while 111 and
45 methods passed every other criterion. Mean-reversion methods with the fixed 5-bar exit are in
position on the same pullback bars; among MSFT's top six the overlap (the share of the smaller
candidate's in-position bars, D-637) is 0.66–0.98. Under D-637 a method nested inside another
adds no independent trade, so each cluster contributes one method; D-625 sends what passed and
this review says so. On BAC, one selection means several trend rules see one edge — a finding,
not a shortfall. **The high MR overlap is partly the fixed 5-bar exit (D-622), and may fall once
stage 4 frees the exits.**

## 5. The user's suite, measured by the same yardstick (T13 §10)

| method | script | passed (before diversity) / screened | selected |
|---|---|---|---|
| `mr_macd_hist_falling` | #17 | 10 / 14 | **4** (MSFT, TXN L, K, TJX) |
| `mr_n_day_low` | #5 | 9 / 14 | **4** (ETN, RTX, TMUS, EEM) |
| `mr_rsi_sum` | #2 | 9 / 14 | **3** (ADI, TJX, TXN S) |
| `mr_candle_score` | #18 | 9 / 14 | **2** (RTX, GNRC) |
| `mr_down_closes` | #4 | 6 / 14 | **2** (AAPL, TMUS) |
| `mr_ema_slope_drop` | #10 | 6 / 14 | **2** (TXN L, TXN S) |
| `mr_ibs_after_new_high` | #14 | 2 / 14 | **2** (MSFT, AAPL) |
| `mr_macd_hist_turn` | #20 | 1 / 14 | 1 (TXN L) |
| `mr_williams_confirm` | #22 | 4 / 14 | 1 (TMUS, `same_bar`) |
| `tf_base_candle` | #23 | 2 / 4 | 1 (ARKK) |
| `mr_lower_lows` | #3 | 6 / 14 | 0 — passed, lost to overlap |
| `mr_ma_distance_pct` / `_atr` | #9 / #8 | 5 / 4 of 14 | 0 — lost to overlap |
| `mr_ibs` | #0 | 4 / 14 | 0 — lost to overlap |
| `mr_rsi` | #1, #19 | 4 / 14 | 0 — lost to overlap |
| `mr_daily_drop` | #6, #7 | 3 / 14 | 0 — lost to overlap |
| `tf_atr_band` | #11 | 2 / 4 | 0 — lost to overlap |

**22 of the 31 selections are the user's rules** (MR 21 of 25; TF 1 of 6). The library methods
selected: `mr_stochastic_k` (2), `mr_zscore`, `mr_connors_rsi`; `tf_ichimoku` (2), `tf_hma_turn`,
`tf_keltner_breakout`, `tf_sma_cross`. No user rule failed everywhere; the unselected ones pass
every other criterion somewhere and lose to a higher-ranked method holding the same bars.

About the script itself (D-632): **the short of #18 (candle score) is a slip in the script** — it
uses the same threshold as the long (`≥ −7`) and fires on 88 % of daily bars; the short here is
the mirror (`≥ +7`). **#2's short, `> 140`, is not a mirror** of `< 20` (the mirror is `> 180`).
#11 and #22 have no short in the script; they get the framework mirror. Williams (#22) as the
user's backtests ran it is the `same_bar` reading (the trigger has no `var`); the `latched`
reading was screened too (D-633) and selected nowhere.

## 6. Grids: the task's and the replacement (D-631)

Measured on the real passes before the plan (`docs/tasks/T13_plan.md` §3,
`docs/reviews/T13_plan_grid_summary.csv`): share of cells reaching the trade minimum, and the
mean profitable share after costs, real / control.

| method | task grid | min-trades | profitable | replacement | min-trades | profitable |
|---|---|---|---|---|---|---|
| `mr_zscore` | n {10,20,30,40}, t {1.5,2,2.5,3} | 50 % | 36 / 12 % | t {1.0,1.25,1.5,2.0} | 99 % | 63 / 21 % |
| `mr_connors_rsi` | rsi_len {2..5}, t {5,10,15,20} | 29 % | 29 / 16 % | t {15,20,25,30} | 62 % | 56 / 33 % |
| `mr_rsi_sum` | n {2..5}, m {2,3}, level {5,10,15,20} | 46 % | 43 / 13 % | level {15,20,25,30} | 86 % | 72 / 20 % |
| `mr_rsi` | n {2,3,5,14}, t {10,20,30,35} | 75 % | 56 / 20 % | n {2,3,5,7}, t {15,20,30,35} | 83 % | 62 / 21 % |
| `mr_ibs` | t {10,20,30,40}, k {1,2,3} | 74 % | 47 / 26 % | t {15,20,30,40} | 81 % | 52 / 30 % |
| `mr_ibs_after_new_high` | n {5,10,20,50}, t {10,15,20,25} | 64 % | 29 / 41 % | n {3,5,10,20}, t {15,20,25,30} | 94 % | 33 / 35 % |
| `mr_ema_slope_drop` | n {3,5,10,20}, p {0.25,0.5,1,1.5} % | 73 % | 47 / 20 % | n {3,5,8,10}, p {0.25,0.5,0.75,1} % | 93 % | 61 / 21 % |
| `mr_candle_score` | n {2,3,5,8}, level {−3…−1.5} | 78 % | 54 / 19 % | n {2,3,4,5}, level {−2.5…−1} | 95 % | 61 / 27 % |
| `mr_stochastic_k` | t {5,10,20,30} | 73 % | 44 / 17 % | t {10,15,20,30} | 94 % | 57 / 22 % |
| `mr_keltner_lower` | mult {1,1.5,2,2.5} | 79 % | 51 / 19 % | mult {0.5,1,1.5,2} | 92 % | 54 / 20 % |
| `mr_lower_lows` | k {2,3,4,5} | 88 % | 61 / 25 % | k {1,2,3,4} | 100 % | 61 / 32 % |
| `mr_n_day_low` | n {3,5,7,10} | 100 % | 70 / 26 % | n {3,5,10,20}, source {low, close} (D-634) | 100 % | 70 / 25 % |
| `tf_sma_cross` | fast {10..40}, slow {60,100,150,200} | 27 % | 27 / 12 % | fast {5,10,15,20}, slow {30,50,75,100} | 83 % | 81 / 42 % |
| `tf_bb_upper` | mult {1.5,2,2.5,3} | 64 % | 64 / 16 % | mult {1,1.5,2,2.5} | 89 % | 86 / 23 % |
| `tf_adx_di` | n {7,14,21,28}, t {15..30} | 61 % | 50 / 17 % | n {5,7,10,14}, t {10..25} | 98 % | 72 / 19 % |
| `tf_keltner_breakout` | mult {1,1.5,2,2.5} | 88 % | 88 / 36 % | mult {0.75,1,1.5,2} | 98 % | 98 / 34 % |
| `tf_aroon_cross` | n {14,25,50,100} | 75 % | 75 / 19 % | n {10,14,25,50} | 100 % | 88 / 19 % |

Also split by D-630: `mr_ma_distance` → `mr_ma_distance_pct` (p {0.5,1,2,3} %) and
`mr_ma_distance_atr` (a {0.25,0.5,1,1.5}), n {5,10,20,50} each. `tf_base_candle` gained the
strong-close fraction {0.25, 1/3, 0.4, 0.5} (the script has none). Dual momentum is deferred to P1
(D-635). **Caveat on the plan's numbers:** the plan's script used the textbook Connors RSI, whose
mirror was broken (§8), so its Connors figures on the short profiles are not this code's.

## 7. What was built

| module | content |
|---|---|
| `components/base.py` | `GridRules`: 2 to 4 coarse values per parameter (D-630), ≤ 64 cells |
| `components/entries/methods_mr.py`, `methods_tf.py` | 20 MR + 15 TF stage-2 methods (`screen = True`), each with a declared `warmup(params)`; ratio rules and Connors' ROC in the `\|ref\|` form (D-632) |
| `configs/stages/s02_screen.yaml`, `stages/screen_config.py` | methods per edge type (validated both ways against the registry), good-region share, baseline draws, family-score constants, selection, `unconfirmed_timeframes`; **the exits are read from `s01_edge.yaml`** and cannot be restated (D-622) |
| `metrics/family.py` | family score, good region and its median cell, failed cells as −∞, weighted rank-sum, overlap (D-637), the diversity walk |
| `metrics/names.py`, `configs/gates/default.yaml` | `method_q_value <= 0.1` under `s02_screen` (D-629) |
| `stages/screen.py`, `stages/screen_artifact.py` | the stage (see its docstring), `MethodScreen` schema v1 (stage 3's input, F-2.7) |
| `core/config.py` | `stage_inputs` and `symbol_scope: stage_inputs`; left out of the canonical JSON when empty, so **no existing config hash changes** |
| `pipeline/stage_run.py`, `cli.py` | `run_stage2`; `sfac run` dispatches `s01_edge` / `s02_screen` |
| `configs/pipeline/s02_*.yaml` | the full run, the control, the pilot (per timeframe) |

Nothing in the engine changed. No new dependency.

## 8. Deviations and judgement calls

1. **Connors RSI is computed in the method** with its one-bar ROC as `(c − c[1]) / |c[1]|`: the
   textbook ratio broke the mirrored short, which the engine-truncation gate's vacuity check found
   (pilot §5). Equal to the T07 golden indicator for positive prices (tested).
2. **Stage-2 names** `tf_bb_upper`, `tf_supertrend`, `tf_ichimoku` (the stage-1 probes hold the
   longer names).
3. **Williams `confirm` = {off, same_bar, latched}** (D-633, D-637): 48 cells.
4. **The candle score's first bar is NaN** where the script scores it −3 through Pine's `na`
   comparisons (no previous bar); one bar at the start of a series.
5. **`mr_daily_drop`'s #6 form**: the script writes `close · 1.01 < close[1]` (i.e.
   `close[1] / 1.01`) for #6 and `close < close[1] · 0.99` for #7; the method uses the #7 form for
   both. They differ on ~0.5 % of #6's signals (plan §4).
6. **Artifacts for every method**, not only the selected ones (T13 §8 names the selected): the
   rejected ones carry the verdict and the grid, which the review and stage 7's trial count use.
7. **The T07 tests were scoped to the stage-1 probes** they were written for; the positive-scale
   mirror property cannot hold for a ratio rule under any reflection. The stage-2 methods have
   their own mirror tests (negation for all; positive scale for the 31 translation-invariant
   ones). The engine-truncation gate (F-0.3.9) runs all 35 new methods unchanged.
8. **The baseline warm-up is each method's declared warm-up per cell** (the plan measured with one
   bound of 210 bars); a test asserts no cell ever signals before its warm-up.

## 9. How each acceptance criterion is tested

| criterion | proving test(s) |
|---|---|
| F-2.1 / F-2.2: params declared, ≤ 3 params, 2–4 values, ≤ 64 cells; the library complete | `test_F_2_1_the_library_is_complete_and_listed`, `…every_method_respects_the_coarse_grid`, `test_F_0_4_1_param_spec_requires_two_to_four_coarse_values`, `…d630_*` |
| F-2.1: indicator reference | every indicator is T07's (TradingView goldens); Connors: `…d632_connors_is_the_golden_indicator_for_positive_prices`; the user's rules: `…the_user_rules_equal_a_naive_port_of_the_script` (21 rules, 4 seeds), `…d633_latched_is_the_intended_trigger` |
| D-627: no duplicates | `…d627_no_two_methods_produce_the_same_signals` (SPY 1D, XAUUSD 1H), mutation `…d627_the_guard_catches_a_registered_duplicate` |
| D-626 / D-632: mirror | `…d626_the_short_is_the_long_on_negated_prices`, `…d626_translation_invariant_methods_mirror_on_a_positive_scale`, `…d632_ratio_rules_mirror_exactly`, `…d632_the_literal_ratio_form_would_break_the_mirror` |
| Warm-up (D-615 allowed range) | `…no_method_signals_before_its_warmup` (every cell, 12 series), mutation `…the_warmup_check_catches_a_late_warmup` |
| Rule 3: leakage | `tests/leakage/test_F_2_1_method_truncation.py` (every cell of every method; the stage's own `method_run`), and F-0.3.9 over all 35 methods × 5 exits × 2 modes |
| F-2.3: cells in the registry | db `test_F_0_7_1_stage2_registry_rows` (trials = Σ cells_run, per candidate), `test_F_2_7_every_method_of_every_pass_has_a_valid_artifact` |
| F-2.4: one good cell < uniformly good | `test_F_2_4_one_good_cell_scores_below_a_uniformly_good_method`; boundaries, failed cells, weights, good region, consistency |
| F-2.5: invariant to monotone rescaling | `test_F_2_5_rank_sum_is_invariant_to_monotone_rescaling` (4 transforms), ties, weights |
| F-2.6: no two selected above 60 % | `test_F_2_6_no_two_selected_candidates_overlap_above_the_threshold` (Hypothesis), `…top_two_overlap_the_third_is_chosen`, `…the_cap_holds_and_every_method_gets_a_verdict`, stage-level `test_F_2_6_selection_respects_…` |
| F-2.7: gate by name, thresholds from config | `test_F_2_7_each_criterion_fails_by_name_from_the_config` (5 criteria incl. D-629), `…the_1h_trade_minimum_comes_from_the_override` |
| D-623 wiring: gate after cost, ranking zero cost | `test_F_2_7_d623_the_gate_reads_costs_the_ranking_does_not` (mutation: ranking on the cost leg fails it) |
| D-629: BH within the profile | `test_F_2_7_d629_method_q_is_bh_across_the_profile` |
| F-2.7: artifact is stage 3's input | `MethodScreen` schema; `…every_method_of_every_pass_has_a_valid_artifact`, `…trades_only_for_selected_methods` |
| D-607: serial = parallel | `test_F_2_7_d607_serial_and_parallel_runs_are_bit_identical`; the pilot re-run (byte-identical) |
| Holdout (rule 2, D-616) | T12's `test_F_1_8_d616_*` guard, which scans every `stages/*.py` (so `screen*.py` too) |
| D-615 control; refusals | `…the_control_changes_the_bars_and_the_ids`, `…a_moved_reference_is_refused`, `…a_control_stage1_run_is_refused_as_input`, `…d622_the_exits_are_stage_1s…`, `…the_config_cannot_lose_a_method` |
| D-628 unconfirmed; D-636 ids; rule 8 hashes | `…d628_unconfirmed_timeframes_are_flagged`, `…d636_candidate_id_carries_…`, `test_F_0_8_2_stage_inputs_keep_old_hashes_and_enter_new_ones` |

## 10. Decisions used or made

- **Used:** D-004, D-012, D-101, D-102, D-110 (as amended), D-130, D-160, D-236, D-306, D-334,
  D-354, D-601 … D-621, D-802, D-805.
- **Made, supervisor range:** D-622 … D-628 (T13 §2), **D-629** (amends D-624 / F-2.7), **D-630**
  (amends D-110), D-631 … D-636 (the plan's answers), **D-637** (the overlap, on the pilot).
- **Stream A:** none; P-107 … P-115 all answered. **Stream A has no open question.**

## 11. The acceptance review, and what changed

*(filled in from the `acceptance-reviewer` subagent's findings)*

## 12. Acceptance

*(the final run after the reviewer's fixes)*
