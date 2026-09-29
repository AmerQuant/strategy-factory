# T16 — Stage-7 statistics library (`stats`)

**Stream B.** Plan first (D-403): draft, stop for "Plan approved", then implement; stop for the
review before merge. Starts after T04j, and after stream A's preparatory PR (§3) is merged.
Features: F-7.1 … F-7.7 (module `stats` in `docs/features.md`).

## 1. What this task builds

A **pure statistics library** for stage 7 (spec §7): arrays in, results out. No registry, no
artifacts, no stage wiring — the stage-7 stage that feeds it real data is a later stream-A task.
Building the library now, independently of the funnel, means it is ready and tested when the funnel
reaches stage 7.

## 2. Decisions to record before implementing

Supervisor range, marked *(supervisor)*, each citing this task. Next free supervisor id: D-658
(D-657 is T04j's per-instrument gate).

| ID | Decision |
|---|---|
| D-658 | **The stage-7 statistics library lives in `src/strategy_factory/stats/` and is stream B's path.** The spec already names the module `stats`. `robustness/spp.py` (stage 3's SPP, stream A) stays where it is. The stage-7 stage that uses the library is stream A's (D-611). |
| D-659 | **`arch` is a production dependency**, chosen by the user, for Hansen's SPA and the time-series bootstraps (stationary and block). The rest — the effective number of trials, the Deflated Sharpe Ratio, PBO by CSCV, the Minimum Track Record Length, the t-test with HAC, the permutation test — is implemented in the library and tested against published reference values or independent implementations. Adding `arch` must not move the numba/numpy pins (D-330); if it would, that is raised, not absorbed. |
| D-660 | **The library is pure**: numpy arrays (and plain Python values) in, frozen result objects out; no I/O, no registry, no config loading, no global state; randomness only through an explicit seed argument. Every threshold of the stage-7 gate stays in `configs/gates/` and is applied by the later stage, never inside the library. |

## 3. Preparation by stream A (before this task starts)

`pyproject.toml`, `uv.lock` and `docs/streams/ownership.yaml` are stream-A only (D-357). Stream A
opens one small PR that (a) adds `arch` with its dependencies and confirms the numba/numpy pins are
unchanged, (b) assigns `src/strategy_factory/stats/` and `tests/**/test_F_7_*` to stream B in
`ownership.yaml`, with tests. Stream B starts T16 once it is merged.

## 4. The functions (F-7.1 … F-7.7)

Each takes the data it needs as arrays and returns a result object with the statistic, the p-value
or probability where one exists, and the inputs' sizes.

| feature | function | input | output |
|---|---|---|---|
| F-7.1 | t-test on trade returns; HAC (Newey–West) t-test on daily returns; bootstrap confidence intervals for Sharpe and expectancy | a return series; the HAC lag rule and bootstrap scheme as arguments | statistic, p, interval |
| F-7.2 | Monte-Carlo permutation p-value | the observed statistic and the statistics of random-entry runs (stage 1's matched baseline supplies them) | p |
| F-7.3 | effective number of trials | a matrix of trial return series (trials × time) | N effective, N raw, the clusters |
| F-7.4 | Deflated Sharpe Ratio | the selected Sharpe, its sample length, skewness, kurtosis, N effective and the variance of the trials' Sharpes | the probability |
| F-7.5 | PBO by CSCV | a matrix of trial performance over time (trials × time), the number of partitions | PBO, the logit distribution |
| F-7.6 | Hansen SPA | the benchmark and the candidates' loss or return series | p (consistent, lower, upper), via `arch` |
| F-7.7 | Minimum Track Record Length | Sharpe, skewness, kurtosis, the target Sharpe and confidence | the length |

## 5. Tests (the acceptance of each feature)

- **F-7.1:** the t-test and HAC match an independent implementation (`statsmodels`, which arrives
  with `arch`, used as the test oracle only); bootstrap intervals cover a known mean at their nominal
  rate on simulated data.
- **F-7.2:** on the null, p-values are close to uniform (a KS check with a stated tolerance).
- **F-7.3:** N effective ≤ N raw always; close to 1 on perfectly correlated trials; close to N raw on
  independent ones.
- **F-7.4:** equals the worked example in Bailey & López de Prado's DSR paper to its printed precision.
- **F-7.5:** close to 0.5 on random trials; low on a matrix where one trial dominates out of sample;
  the CSCV partition count matches the combinatorics.
- **F-7.6:** rejects on a planted superior candidate, and has close to nominal size on the null.
- **F-7.7:** equals the paper's worked example; decreases as Sharpe rises.
- **Purity (D-660):** a static check that `stats/` imports no registry, I/O or config module; a
  determinism check for every seeded function.
- Hypothesis properties where a property is stated (monotonicity, bounds, invariance to scaling).

## 6. Acceptance

Fast suite, parity/leakage/oracle, db with 0 skipped, ruff, format, mypy (Windows and
`--platform linux`), stream guards. The review lists every reference value used and its source.
Then stop for "Approved".

## 7. Raise, do not decide

- **The clustering method behind F-7.3** (the spec says only "clustering correlated results"):
  measure the candidates on synthetic trial matrices with a known number of independent groups, and
  bring the options with their numbers.
- The HAC lag rule and the bootstrap block length: options with their effect on known cases.
- The number of CSCV partitions for PBO, and how it scales with the trial count the funnel produces
  (stage 3 alone wrote thousands of trials per run).
- Anything in `arch`'s API that constrains the library's shape.
