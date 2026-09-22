# T12 — stage-1 pilot (runbook step 8)

**Stopped before step 9, as instructed.** *(Sections 1-6 are the first pilot; sections 7-11 below are the re-run after D-618, and supersede its numbers.)* The full run is not started. The pilot also found
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

---

# After D-618: the pilot re-run (2026-09-22)

This re-run follows the supervisor's answers:
- **P-100 → D-618**: baseline trades hold exactly their drawn periods, with no stop of their own.
- **P-101 → D-619**: run as is and state the conclusion.
- **P-102 → D-620**: keep the numbers and drop the two warnings.

The same ten symbols, configs and seed as before. **Stopped again before step 9.**

## 7. Runs

| run | run id | profiles | passed | wall time |
|---|---|---|---|---|
| 1D | `77bab6c3…` | 40 | 1 | 37 s |
| 1D, second run | `eaa65c3e…` | 40 | 1 | 35 s |
| 1H | `ed995f85…` | 40 | **0** (was 3) | 109 s |
| 1D random-walk control | `6ee56235…` | 40 | **0** | 37 s |
| 1H random-walk control | `9b223938…` | 40 | **0** (was 2) | 126 s |

- **Reproduced exactly.** The second 1D run's `summary.json` files are identical to the first
  (apart from the run id).
- **The fix did what it should.** Both random-walk controls now pass **0 of 40**. The real-data
  1H passes (TF long on AAPL, AMZN and AMD) are **gone**: they were the drift D-618 removes, not edges.

**Compute.** Wall time is about twice the first pilot's, and the new stop is **not** the cause:
the infinitely far stop measured 1.5 s per profile against 2.2 s for the old 3-ATR stop, and
profile times vary noticeably between runs. At the slower rate the full scope comes to about
**29 min on 1D and 67 min on 1H, ≈ 3.4 h with both controls**. That is at the edge of "a few
hours", so no reduction is proposed, but the supervisor should know it.

## 8. The numbers

### ESS distribution

| | min | p25 | median | p75 | max | ESS ≥ 50 | passed |
|---|---|---|---|---|---|---|---|
| 1D | 0.3 | 2.1 | 17.4 | 35.0 | 60.8 | 1 | 1 |
| 1H | 0.0 | 1.2 | 8.6 | 30.5 | 61.8 | 2 | 0 |
| 1D control | 0.2 | 0.9 | 2.1 | 11.3 | 40.7 | 0 | 0 |
| 1H control | 0.2 | 0.8 | 2.2 | 13.4 | 37.1 | 0 | 0 |

ESS histogram, profiles per band of 10 points, from 0–10 up to 90–100:

| | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1D | 17 | 3 | 5 | 9 | 5 | 0 | 1 | 0 | 0 | 0 |
| 1H | 22 | 4 | 3 | 5 | 4 | 1 | 1 | 0 | 0 | 0 |

Mean points per component:

| | breadth /30 | magnitude /30 | significance /20 | consistency /20 |
|---|---|---|---|---|
| 1D | 0.6 | 13.0 | 3.9 | 2.7 |
| 1H | 0.5 | 9.4 | 4.1 | 2.1 |

Median ESS by edge type and direction. **The TF-long outlier is gone:**

| | MR long | MR short | TF long | TF short |
|---|---|---|---|---|
| 1D, first pilot | 18.9 | 17.2 | **37.8** | 1.3 |
| 1D, after D-618 | 17.4 | 17.7 | 18.0 | 18.2 |
| 1H, after D-618 | 1.5 | 10.3 | 12.2 | 19.9 |

**The one pass:** 1D AAPL MR long, ESS 60.8, groups momentum, oscillator and sequence, quality `ok`.

**Why profiles fail.** On 1D the profile gate fails on `accepted_probe_groups` 39 times and on
`ess` 39 times; on 1H, 40 and 38 times. 3 of 340 probes are accepted on each timeframe.

| probe-gate criterion (1D) | failures |
|---|---|
| `probe_q_value` | 336 |
| `probe_percentile` | 311 |
| `profit_factor` | 235 |
| `n_trades` | 93 |

**Magnitude dominates ESS** (13 of 30 points on 1D against 3.9 of 20 for significance). It even
gives the controls 4–6 points. Since the numbers are now clean, this is what §11's "ESS constants
badly placed?" should look at. I report it and change nothing. It explains why many
non-significant profiles sit at ESS 30–40, and 0.10 ATR as the full-magnitude target is the
constant to question in T15.

### Probe percentiles by edge type and direction

Mean percentile / share at or above 90:

| | MR long | MR short | TF long | TF short |
|---|---|---|---|---|
| 1D | 51.4 / 11 % | 57.1 / 14 % | 47.4 / 5 % | 48.4 / 3 % |
| 1H | 39.6 / 14 % | 46.3 / 11 % | 55.1 / 13 % | 57.2 / **21 %** |
| 1D control | 40.0 / 0 % | 34.5 / 3 % | 37.2 / 1 % | 39.4 / 0 % |
| 1H control | 41.7 / 3 % | 40.4 / 7 % | 35.7 / 3 % | 38.9 / 5 % |

**Two residuals, reported and not explained away:**
1. **The permuted-returns control is conservative.** Its percentiles average 38–42, with 0–7 %
   at or above 90, where a clean null gives about 50 and 10 %. Its 0 passes are therefore a
   **lower** bound on the false-positive rate. The calibrated null is the synthetic one: after
   D-618 a drifted geometric random walk gives TF long a mean percentile of 50–53 with about 10 %
   at or above 90, and that is pinned in the uniformity test.
2. **TF short sits a little high** (1H 57.2 with 21 % at or above 90; synthetic 55–58 with
   14–17 % under drift). **MR short sits low** on synthetic data (about 35, even without drift).
   Both are far smaller than the D-615 bias. They are to be checked on the full-scope control
   before any threshold is read.

### Quality split

Too small to judge at 40 profiles. On 1D the one pass is `ok` (1 of 28 `ok`, 0 of 12
`warning`); on 1H there are no passes.

## 9. P-101 → D-619: TF on 1D, stated plainly

**Finding: under D-101's fixed TF exits and the 30-trade minimum, TF on 1D is close to
unpassable. The two causes need different remedies.**

The 1D development window is about 7.6 years (median). Per probe, out of 20 profiles:

| TF probe | entry signals (median) | closed trades (median) | profiles below 30 | limited by |
|---|---|---|---|---|
| `tf_sma_cross_20_100` | 13 | 12 | 20 of 20 | **signal frequency** (1.7 per year) |
| `tf_supertrend_flip` | 28 | 28 | 13 of 20 | **signal frequency** (3.7 per year) |
| `tf_donchian55_breakout` | 52 | 15 | 20 of 20 | **the exit** |
| `tf_bb_upper_cross` | 55 | 26 | 16 of 20 | **the exit** |
| `tf_ichimoku_cloud` | 490 | 28 | 12 of 20 | **the exit** |
| `tf_donchian20_breakout` | 108 | 29 | 10 of 20 | **the exit** |
| `tf_ma50_slope_up` | 48 | 48 | 2 of 20 | — |
| `tf_roc20_cross_zero` | 83 | 82 | 0 of 20 | — |

"The exit" means the reverse-signal exit with its 50-bar cap holds each position so long that
most signals arrive while the probe is already in a trade, and are ignored.

- **What that leaves.** A median TF profile on 1D has **3 probes** with enough trades. In
  **7 of 20** TF profiles, fewer than 3 groups have any probe with enough trades, so
  `accepted_probe_groups ≥ 3` cannot be met whatever the data say.
- **What T15 must know.**
  - **For four probes it is the exits**: shortening the TF hold would multiply their trades
    (donchian20 already fires 108 times).
  - **For two it is the threshold or the battery**: no exit can give `sma_cross_20_100` 30
    trades in 7.6 years, because it fires 13 times.
  - **So the answer is not one or the other.** TF on 1D needs a shorter exit or a lower
    minimum for the first group, and a different probe or no 1D use for the second.
- **On 1H the problem mostly goes away.** Only `tf_sma_cross_20_100` (16 of 20 below 100) and
  `tf_donchian55_breakout` (4 of 20) fall short, and every TF profile has all 5 groups with at
  least one eligible probe.
- **MR is unaffected** on both timeframes: 0 of 20 below the minimum for every probe.

## 10. P-102 → D-620: the disaster-stop hit rate is itself a finding

The warnings are gone; the numbers stay in every probe result. The distribution of each
probe's share of trades exiting on the 3-ATR disaster stop:

| | p10 | p25 | median | p75 | p90 | share of probes above 2 % |
|---|---|---|---|---|---|---|
| 1D, all probes | 3.1 % | 5.1 % | **8.0 %** | 27.3 % | 42.9 % | 97 % |
| 1D, MR | | | 6.0 % | | | 98 % |
| 1D, **TF** | | | **28.6 %** | | | 97 % |
| 1H, all probes | 5.3 % | 6.1 % | 7.9 % | 35.3 % | 44.3 % | 100 % |
| 1H, MR | | | 6.4 % | | | 100 % |
| 1H, **TF** | | | **36.1 %** | | | 100 % |

**D-130's 2 % was written for an optimised strategy's exit (stage 4), not for a raw probe.
Stage 1 measures far above it, and the missing warning is not agreement with 2 %.**

For **TF the disaster stop is effectively a primary exit**, closing about a third of all
trades. The 3-ATR stop, set from the signal bar's ATR, is usually reached before the reverse
signal or the 50-bar cap. That is part of what D-101's TF exits measure, and it belongs next to
§9 when T15 revisits the TF exits.

## 11. Stop

Step 9 is not started. The full-run configs are ready
(`configs/pipeline/s01_broker_{1d,1h}.yaml` and `_control` variants), with a projected ≈ 3.4 h
in total. Step 9 waits for the supervisor.

## 12. The doubled wall time, profiled (before step 9)

**Benign: not the code, and not in this session.** The 2× slowdown of §7 was one time window
on the machine, **12:42–12:48 UTC**, not a property of the D-618 code.

- **Serial, one symbol end to end** (AAPL 1D, four profiles, cProfile): the pre-D-618 code
  (commit `8e5096d`, in a scratch worktree) and the current code both take **≈ 12 s**
  (11.8–12.7 s against 11.5–13.0 s).
- **Parallel, the 1D pilot:** both codes take **19 s** today (pre-D-618 with a warm cache 19 s;
  current code 19 s, 19 s and 18 s).
- **Where the time goes** (cProfile, 13.6 s):

  | part | time | share |
  |---|---|---|
  | the baseline (34,000 simulations) | 10.8 s | 80 % |
  | … the engine calls | 5.1 s | |
  | … drawing placements | 3.4 s | |
  | … trade years | 0.6 s | |
  | loading the universe YAML (once per run) | 1.8 s | |
  | **re-parsing every cost profile, per symbol** | **0.5 s a symbol** | |

  Nothing unintended runs inside the stage.
- **The one waste found**, the per-symbol cost-profile parsing, cost 0.5 s per symbol in the
  parent while the workers waited: about 14 minutes over the full scope and its controls. The
  profiles are now **parsed once per run**, and the pilot's output is byte-identical to before
  (40 profiles and the index).
- **Not a Numba recompile in the main folder.** The engine's cache files were last written at
  08:11 UTC, hours before the slow window.
- **Everything run in the window was slow**: all five runs between 12:42 and 12:48 UTC, and
  none before (12:13–12:18) or after (from 13:07).
- **Most likely cause: CPU contention from outside this session.** Stream B committed its T04m
  plan at **12:35 UTC**, seven minutes before the window, and its acceptance checks would load
  the machine. This cannot be proven after the fact, because the process list from then is
  gone. The machine was idle when measured before step 9.
- **The 144 s run of the old code** was that code's first parallel run from a new folder
  (Numba's cache is per path); re-run warm, it took 19 s.

**Projection for step 9 at the measured rate:** 1D ≈ 15 min, 1H ≈ 33 min, and the same again
for the controls: **≈ 1.6 h**. That is the original projection, not 3.4 h.

**Not changed, for the record.** The executor's `auto` budget (D-351) runs 4 workers × 5 Numba
threads. Stage 1's `simulate` is single-threaded, so 16 of the 20 cores idle. A stage-1 budget
of about 20 workers × 1 thread would be roughly 4–5× faster, but it would take every core
while stream B works. That is a D-351 question for later, not something to change inside step 9.
