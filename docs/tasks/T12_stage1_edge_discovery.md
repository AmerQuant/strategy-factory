# T12 — Stage 1: edge discovery (s01_edge)

**Critical task (D-402): stops for "Approved" before merge.** Plan first (D-403): draft, stop for
"Plan approved", then implement.
Features: F-1.1, F-1.2, F-1.3, F-1.4, F-1.5, F-1.6, F-1.8 (F-1.7 is P1 — reserve the artifact
fields, do not compute).
Depends on: T07 (probes and indicators), T08 (engine), T09 (metrics), T10a (gates, pipeline
config, universe), T10b (executor, metric-name registry, config hash), T04k and T04l (clean and
boundary-trimmed references).

## 1. What stage 1 answers

For one symbol, one timeframe, one edge type and one direction: **is there an edge at all?**
Not whether it is tradeable, not which parameters are best — those are stages 2 and 3.

The answer is an **EdgeProfile** artifact plus a gate verdict, produced from a battery of
fixed-parameter probes (D-100, D-101) measured against a matched random baseline (D-102) and
scored by ESS (D-103).

## 2. Decisions to record before implementing

These were settled by the supervisor and use the supervisor range. Record them in
`docs/decisions/decisions_log.md` marked *(supervisor)*, each citing this task.

| ID | Decision |
|---|---|
| D-601 | **The percentile statistic is the mean excess return per trade in ATR units**, ATR taken at the signal bar (the same ATR the engine sizes and stops with). The median of the same quantity is computed and reported as a robustness check; a large divergence between the two is a warning in the artifact, never a gate criterion. |
| D-602 | **Probes and baseline both run with zero costs; the profit factor is computed separately with the full Moneta cost profile.** The percentile answers "is there an edge", the PF answers "does it survive costs"; mixing them into one number hides which failed. Both numbers are in the artifact and both are gated (D-604). |
| D-603 | **MVP scope is the broker universe only** (`universe_filter: broker`, D-342/D-524) on 1D and 1H. Symbols outside it are not traded, so they are not screened. Widening the scope later is a config change, not a code change, and must re-state the multiple-testing count (D-605). |
| D-604 | **The unit of work — and of the EdgeProfile — is (symbol, timeframe, edge_type, direction).** Up to four profiles per symbol and timeframe (MR/TF × long/short). Breadth (D-100) is counted inside one edge type. Long and short are never merged: US equities carry a long drift, which would hide a short edge behind it. |
| D-605 | **Multiple testing is controlled in three layers, and the probe percentile threshold stays at 90.** (1) The percentile ≥ 90 screen (raising it to 99 is rejected: with 1000 simulations only 10 draws sit above it, and it kills weak but real edges). (2) Benjamini–Hochberg on the probes' empirical p-values **within each profile**, `q ≤ 0.1`, as a new `s01_probe` criterion `probe_q_value`. (3) The breadth requirement of ≥ 3 accepted groups (D-100), which is the real net: three independent groups passing by chance at once is far less likely than one. **Every profile records the number of probes run**, because stage 7 needs the effective trial count (D-160) and it cannot be reconstructed later. |
| D-606 | **ESS components** (weights from D-103, every constant in config): breadth = 30 × accepted_groups / applicable_groups (MR 4, TF 5); magnitude = 30 × min(1, median excess return per trade in ATR / target), target 0.10 ATR; significance = 20 × min(1, median −log₁₀(p) / 2), so p = 0.01 scores full, with p floored at 1/1001; consistency = 20 × max(0, (share of years with positive excess return − 0.5) / 0.5). Medians, not means, are used across probes so one exceptional probe cannot carry a profile. ESS is 0–100. The ESS ≥ 50 threshold and these constants are **calibrated in T15** against random-walk and planted-edge data; until then they are provisional and the artifact records the config hash that produced them. |
| D-607 | **Baseline seeding**: each probe's 1000 simulations are seeded from `sha256(run_seed, symbol, timeframe, probe_name, direction)`, as T10b seeds work units. Execution order, chunking and worker count must not change any number. A test asserts serial and parallel runs are bit-identical. |
| D-608 | **The artifact stores no probe trades except for passing profiles**, and there only for the accepted probes. At 515 symbols × 34 probes the full trade set is tens of gigabytes and stage 2 does not read it. |
| D-609 | **Every passing profile goes to stage 2**, including two edge types on the same symbol. Trade overlap between candidates is controlled in stage 2 (D-110); restricting diversity at stage 1 is premature. |
| D-610 | **Data caveats travel with the profile.** If the symbol's reference carries a splice marker (T04l), a quality `warning`, or a boundary trim, the EdgeProfile states it. A reader of a profile must not have to consult the catalog to learn that the series is caveated. |

## 3. Inputs

- Universe: the broker universe from `configs/universe.yaml`, 1D and 1H (D-603). Report the
  resolved counts; do not hard-code them.
- References: the current reference per (symbol, timeframe) — the T04k clean daily snapshot and
  the T04l boundary-derived snapshot where one exists. `resolve_config` already refuses a
  `critical` quality status; a `warning` is allowed and recorded (D-610).
- **Development data only.** The holdout is stage 6's (D-306); `open_holdout` must never be
  reachable from this stage, and a test asserts the stage module cannot call it.
- Costs: the Moneta profile for the PF leg (D-602), through the existing cost arrays.

## 4. What to build

| module | content |
|---|---|
| `stages/edge.py` | the stage: per work unit, run the probe battery, the baseline, the statistics, ESS, the gate, and write the artifact |
| `baseline/random_entries.py` | the matched random-entry generator (F-1.4, D-102, D-607) |
| `metrics/ess.py` | the four components and the total (F-1.6, D-606) |
| `stages/edge_profile.py` | the `EdgeProfile` pydantic model and its JSON schema |
| `configs/stages/s01_edge.yaml` | every constant: ATR target, significance scale, BH q, group lists, baseline simulation count, probe list |

Probe entries and their group metadata already exist from T07 (F-1.1, F-1.2); this task wires
them, it does not redefine them. Probe exits are fixed by D-101 and are engine settings, not new
components.

## 5. Statistics, precisely

For each probe, on the development window:

1. Run the probe with its fixed parameters and fixed exits (D-101), zero costs, `n_closed_trades`
   per D-301.
2. **Excess return per trade** = trade return (entry fill to exit fill) divided by the ATR at the
   signal bar, expressed in ATR units. Report mean (D-601) and median.
3. **Baseline**: 1000 simulations matched on direction, trade count and the holding-period
   distribution, entries drawn only from allowed bars; no overlapping positions when the probe has
   none (D-102). Each simulation yields the same mean statistic.
4. **Percentile** = share of baseline means strictly below the probe's mean, ×100.
   **Empirical p** = (1 + #{baseline ≥ probe}) / (1 + n_sim), floored at 1/1001.
5. **BH within the profile** over all probes' p-values → `probe_q_value` (D-605).
6. **Profit factor** with full costs on the same trades (D-602).
7. **Consistency**: share of calendar years in the development window whose mean excess return is
   positive. Years with fewer than a configured minimum of trades are excluded and the count of
   excluded years is recorded.

A probe is **accepted** when it passes every `s01_probe` criterion: `n_trades`, `probe_percentile`,
`profit_factor`, `probe_q_value`. A group is accepted when at least one of its probes is.

## 6. Gate wiring

`s01_probe` and `s01_edge` already exist in `configs/gates/default.yaml` (T10a) with
`n_trades`, `probe_percentile`, `profit_factor`, `accepted_probe_groups`, `ess`. This task adds
**one** criterion, `probe_q_value ≤ 0.1`, and registers the metric names it produces in the T10b
registry.

`configs/gates/` and `metrics/` are **stream A's paths** (D-357). If stream B implements T12, the
gate YAML and metric-name registration are a separate stream-A change: raise it, do not edit
those files.

## 7. Compute

Work unit = (symbol, timeframe, edge_type, direction) — the executor's unit from T10b, which
gives chunking, the thread budget (D-334) and parent-only registry writes for free.

Budget before building: 515 symbols × 2 timeframes × 17 probes × 2 directions × 1001 runs is the
worst case. Measure the per-probe cost on a 10-symbol pilot first and report the projected total;
if it exceeds a few hours, say so and propose a reduction (vectorising the baseline inside one
grid call is the first thing to try — the baseline entries are just another signal matrix).

## 8. Artifact

`artifacts/<run_id>/s01_edge/<candidate_id>/summary.json`, one per profile (D-604):

- identity: symbol, timeframe, edge_type, direction, snapshot hash, config hash, development
  window, code version;
- per probe: name, group, trigger (D-105), n_closed_trades, mean and median excess return in ATR,
  percentile, p, BH q, PF with costs, share of positive years, accepted with the failing criterion
  named when not;
- profile: the four ESS components with their raw values and their points, total ESS, accepted
  groups, applicable groups, gate verdict per criterion;
- `probes_run`: the count for D-160 (D-605);
- data caveats (D-610);
- reserved and empty for P1: `complementary_stats` (F-1.7 — VR, Hurst, half-life).

Trades only for accepted probes of passing profiles (D-608), as `trades.parquet`.

## 9. Tests

- **Unit**: each ESS component against hand-computed cases, including the boundaries (0 accepted
  groups, share of positive years exactly 0.5, p at the floor); the percentile and p formulas;
  the BH implementation against a worked example.
- **Baseline properties** (F-1.4 acceptance): on random-walk data the probe percentiles are
  approximately uniform; the matched properties (direction, count, holding distribution) are
  exactly equal to the probe's by construction; no overlap when the probe has none.
- **Planted edge**: on a series with an injected mean-reversion edge, the percentile and ESS are
  high; on random-walk data they sit near the middle (F-1.5 acceptance).
- **Reproducibility**: same seed, same numbers, serial vs parallel bit-identical (D-607).
- **Leakage** (rule 3): truncation invariance for every probe signal and for the stage's own
  statistics — nothing computed at bar t may use bar t+1.
- **Holdout**: the stage cannot reach `open_holdout`; asserted, not assumed.
- **Gate**: a profile failing each criterion in turn is rejected with that criterion named, and
  the thresholds come from the config (rule 1).

## 10. Acceptance

- Every constant in config, none in code (rule 1).
- The 10-symbol pilot runs end to end and its numbers are reproduced by a second run.
- The full MVP-scope run completes and the review reports: how many profiles were produced, how
  many passed, the ESS distribution, the failing criterion counts, and the `probes_run` total.
- A random-walk control run at the same scale: the review states how many profiles pass on data
  with no edge. **This number is the headline result of the task** — if it is not small, the
  gate is not doing its job and the thresholds go back to the supervisor before anything is built
  on top.
- Fast suite, parity/leakage/oracle, db with 0 skipped, ruff, format, mypy, stream guards.
- The review, then stop for "Approved" (D-402).

## 11. Raise, do not decide

- The ESS constants and the ESS ≥ 50 threshold are provisional until T15 calibrates them
  (D-606). If the pilot shows them badly placed, report the evidence and stop.
- If the pass rate on the random-walk control is high, that is a supervisor question, not a
  threshold to tune quietly.
- Any probe whose trade count is systematically below the minimum on 1H (D-104's 100) — report
  it; do not drop the probe.
