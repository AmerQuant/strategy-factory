# RUNBOOK — T16: the stage-7 statistics library (stream B)

One task. **Two stops:** the plan (**"Plan approved"**, D-403), and the review before the merge
(**"Approved"**). Task file: `docs/tasks/T16_stats_library.md` (the supervisor's, unchanged). Plan
and measurements: `docs/tasks/T16_plan.md`. Decisions: **D-658 … D-660** (on `main`) and the answers
to **P-97 … P-99**. Features: F-7.1 … F-7.7.

## Branches

| step | branch | base | stop |
|---|---|---|---|
| plan | `b/T16-plan` | `main` after #61 | **"Plan approved"** |
| 1 … 9 | `b/T16-stats-library` (one task, one review file) | stacked on `b/T16-plan` | after the review, **"Approved"** |

Paths: `src/strategy_factory/stats/` (except `stats/edge.py`, stream A's) and `tests/**/test_F_7_*`
are stream B's (D-658, `ownership.yaml`). `scripts/`, `docs/tasks/`, `docs/reviews/` are shared.
Nothing in `stages/`, `configs/gates/`, `pyproject.toml` or `uv.lock` is touched; a need there is a
relay to stream A (plan §8).

## Preconditions

1. P-97 … P-99 answered (or accepted with "Plan approved").
2. `main` green; `arch` installed at its locked version (D-659, #60).
3. The reference values of plan §6 checked against the papers' text; any that cannot be is raised.

## Order of work (tests first in each step)

1. **Result types** (`stats/results.py`): frozen Pydantic models, one per function (statistic, p or
   probability, interval, input sizes). The purity test (D-660): a static import check over
   `stats/` except `edge.py`, and a determinism check per seeded function.
2. **F-7.1** `stats/ttest.py`, `stats/bootstrap.py`: the trade-return t-test, the HAC t-test (the
   lag rule of P-98), bootstrap intervals for Sharpe and expectancy (the scheme and block length of
   P-98, `arch` for the stationary / block bootstraps). Oracle: `statsmodels` (tests only).
3. **F-7.2** `stats/permutation.py`: the permutation p-value against supplied random-entry
   statistics, `(1 + #{null >= observed}) / (1 + n)`; the uniformity (KS) test on the null.
4. **F-7.3** `stats/neff.py`: the method of P-97, on a trials × time matrix; N raw, N effective,
   the clusters. Tests: N_eff ≤ N raw (Hypothesis); ≈ 1 on identical trials; ≈ N on independent
   ones; the planted-K scenarios of plan §2 within their measured tolerance.
5. **F-7.4 / F-7.7** `stats/dsr.py`: SR_0 (the expected maximum), the DSR probability, the Minimum
   Track Record Length. Tests: the papers' worked examples to their printed precision (§6);
   MinTRL decreasing in Sharpe (Hypothesis).
6. **F-7.5** `stats/pbo.py`: CSCV with S partitions (P-99); PBO and the logit distribution; the
   partition count equals C(S, S/2). Tests: ≈ 0.5 on noise, low on a strong planted trial.
7. **F-7.6** `stats/spa.py`: `arch`'s SPA behind a numpy interface (returns in, the three p-values
   out; losses and the benchmark per P-98). Tests: rejects a planted superior model; size near
   nominal on the null (seeded, a stated tolerance).
8. **Gates:** fast suite, parity / leakage / oracle, db (0 skipped), ruff, format, mypy (Windows
   and `--platform linux`), `sfac streams check`.
9. **Review** `docs/reviews/T16_review.md` (every reference value and its source), the
   acceptance reviewer, the PR, stop for **"Approved"**.
