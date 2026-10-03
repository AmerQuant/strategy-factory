# T18 — Stage-6 robustness library

**Stream B.** Features **F-6.1 … F-6.4, F-6.7, F-6.9** (the library side). **Priority:** P1.
Plan first (D-403): draft, stop for "Plan approved", then implement; stop for the review before merge.
Same shape as T16: pure functions with known-answer tests on synthetic data, independent of the
funnel; the stage that calls them (stage 6, with the holdout) is a later task.

Read first: `CLAUDE.md`, `docs/spec/spec_v1.2.md` stage 6 (§6.1 … §6.6 and its gate table),
`docs/features.md` §6, decisions **D-150** (walk-forward lengths, Monte-Carlo counts, crisis
periods), **D-308** (the Monte-Carlo drawdown gate, p95 ≤ 25 %), **D-120** (the plateau method),
**D-130** (the disaster stop), **D-306** (the holdout guard), the T16 review (its bootstrap and seed
conventions), and `docs/reviews/T14_review.md` (stage 3's plateau selection, which walk-forward
re-uses per window).

## 1. Why now, and why a library

Stream B is free while stream A finishes T15a and T15b. Stage 6's blocks are, apart from the
holdout, computations on a strategy's trades, equity and re-runs that can be built and proven on
synthetic inputs with known answers. When the funnel reaches stage 6, only the wiring remains.

## 2. Scope — in `src/strategy_factory/robustness/` (stream B's, see §6)

**(a) Consistency (F-6.1, spec §6.1):** per-year (and per-quarter where trades allow) metrics; the
equity curve's R² and K-ratio; the KS test between the two halves' trade-return distributions; the
coefficient of variation of the yearly metrics; the anomaly checks (share of profit from the best
5 % of trades, profit without the 10 best trades, profit without the best year).

**(b) Walk-forward (F-6.2, F-6.3, spec §6.2–6.3):** window generation, anchored and rolling, with
D-150's lengths and its auto-shrink when fewer than 4 out-of-sample windows fit (flagged); the
re-optimization in each window is **a callable the caller passes in** (stage 3's plateau selection
when wired; a known function in the tests), so the library never imports a stage; the WF
efficiency and the share of profitable OOS windows; the WF matrix over in-sample × out-of-sample
lengths and its share of passing cells.

**(c) Monte Carlo (F-6.4, spec §6.4):** the seven types — trade-order shuffle, trade bootstrap,
random removal of 10–20 % of trades, price noise, parameter noise, random start date, cost stress
(× 1.5, 2, 3). The first three work on a trade list; the last four **re-run a strategy through a
callable the caller passes in** (the engine when wired). 1000 runs for screening, 5000 for final
(D-150); distributions and percentiles kept; seeds derived from the run seed and a stable key, as
in T16 (never Python's salted `hash()`), so parallel equals serial.

**(d) Crisis periods (F-6.7):** a per-period performance table for D-150's periods, each marked
"no data" where the series does not cover it.

**(e) The robustness score (F-6.9):** each block's pass/fail and 0–100 score, the weighted total,
and the rule that a failure in walk-forward, the 2 × cost stress or the holdout rejects on its own,
whatever the total (the holdout's result is an input here; opening it is stage 6's, D-306).

**Out of scope:** opening the holdout (F-6.8), SPP (stage 3 has it, F-6.5), cross-symbol validation
(F-6.6, report-only, needs the universe's groups), the stage itself, and the UI.

## 3. Raise, do not decide (the plan) — these are the user's

The spec leaves these open; for each, give the options with their pros, cons and effect on the
gate, measured on synthetic data where a measurement can decide it, and pick none:

1. **WF efficiency's definition**: annualized return OOS / IS (the spec's words), or a risk-adjusted
   ratio; and what happens when the in-sample return is ≤ 0.
2. **The WF matrix's lengths**: the 5 × 5 in-sample and out-of-sample lengths per timeframe, and
   what "a passing cell" means.
3. **Trade bootstrap**: i.i.d. trades or a block bootstrap (trades of a mean-reversion suite can be
   serially dependent); T16's block-length conventions if blocks.
4. **Price noise**: its size (in ATR or in spread multiples), its distribution, and how OHLC
   consistency and the bar's high/low are kept.
5. **Parameter noise**: its size per parameter type (integer lengths, thresholds), and whether it
   stays inside the stage-3 grid.
6. **Random start date**: the range and distribution of the start, and the minimum remaining length.
7. **The coefficient-of-variation threshold** ("below a defined threshold" in the spec has no number)
   and the R² ≥ 0.8 criterion's treatment of short series.
8. **The robustness score's block weights** and each block's 0–100 scale.
9. **Which of these are gates and which are report-only**, against the gate table in
   `configs/gates/default.yaml` (D-308 already gates the Monte-Carlo drawdown).

## 4. Acceptance

- Every function has a known-answer test (a synthetic trade list or equity curve whose R², K-ratio,
  WFE, percentiles … are computable by hand or from a reference implementation), plus property
  tests where a law exists (a shuffle keeps total profit; removal never adds trades; cost stress ×1
  equals the base run).
- Monte Carlo: the same seed gives bit-identical results, serial and parallel; the percentile of a
  known distribution is recovered within its Monte-Carlo error.
- Walk-forward: window boundaries tested at the edges (exact fits, auto-shrink, too short to run),
  with no look-ahead (a test where any use of out-of-sample data in the optimization changes the
  result).
- ruff, format, mypy (strict for `robustness`), fast suite, stream guards.
- Review in `docs/reviews/T18_review.md`; stop for "Approved. Merge".

## 5. Working rules

- Light work by day, heavy runs only at night (the user's rule): the Monte-Carlo measurements for
  §3 run unattended, resumable, logging line by line, behind T16's in tonight's queue or later.
- Decisions from D-726 (stream B's own range, below D-760); supervisor-settled ones marked
  (supervisor). Pending questions from P-150.

## 6. Prerequisite (stream A)

`src/strategy_factory/robustness/` and its tests (`tests/**/test_F_6_*`) are assigned to stream B in
`docs/streams/ownership.yaml`, as `stats/` was for T16 (D-658). Until that lands, stream B writes the
plan only.
