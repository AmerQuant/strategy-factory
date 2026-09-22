# T12 — Stage 1: edge discovery (s01_edge) — review

**Critical task (D-402): stopped for "Approved".** Branch `a/T12-edge-discovery`.
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
| 1H | `6f603a07…` | 367 | 1,468 | 3 | **4** | 0.27 % | 42 min |
| 1H control | `9c4fcde5…` | 367 | 1,468 | 3 | **1** | 0.07 % | 37 min |

- **Scope.** 29 broker symbols were excluded at resolution for having no reference: the FX and
  CFD instruments (`scope_excluded`). On 1H, three symbols are too short for a split and are
  listed, not profiled.
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
| Rule 3: no look-ahead in the stage's statistics | `tests/leakage/test_F_1_5_stage_truncation.py` (34 cases) |
| D-354 (1) (2) | `test_F_1_8_d354_*` |
| D-616 broker scope; D-615 control | `test_F_0_8_2_d616_*`; `test_F_1_5_d615_*` |
| D-804 efficiency-mode opt-out | `test_F_0_3_7_d804_*` (8 tests) |
| The pilot and the full run reproduce | pilot §7 (byte-identical); every run records its config hash, seed and code version |

Every guard test added here was mutation-checked, and each break fails its test:
- BH without its step-up; ties counted as below; a warm-up one bar late;
- no holding permutation; blocks one bar short;
- the MR exit's comparison changed;
- the baseline stop reinstated (D-618);
- a `SplitManager` import; `DEFAULT_ENGINE_CONFIG`;
- the second pending range removed;
- the worker opt-out removed; its failure not caught; throttling switched on instead of off.

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

## 10. Decisions used or made

- **Used:** D-012, D-100 … D-105, D-130, D-233, D-306, D-334, D-351, D-354, D-601 … D-612,
  D-707, D-713, D-802.
- **Made, supervisor range:** D-613 (amends D-601 and D-606), D-614, D-615, D-616, D-617,
  **D-618** (amends D-615: why the original was wrong is recorded), D-619, D-620.
- **Made, stream A range:** D-803 (second pending range) and **D-804** (efficiency-mode opt-out).

## 11. Open questions

- **P-104:** the executor's `auto` budget on hybrid CPUs (efficiency cores, hyper-threads).
- **The 1H passes** (§3): unconfirmed; three of four are on `price_spikes` series. A T15 item
  together with the hourly cleaning question (D-707).
- **T11b / D-335 / D-336** stay open (D-802).

## 12. Acceptance

See the commit message of this review for the final run: fast suite, parity/leakage/oracle,
`pytest -m db` with 0 skipped, ruff, format, mypy (also `--platform linux`), and `sfac streams
check`.
