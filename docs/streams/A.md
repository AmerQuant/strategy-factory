# Stream A — main folder

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory` (the repository's main worktree).
Governed by **D-355** and **D-357**; the full rules are in `docs/streams/PROTOCOL.md` and the
path ownership in `docs/streams/ownership.yaml`. This file is stream A's status; `HANDOFF.md`
(v10, 2026-09-29) is written **only by stream A**, at merges, from this file and
`docs/streams/B.md`. From D-802 on, this file lives on `main`.

New branches here carry the **`a/`** prefix. Run the guards locally with
`uv run sfac streams check --base origin/main`.

> **Open gap — do not read it as closed.** The parity `to_verify` ledger is at **3 of 5**.
> **D-335** (the stop-first branch and exact tie of the TradingView intrabar path) and **D-336**
> (exit and re-entry at one open) are **unverified against TradingView**. Their reference,
> **T11b, is parked (D-802)** because the user is not exporting for now. D-336 is also the
> research default, so if T11b later shows an engine difference, **research results produced in
> the meantime may need re-running** (found by `code_version`, D-352). Every stage review until
> then states this.

## Where to start (a fresh session)

1. **Session check** (D-357 (1)): `uv run sfac streams session --stream A`. Omit `--stream` if
   you are a spawned or helper session — and then you need your **own** worktree.
2. Read `HANDOFF.md` (v10) and this file; for stage work also `docs/streams/B_data_state.md`,
   `docs/reviews/T12_review.md` (stage 1), `docs/reviews/T13_review.md` (stage 2) and `docs/reviews/T14_review.md` (stage 3).
3. Work branches start from `origin/main`. Obsolete stream-A branches (listed under "Open")
   are not deleted without the supervisor's word.
4. If `git worktree list` shows scratch entries under `AppData\Local\Temp\claude\…`, run
   `git worktree prune`. `StrategyFactory_dl` (detached) is not stream A's; leave it.

## Scope

1. Batch 2b, **T11** (#26), **D-368** (#31) — **merged**.
2. **T11b** — **parked (D-802)**; the plan stands in `docs/tasks/T11b_parity_tie_reentry.md`.
3. Stream and CI tooling — D-611/D-612 ownership, D-377 encodings, D-378 range, D-379 UTF-8
   output, D-800 Windows job, D-801 one `checks` run per PR update, D-806 pinned runners —
   **merged** (#33 … #43, #48).
4. **T12 — stage 1, edge discovery** (critical, D-402) — ✅ **merged (#47)**.
5. **T13 — stage 2, method screening** — ✅ **merged (#51)**.
6. **T14 — stage 3, entry optimisation** — ✅ **merged (#54 plan, #55 stage)**.
7. **Next: the next task waits for its task file.** As for T12 … T14, the supervisor and the user
   settle the design in chat first; until the task file arrives stream A neither plans nor
   starts it.

## ID ranges (D-355, D-378)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 (used up) and D-600 … D-699 | — |
| **stream A (this one)** | **D-360 … D-379** (used up) **and D-800 … D-899** | **P-40 … P-59** (used up) **and P-100 … P-149** (D-803) |
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 (used up) and P-80 … P-99 |

Stream A has used **D-360 … D-379**, **D-800 … D-807**, **P-40 … P-59** and **P-100 … P-133**;
all answered — **stream A has no open question** (P-124 … P-133 → D-662 … D-671). **Next free here: D-808, P-135** (P-134 is on the T15a branch). Supervisor
rows written by stream A: D-601 … D-656 and D-662 … D-671 (D-651 (1) amended on the T14 review;
D-652 … D-656 from the T15a task file, D-662 … D-671 its plan's answers; **D-657 … D-661 are
assigned elsewhere**: D-657, D-661 to stream B's T04j, D-658 … D-660 to T16); **next free
supervisor id D-672**. Everything through D-651 and D-807 is on `main` (#54, #55).

## Rules that bind this stream (D-355, D-357)

- **One worktree, one session** (D-357 (1), amended): every session, spawned or helper included,
  works in its own git worktree on its own branch, and **never switches the checkout of a folder
  it does not own**.
- **No messages to stream B's session.** Cross-stream communication goes through these status
  files and the supervisor — put anything for stream B in the section below.
- **Database:** `.env` here points at `sfac` on the shared Postgres (port 5433, D-305).
  Stream B uses `sfac_b`. Never point this `.env` at stream B's database. A new worktree needs a
  copy of `.env` (it is git-ignored).
- **Data root:** **stream A does not write to `SFAC_DATA_ROOT`.** Stream A reads the store and
  reads `SFAC_RAW_ROOT` read-only (D-028, rule 11). Stage artifacts go to `SFAC_ARTIFACTS_ROOT`
  (`D:/SfacData/artifacts`). The one store exception so far: `manifest.json` in the parity
  reference folder, written by `scripts/write_parity_manifest.ps1` on the supervisor's
  instruction.
- **`configs/universe.yaml` is stream A's (D-394).** After a stream-B merge that moves a symbol,
  run `sfac universe generate`.
- **Docs:** decision and pending edits go on stream A's own branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**, one row
  per ID (the most-resolved version wins). A row may be **amended in place** only within stream
  A's ranges or the supervisor's, never deleted (D-369).
- **Measure before proposing** (the T13 plan's method): a grid, a gate or a threshold is checked
  on real data **and on the D-615 control** before it is proposed; the control is what exposed the
  drift in T13's first gate (D-629).
- **Guard tests are mutation-checked against the real file**: break the thing on its real shape
  and watch the test fail before claiming the test catches it.
- **Mirror rule (D-626, D-632):** a short is the long rule on `Bars.mirrored()` (`p → −p`). Ratio
  rules must be written in the `|ref|` form (`x < ref − f·|ref|`) or their mirror breaks — Connors
  RSI's ROC did, and the engine-truncation gate's vacuity check (F-0.3.9) caught it.
- **Rule-definition constants (D-638):** the fixed parts of a rule's definition (MACD 12/26/9,
  Connors 2/100, stochastic smoothing, KAMA 2/30, the user rules' ATR 5/10) may be class constants;
  rule 1 governs thresholds, weights and free parameters.
- **Runner images are pinned (D-806).** `ubuntu-24.04` and `windows-2025`; no job may use a
  `-latest` label (`tests/unit/test_F_X_9_pinned_runners.py`). Moving a pin is its own decision.
- **Encodings (D-377, D-379):** every text-mode subprocess and file access passes `encoding=`;
  the static guard fails otherwise. After a change to the `sfac` entry point, run `uv sync`.
  PowerShell scripts written from now on set `[Console]::OutputEncoding` to UTF-8 before
  calling `sfac`.
- **A file committed "unchanged" must be byte-identical**: the repository normalises text to LF
  (`* text=auto eol=lf`), so a CRLF original needs a `-text` rule in `.gitattributes` (done for
  `tools/tradingview/user_mr_suite.pine`, as D-359 does for the parity fixtures).
- **Benchmarks** run only when stream B is idle — they take every core.
- Every branch **rebases onto `main`** right before its merge; merges one at a time. D-401 and
  D-402 unchanged.
- **The venv can break silently.** If `mypy` suddenly reports `Failed to find builtin module
  "mypy_extensions"` or a wall of pydantic `import-untyped` errors: `uv sync --reinstall`.

## Status — 2026-09-30 (the T15a acceptance queue is paused)

**Supervisor range (D-677, 2026-10-03): only stream A writes D-600 … D-699** (and the used-up D-355 … D-359); the guard refuses rows added or amended there on `b/` branches. **D-678:** `api/`, `ui/` and `B_ui.md` are stream B's (its UI session, `StrategyFactory_UI`, **D-760 … D-799**; D-678 amended); FastAPI, uvicorn and `sse-starlette` (the user's choice) are dependencies. #62 merged D-676 (P-150 … P-199 to stream B; `scipy`). **D-679:** within stream B, `b/ui-…` branches write D-760 … D-799 and the other `b/` branches D-700 … D-759 (enforced in CI). Next free supervisor id: **D-680** (D-675 waits for the T15a rebase).

**T15a is paused mid-acceptance so the user can use the machine; this folder stays on
`a/T15a-orchestrator`, untouched, until the resumed queue is done.** The implementation, the report
and the acceptance review's fixes are on `a/T15a-orchestrator` (pushed); the pilot's code version is
pinned by `a/T15a-pilot-code`. The acceptance funnels run in the helper worktree
`../StrategyFactory_T15a_runs` (branch `a/T15a-runs`, clean at `cc7f73a`) so every stage run records
one clean code version.

**Stage runs complete and reusable** (registry `funnel_stage_runs`, all `done`):

| funnel | id | state |
|---|---|---|
| planted | `e4b3e66b-2b37-460f-a48f-9d811bd23588` | **done** -- all 12 stage runs (1D, 1H x 3 stages x 2 arms); report built |
| null, seed 1 | `70d46a07-ceee-45e7-b124-48d51d4fe551` | **done** -- all 12; report built (1D 4 of 490 = 0.82 %, 1H 1 of 371) |
| real (MVP) | `9f26a370-0755-426d-9da8-5be19248e55f` | **failed (interrupted), resumable**: the 6 1D stage runs are `done` and are reused by the resume; 1H s01 real was interrupted -- its stage row is `failed` and its pipeline run `66adeb49…` is `aborted` (the resume re-runs it under a new run id; the partial folder `<artifacts>/66adeb49…` is an orphan, never read) |
| null, seed 2 | -- | not started |
| null, seed 3 | -- | not started |

A `running` stage row is never accepted as complete (resume reuses only `done` rows under the same
`stage_key`). **The resume command** (the user runs it, unattended; it resumes the real funnel, then
null 2 and null 3 -- planted and null 1 are complete and are not re-run):

```powershell
Set-Location D:\AmerAndish\Projects\Trade\StrategyFactory_T15a_runs; $env:PYTHONIOENCODING='utf-8'; $log='D:\SfacData\artifacts\funnels\T15a_acceptance_resume.log'; foreach ($c in 'mvp','null_seed2','null_seed3') { "== $c $(Get-Date -Format u)" | Out-File -Append -Encoding utf8 $log; uv run sfac funnel run "configs/funnel/$c.yaml" --workers 6 --notes "T15a acceptance: $c" 2>&1 | Out-File -Append -Encoding utf8 $log; "== $c exit $LASTEXITCODE $(Get-Date -Format u)" | Out-File -Append -Encoding utf8 $log }
```

**On rebasing `a/T15a-orchestrator` onto `main` (after the queue):** stream B's #61 took **D-673**
(the bounded OHLC repair, already written into store snapshot notes); **stream A's P-134 answer is
renumbered to D-675** (the user's choice, relayed in `docs/streams/B.md`); every reference in the
T15a documents moves with it. **D-676** grants stream B `P-150 … P-199` (PR `a/stream-b-pending-scipy`).

## Status — 2026-09-29

**T15a plan approved (2026-09-29); P-124 … P-133 answered as D-662 … D-671** (all as proposed; the
user decided Latin digits). Plan `docs/tasks/T15a_plan.md`, runbook `docs/tasks/RUNBOOK_T15a.md`.
Headline, in two parts (D-671): **stage 1 admits noise** — the calibrated null reaches the end of
stage 3 on 1.23 % of daily symbols (6 of 486) against the real 0.41 % (2 of 486) — **and misses real
edges** — a planted MR edge on every symbol is found 0 % of the time at 1 ATR and 40 % at 3 ATR, TF
3–10 %; the reshuffled control's zeros understated the false-positive rate (ATR 17–30 % too high).
Next: the T16 preparatory PR (stream B waits on it), then T15a's implementation to the planted pilot.

**T14 is merged (#54 plan, #55 stage; merge commit `85870be`). Stream A has nothing open and waits
for the next task file.** `main` is at `85870be` plus this status (HANDOFF v10).

### T14 — stage 3, entry optimisation (#54, #55)

Task file `docs/tasks/T14_stage3_entry_optimisation.md`, plan `docs/tasks/T14_plan.md` (132,408
measured runs, with an erratum), pilot `docs/reviews/T14_pilot.md`, review
`docs/reviews/T14_review.md` (the PR body). Decisions **D-639 … D-651** (D-651 (1) amended) and
**D-807**. Approved on 2026-09-29.

| run (committed tree `effba41`) | run id | candidates | cells | pass |
|---|---|---|---|---|
| 1D | `f72b80ee…` | 25 | 5,383 | **2** |
| 1H (`unconfirmed`) | `ce348ae8…` | 6 | 5,651 | **4** |
| **1D control** (D-644) | `0a4fb887…` | 25 | 5,383 | **0** |
| **1H control** | `9d37799d…` | 6 | 5,651 | **0** |

- **The control passes nothing.** Its two nearest misses (MSFT `mr_ibs_after_new_high`, TMUS
  `mr_williams_confirm`, both drift longs) fail on plateau area alone.
- **The passes:** 1D **SHW** long `mr_connors_rsi` and **TXN** long `mr_ema_slope_drop` (a
  boundary pass at plateau 0.100; costs moved its plateau 11 steps — D-642's example); 1H ARKK
  `tf_base_candle`, BAC `tf_keltner_breakout`, TSLA `tf_hma_turn` and `tf_ichimoku` (`unconfirmed`;
  the two TSLA ones overlap 0.64). **No short passes.** Stage 4 reads the passing
  `EntryOptimisation` artifacts of `f72b80ee…` (1D) and `ce348ae8…` (1H).
- **D-651 (1), amended:** 21 of 31 real and 9 of 31 control meet the stability threshold, and no
  candidate fails on it alone — it decides no verdict. The plan had printed 24 / 22: polars counts
  `NaN >= 0.8` as true. **Any count behind a decision is computed so that NaN cannot pass**
  (`gates.engine.count_meeting`, tested).
- **D-807:** the stage-3 candidate id hashes the trade minimum (whole and per half) and the plateau
  cut; the full scope and the control were re-run and are unchanged apart from the ids.
- The eight small grids (seven of 3 cells, EEM's 9) all fail; stage 3 can only accept or reject
  their stage-2 parameter (D-648). MRNA 1H `tf_ichimoku` has no cell at 100 trades per half (D-647).
- Built: `stages/optimize*.py`, `metrics/plateau.py`, `robustness/spp.py`, the `EntryOptimisation`
  artifact (surfaces as data, axes as an ordered list), `method_run` segments (stage 2 unchanged),
  `CostArrays.segment`, `plateau_cells >= 3` in the gates, `sfac run` for `s03_entry`. No engine
  change, no new dependency.
- Acceptance on Windows: fast **2,534**, parity/leakage/oracle **869**, db **24 / 0 skipped**, slow
  **20**, ruff, format, mypy (both platforms), stream guards; CI green on #54 and #55. The
  acceptance reviewer recomputed all 62 artifacts (0 mismatches); its findings are fixed (review
  §12).
- Commit `caf74be` carries a byte-order mark in its subject line, left as it is (review §14).

> **The repository is public since 2026-09-28.** Everything pushed here is public immediately,
> and going private again would not undo it. **Turn on secret scanning and push protection** —
> free for public repositories, and it scans the history retroactively. The pre-public audit of
> the whole history (2026-09-27) found no secret ever committed and no workflow that could expose
> one (details: `HANDOFF.md` §7 and this file's history at `ac20c9c`).

### T13 — stage 2, method screening (#51)

Plan `docs/tasks/T13_plan.md` (measured on real data and on the control before proposing), pilot
`docs/reviews/T13_pilot.md`, review `docs/reviews/T13_review.md` (the PR body). Decisions
**D-622 … D-638**. Approved on 2026-09-29.

| run (committed tree `b71563a`) | run id | profiles | methods / cells | pass the gate | selected |
|---|---|---|---|---|---|
| 1D | `dea1d423…` | 14 | 280 / 4,256 | 25 | **25** |
| 1H (`unconfirmed`, D-621) | `6025ef15…` | 4 | 60 / 1,008 | 6 | **6** |
| **1D control** (D-615) | `dd27baf5…` | 14 | 280 / 4,256 | **0** | 0 |
| **1H control** | `ae578471…` | 4 | 60 / 1,008 | **0** | 0 |

- **The control first:** 0 methods pass; **45 daily and 11 hourly methods clear every other
  criterion** on the permuted series and are stopped only by `method_q_value` (D-629: the
  good-region median cell against its matched baseline, BH within the profile). The gate as first
  specified had no comparison with chance and passed 43 of 266 in the plan's measurement.
- **11 of 14 daily profiles and all 4 hourly ones end with fewer than 3 candidates** (D-625):
  mean-reversion methods with the fixed 5-bar exit hold the same bars, and D-637 counts a nested
  method as overlapping. 111 daily methods passed every criterion but the overlap.
- **22 of the 31 selections are the user's rules** (`mr_macd_hist_falling` #17 and `mr_n_day_low`
  #5 on four profiles each). **ETN long keeps one method at q 0.092**, at the threshold.
- Costs take a third to three quarters of the daily edge (after-cost grid medians 40–70 % of
  the zero-cost ones on the selected methods), and every selected method stays positive.
- What was built: 35 stage-2 methods (20 MR, 15 TF; dual momentum deferred, D-635), the 2–4
  values grid rule (D-630), `metrics/family.py` (family score, good region, weighted rank-sum,
  overlap, diversity walk), `stages/screen.py` (`s02_screen`), the `MethodScreen` artifact
  (stage 3's input), `stage_inputs` in `PipelineConfig` (old hashes unchanged, 34/34
  recomputed), `sfac run` for `s02_screen`. The engine is untouched; no new dependency.
- Acceptance on Windows: fast suite **2,464**, parity/leakage/oracle **858**, db **23 / 0 skipped**,
  slow **20**, ruff, format, mypy (both platforms), stream guards — all green; the acceptance
  reviewer recomputed every number (0 mismatches) and its findings are fixed (review §11).

### T12 — stage 1 (#47), in one paragraph

14 of 1,944 daily profiles pass against 0 on the control, all short-horizon mean reversion on
large US names; on 1H, 4 passes against 1 on the control, treated as `unconfirmed` (D-621). The
review is `docs/reviews/T12_review.md`; its §6 is T15's calibration list, carried below. T12's
evidence runs predate D-805 and are **not re-run** (T15 re-runs the full scope anyway).

### Open, and on whom

- **T15a**: paused mid-acceptance (above); the prerequisite PRs for stream B run meanwhile from
  the helper worktree `../StrategyFactory_A_prereq`, one at a time.
- **Deferred by the user: speed optimisation of the funnel**, until the project is finished
  (2026-09-30). The P-104 executor timings (D-667) are T15b's.
- **On the user: turn on secret scanning and push protection** (the repository is public).
- **T11b, P-50** — parked (D-802); they resume when the user exports.
- **Obsolete branches (2026-09-29, the user's word):** deleted locally and on origin, each checked
  fully merged into `main` first — `a/stream-a-status`, `a/stream-a-idle-t13`, `a/T13-plan`
  (ancestors of `main`) and `a/docs-T12-plan` (its one commit is patch-identical to `6943204` on
  `main`).
- **Two branches with unmerged commits, deleted on the user's explicit approval (2026-09-29)**,
  locally and on origin: `a/fix-metrics-fixture-prices` (tip `91ea691`, one commit of 2026-09-20:
  a fixture fix that scales prices — superseded by D-368's `qty` fix in #31, never merged) and
  `a/T11b-parity-tie` (tip `9a2c335`, seven A.md status commits of 2026-09-21/22, superseded by
  the A.md on `main`). **The user approved losing that unmerged work.** When T11b resumes it starts
  from a fresh branch off `main`; its plan stays in `docs/tasks/T11b_parity_tie_reentry.md`.
- **Merged branches** `a/stream-a-status-t13` (#52), `a/stream-a-branch-cleanup` (#53),
  `a/T14-plan` (#54), `a/T14-entry-optimisation` (#55) and `a/stream-a-status-t14` (#56): the user
  approved deleting them (2026-09-29); they were already gone locally and on origin (deleted at
  their merges).

### What T15 must calibrate

From T12 (review §6):

1. **The magnitude target of 0.10 ATR is too generous** — the primary target. Magnitude carries
   11.0 of 30 ESS points on 1D against 3.9 of 20 for significance, and the **control** earns 8.05
   magnitude points with 31 control profiles above ESS 50.
2. **TF on 1D is near-unpassable**: in 46 % of TF profiles fewer than 3 groups have any probe
   with enough trades. Four probes are limited by the 50-bar exit, two by signal frequency — so
   the exits and the threshold need different answers.
3. **The disaster stop is a primary exit for TF** (median 32 % of trades on 1D, 37 % on 1H,
   against D-130's 2 %, which was written for an optimised exit).
4. **Two band/channel probes are the same rule** (`close_below_bb_lower` ≡ `zscore_below_minus_2`,
   identical in 972/972 profiles): it double-weights one rule in the ESS medians and inflates the
   trial count. It does **not** inflate breadth. (Stage 2 already keeps only the z-score form.)
5. **The reshuffled-returns control is conservative** (its percentiles average 28–46, not 50), so
   its 0–1 passes are a **lower bound**; the calibrated null is the synthetic random walk.
6. **Residual biases after D-618** (TF short slightly high, MR short low on synthetic data).
7. **P-104:** whether the executor's `auto` budget should discount efficiency cores and
   hyper-threads (D-621 (2)).

From T13 (supervisor, 2026-09-29):

8. **11 of 14 daily profiles below three candidates** (and 4 of 4 hourly): partly the fixed
   5-bar exit (D-622, D-637) — the MR methods hold the same bars; re-measure once stage 4 frees
   the exits.
9. **Cleanup of private cross-module helpers** (T13 review §8 item 16): `stages/screen.py` uses
   stage 1's `_cost_arrays` and `_require_research_engine` (whose message still says "stage 1"),
   and `components/entries/methods_tf.py` imports the MR module's parameter helpers.
10. **T13's family-score constants** (D-636: median target 1.0, excess target 0.10 ATR,
    consistency floor 0.5, 5 trades per year) are provisional like D-606's.

From T14 (D-651, review §3, §6):

11. **The stability threshold may be redundant**: in the full runs no candidate, real or control,
    fails on stability alone; the half-2 check (20 real vs 6 control) and plateau area do the gate's
    work (corrected numbers, P-122).
12. **3-cell grids cannot be optimised** (D-648): stage 3 only accepts or rejects their stage-2
    parameter; and MRNA 1H `tf_ichimoku` has no cell at 100 trades per half (D-647).

From T15a's plan (D-671; `docs/tasks/T15a_plan.md` §1–§4). **Stage 1 both admits noise and misses
real edges, so T15b is a redesign of how stage 1 decides, not only a tuning of thresholds.**

13. **1H stage 1 is not calibrated on a random walk** with the real session profile: null
    percentiles 52–61 (MR short 57–61 / 17 % at or above 90) — the matched baseline ignores
    intraday timing; the null's 7 hourly stage-1 passes are all TF long, like the 4 real ones.
14. **The reshuffled-returns control distorts bar shape** (gap variance 1.3–1.7× the return
    variance, ATR 17–30 % too high) and passes 0 at every stage where the calibrated null passes
    15 / 27 / 7 on 1D: the stage reviews' headline, not the calibration target.
15. **Stage 1 admits noise:** the calibrated null reaches the end of stage 3 on **1.23 % of daily
    symbols (6 of 486)** against the real 0.41 % (2 of 486); stage 1 passes the null at the real
    rate (15 vs 14 profiles); stage 3 passes 26–31 % of null candidates against 8 % of real ones.
16. **Stage 1 misses real edges:** a planted MR edge present on every symbol from 1 ATR is found
    0 % of the time at 1 ATR and 40 % at 3 ATR; a planted TF edge 3–10 % of the time.

### For stream B (relayed by the supervisor — D-357, no direct messages)

- **D-377 is on `main` (#38).** A new text-mode `subprocess` call or text file access without
  `encoding=` fails CI (a positional `read_text("utf-8")` counts as declared). **Three existing
  sites in your paths are exempted for you to fix**; remove each one's `ALLOWED` entry in
  `tests/unit/test_F_X_9_explicit_encoding.py` in the same change (a stale entry fails):
  `src/strategy_factory/data/download/dukascopy.py:166`, `tests/unit/test_F_0_1_3_dukascopy.py:229`,
  `scripts/analysis/T04f_symbol_change_evidence.py:238`.
- **D-379 (#41) is merged:** the `sfac` entry point is `strategy_factory.cli:run`. **Run
  `uv sync`** in your worktree after rebasing so the installed `sfac` is regenerated.
- **D-800 / D-801 (#42, #43):** a `windows-fast` job runs the fast suite on every PR, yours
  included; `checks` no longer runs on pushes to non-`main` branches, so open a PR to get CI.
- **D-378 (#40):** **D-800 … D-899 is stream A's**; `docs/streams/B.md`'s ID table still shows
  stream A with D-360 … D-379 only.
- **D-611 / D-612:** `configs/gates/`, `metrics/`, `stages/`, `baseline/`, `components/`,
  `configs/stages/` are stream A's paths. **T13 (#51)** added `method_q_value` to the gates,
  `PipelineConfig.stage_inputs` (a new optional field; existing configs and hashes unchanged) and
  the D-630 grid rule (2–4 values per parameter) in `components/base.py`. **T14 (#55)** added
  `plateau_cells` to the gates, `CostArrays.segment` in `costs/arrays.py` (shared) and
  `gates.engine.count_meeting` (shared): **any count behind a decision uses it** so NaN cannot
  pass a comparison (D-651 (1)) — this binds stream B's analyses too.

### Next actions, in order

1. **The next task** — wait for the supervisor's task file; then plan (D-403), measuring on real
   data and on the control before proposing, and stop for "Plan approved". Stage 4 would read the
   passing `EntryOptimisation` artifacts of `f72b80ee…` (1D) and `ce348ae8…` (1H).
2. **Next free ids:** D-808, P-134 (stream A); supervisor D-672.
3. `configs/universe.yaml` — no stream-B merge since #45/#46 moved a traded symbol, so D-394 owes
   no regeneration.
4. **T11b** when the user exports (D-802). **T15b** owns the calibration list above (16 items; D-652, D-671).
