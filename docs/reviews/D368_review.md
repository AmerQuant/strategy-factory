# D-368 — the metrics fixture, and the CI gap that hid it — review

Branch `a/D368-hypothesis-ci`, rebased onto `main` at `d2ebc6a` (after stream B's #28–#30). Stream A. Features: F-0.5.1 (the
metrics property), F-X.9 (the Hypothesis setup). Decision: **D-368** (the answer to P-44).

## 1. The fixture (D-368, part 1)

**The bug.** `tests/fixtures/metrics_runs.py` builds each random run's trades with a fixed
`entry_price = 1000` and `qty = 100` and derives `exit_price = 1000 ± pnl_gross / qty`.
`RunSpec.scaled(k)` multiplied the P&L and the costs but not the position, so scaling moved the
**price level** by `k` instead of growing the position — and a large enough `k` drove a derived
exit price to zero or below, which `TradeLog` refuses (`prices must be > 0`).

**The fix.** `RunSpec` carries `qty` (default 100) and `scaled(k)` multiplies it with the P&L and
the costs, so a scaled run is a `k`-times larger position at **unchanged prices**. `TradeLog`'s
"prices > 0" is a correct domain rule and is untouched. The bound that keeps unscaled prices
positive is now written next to the field: the largest move per unit is 13 bars × 3000 / 100 =
390, so every derived price stays in (610, 1390) at any `k`.

**The falsifying example, found rather than invented.** A random run of the property at its
per-PR budget did not find it on three seeds — which is the CI gap in miniature. A direct search
(`hypothesis.find`, 20,000 cases) found and shrank it: **k = 10**, and a short trade whose gross
P&L is exactly **+10,000** at qty 100, so the derived exit price was `1000 − 10·10,000/100 = 0`,
exactly the boundary. After the fix the same search finds **no** falsifying example in 20,000.

**Proofs** (each run under `HYPOTHESIS_PROFILE=ci` with no local example database — the
situation of a CI runner):

| check | result |
|---|---|
| the pinned examples pass with the fix | `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio` passes on both |
| **the pinned examples fail without it** (the `qty` scaling removed) | the property fails through **both** explicit examples with the original `TradeLog prices must be > 0`; the fixture test fails on both |
| **the property still fails when the metric is broken** — the fix did not make it unfalsifiable | profit made non-linear (`+ 1 USD`): **fails**; drawdown made non-linear (`** 1.01`): **fails**; the fixture test correctly stays green on both |

A new test, `test_F_0_5_1_scaling_grows_the_position_not_the_price_level`, pins what scaling
now means: every price unchanged, and quantity, gross P&L and commission exactly `k` times.

## 2. The CI gap (D-368, part 2 — the larger half)

The per-PR profile is derandomized and `.hypothesis/` is git-ignored (it stays so), so a
falsifying example found on a laptop never reaches CI. Two changes close it:

**Pinned examples.** Every example known to have falsified a property is an explicit `@example`
on its test, next to the property, where it runs under **any** profile:

- **2 examples are pinned** — `FOUND_P44` (the example Hypothesis found and shrank, verbatim)
  and `BOUNDARY_P44` (the same boundary in six bars, checkable by hand) — both on
  `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio`, and both also drive the fixture
  test above. These are all the falsifying examples known in this repository: P-44 is the only
  one ever reported, and a direct search for other price-domain breaks finds none (§3).

**The weekly job.** `.github/workflows/ci.yml` gains `weekly-hypothesis`:

| | |
|---|---|
| when | cron `0 4 * * 0` (Sunday 04:00 UTC), or by hand (`workflow_dispatch`); **never on a pull request**, so it gates no merge |
| what | every test file with a `@given` (11 files: property, oracle, leakage, unit), `-m "not slow and not db"` |
| how | profile **`weekly`**: randomized (`derandomize=False`), no example database, `print_blob=True` so a failure prints a `@reproduce_failure` blob |
| budget | `HYPOTHESIS_BUDGET_MULTIPLIER` = **40**, applied to every test (see below) |
| report | a failing run is red, and a job-summary step lists each falsifying example and blob with the instruction to pin it; no `continue-on-error`, which would hide the report |

**Why a budget multiplier and not just a profile.** A test's own `@settings(max_examples=...)`
overrides the active profile, and eleven tests set one — so a weekly profile alone would have
run those tests at their per-PR budgets, only randomized. Every budget now goes through
`fixtures.hypothesis_budget.examples(n)`, which is `n` per PR and on a laptop and `n × 40`
in the weekly job; the `weekly` profile multiplies the default budget too. A guard test fails if
any test sets a literal `max_examples`, so a new suite cannot quietly escape it.

`nightly-slow` is narrowed to its own cron, so the two schedules do not start each other's jobs.

**Measured on a GitHub runner before merge**, by dispatching the workflow on this branch (it ran
the job from the branch; nothing was merged):

| multiplier | tests | test time | job time | result |
|---|---|---|---|---|
| 10× | 126 passed | 9 min 33 s | 9 min 50 s | pass |
| **40×** (committed) | 126 passed | **29 min 53 s** | 30 min 13 s | pass |

The log of each run confirms the job ran the `weekly` profile with the stated multiplier. 40×
uses about a sixth of the job's 180-minute timeout, so the suite can grow before it matters.

**Cost, for the account holder.** The job adds about 30 runner-minutes a week, ~120–150 a month,
on top of the ~4 minutes each push already costs. GitHub Actions is free for public repositories;
a private one draws on the account's monthly minutes (Settings → Billing and plans). Setting the
multiplier back to 10 cuts the job to ~10 minutes a week — one line in `ci.yml`.

## 3. The sweep (D-368, part 3)

Every Hypothesis suite, read for a generator or transformation whose derived prices or
quantities can leave their domain:

| suite | how it builds prices / quantities | verdict |
|---|---|---|
| `metrics_runs.RunSpec.scaled` | fixed entry, exit derived from P&L / qty | **the bug — fixed** |
| `metrics_runs.RunSpec.with_extra_cost` | adds cost; gross P&L, hence prices, unchanged | safe |
| `metrics_runs.trade_log` (hand fixtures, `rising_run`) | derives exit prices from fixed, small P&L | safe (no transformation) |
| engine / oracle `random_case` | log-normal walk; fills `base ± ≤ 0.05 + 0.02 + 0.1·ATR` | safe by construction |
| engine long/short mirror | `p → K − p`, `K = 2·max(high) + 10` | safe by construction |
| engine costs-monotonic | bumps ≤ 0.5 on prices ≈ 100; checks `SimResult`, not `TradeLog` | safe |
| indicator edges mirror | `p → K − p`, `K = 4·max(high)` | safe by construction |
| indicator edges `random_bars` low | min(o, c) · (1 − \|N(0, vol/2)\|), `vol ≤ 0.03` | **safe in practice, not by construction** — negative needs a draw beyond ~66σ. Noted, not changed. |
| naive indicators `ohlc()` | prices ≥ 1, extension ≤ 5 % | safe by construction |
| resample leakage | log-normal; later bars × U(0.5, 1.5) | safe by construction |
| costs / moneta / split | cost parameters, dates — no derived prices | not applicable |

Nothing else is in scope to fix and nothing needs raising. The empirical check agrees: the
weekly profile run randomized over all eleven files — at 5× locally, and at 10× and 40× on a
GitHub runner (§2) — finds no failure in any property. (The 5× local trial did fail two tests:
both were the new guard tests themselves — the literal-budget guard caught its own docstring,
and the workflow still carried a placeholder multiplier. Both fixed before the runner runs.)

## 4. Files

| file | change |
|---|---|
| `tests/fixtures/metrics_runs.py` | `RunSpec.qty`; `scaled(k)` grows the position |
| `tests/property/test_F_0_5_metrics_properties.py` | the two pinned examples; the fixture test |
| `tests/fixtures/hypothesis_budget.py` | **new** — `examples(n)`, the weekly multiplier |
| `tests/conftest.py` | the `weekly` profile |
| `tests/property/test_F_X_9_hypothesis_setup.py` | guards: the profiles, no literal budgets, the multiplier, the workflow's weekly job |
| 9 test files | `max_examples=N` → `max_examples=examples(N)` (11 call sites) |
| `.github/workflows/ci.yml` | the `weekly-hypothesis` job; `nightly-slow` on its own cron |

Dependencies: none added. The workflow change needs the `workflow` token scope, which the user
granted.

## 5. How each part is tested

| requirement | test |
|---|---|
| scaling grows the position, prices unchanged | `test_F_0_5_1_scaling_grows_the_position_not_the_price_level` ×2 |
| the falsifying example (k = 10) passes | `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio` via `@example` |
| the pins catch the old bug under the CI profile | checked by mutation (§1), not a committed test |
| the property still catches a broken metric | checked by two mutations (§1) |
| per-PR profile derandomized, weekly randomized, no DB, blob printed | `test_F_X_9_d368_the_per_pr_profile_is_derandomized_and_the_weekly_one_is_not` |
| no test escapes the weekly budget | `test_F_X_9_d368_every_budget_goes_through_examples` |
| the multiplier: 1 by default, refuses < 1 | `test_F_X_9_d368_the_budget_multiplier` |
| the weekly job is scheduled, randomized, multiplied, and gates nothing | `test_F_X_9_d368_the_weekly_job_is_scheduled_and_does_not_gate` |

## 6. Acceptance

```
uv run pytest -m "not slow"                                       1459 passed, 0 skipped
HYPOTHESIS_PROFILE=ci uv run pytest tests/parity tests/leakage tests/oracle tests/property
                                                                   359 passed
uv run pytest -m db                                                21 passed, 0 skipped
uv run ruff check . / ruff format --check . / mypy src             clean
uv run sfac streams check --base origin/main                       all three guards ok
weekly-hypothesis on a GitHub runner, 40x                          126 passed in 29 min 53 s
```
