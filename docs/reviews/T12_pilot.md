# T12 — stage-1 pilot (runbook step 8)

**Stopped before step 9, as instructed.** The full run is not started. The pilot also found
**a bias in the random baseline as D-615 defines it**. It inflates trend-following long
probes under drift, and it is raised as **P-100**, with a proposed amendment to D-615. Until
it is answered, the pilot's ESS numbers below are **not** a sound basis for calibration.

Branch `a/T12-edge-discovery`. Registry: the local `sfac` database. Artifacts:
`SFAC_ARTIFACTS_ROOT/<run_id>/s01_edge/`.

## 1. What ran

Ten broker symbols, chosen to cover both timeframes, both quality statuses and one research
window: **AAPL, ADBE, AMAT, AMD, AMGN, AMZN, BA, CSX, DOW, DUK**.

| role | symbols |
|---|---|
| ok on 1D and 1H | ADBE, AMD, BA |
| ok on 1D, warning on 1H | AAPL, AMAT, AMZN |
| warning on both | CSX, DUK |
| warning on 1D, ok on 1H | AMGN |
| research window on both (D-713) | DOW |

The configs are `configs/pipeline/s01_pilot_{1d,1h}.yaml` and `s01_pilot_{1d,1h}_control.yaml`
(the random-walk control, D-615). Each profile runs 1,000 baseline simulations per probe
(D-102) with seed 42.

| run | run id | profiles | passed | wall time |
|---|---|---|---|---|
| 1D | `c0c62353…` | 40 | 1 | 19 s |
| 1D, second run | `299f95b2…` | 40 | 1 | — |
| 1H | `328cd5e5…` | 40 | 3 | 53 s |
| 1H, second run | `c4eecc44…` | 40 | 3 | — |
| 1D random-walk control | `4b3c824c…` | 40 | **0** | 18 s |
| 1H random-walk control | `19ffd48c…` | 40 | **2** | 59 s |

**Reproduced exactly.** In both second runs, every `summary.json` (apart from its run id) and
the `index.csv` are byte-identical to the first run.

## 2. Compute: the projection is below the §7 trigger

The measured scope (runbook step 0) is 486 symbols on 1D and 367 on 1H. At the pilot's rates
(executor `auto`: 4 workers × 5 threads):

| | per 10 symbols | full scope | with its control |
|---|---|---|---|
| 1D | 19 s | ≈ 15 min | ≈ 30 min |
| 1H | 53–59 s | ≈ 33 min | ≈ 65 min |
| **total** | | | **≈ 1.6 h** |

That is not "more than a few hours", so no reduction is proposed. The engine is unchanged (§13).

## 3. The numbers the supervisor asked for

### ESS distribution (40 profiles per timeframe)

| | min | p25 | median | p75 | max | ESS ≥ 50 | ≥ 3 accepted groups | passed |
|---|---|---|---|---|---|---|---|---|
| 1D | 0.3 | 2.2 | 13.4 | 35.3 | 65.7 | 2 | 1 | 1 |
| 1H | 0.0 | 0.9 | 7.5 | 27.2 | 81.8 | 5 | 3 | 3 |

ESS histogram, profiles per band of 10 points, from 0–10 up to 90–100:

| | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1D | 19 | 2 | 4 | 9 | 4 | 1 | 1 | 0 | 0 | 0 |
| 1H | 21 | 4 | 7 | 2 | 1 | 2 | 1 | 0 | 2 | 0 |

Mean points per component:

| | breadth /30 | magnitude /30 | significance /20 | consistency /20 |
|---|---|---|---|---|
| 1D | 0.7 | 12.4 | 4.0 | 3.0 |
| 1H | 2.2 | 8.7 | 4.6 | 2.3 |

Median ESS by edge type and direction. This is where the bias of §4 shows:

| | MR long | MR short | TF long | TF short |
|---|---|---|---|---|
| 1D | 18.9 | 17.2 | **37.8** | 1.3 |
| 1H | 1.4 | 12.8 | **35.3** | 2.6 |
| 1H random-walk control | 4.0 | 7.5 | **36.2** | 21.9 |

### Passes

| run | profile | ESS | accepted groups | quality |
|---|---|---|---|---|
| 1D | AAPL MR long | 65.7 | momentum, oscillator, sequence | ok |
| 1H | AAPL TF long | 81.8 | 4 groups | warning |
| 1H | AMZN TF long | 81.3 | 5 groups | warning |
| 1H | AMD TF long | 62.4 | 3 groups | ok |
| 1H control | AMD TF long | 71.7 | channel_breakout, ichimoku, ma | — |
| 1H control | AAPL TF long | 64.2 | channel_breakout, ichimoku, momentum | — |

### Why profiles fail

- **Profile gate:** 1D fails on `accepted_probe_groups` 39 times and on `ess` 38 times; 1H fails 37 and 35 times.
- **Probe gate** (340 probes per timeframe; 4 accepted on 1D, 19 on 1H):

| criterion | 1D | 1H |
|---|---|---|
| `probe_q_value` | 334 | 314 |
| `probe_percentile` | 304 | 277 |
| `profit_factor` | 235 | 295 |
| `n_trades` | 93 | 20 |

**Probe percentiles.** On 1D the mean is 50.6, with 10.6 % at or above 90, which is what a
null would give. On 1H the mean is 49.9, but 18.5 % are at or above 90.

**Quality split (§12.2; too small to judge at 40 profiles):**

| | `ok` | `warning` |
|---|---|---|
| 1D | 1 of 28 pass | 0 of 12 |
| 1H | 1 of 16 | 2 of 24 |

## 4. Finding: the D-615 baseline inflates TF long probes under drift (P-100)

**Symptom.** On the **permuted** 1H control, which has no serial structure, 2 of 40 profiles
pass. Both are TF long on the two names with the strongest drift (AMD, AAPL). The control's
TF-long probes average the **67.5th percentile, with 24 % at or above 90**. MR long (52.8),
MR short (54.4) and TF short (52.0) are close to uniform.

**Drift reproduces it on synthetic data.** Geometric random walks with no serial structure,
6,000 bars, 12 seeds, the TF probes:

| drift per bar | TF long: mean percentile / share ≥ 90 | TF short |
|---|---|---|
| 0 | 53.2 / 9 % | 49.3 / 9 % |
| 0.0003 | 71.0 / 26 % | 30.9 / 2 % |
| 0.0006 | 76.7 / 42 % | 18.5 / 2 % |

**The exit, not the entry.** Drift 0.0006, 40 seeds, `tf_donchian20_breakout`:

| entries | exit | mean percentile |
|---|---|---|
| probe | reverse signal (D-614) | 80.1 |
| **random** | reverse signal | **84.3** |
| probe | time exit only | 44.8 |

**Not compounding.** Measuring returns in log terms instead of price differences leaves it
(donchian20 77.3 → 75.5, ichimoku 87.3 → 86.2, ma50 slope 76.5 → 74.3).

**The cause: a second disaster stop in the baseline.** D-615 says baseline trades "exit at their
drawn holding period, **or earlier on the 3-ATR disaster stop**". But the drawn holding
periods are the probe's own `bars_held`, which already include the probe's disaster-stop
exits. The baseline then cuts its random trades a second time. For TF probes (holding about 37
bars) the baseline holds only **84 %** of the probe's bars. Under drift, a shorter hold earns
less drift, so the baseline mean is low and the TF long probe looks significant. For MR (5
bars) the baseline holds 99 % of the bars, which is why MR is not affected. Switching the
stop off in the baseline:

| probe, drift 0.0006 | baseline with the stop (D-615) | baseline without it |
|---|---|---|
| tf_donchian20_breakout | 77.3 | **40.0** |
| tf_ichimoku_cloud | 87.3 | **43.0** |
| mr_rsi2_below_10 | 57.5 | 56.8 |

Without drift both versions are near 50. There is a **residual** after the fix: TF percentiles
of 40–45 even without drift. It is small, and it is measured again after the fix before
anything is calibrated.

**Proposed (P-100): amend D-615.** Baseline trades hold **exactly** their drawn holding period,
with no disaster stop of their own. The probe's disaster exits are already in the holding
periods that are drawn. After that:
- F-1.4's uniformity test gains a drifted TF case, so this cannot come back unseen;
- the pilot is re-run (about 2.5 minutes) and reported again **before** step 9.

## 5. §11 triggers and the other findings

1. **Probes systematically below the trade minimum (the §11 trigger; P-101).** Profiles whose
   probe is below the minimum, out of the 20 profiles each probe runs in (10 symbols × 2
   directions):

   | probe | 1D (minimum 30) | 1H (minimum 100) |
   |---|---|---|
   | `tf_sma_cross_20_100` | 20 of 20 | **16 of 20** |
   | `tf_donchian55_breakout` | 20 of 20 | 4 of 20 |
   | `tf_bb_upper_cross` | 16 of 20 | — |
   | `tf_supertrend_flip` | 13 of 20 | — |
   | `tf_ichimoku_cloud` | 12 of 20 | — |
   | `tf_donchian20_breakout` | 10 of 20 | — |
   | `tf_ma50_slope_up` | 2 of 20 | — |

   The 1D development window is about 7.5 years (a median of 1,905 bars). So **TF on 1D can
   rarely reach 3 accepted groups** at all: most of its probes cannot pass `n_trades`.
   Reported, not dropped (§11).
2. **Two warnings that fire almost everywhere carry no information (P-102).**
   - **D-601 mean/median divergence** above 0.25 ATR, a provisional value of mine: it fires on
     232 of 340 probes on 1D and 267 of 340 on 1H.
   - **D-130 disaster stop above 2 %:** it fires on 92–100 % of probes. The median disaster
     share is 8 % of trades, because a 3-ATR stop is often hit on the path of a 5- or 50-bar
     probe.
3. **ESS.** Magnitude carries most of the score, 12.4 of 30 points on 1D against 4.0 of 20
   for significance. It is inflated by the same TF long bias. **Whether the ESS constants are
   "badly placed" (§11) cannot be judged until P-100 is fixed**; that is the reason to re-run
   the pilot first.
4. **The research window** (DOW) ran like any other symbol: short history and a caveat in the
   profile (D-610, D-713). Nothing was skipped: every pilot symbol passes D-008 on both
   timeframes.
5. **The 1D control passes 0 of 40** and the 1H control 2 of 40. §4 explains the 1H pair.

## 6. Open questions (P-100 … P-102, stream A's second pending range, D-803)

- **P-100:** amend D-615 so the baseline has no second disaster stop, then re-run the pilot before step 9.
- **P-101:** TF probes on 1D, and `tf_sma_cross_20_100` on 1H, are systematically below the trade minimum. Run the full scope as it is and report the per-probe counts, or change something first?
- **P-102:** both near-universal warnings. Proposed: keep the numbers in the artifact and drop the warnings, or make them relative; the supervisor decides.
