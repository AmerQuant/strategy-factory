# T16 — plan: the stage-7 statistics library, measurements and the §7 questions

Stream B's plan for `docs/tasks/T16_stats_library.md` (D-403). The task file is the supervisor's
and is not edited. Decisions: **D-658** (the path), **D-659** (`arch`), **D-660** (pure), D-012
(a Monte-Carlo run is not a trial), D-160 (stage 7: N effective by clustering; DSR ≥ 0.95,
PBO ≤ 0.25, SPA p < 0.05), D-377 (encodings), D-651 (1) (NaN never passes a count). Open questions:
**P-97 … P-99** (`docs/decisions/pending.md`). Runbook: `docs/tasks/RUNBOOK_T16.md`.

**Measured, not assumed.** Every number below comes from two read-only scripts on synthetic data
with a known answer (no registry, no store):

| script | output |
|---|---|
| `scripts/analysis/T16_plan_neff.py` | `docs/reviews/T16_plan_neff.csv`: 7 N-effective candidates × 19 scenarios × 3 seeds |
| `scripts/analysis/T16_plan_inference.py hac / boot / cscv / spa` | `docs/reviews/T16_plan_{hac,boot,cscv,spa}.csv` |

**§7 says "raise, do not decide".** Each question below lists its options and what each one does
to cases with a known answer. The plan **does not choose** among them.

## 1. What T16 builds

A pure library in `src/strategy_factory/stats/` (D-658). `stats/edge.py` stays stream A's.

| module | features | inputs → result (frozen Pydantic, D-660) |
|---|---|---|
| `stats/results.py` | all | one result type per function: the statistic, p or probability, interval, the inputs' sizes |
| `stats/ttest.py` | F-7.1 | trade returns → t, p; daily returns + a lag rule (P-98) → HAC t, p, lags used |
| `stats/bootstrap.py` | F-7.1 | returns, scheme, block length (P-98), reps, seed → interval for Sharpe and expectancy |
| `stats/permutation.py` | F-7.2 | the observed statistic and the random-entry statistics → p = (1 + #{null ≥ obs}) / (1 + n) |
| `stats/neff.py` | F-7.3 | trials × time returns → N raw, N effective, the clusters (method: P-97) |
| `stats/dsr.py` | F-7.4, F-7.7 | SR, T, skewness, kurtosis, N effective, V[SR] → SR₀, DSR; SR, target, confidence → MinTRL |
| `stats/pbo.py` | F-7.5 | trials × time performance, S (P-99) → PBO, the logits, the split count |
| `stats/spa.py` | F-7.6 | benchmark and candidates' returns → consistent / lower / upper p (via `arch`, P-98) |

- **No threshold inside** (D-660). The library returns probabilities and p-values; stage 7 (stream
  A) compares them with `configs/gates/`.
- **Randomness only through `seed`.** Every seeded function is tested for determinism.
- **Purity check:** a static test that `stats/` (except `edge.py`) imports nothing from `registry`,
  `data`, `core.config`, `pipeline`, `stages`, and no `polars` / `pathlib` I/O.
- **NaN:** a NaN input statistic gives a NaN result, never a pass (D-651 (1)).
- **pandas** appears only inside `stats/spa.py`, at the `arch` boundary (CLAUDE.md: pandas only at
  the edges, stats libraries). Nothing pandas leaves the module.

## 2. §7 (1) — the effective number of trials (F-7.3, P-97)

The spec says only "clustering correlated results" (D-160). Seven candidates, measured on trial
matrices (200 trials × 1,000 daily returns unless stated; 3 seeds; mean shown). A scenario with K
planted groups has the known answer K: trials correlate at ρ within a group and 0 across.

| scenario | truth | avg_corr | eig_participation | eig_li_ji | eig_mp | hier ρ-cut 0.5 | hier ρ-cut 0.3 | onc* |
|---|---|---|---|---|---|---|---|---|
| identical trials | 1 | 1.0 | 1.0 | 1.3 | 1.0 | 1.0 | 1.0 | 1.0 |
| independent trials | 200 | 200.0 | 166.8 | 197.3 | **1.0** | 200.0 | 200.0 | 2.0 |
| K=1, ρ 0.95 / 0.7 / 0.4 | 1 | 1.0 / 1.4 / 2.5 | 1.1 / 2.0 / 6.0 | 11 / 61 / 120 | 1 / 1 / 1 | 1 / 1 / **199** | 1 / 1 / 1 | 2 / 2 / 2 |
| K=5, ρ 0.95 / 0.7 / 0.4 | 5 | 5.3 / 7.2 / 12.2 | 5.5 / 9.8 / 26.8 | 17 / 65 / 124 | 5 / 5 / 5 | 5 / 5 / **200** | 5 / 5 / 5 | 5 / 5 / 5 |
| K=20, ρ 0.95 / 0.7 / 0.4 | 20 | 21.7 / 28.4 / 45.1 | 21.5 / 35.8 / 75.9 | 39 / 83 / 136 | 20 / 20 / 20 | 20 / 20 / **200** | 20 / 20 / 20 | 20 / 2.3 / 3.7 |
| K=50, ρ 0.95 / 0.7 / 0.4 | 50 | 54.2 / 67.5 / 94.9 | 51.3 / 75.2 / 119.5 | 83 / 116 / 161 | 50 / 47.3 / 31.3 | 50 / 50 / **200** | 50 / 50 / 50 | 34 / 5.3 / 2.0 |
| unequal groups (100, 40, 20 … 2), ρ 0.7 | 10 | 4.5 | 6.5 | 72.3 | 9.0 | 10.0 | 10.0 | 8.0 |
| K=50, ρ 0.7, **1,000 trials** | 50 | 73.5 | 88.9 | 346.7 | 50.0 | 50.0 | 50.0 | 4.0 |

**No single right answer: a parameter grid.** These are the realistic cases. A stage-3 grid's
neighbouring cells correlate strongly and far cells weakly; families, methods and cells nest.

| scenario | avg_corr | eig_participation | eig_li_ji | eig_mp | hier 0.5 | hier 0.3 | onc* |
|---|---|---|---|---|---|---|---|
| 1-D grid, neighbours `exp(−|i−j|/5)` | 20.5 | 38.5 | 93.7 | 25.3 | 37.7 | 20.7 | 2.3 |
| 1-D grid, `exp(−|i−j|/20)` | 5.5 | 10.4 | 48.0 | 14.0 | 8.7 | 5.3 | 2.0 |
| nested: 4 families × 5 methods × 10 cells | 10.0 | 19.9 | 77.7 | 20.0 | 20.0 | 5.0 | 4.0 |

**Runtime** (seconds per call; the correlation matrix itself is extra, 1.5 s at 11,000 trials):

| trials | avg_corr | eig_participation | eig_li_ji | eig_mp | hier (either cut) | onc* |
|---|---|---|---|---|---|---|
| 200 | < 0.01 | < 0.01 | < 0.01 | < 0.01 | < 0.01 | 12–14 |
| 1,000 | < 0.01 | 0.17 | 0.21 | 0.21 | 0.03 | 227 |
| 5,000 | < 0.01 | 10.7 | — | 7.8 | 0.4 | — |
| 11,000 (a T14-sized run) | 0.1 | 91 | — | 98 | 5.7 | — |

At 11,000 trials the correlation matrix alone is **about 1 GB** (float64).

**What each one is:**

- **avg_corr** — `N / (1 + (N − 1) ρ̄)`. One number and no parameter. It overcounts when the
  correlation inside groups is weak (K=50, ρ 0.4 → 95). It undercounts when one group dominates
  (unequal → 4.5 of 10), because the big group's pairs dominate ρ̄. It is exact on independent and
  identical trials.
- **eig_participation** — `(Σλ)² / Σλ²`. No parameter; same direction of error as avg_corr, larger.
  Independent trials read 167 of 200 (sampling noise in the eigenvalues).
- **eig_li_ji** (Li & Ji 2005, from genetics) — counts the fractional parts of every eigenvalue, so
  noise eigenvalues add up. It overcounts badly everywhere (1,000 trials, K=50 → 347).
- **eig_mp** — eigenvalues above the Marchenko–Pastur noise edge. Exact on strong blocks. It counts
  **common factors, not independent trials**: independent trials read **1**, not 200. As an N
  effective it needs a companion rule for the trials no factor explains. It also depends on T/N.
- **hierarchical, average linkage, cut at a correlation level** — the only candidate that is
  "clustering" in the spec's own word, and it returns the clusters. Exact on every block scenario
  **whose within-group correlation is above the cut**. Below the cut it splits every trial into its
  own cluster (ρ 0.4 under the 0.5 cut → 199–200). The **cut is a number**; it would live in
  config, and it decides the answer on a grid (L=5: 37.7 at 0.5, 20.7 at 0.3). It is fast at funnel
  scale.
- **onc\*** (López de Prado 2019): k-means on the correlation-distance rows, the partition with the
  best silhouette quality. **\*Not judged by these numbers.** This is a simplified implementation
  (scipy's `kmeans2`, 10 restarts, without the method's recursive re-clustering step), and its
  failures (K=20 → 2.3; independent → 2) are more likely this implementation's than the method's.
  A faithful implementation would have to be built and re-measured before it could be compared.
  Independently of accuracy, its cost is measured: 227 s at 1,000 trials, which is impractical at
  11,000 without restricting it.

**What the choice does downstream (DSR).** SR₀, the expected maximum Sharpe of N_eff null trials
(Bailey & López de Prado 2014, eq. 1), in units of the trials' Sharpe standard deviation:

| scenario (truth) | avg_corr | participation | li_ji | mp | hier 0.5 | hier 0.3 | truth's SR₀ |
|---|---|---|---|---|---|---|---|
| K=20, ρ 0.7 | 2.05 | 2.15 | 2.46 | 1.90 | 1.90 | 1.90 | 1.90 |
| independent, 200 | 2.77 | 2.71 | 2.76 | **0.00** | 2.77 | 2.77 | 2.77 |
| grid L=5 (none) | 1.91 | 2.17 | 2.51 | 2.00 | 2.17 | 1.92 | — |
| nested (none) | 1.57 | 1.90 | 2.44 | 1.90 | 1.90 | 1.19 | — |

A higher SR₀ is a harder DSR bar. So an overcounting method is conservative, an undercounting one
is lenient. On the grid and nested cases the methods disagree by up to 0.7 standard deviations of
the trials' Sharpes.

**Options for P-97**, neutrally:
- (a) average correlation;
- (b) participation ratio;
- (c) Marchenko–Pastur factors with a rule for unexplained trials;
- (d) hierarchical average linkage with a configured correlation cut, and which cut;
- (e) a faithful ONC, to be implemented and measured first;
- (f) report several, with one named as the DSR input.

## 3. §7 (2) — the HAC lag rule and the bootstrap block length (F-7.1, P-98)

**HAC.** Size of the two-sided 5 % t-test of "mean = 0" on series whose mean is 0 (2,000
replications; nominal 5.0 %):

| process | T | no HAC | Newey–West 1994: ⌊4(T/100)^(2/9)⌋ | ⌊T^(1/4)⌋ | Andrews 1991 AR(1) plug-in |
|---|---|---|---|---|---|
| AR(1) φ 0 | 250 / 1,000 / 2,500 | 5.1 / 4.0 / 5.3 | 5.5 / 4.4 / 5.7 | 5.3 / 4.3 / 5.7 | 5.3 / 4.0 / 5.5 |
| AR(1) φ 0.1 | 250 / 1,000 / 2,500 | **7.3 / 6.7 / 8.5** | 5.9 / 4.7 / 5.8 | 6.0 / 4.7 / 5.8 | 5.9 / 4.7 / 5.9 |
| AR(1) φ 0.3 | 250 / 1,000 / 2,500 | **14.8 / 13.2 / 16.4** | 7.0 / 5.8 / 6.4 | 7.3 / 5.9 / 6.6 | 7.0 / 5.6 / 6.3 |
| GARCH(1,1) | 250 / 1,000 / 2,500 | 5.1 / 3.9 / 6.2 | 5.6 / 4.2 / 6.0 | 5.3 / 4.2 / 6.1 | 5.3 / 4.0 / 6.1 |

Median lags used at T = 250 / 1,000 / 2,500:
- Newey–West 1994: 4 / 6 / 8, whatever the data.
- ⌊T^(1/4)⌋: 3 / 5 / 7, whatever the data.
- Andrews: 1 / 1 / 1 without autocorrelation, 5 / 8 / 11 at φ 0.3. It adapts to the data.

**Every HAC rule removes the plain t-test's over-rejection** (16 % → about 6 % at φ 0.3). The three
rules differ by less than one point, and all over-reject a little at T = 250 with φ 0.3
(7.0–7.3 %). The library's HAC statistic equals `statsmodels`' `cov_type="HAC"` to 1e-12 at the
same lag (checked in the script).

**Bootstrap block length.** Coverage of the 95 % stationary-bootstrap percentile interval for the
**mean** and the **Sharpe ratio** (true values known; 400 series of T = 1,000, 499 resamples):

| process | i.i.d. (block 1) | T^(1/3) = 10 | Politis–White (`arch.optimal_block_length`) |
|---|---|---|---|
| AR(1) φ 0 | 93.5 / 93.8 | 93.0 / 93.0 | 94.2 / 94.5 (median block 1.3) |
| AR(1) φ 0.2 | **88.0 / 87.8** | 93.0 / 93.0 | 93.2 / 93.2 (median block 5.4) |
| GARCH(1,1) | 93.2 / 93.8 | 92.8 / 92.5 | 93.2 / 93.2 (median block 1.5) |

- **i.i.d. resampling under-covers with serial correlation** (88 % at φ 0.2).
- Both block rules hold 92.5–94.5 % everywhere.
- Politis–White adapts: it chooses a block near 1 when there is no dependence, and 5.4 at φ 0.2.
- All three sit slightly below 95 %, which is the percentile interval's known small-sample shortfall.
- `arch` also offers `bca` and `studentized` intervals (`conf_int(method=…)`); the interval method
  is part of the question.

**Options for P-98:**
- the HAC lag rule: Newey–West 1994, ⌊T^(1/4)⌋ or Andrews;
- the bootstrap scheme and block rule for Sharpe and expectancy: stationary or circular block,
  with a block of T^(1/3) or Politis–White;
- the interval method: percentile, `bca` or studentized;
- **for SPA** (§5): the benchmark and the block size, which `arch` requires the caller to choose.

## 4. §7 (3) — the CSCV partition count S (F-7.5, P-99)

PBO on T = 2,000 daily bars. **Noise** trials: the true answer is 0.5. **Planted**: one trial with a
real daily Sharpe of 0.1 (moderate) or 0.3 (strong); the answer is near 0 for a strong edge. 5 seeds
(2 at 5,000 trials); mean ± sd; seconds per call.

| trials | S (splits) | noise | planted 0.1 | planted 0.3 | seconds |
|---|---|---|---|---|---|
| 50 | 8 (70) / 10 (252) / 12 (924) / 16 (12,870) | 0.68 / 0.64 / 0.66 / 0.66 (sd 0.12–0.15) | 0.19 / 0.18 / 0.20 / 0.20 | 0.00 | 0.00 / 0.01 / 0.03 / 1.5 |
| 200 | same | 0.45 / 0.42 / 0.45 / 0.45 (sd 0.10–0.15) | 0.21 / 0.17 / 0.21 / 0.21 | 0.00 | 0.01 / 0.04 / 0.14 / 2.0 |
| 1,000 | same | 0.45 / 0.44 / 0.44 / 0.45 (sd 0.09–0.11) | 0.28 / 0.29 / 0.27 / 0.27 | 0.00 | 0.05 / 0.08 / 0.21 / 2.8 |
| 5,000 | same | 0.51 / 0.46 / 0.44 / 0.48 | 0.47 / 0.43 / 0.40 / — | 0.00 | 0.55 / 0.66 / 1.1 / 12.1 |

- **S barely moves PBO.** The noise mean is 0.42–0.68, and its spread across seeds (sd 0.1–0.15)
  is larger than any difference between S values. That spread comes from the data, not the split
  count: one noise matrix can read 0.3 or 0.7 at any S.
- **The trial count matters more than S.** A moderate real edge reads PBO 0.19 among 50 trials but
  0.40–0.47 among 5,000: it is drowned by the number of alternatives, the multiple-testing effect
  PBO exists to show. A strong edge reads 0 at every size.
- **Cost:** C(S, S/2) splits: 70 / 252 / 924 / 12,870. S = 16 costs about 12 s at 5,000 trials;
  S ≤ 12 costs about 1 s.
- Each block holds T / S bars: 250 at S = 8, 125 at S = 16 on these 2,000 bars. On a short 1D
  development window (about 1,500 bars) S = 16 leaves blocks of about 94 bars.

**Options for P-99 (a):** S = 8, 10, 12 or 16, or S chosen from T (a minimum block length in
bars). PBO carries no hyper-parameter as significant as its input set, which is the next point.

## 5. `arch` and what it constrains (§7 (4))

- **SPA takes losses** (lower is better) and **requires a benchmark series**. Returns are negated
  inside the library. Options for the benchmark: zero, meaning "better than not trading"; stage
  1's matched random-entry baseline; or the funnel's own best-before-selection. The benchmark is
  part of P-98.
- `SPA(..., block_size=None)` picks its own block; the library would pass it explicitly (P-98).
  `seed=` makes a run reproducible.
- `pvalues` comes back as a pandas Series (consistent, lower, upper); `optimal_block_length` as a
  DataFrame. Both are converted at the module edge.
- **Measured** (T = 1,000, 1,000 bootstrap reps, block 10):

  | models | null rejection (nominal 5 %) | power, one planted daily Sharpe 0.1 | seconds / call |
  |---|---|---|---|
  | 10 | 5.0 % (200 sims) | 69 % | 0.28 |
  | 100 | 10 % (50 sims, ±4) | 60 % | 0.5 |
  | 1,000 | 0 % (10 sims) | 30 % | 7.4 |

  At 10 models the size is on target. The 100- and 1,000-model null rows rest on 50 and 10
  simulations, **too few to judge size**, and the implementation's tests will measure them
  properly. Power falls as models are added: the same one planted edge is found 69 % of the time
  among 10, 30 % among 1,000.
- `arch` did not move the numba / numpy pins (D-659; #60 confirmed). **`scipy`** — the normal and
  t distributions and hierarchical clustering — **reaches the venv only through `arch` and
  `statsmodels`**; the library would import it directly (§8).

## 6. Reference values (task §5) — verified against the papers' text

| feature | reference | value | how verified |
|---|---|---|---|
| F-7.4 | Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*, "A numerical example": SR 2.5 annualized, N = 100, V[SR] = 0.5 (annualized), T = 1,250 daily (250 a year), skewness −3, **raw** kurtosis 10 | SR₀ = 0.1132 (non-annualized), **DSR = 0.9004**; at N = 46, **0.9505**; normal returns cross 0.95 at N = 88 | the text's printed "90 %", "0.9505" and "N=88" reproduced exactly; the inputs' glyphs did not survive text extraction, so N = 100 and V = 0.5 are **inferred** from those three results. The formula uses raw kurtosis (normal = 3) |
| F-7.7 | Bailey & López de Prado (2012), *The Sharpe Ratio Efficient Frontier*, §5 and appendix A.3 (the authors' code) | **MinTRL = 59.895 months = 4.99 years** (monthly SR 2/√12 vs 1/√12, skewness −0.72, kurtosis 5.78, 95 %); daily normal **2.73 y**, weekly **2.83 y**, monthly **3.24 y**; PSR at 59.895 obs = 0.95 | all five printed values reproduced exactly; the paper's own code confirms the formula |
| F-7.5 | Bailey, Borwein, López de Prado, Zhu (2017), CSCV | PBO ≈ 0.5 on noise (the task's test); the split count C(S, S/2) | property tests, as the task states (§4's table sets the tolerance: sd 0.1–0.15 per matrix) |
| F-7.1 | `statsmodels` (test oracle only) | t and HAC t equal to 1e-12 | as above |
| F-7.6 | `arch` | as §5 | size and power tests |

Sources: the two papers as published by D. H. Bailey (davidhbailey.com, `deflated-sharpe.pdf`,
`sharpe-frontier.pdf`), read on 2026-09-30.

## 7. The trial matrix — what feeds F-7.3 and F-7.5 (P-99 (b))

F-7.3 needs a **trials × time matrix of returns** and F-7.5 a **trials × time matrix of
performance**. The registry's `trials` table holds **metrics only** (params, the main metrics,
`extra`; design, the registry tables): it stores no return series. CLAUDE.md also forbids storing
full equity curves for every grid cell. So **today no stage can hand stage 7 the matrix these two
functions need.**

T16 builds the library with the matrix as its input either way. The question is for stage 7 (stream
A) and affects the library's shape:
- **(i) re-run the trials** that count (by `sfac reproduce`; the engine is deterministic, rule 8)
  at stage 7, only for the families behind the surviving candidates;
- **(ii) store a compact return series** per trial (for example daily P&L at 1D) for the stages
  that feed stage 7 — the size is about 11,000 × 1,500 × 8 bytes ≈ 130 MB per T14-sized run, and
  it needs a decision against the "no full curves for every cell" rule;
- **(iii) estimate N effective without returns** (from parameter distances or metric correlations)
  — the spec's "correlated results" could be read that way, but no measurement here supports it.

Also open: **which set is "the set"** for SPA and PBO — every trial of the funnel (thousands), the
candidates reaching stage 6, or one family's grid. §4 and §5 show both statistics depend strongly
on that count.

## 8. Requests outside stream B's paths (relayed through `docs/streams/B.md`)

- **`scipy` as a declared dependency** (`pyproject.toml`, stream A's, D-357), if the library imports
  it directly. It is already installed through `arch`; no version moves.
- **A third pending range for stream B:** `P-97 … P-99` are the last of `P-80 … P-99`. T16's
  questions are folded into those three rows until a range is granted.

## 9. Tests (task §5)

| feature | tests |
|---|---|
| F-7.1 | t and HAC t against `statsmodels`; interval coverage on simulated series at the nominal rate within §3's measured tolerance; determinism |
| F-7.2 | p uniform on the null (KS, a stated tolerance); `(1 + #) / (1 + n)` by hand |
| F-7.3 | N_eff ≤ N raw (Hypothesis); ≈ 1 on identical and ≈ N on independent trials; the planted-K scenarios for the chosen method within §2's measured tolerance |
| F-7.4 | §6's DSR example to 4 decimals (0.9004, 0.9505) and SR₀ = 0.1132 |
| F-7.5 | ≈ 0.5 on noise (averaged over seeds; §4's sd); 0 on a strong planted trial; split count = C(S, S/2) |
| F-7.6 | rejects a planted superior model; size near nominal on the null (enough simulations this time); determinism with `seed` |
| F-7.7 | §6's MinTRL values (59.895; 2.73 / 2.83 / 3.24 y); decreasing in SR (Hypothesis) |
| D-660 | the static import check; determinism of every seeded function |

## 10. Assumptions (in `pending.md` only where a decision is needed)

- Stage 7 itself (loading trials, applying the gate, reporting) is not T16's: it is a later stream-A
  task (the task file, §1).
- Kurtosis in DSR and MinTRL is **raw** (normal = 3), as both papers' formulas use; the result types
  say so.
- The permutation p-value takes the random-entry statistics as given; producing them is stage 1's
  matched baseline (F-1.4, which F-7.2 depends on), not this library's.
