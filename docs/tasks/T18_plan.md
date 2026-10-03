# T18 — plan: the stage-6 robustness library, measurements and the nine choices

Stream B's plan for `docs/tasks/T18_robustness_library.md` (D-403). The task file is the
supervisor's and is not edited. Features F-6.1 … F-6.4, F-6.7, F-6.9 (library side). Decisions read:
D-008, D-120, D-130, D-150, D-306, D-308, D-660 (T16's purity, copied), D-722 … D-725 (T16's
bootstrap and seed conventions), D-651 (1) (NaN never passes a count). Open questions:
**P-150 … P-159** (`docs/decisions/pending.md`). Runbook: `docs/tasks/RUNBOOK_T18.md`.

**§3 says "raise, do not decide".** Each of the nine choices below lists its options and what each
does to the gate, with measurements on synthetic data where a light computation can inform it.
The plan **picks none**. **No code in `robustness/` yet:** the path is not stream B's until stream
A's ownership PR lands (task §6).

**Measured, not assumed.** One light script, about 30 s in all (`scripts/analysis/T18_plan_measure.py`,
fixed seeds; the store only read, the catalog):

| run | output |
|---|---|
| `wfe` | `docs/reviews/T18_plan_wfe.csv` — WF efficiency definitions in three worlds, 400 simulations each |
| `windows` | `docs/reviews/T18_plan_windows.csv`, `T18_plan_wf_matrix.csv` — how many WF windows the store's development windows fit |
| `trade_boot` | `docs/reviews/T18_plan_trade_boot.csv` — i.i.d. against block trade bootstrap on dependent trades |
| `consistency` | `docs/reviews/T18_plan_consistency.csv` — R², K-ratio, the CV of yearly profit, the KS test |

The choices that need **engine re-runs** (price noise, parameter noise, random start) are not
measured by day. §10 lists what tonight-or-later runs would measure, behind T16's queue.

## 0. A finding that comes before the nine: D-150's daily lengths do not fit the Alpaca data (P-159)

The development window of each 1D / 1H reference in the store is its span minus the holdout (20 %,
at least 18 months) minus the embargo (250 bars: about **one year** on 1D, about two months on 1H;
`configs/data/split.yaml`). D-150's walk-forward lengths, counted in out-of-sample windows:

| source, timeframe | references | development years (p10 / median / p90) | OOS windows at D-150 (median) | ≥ 4 windows | auto-shrink (1–3) | none fit |
|---|---|---|---|---|---|---|
| Alpaca 1D (4 y / 1 y) | 6,708 | −1.1 / **4.4** / 7.6 | **0** | **0 %** | 48 % | **52 %** |
| Alpaca 1H (2 y / 6 m) | 805 | 2.9 / 8.4 / 8.4 | 12 | 88 % | 3 % | 9 % |
| Dukascopy 1D (4 y / 1 y) | 8 | 7.3 / 11.1 / 12.3 | 6 | 75 % | 12.5 % | 12.5 % |
| Dukascopy 1H (2 y / 6 m) | 9 | 5.1 / 10.7 / 13.2 | 17 | 89 % | 0 % | 11 % (the 2024 Q1 pilot) |

**Not one Alpaca daily series fits D-150's four out-of-sample windows.** Even a full 2016–2026 history
leaves 7.6 development years, which is 3 windows. So D-150's auto-shrink (proportionally smaller
windows, flagged) would run for every daily US equity, and half of them fit no window at all. The
p10 is negative because short histories cannot be split at all (D-008); those never reach stage 6.
The library implements D-150 as written (task §2 (b)). Whether D-150's 1D lengths should change, or
the auto-shrink is the intended daily case, is the user's question (**P-159**).

## 1. What T18 builds (once the path is stream B's)

A pure library in `src/strategy_factory/robustness/`, same shape as T16 (`stats/`): arrays and plain
values in, frozen Pydantic results out; no registry, no store, no config loading, no stage import;
randomness only through a seed. `robustness/spp.py` (stage 3's SPP, F-6.5) stays as it is.

| module | features | inputs → result |
|---|---|---|
| `robustness/results.py` | all | one frozen result type per function |
| `robustness/consistency.py` | F-6.1 | trades (P&L, entry/exit times), equity curve → yearly / quarterly metrics (through `metrics/`, F-0.5.x, never re-implemented), R², K-ratio, KS between halves, the CV of yearly metrics, the three anomaly checks |
| `robustness/walkforward.py` | F-6.2, F-6.3 | the development window's timestamps, D-150's lengths, mode (anchored / rolling), **a re-optimization callable** (stage 3's plateau selection when wired; a known function in tests) and **an evaluation callable** → windows (with the auto-shrink flag), per-window IS / OOS results, WFE, the share of profitable OOS windows, the WF matrix and its share of passing cells |
| `robustness/montecarlo.py` | F-6.4 | the seven types: shuffle, bootstrap, random removal (10–20 %) on a trade list; price noise, parameter noise, random start, cost stress (× 1.5, 2, 3) **through a re-run callable** (the engine when wired) → each run's metrics, the distribution's percentiles, the seeds |
| `robustness/crisis.py` | F-6.7 | equity / trades and D-150's periods → a per-period table, "no data" where the series does not cover a period |
| `robustness/score.py` | F-6.9 | each block's result, the holdout's result (an input; opening it is stage 6's, D-306) → each block's pass / fail and 0–100, the weighted total, and the critical-block rejection |

- **No threshold inside.** The gate's numbers stay in `configs/gates/default.yaml` (`s06_robust`); the
  library returns values, and the stage compares them. The score's weights and scales are inputs.
- **Seeds:** each Monte-Carlo run's seed derives from the run seed and a stable key with CRC32, never
  Python's salted `hash()` (T16). So a parallel run equals a serial one, bit for bit.
- **No look-ahead in walk-forward:** the re-optimization callable is handed **only the in-sample
  slice**. A test passes an optimizer that would pick differently if it saw any out-of-sample bar.
- **Monte Carlo is not a trial** (D-012): the library returns distributions and percentiles; nothing
  is written to the registry.

## 2. §3 (1) — WF efficiency's definition (P-150)

The spec: "the ratio of the annual out-of-sample return to the in-sample return". Measured on a
family of 50 correlated variants of one strategy; rolling WF, 4 y / 1 y over 8.5 y (4 windows); in
each window the variant with the best in-sample Sharpe is chosen (a stand-in for the plateau
selection). 400 simulations per world; median (p10 … p90) and the share passing the gate (WFE ≥ 0.5;
OOS-profitable share ≥ 0.6):

| definition | true edge in every variant | edge in one variant | pure noise |
|---|---|---|---|
| (a) pooled annual return: mean OOS / mean IS | 0.69 (0.30 … 1.11), **70 % pass** | 0.96, 85 % | 0.08 (−1.64 … 1.09), **27 % pass**, undefined 11 % (IS ≤ 0) |
| (b) mean of per-window ratios | 0.75 (0.35 … 1.20), 76 % | 1.10, 87 % | 0.29 (−3.14 … 3.45), **42 % pass** |
| (c) as (b), skipping windows with IS ≤ 0 | 0.75, 76 % | 1.13, 90 % | 0.22, 38 %, undefined 4 % |
| (d) pooled Sharpe: mean OOS Sharpe / mean IS Sharpe | 0.68 (0.29 … 1.11), 68 % | 0.96, 85 % | 0.09, **27 % pass**, undefined 11 % |
| share of profitable OOS windows (the second gate) | 1.0, 89 % | 1.0, 87 % | 0.5, 30 % |

- **With 4 windows WFE separates real from noise only loosely.** A real edge passes 68–76 % of the
  time, noise 27–42 %. The per-window mean (b) is the most lenient on noise, because a few large
  ratios dominate.
- **IS ≤ 0** happens only under noise here; it leaves the pooled ratios undefined in 11 % of noise
  runs. Options: undefined → fail; undefined → skip the window; floor IS at a small positive value.
- **Options:** (a), (b), (c) or (d), plus a rule for IS ≤ 0. The gate is `wf_efficiency ≥ 0.50`,
  critical.

## 3. §3 (2) — the WF matrix's lengths, and what "a passing cell" is (P-151)

Two candidate 5 × 5 matrices per timeframe, counted at each source's median development length: the
number of cells that fit ≥ 4 / 1–3 / no out-of-sample windows (`T18_plan_wf_matrix.csv`):

| matrix (IS years × OOS years) | Alpaca (median dev) | Dukascopy (median dev) |
|---|---|---|
| 1D A, D-150 centred: IS 2, 3, 4, 5, 6 × OOS 0.5, 0.75, 1, 1.25, 1.5 | 4.4 y: **1 / 8 / 16** | 11.1 y: 24 / 1 / 0 |
| 1D B, shorter: IS 1, 1.5, 2, 3, 4 × OOS 0.25, 0.5, 0.75, 1, 1.5 | 4.4 y: 8 / 12 / 5 | 11.1 y: 25 / 0 / 0 |
| 1H A, D-150 centred: IS 1, 1.5, 2, 2.5, 3 × OOS 0.25 … 1 | 8.4 y: 25 / 0 / 0 | 10.7 y: 25 / 0 / 0 |
| 1H B, shorter: IS 0.5 … 3 × OOS 0.125 … 1 | 8.4 y: 25 / 0 / 0 | 10.7 y: 25 / 0 / 0 |

- **On Alpaca 1D a D-150-centred matrix leaves 16 of 25 cells empty**; even the shorter one leaves 5
  (§0).
- **"A passing cell"**, options:
  - (i) the cell's own WFE ≥ the WFE gate (0.5);
  - (ii) WFE ≥ 0.5 **and** its OOS-profitable share ≥ 0.6, i.e. both WF gates;
  - (iii) the cell's pooled OOS return > 0.
- **Empty cells**, options: (α) excluded from the share; (β) counted as failures.
- The gate: `wf_matrix_success_share ≥ 0.60`, critical.

## 4. §3 (3) — the trade bootstrap: i.i.d. or blocks (P-152)

300 trades whose P&L is serially dependent in trade order. The true 95th percentile of the max
drawdown (from 20,000 fresh draws of the process) against each bootstrap's estimate from one series
(200 series, 1,000 resamples):

| trade P&L | true p95 max DD | i.i.d.: median estimate (bias) | block, Politis–White: estimate (bias), median block |
|---|---|---|---|
| independent | 21.1 | 22.1 (+5 %) | 21.6 (+2 %), 1.3 |
| AR(1) φ 0.3 | 32.2 | 22.5 (**−30 %**) | 30.0 (−7 %), 4.4 |
| AR(1) φ 0.6 | 52.5 | 23.1 (**−56 %**) | 46.5 (−12 %), 8.2 |
| regimes (streaks of ~20 trades) | 60.5 | 21.1 (**−65 %**) | 41.4 (−32 %), 9.2 |

- **i.i.d. resampling erases serial dependence, so it understates drawdown risk** by a third to two
  thirds when trades cluster. The block bootstrap with T16's automatic length (D-723 / D-725) halves
  that error or better, but still understates under regimes.
- With independent trades the two agree, and Politis–White picks a block near 1 by itself.
- The trade **shuffle** (F-6.4's first type) has the same blind spot: it measures order risk only for
  exchangeable trades.
- **Options:** i.i.d. (the spec's literal "with replacement"); the stationary block bootstrap with
  Politis–White (T16's convention); or both reported, one gated. Through D-308
  (`mc_max_dd_p95_pct ≤ 25`), this choice moves the gate directly.

## 5. §3 (4) — price noise (P-153)

Not measured by day (it needs engine re-runs). The options:

- **Size:** a fraction of the bar's ATR (for example 0.05, 0.1, 0.2 × ATR(14)), or a multiple of the
  cost profile's spread (0.5, 1, 2 × spread).
- **Distribution:** Gaussian or uniform; per bar, independently or with the bar's four prices moving
  together.
- **OHLC consistency**, options:
  - (i) noise the close only and rebuild a consistent bar (open = previous noisy close; high / low
    widened to contain open and close);
  - (ii) noise all four prices independently, then repair (high = max, low = min);
  - (iii) one multiplicative factor per bar on all four prices, which keeps the bar's shape exactly.
- **Effect:** (iii) never changes a high / low ordering, but leaves the bar's range scale unchanged;
  (ii) can widen ranges, which is harsher on stops (the D-673 argument); (i) changes gap behaviour at
  the open.
- Indicators are recomputed on the noisy series, and the disaster stop's ATR moves with it (D-130).

## 6. §3 (5) — parameter noise (P-154)

Not measured by day. The options:

- **Integer lengths:** ±1 or ±2 steps of the stage-3 grid's step, or ±10 % rounded.
- **Continuous thresholds:** ±0.5 or ±1 grid step, or a Gaussian with sd = one step.
- **Inside the grid**, options: (a) clipped to the stage-3 fine grid's bounds, the plateau's world
  (D-120); (b) reflected at the bounds; (c) free, allowed outside.
- **Choice parameters** (fixed by D-640): never noised, or noised among neighbours.
- **Effect:** inside-the-grid noise re-measures the plateau, which stage 3 already proved (D-120:
  ±1 step, plateau ratio ≥ 0.8); noise beyond it tests something stage 3 did not.

## 7. §3 (6) — random start date (P-155)

Not measured by day. The options:

- **Range of the start:** the first 10 %, 20 % or 30 % of the development window.
- **Distribution:** uniform over that range, or uniform over whole months.
- **Minimum remaining length**, options:
  - (a) at least one year;
  - (b) at least D-008's length, so the remaining series can still be split;
  - (c) at least the run's minimum trade count.
- **Effect:** on Alpaca 1D (median 4.4 development years, §0) a 30 % range removes up to 1.3 years,
  which interacts with (b): many daily series would fail it.

## 8. §3 (7) — the CV threshold, and R² ≥ 0.8 on short series (P-156)

Strategies with a constant true edge (daily returns, 400 simulations each):

| true annual Sharpe | years | R² median | share with R² ≥ 0.8 | K-ratio median | CV of yearly profit, median (p90) |
|---|---|---|---|---|---|
| 0.5 | 2 / 4 / 8 | 0.52 / 0.57 / 0.70 | 22 / 28 / 36 % | 0.80 / 1.04 / 1.51 | 1.22 (7.3) / 1.81 (9.3) / 2.04 (9.6) |
| 1.0 | 2 / 4 / 8 | 0.77 / 0.86 / 0.92 | **44 / 60 / 82 %** | 1.80 / 2.45 / 3.41 | 0.69 (3.6) / 0.91 (3.0) / 0.96 (1.8) |
| 2.0 | 2 / 4 / 8 | 0.92 / 0.96 / 0.98 | 84 / 96 / 100 % | 3.48 / 4.70 / 6.62 | 0.36 (0.85) / 0.45 (0.86) / 0.49 (0.73) |

- **R² ≥ 0.8 is mostly a Sharpe-and-length test.** A genuine Sharpe-1 strategy fails it more than
  half the time on 2 years and 18 % of the time on 8; Sharpe 0.5 fails it two thirds of the time at
  any length. Options for short series: (a) as written; (b) R² read against a length-dependent
  reference (the distribution above); (c) report-only below a minimum length.
- **The CV threshold:** CV of yearly profit is about 1 / (annual Sharpe) and very heavy-tailed when
  the edge is small (p90 up to 9.6 at Sharpe 0.5). Options:
  - a fixed value (for example 1.0 or 1.5), which a genuine Sharpe-1 strategy passes about half the
    time;
  - a rule relative to the strategy's own Sharpe;
  - report-only.
- **The KS test between halves has almost no power:** when the second half's edge halves, it rejects
  3.8 % (50 trades), 5.0 % (200) and 7.2 % (500) of the time, about its false-alarm rate
  (4.2–6.0 %). "Not rejected at 0.05" is passed by nearly anything. This is a fact for P-158's
  gate / report question, not a separate choice.

## 9. §3 (8) and (9) — the score's weights and which blocks gate (P-157, P-158)

Judgement, not measurement. The options:

- **Block weights (P-157):** (a) equal across the six blocks (consistency, WF, WF matrix, Monte Carlo,
  cost stress, crisis); (b) the critical blocks heavier (WF, cost stress); (c) by evidence strength —
  heavier where the measurement separates real from noise better (§2, §8 inform this);
  (d) no weighted total, the pass count only.
- **Each block's 0–100 scale (P-157):** (i) linear between the gate threshold (50) and a "comfortable"
  level (100); (ii) a percentile against a reference distribution, such as the null strategies of
  T15; (iii) 100 × the share of a block's checks passed.
- **Gate or report (P-158):** the gate table already gates WFE, OOS-profitable share, WF-matrix share
  and 2× cost (critical), the MC drawdown p95 (D-308) and the holdout. Open per block:
  - consistency: R², KS, CV, anomalies — each gate or report;
  - the other Monte-Carlo types: removal, noise, random start, cost × 1.5 and × 3;
  - crisis periods: report-only, or a gate on "no crisis loses more than X";
  - the score itself: a gate (total ≥ X) or report-only beside the critical-block rule.

## 10. Measurements that need engine re-runs (tonight or later, behind T16)

After the plan is approved and the options are narrowed, an unattended, resumable script (logging
line by line, like T16's) would run, on one or two real stage-3 candidates through the engine:

- price noise at each size and OHLC option (P-153): the spread of the metrics;
- parameter noise inside / outside the grid (P-154);
- random start under each minimum-length rule (P-155);

each against the candidate's base run, with the runtime per run.

## 11. Tests (task §4)

| block | known-answer tests | property tests |
|---|---|---|
| consistency | R² and K-ratio of a hand-built equity curve; KS against `scipy`; the anomaly checks on a hand-built trade list | — |
| walk-forward | window boundaries at the edges (exact fit, auto-shrink, too short); WFE by hand; a look-ahead test (an optimizer that would choose differently if it saw out-of-sample data) | — |
| Monte Carlo | percentiles of a known distribution recovered within the Monte-Carlo error; same seed bit-identical, serial and parallel | a shuffle keeps total profit; removal never adds trades; cost stress × 1 equals the base run |
| crisis | a series covering some periods and not others → the table and the "no data" marks | — |
| score | the critical-block rule rejects whatever the total; the weighted total by hand | — |
| purity | the static import check (as T16's) | — |

## 12. Assumptions (in `pending.md` only where a decision is needed)

- The walk-forward re-optimization callable receives only the in-sample slice and returns the
  selected parameters; the evaluation callable runs them on a slice. Both are pure from the
  library's side.
- The stage-6 stage, the holdout (F-6.8), final SPP (F-6.5) and cross-symbol validation (F-6.6) are
  not T18's (task §2).
- Yearly and quarterly metrics come from `metrics/` (stream A's, F-0.5.x), imported, never copied.
