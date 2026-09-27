# T12 — Stage 1: edge discovery (s01_edge) — review

**Critical task (D-402): approved with conditions on 2026-09-27; both are met (§14).** Branch
`a/T12-edge-discovery`.
Features: F-1.1 … F-1.6, F-1.8 and F-1.9; F-1.7 is reserved (P1). Decisions: D-601 … D-620,
D-802 … D-804, and those cited below.

> **Read the controls before the passes (§2).** The reshuffled-returns control's "0 false
> positives" is **not** the headline: that control is conservative, and its zero is a lower
> bound. The calibrated null is the synthetic one.

> **Open parity gap (D-802).** D-335 and D-336 are unverified against TradingView (T11b is
> parked). **D-336 is the research default and shaped every probe run here**: an MR exit
> scheduled at a close may be followed by a re-entry at the same open. If T11b later shows an
> engine difference, these results may need re-running; every run records its `code_version`.

## 1. The full run (runbook step 9)

The run covered the whole MVP scope: the broker universe (D-603), 1D and 1H, each with its
random-walk control (D-615). The seed is 42. The pilot is in `docs/reviews/T12_pilot.md`.

| run | run id | symbols | profiles | skipped (D-008) | passed | pass rate | wall time |
|---|---|---|---|---|---|---|---|
| 1D | `db666562…` | 486 | 1,944 | 0 | **14** | 0.72 % | 22 min |
| 1D control | `279018ed…` | 486 | 1,944 | 0 | **0** | 0.00 % | 32 min |
| 1H | `6f603a07…` | 370 (367 profiled) | 1,468 | 3 | **4** | 0.27 % | 42 min |
| 1H control | `9c4fcde5…` | 370 (367 profiled) | 1,468 | 3 | **1** | 0.07 % | 37 min |

- **Scope.** Of the 515 broker symbols:
  - **1D:** 486 ran; 29 were excluded at resolution for having no reference (the FX and CFD
    instruments, `scope_excluded`).
  - **1H:** 370 ran; **145 were excluded** (119 have no 1H in the universe, 26 have no 1H
    reference). Of the 370, three are too short for a split and are listed, not profiled.
- **`probes_run`**, the trial count for D-160, is **16,524** on 1D and **12,478** on 1H. It
  equals the trial rows written (tested).
- **Wall time.** The 1D control and the 1H run were slowed by Windows scheduling the run on the
  efficiency cores; an interim opt-out was applied from 14:40 UTC (pilot report §13). That is
  now permanent as **D-804**. None of it changes a number (D-607).

## 2. The headline: false positives, and which null to believe

| | 1D | 1H |
|---|---|---|
| real data: passes | 14 of 1,944 | 4 of 1,468 |
| **reshuffled-returns control** (D-615): passes | 0 of 1,944 | 1 of 1,468 |
| … its mean probe percentile (a clean null gives 50) | 43–46 | **28–36** |
| … its share of probe percentiles at or above 90 (clean: 10 %) | 4.5–7.4 % | 1.9–4.1 % |
| **synthetic null**, pinned in `test_F_1_4_baseline_uniformity` | pooled 47.7 / 9.9 % | TF under drift about 50 / 10 % (after D-618) |

- **The calibrated null is the synthetic one.** A random walk, driftless or drifted, gives
  probe percentiles close to uniform: about 50, with about 10 % at or above 90. That is the
  property the gate's threshold of 90 assumes.
- **The reshuffled-returns control is conservative**, markedly so on 1H (percentiles averaging
  28–36). Its **0 and 1 passes understate the false-positive rate** and must not be read as
  "stage 1 has no false positives". A full-scale false-positive rate on calibrated random walks
  is F-X.5 (T15).
- **The 1H control still produced a pass: CSCO TF long**, ESS 73.0, with 4 groups accepted at
  q-values of 0.07–0.10. It is a genuine false positive on permuted data. It looks structurally
  like the real 1H passes, whose q-values are 0.02–0.08. So **1H real 4 against 1H control 1 is
  weak evidence of edge.** 1D real 14 against control 0 is stronger, but see §3.

## 3. The passes, by edge type and direction

| 1D | profiles | passed | pass rate | median ESS | probe percentile mean / share ≥ 90 |
|---|---|---|---|---|---|
| MR long | 486 | 7 | 1.4 % | 9.7 | 52.1 / 12.0 % |
| MR short | 486 | 7 | 1.4 % | 22.0 | 60.7 / 19.0 % |
| TF long | 486 | 0 | 0 % | 2.2 | 42.3 / 6.2 % |
| TF short | 486 | 0 | 0 % | 2.7 | 45.3 / 5.6 % |

| 1H | profiles | passed | pass rate | median ESS | probe percentile mean / share ≥ 90 |
|---|---|---|---|---|---|
| MR long | 367 | 0 | 0 % | 2.1 | 41.7 / 6.7 % |
| MR short | 367 | 0 | 0 % | 5.8 | 51.2 / 13.0 % |
| TF long | 367 | 4 | 1.1 % | 2.7 | 44.7 / 7.6 % |
| TF short | 367 | 0 | 0 % | 2.7 | 47.0 / 8.4 % |

**The passes are not independent edges; they concentrate in one family per timeframe.**

**1D: all 14 are mean reversion**, 7 long and 7 short, on 13 symbols (TXN passes in both
directions). The passing profiles are, by ESS: MSFT L 89.7, TXN L 87.5, TXN S 87.5, RTX L 84.2,
K S 83.4, TJX S 82.3, LEN S 81.0, GNRC S 80.7, ADI S 78.7, TMUS L 74.7, ETN L 74.7, SHW L 72.9,
EEM S 72.0, AAPL L 60.8. All are quality `ok`.
- **Every one rests on the band/channel and oscillator groups**, and 11 add sequence. Across
  all 1D profiles the accepted probes are overwhelmingly MR band/channel (131) and MR
  oscillator (76), with TF at 13.
- The probes most often accepted in the passing profiles are `rsi2_below_10` (12),
  `three_down_closes` (11), `close_below_bb_lower` (10), `zscore_below_minus_2` (10) and
  `donchian20_new_low` (10).
- **So this is one finding about the battery:** short-horizon MR on large US names shows up in
  the band/oscillator probes. It is not 14 independent edges.

**Two band/channel probes are the same rule.** `mr_close_below_bb_lower` (20, 2) and
`mr_zscore_below_minus_2` (20) are mathematically identical: close < SMA − 2σ is the same as
z < −2. They produced **identical trades in all 972 MR profiles**.
- **Correcting a remark of mine:** this does **not** inflate breadth, because an accepted group
  counts once.
- **What it does:** it weights one rule twice in the ESS medians (magnitude, significance and
  consistency), adds a redundant test to the profile's Benjamini-Hochberg set, and overstates
  `probes_run`, the trial count stage 7 will use (D-160), by one per MR profile.
- For T15: drop one of the two, or replace it with a distinct band/channel rule.

**1H: all 4 are TF long**, on BAC (ESS 82.5), TSLA (68.8), ARKK (68.4) and MRNA (65.0).
- **Three of the four are on series flagged `price_spikes`** in the uncleaned hourly layer
  (D-707).
- With the 1H control also passing a TF long profile (CSCO), and TF short near the 1H
  residual of §6, **these four should be treated as unconfirmed.** They are high-volatility,
  trending names where both data defects and a residual trend bias are plausible.
- **No MR profile passes on 1H.**

## 4. The quality split (T12 §12.2, D-617)

| | `ok`: passed / profiles | `warning`: passed / profiles | z (warning − ok) | two-sided p |
|---|---|---|---|---|
| 1D | 14 / 1,528 (0.92 %) | 0 / 416 (0.00 %) | −1.96 | 0.050 |
| 1H | 1 / 696 (0.14 %) | 3 / 772 (0.39 %) | +0.90 | 0.37 |
| 1H control | 1 / 696 | 0 / 772 | −1.05 | 0.29 |

- **1D: flagged series pass *less* often**, not more (p = 0.05). There is no sign of bad data
  showing up as edge on the clean daily layer (T04k).
- **1H: flagged series pass more often (3 of 4 passes), but not significantly** (p = 0.37, from
  4 passes). The direction matches the concern about the uncleaned hourly layer (D-707).
  Reported, not decided: with 4 passes it cannot be settled either way.
- **The 1H pass rate is reported separately** (B_data_state item 3): 0.27 %, against 0.72 % on
  1D.

## 5. The ESS distribution, and the primary T15 calibration target

| | min | p10 | p25 | median | p75 | p90 | max | ESS ≥ 50 | passed |
|---|---|---|---|---|---|---|---|---|---|
| 1D | 0.0 | 0.8 | 1.6 | 6.9 | 34.9 | 46.0 | 89.7 | 131 | 14 |
| 1D control | 0.0 | 0.6 | 1.3 | 2.5 | 23.5 | 36.7 | 72.7 | **31** | 0 |
| 1H | 0.0 | 0.5 | 1.2 | 3.0 | 19.2 | 38.8 | 82.5 | 24 | 4 |
| 1H control | 0.0 | 0.2 | 0.5 | 1.2 | 2.7 | 14.4 | 73.6 | 4 | 1 |

Mean points per component:

| | breadth /30 | magnitude /30 | significance /20 | consistency /20 |
|---|---|---|---|---|
| 1D | 0.66 | **11.03** | 3.90 | 2.29 |
| 1D control | 0.22 | **8.05** | 2.94 | 1.02 |
| 1H | 0.14 | 6.57 | 3.42 | 1.68 |
| 1H control | 0.04 | 2.15 | 1.84 | 0.57 |

**Primary T15 calibration target: the magnitude target of 0.10 ATR (D-606) is too generous.**
- Magnitude dominates ESS: on 1D, 11.0 of 30 points against 3.9 of 20 for significance.
- **The permuted control earns 8.05 magnitude points on average on 1D.** 31 control profiles
  reach ESS ≥ 50 on no edge, up to 72.7.
- Of the 131 real 1D profiles at ESS ≥ 50, only 14 pass: the breadth criterion, not ESS, is
  doing the selecting.
- An excess of 0.10 ATR per trade earns full magnitude, and random noise in a probe's mean
  reaches that easily. **Not changed here:** the full run is the measurement it is calibrated
  on (the supervisor's instruction), and every artifact records the stage-config hash.

## 6. T15's calibration list (the numbers, stated plainly)

1. **Magnitude target of 0.10 ATR, the primary target** (§5): too generous; the controls score
   on it.
2. **TF on 1D is near-unpassable (D-619).** At full scope:

   | TF probe | profiles below 30 trades | median trades |
   |---|---|---|
   | `sma_cross_20_100` | 100 % | 11 |
   | `donchian55_breakout` | 100 % | 15 |
   | `bb_upper_cross` | 84 % | 27 |
   | `supertrend_flip` | 76 % | 27 |
   | `donchian20_breakout` | 69 % | 27 |
   | `ichimoku_cloud` | 67 % | 27 |
   | `ma50_slope_up` | 7 % | 54 |
   | `roc20_cross_zero` | 2 % | 90 |

   In **46 % of TF profiles (450 of 972) fewer than 3 groups** have any probe with enough
   trades, so the profile gate cannot be met whatever the data say. The cause is split (pilot
   §9): **four probes are limited by the exit** (bb_upper_cross, the two donchians, ichimoku —
   the 50-bar reverse-signal hold blocks most signals); **two by signal frequency**
   (`sma_cross_20_100` fires about 1.7 times a year, `supertrend` about 3.7). T15 must move the
   **exits** for the first four and the **threshold or the battery** for the other two.
   On 1H only `sma_cross_20_100` falls short (57 %), and 99 % of TF profiles have all 5 groups
   eligible. MR is unaffected on both timeframes (at most 6 % of profiles below the minimum).
3. **The disaster stop is a primary exit for TF (D-620).**

   | probes | p25 | median | p75 | share of probes above D-130's 2 % |
   |---|---|---|---|---|
   | 1D, TF | 12.5 % | **32.1 %** | 44.4 % | 97 % |
   | 1D, MR | 3.9 % | 5.6 % | 7.7 % | 93 % |
   | 1H, TF | 18.7 % | **36.8 %** | 44.3 % | 100 % |
   | 1H, MR | 5.5 % | 6.3 % | 7.1 % | 100 % |

   **D-130's 2 % was written for an optimised strategy's exit (stage 4), not a raw probe; stage
   1 measures far above it, and the dropped warning is not agreement with 2 %.** For TF about a
   third of all trades end on the 3-ATR stop from the signal bar, before the reverse signal or
   the 50-bar cap. That belongs with item 2 when the TF exits are revisited.
4. **The duplicate probe** (§3): `close_below_bb_lower` ≡ `zscore_below_minus_2`.
5. **The reshuffled-returns control is conservative** (§2), especially on 1H. T15 should
   calibrate on synthetic random walks (F-X.5), not on this control.
6. **Residual biases after D-618**, small and not explained away (pilot §8):
   - TF short sits a little high (1H 47.0 / 8.4 % here; up to 58 / 17 % on drifted synthetic
     data).
   - MR short sits high on real 1D data (60.7 / 19 %), which may be real edge, but is low on
     synthetic data (about 35).
   - MR long is slightly low on synthetic data.
7. **P-104:** whether the executor's `auto` budget should discount efficiency cores and
   hyper-threads.

## 7. What was built

| module | content |
|---|---|
| `stats/edge.py` | percentile (strictly below), empirical p (floored at 1/(n+1)), Benjamini-Hochberg q, two-proportion z |
| `metrics/ess.py` | the four ESS components and the total (D-606 as amended by D-613), weights normalised to 0–100 |
| `metrics/names.py`, `configs/gates/default.yaml` | `probe_q_value` registered and gated at ≤ 0.1 (D-605); `ess` re-described as the 0–100 score |
| `configs/stages/s01_edge.yaml`, `stages/config.py` | edge types, applicable groups (D-233), fixed exits (D-101, D-614), the 17 probes with exact warm-ups, the baseline count, the ESS constants; validated against the registries |
| `components/exits/probe.py` | MR `prev_extreme` and TF `reverse` exits (D-614); the parity harness keeps its own copy |
| `baseline/random_entries.py` | the matched baseline: exact count and permutation of holding periods, no overlap, uniform placement, D-607 seeds, zero costs, **no stop of its own (D-618)** |
| `stages/base.py`, `stages/reference.py` | `RunContext` (**no split manager**, D-616), `Stage`, `StageResult`; the D-610 caveats read from the catalog |
| `stages/edge_profile.py`, `stages/edge.py` | the `EdgeProfile` artifact (schema v1) and the stage: units per (symbol, timeframe, edge type, direction), both gates, registry writes, artifacts, the index |
| `stages/control.py` | the reshuffled-returns control (D-615) |
| `core/config.py` | `symbol_scope: broker` (D-616) and `control` in the run config |
| `pipeline/stage_run.py`, `cli.py` | `sfac run --config` (stage 1 only) |
| `pipeline/qos.py`, `pipeline/executor.py`, `configs/pipeline/executor.yaml` | the Windows efficiency-mode opt-out (D-804) |
| `docs/streams/ownership.yaml` | stream A's second pending range P-100 … P-149 (D-803) |

Nothing in the engine changed. There is no new dependency: the statistics are NumPy
(`math.erfc` for the z-test), and the Windows calls are `ctypes`.

## 8. How each acceptance criterion is tested

| criterion | proving test(s) |
|---|---|
| F-1.1 / F-1.2: all probes, fixed parameters, both directions; groups in config | `test_F_1_1_*` (battery complete, groups from config, a missing or unknown probe refused), `test_F_1_5_d605_probes_run_counts_every_probe_evaluated` |
| F-1.3: exits behave as defined | `test_F_1_3_*` (hand cases, mirror, reverse = the probe's opposite signal, **D-614 equivalence with the parity copy on both parity charts**); truncation `test_F_1_3_probe_exits_are_truncation_invariant` |
| F-1.4: matched properties equal; percentiles uniform on random walks | `test_F_1_4_*` (exact count and holding multiset, no overlap, allowed range, seeds, **D-618: trades hold their drawn periods on violent bars**); slow `test_F_1_4_probe_percentiles_on_random_walks_are_about_uniform` and **the drifted TF case** `test_F_1_4_d618_drift_*` |
| F-1.5: high on a planted edge, near the middle on random data | `test_F_1_5_a_planted_mean_reversion_edge_scores_high`, `…random_walk_sits_near_the_middle`, `…d613_*` |
| F-1.6: 0–100, a weight change takes effect, component tests | `test_F_1_6_*` (18 cases, every boundary) |
| F-1.8: a gate result with its reason in the registry; thresholds from config | `test_F_1_8_each_criterion_fails_by_name_from_the_config` (6 criteria), db `test_F_0_7_1_stage1_registry_rows` |
| F-1.9: the artifact feeds stage 2; the schema is validated | `test_F_1_9_the_stage_writes_valid_profiles_and_the_index`, `…too_short…`, `…moved_reference…`, `…d608_trades_only_for_accepted_probes_of_passing_profiles` |
| F-0.7.1 / F-0.7.3: trials = evaluated configurations; gate rows | db `test_F_0_7_1_stage1_registry_rows` |
| D-607: serial and parallel bit-identical | `test_F_1_5_d607_serial_and_parallel_runs_are_bit_identical` (fast suite, so CI and `windows-fast` run it) |
| Rule 2 / D-306 / D-616: the stage cannot reach the holdout | `test_F_1_8_d616_*` (read from the syntax tree, plus a check that the check fires) |
| Rule 3: no look-ahead | `tests/leakage/test_F_1_5_stage_truncation.py` (34 cases). It drives the stage's own `probe_run` with settings from `EngineConfig`, and covers **the probe trades** every statistic is computed from. The aggregate statistics are functions of the whole development window by design, and the baseline draws depend on the window's length, never on a later price. *This row claimed "the stage's statistics" before the acceptance review, which was overstated.* |
| D-602 / D-613 (3) / D-614 (1) / D-615 wiring | `tests/unit/test_F_1_5_stage_wiring.py`: consistency by hand (per-year baseline, thin years dropped), the PF equals the full-cost run's and is below the zero-cost one's, the disaster stop fires on gapping data and not with the stop moved away, and the `random_walk` control changes every statistic and every candidate id. **Added after the acceptance review**, which broke each wiring in memory while every earlier test still passed. |
| D-610 caveats | `tests/unit/test_F_1_9_d610_caveats.py`, against a real temporary catalog: quality status, failing checks, splices, a research window is not a trim, a T04l trim |
| D-354 (1), the non-USD skip, `sfac run` stage 1 only | `test_F_1_5_d354_a_parity_setting_is_refused_not_ignored`, `test_F_1_9_a_non_usd_symbol_is_listed_as_skipped_not_fatal`, `test_F_1_9_d616_sfac_run_refuses_anything_but_stage_1` |
| D-354 (1) (2) | `test_F_1_8_d354_*` |
| D-616 broker scope; D-615 control | `test_F_0_8_2_d616_*`; `test_F_1_5_d615_*` |
| D-804 efficiency-mode opt-out | `test_F_0_3_7_d804_*` (8 tests) |
| The pilot and the full run reproduce | pilot §7 (every `summary.json` identical apart from the run id; `index.csv` byte-identical); every run records its config hash, seed and code version |

Every guard test added here was mutation-checked, and each break fails its test:
- BH without its step-up; ties counted as below; a warm-up one bar late;
- no holding permutation; blocks one bar short;
- the MR exit's comparison changed;
- the baseline stop reinstated (D-618);
- a `SplitManager` import; `DEFAULT_ENGINE_CONFIG`;
- the second pending range removed;
- the worker opt-out removed; its failure not caught; throttling switched on instead of off;
- **after the acceptance review:** consistency without the per-year baseline and the minimum,
  the PF at zero cost, no disaster stop on probes, and the control ignored (each fails
  `test_F_1_5_stage_wiring`); a trim without the research-window check (fails
  `test_F_1_9_d610_caveats`).

## 9. Deviations and judgement calls

1. **`RunContext` has no split manager** (D-616), a stated deviation from design §4.
2. **The index is `index.csv`, not Parquet** (D-617 named `index.parquet`). Parquet I/O belongs
   to the data layer (D-302), which stage 1 does not extend. Same columns.
3. **Magnitude's share is clipped at 0.** D-606's formula would give negative points for a
   negative excess, and F-1.6 requires 0–100.
4. **The baseline places draws exactly and uniformly ("stars and bars") instead of re-drawing.**
   D-615 speaks of re-drawing up to a configured number of attempts; the exact method never
   needs one, and an impossible fit is counted (`baseline_infeasible`).
5. **D-354 (2)**, "`s06_robust` only in `data/split.py` and the stage-6 module", is enforced on
   stage code. `metrics/names.py` has named it as the stage-6 metrics' producer since T10b.
6. **Profit factor infinite** (no losing trade) is stored as `null` with a warning, because JSON
   has no infinity.
7. **The probe warm-ups are configured**, and pinned exact by a test (never before; slow: exactly
   at), because no component declares one.
8. **`candidate_id` adds `control` and the stage-config hash** to D-616's list (D-805, the
   answer to P-106): a control profile never collides with a real one, and a recalibrated run
   never overwrites this one's candidates.
9. **Missing statistics are skipped, not zeroed.** The ESS medians and the Benjamini-Hochberg `m`
   run over the probes **that have a statistic**: a probe with no trades has no mean, p or
   consistency. Consistency also drops a year with **no baseline trade**, alongside D-613's
   5-trade rule. D-613's "over all probes run" is read as "all probes run that produced a number".
10. **The stored trades (D-608)** are the **full-cost** run of each accepted probe, written by
    `write_run_result` (trades, equity and meta), not a single `trades.parquet`. The statistics
    come from the zero-cost run of the same signals.
11. **Non-USD symbols are skipped and listed** (P-105). Before the review they aborted the run.
12. **The stage-config hash is on every trial** (`params.stage_config_hash`), added after the full
    run. The full run's trial rows do not carry it; its `summary.json` files do. Moving
    `batch_units` into the stage config changed that hash but **no number**: a re-run of the 1D
    pilot on the fixed code is identical in all 40 profiles and in the index.
13. **Operational values in code, made explicit:** the baseline's notional and capital are now
    required (from `EngineConfig`, D-004); `volume_step=1e-9` means "no rounding" in the
    frictionless sizing, never a threshold; `batch_units` moved to the stage config.

## 10. Decisions used or made

- **Used:** D-012, D-100 … D-105, D-130, D-233, D-306, D-334, D-351, D-354, D-601 … D-612,
  D-707, D-713, D-802.
- **Made, supervisor range:** D-613 (amends D-601 and D-606), D-614, D-615, D-616, D-617,
  **D-618** (amends D-615: why the original was wrong is recorded), D-619, D-620.
- **Made, stream A range:** D-803 (second pending range) and **D-804** (efficiency-mode opt-out).

## 11. Open questions

- **P-104:** the executor's `auto` budget on hybrid CPUs (efficiency cores, hyper-threads).
- **P-105 → D-621 (3):** non-USD symbols stay skipped and listed; revisited when T04j lands.
- **P-106 → D-805:** the stage-config hash is now part of the candidate id (§14).
- **P-104 → D-621 (2):** deferred to T15.

**Stream A has no open question left.**
- **The 1H passes** (§3) go to stage 2 **flagged `unconfirmed`** (D-621 (1)): D-609 sends every
  pass forward, but stage 2 reports them separately and they never stand in for the daily MR
  finding. T13's task file carries this, and T13 is built knowing the 14 daily passes may move
  when the battery is corrected (D-621 (4)).
- **T11b / D-335 / D-336** stay open (D-802).

## 12. The acceptance review, and what changed

The `acceptance-reviewer` subagent checked the task claim by claim. It recomputed the run's numbers
from the artifacts, and they held. Its findings, each verified and addressed:

| # | finding | what changed |
|---|---|---|
| 1 | **blocking**: the stage's wiring of D-602, D-613 (3), D-614 (1) and the D-615 control had no test that would fail if it broke | `test_F_1_5_stage_wiring.py`, 9 tests, each mutation-checked |
| 2 | the leakage claim was overstated; the test re-implemented the probe run with hard-coded settings | one `probe_run` shared by the stage and the test, settings from `EngineConfig`; the claim reworded (§8) |
| 3 | the D-610 caveat code had no test | `test_F_1_9_d610_caveats.py` against a real catalog |
| 4 | the stage config was in neither the run's hash nor the registry | `stage_config_hash` on every trial; the candidate id is **P-106** |
| 5 | D-354 (1): parity settings were silently ignored | refused with a `ConfigError`, tested |
| 6 | non-USD symbols aborted the run, and the rule was undeclared | skipped and listed, tested; **P-105** |
| 7 | deviations were not declared | §9, items 8–13 |
| 8 | stale text (a D-130 comment; the runbook's file names) | corrected |
| 9 | literal values in code | notional and capital required; `batch_units` into config; `1e-9` documented |
| 10 | `sfac run`'s "stage 1 only" was untested | tested |
| 11 | review numbers: 1H symbols, 1H exclusions, "byte-identical" | corrected (§1, §8) |
| 12 | notes: the stage modules could reach the writable catalog; artifact paths are absolute | the guard now bans `_catalog` outside `reference.py`; absolute paths noted, not changed |

## 13. Acceptance

Re-run in full after rebasing onto `origin/main` (stream B's T04m aux ingest and P-93, which
touch `data/split.py` — the module stage 1 reads through `DataAccess`), on Windows:

| suite | result |
| --- | --- |
| fast (`-m "not slow"`) | 1,788 passed |
| `tests/parity tests/leakage tests/oracle` | 398 passed |
| `-m db -rs` | 22 passed, **0 skipped** |
| `-m slow` (the T12 self-tests included) | 20 passed |
| ruff, `ruff format --check` (360 files), mypy `src` and `--platform linux`, `sfac streams check` | clean |

No stage-1 behaviour changed over the rebase: the aux as-of work is stream B's and stage 1 takes
no auxiliary series, and the evidence runs of §1 are unaffected.

## 14. The supervisor's two conditions (2026-09-27)

1. **The `db` suite on the final code, 0 skipped.** Docker Desktop was down when §13 was first
   run. It is up now: `pytest -m db -rs` gives **22 passed, 0 skipped**.

   **A correction to what I reported.** I said
   `test_F_0_8_2_reproduce_fails_loudly_when_a_cost_profile_changed` was not marked `db`. It
   **was** (and still is). The real defect is different: it builds its own schema and called
   `make_engine` **directly**, instead of going through the fixture that skips, so with no
   database it **failed** where every other `db` test skipped. Fixed at that cause: the shared
   reachability helper is now public (`fixtures.registry_db.require_database`) and the test uses
   it. Proven by pointing `SFAC_DB_URL` at a dead port: the test now **skips** with the shared
   reason. CI still fails on any skipped `db` test, so the guarantee is unchanged. The defect
   predates T12.
2. **P-106 implemented before the merge — D-805.** The **stage-config hash is part of the
   candidate id**, so a run with calibrated thresholds is a different candidate and can never
   overwrite this one's row. Two tests, both failing if the hash is dropped: a single changed ESS
   constant changes the id, and for every profile the stage writes, recomputing the id from the
   artifact's own identity reproduces it, with no id shared between two stage configs.

   **One consequence, stated plainly:** T12's four evidence runs were written **before** D-805, so
   their candidate ids carry no stage-config hash. **No statistic moves** — a re-run of the 1D
   pilot on the fixed code is identical in all 40 profiles and in the index — and every profile
   already records its `stage_config_hash` in `summary.json` and in each trial's `params`. Re-running
   the full scope under the new id scheme costs about 1.6 h and changes no number; whether T12's
   recorded evidence is re-written that way is the supervisor's call (D-805).

**The other answers**, recorded as D-621: the four 1H passes go to stage 2 flagged `unconfirmed`
(§11); P-104 is deferred to T15; P-105 stays as it is until T04j; the duplicate probe and the rest
of §6 remain T15's list, and T13 is built knowing the 14 daily passes may move.
