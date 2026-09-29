# Stream A — main folder

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory` (the repository's main worktree).
Governed by **D-355** and **D-357**; the full rules are in `docs/streams/PROTOCOL.md` and the
path ownership in `docs/streams/ownership.yaml`. This file is stream A's status; `HANDOFF.md`
(v9, 2026-09-29) is written **only by stream A**, at merges, from this file and
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
2. Read `HANDOFF.md` (v9) and this file; for stage work also `docs/streams/B_data_state.md`,
   `docs/reviews/T12_review.md` (stage 1) and `docs/reviews/T13_review.md` (stage 2).
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
6. **T14, stage 3 (entry optimisation)** — plan approved (D-646 … D-651); built, piloted;
   **stopped at the pilot's numbers** (branch `a/T14-entry-optimisation`, stacked on `a/T14-plan`).

## ID ranges (D-355, D-378)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 (used up) and D-600 … D-699 | — |
| **stream A (this one)** | **D-360 … D-379** (used up) **and D-800 … D-899** | **P-40 … P-59** (used up) **and P-100 … P-149** (D-803) |
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 (used up) and P-80 … P-99 |

Stream A has used **D-360 … D-379**, **D-800 … D-806**, **P-40 … P-59** and **P-100 … P-121**,
all answered — **stream A has no open question**. **Next free here: D-807, P-122.** Supervisor
rows written by stream A: D-601 … D-651; **next free supervisor id D-652**. D-639 … D-651 are on
`a/T14-plan`, not yet on `main`.

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

## Status — 2026-09-29

**T14 is built and piloted; stream A is stopped at the pilot's numbers** (T14 §8) and waits for
the word to run the full scope and its control. `main` is at `ee01cde` (#53 merged). Branches:
`a/T14-plan` (task file, plan, D-639 … D-651) and `a/T14-entry-optimisation` stacked on it, both
pushed, no PR yet.

### T14 — the pilot (2026-09-29, `docs/reviews/T14_pilot.md`)

Code `56d78b9` (clean). 1D MSFT + TXN (8 candidates) and 1H BAC (1), each run twice:
**identical**, and **equal to the plan's measurement on all 9** (selected cell, plateau, stability,
verdict). **2 of 9 pass**: TXN long `mr_ema_slope_drop` (plateau exactly 0.100, costs moved it 11
steps) and BAC 1H `tf_keltner_breakout` (`unconfirmed`). The three 3-cell grids all fail (D-648).
Full scope projected at about 2 minutes for all four runs. A test caught an artifact defect (axis
order lost to sorted JSON keys); fixed. Fast suite 2,530, parity/leakage/oracle 869, db 24 / 0
skipped, ruff, format, mypy (both platforms), stream guards green.

### T14 — stage 3, the plan (2026-09-29)

Task file `docs/tasks/T14_stage3_entry_optimisation.md` (supervisor's, committed as delivered),
D-639 … D-645 recorded (section I-S3), plan `docs/tasks/T14_plan.md`, runbook
`docs/tasks/RUNBOOK_T14.md`, questions **P-116 … P-121**. Measured on the 31 stage-2 selections
and their reshuffled-returns control (132,408 runs, 1 min 42 s;
`scripts/analysis/T14_plan_measure.py`, `T14_plan_analyse.py`):

- **Under the proposals: 9 real passes, 0 on the control** (6 real with P-118). All nine are long;
  4 are the 1H `unconfirmed` TF candidates. Stability ratio does not discriminate (22 of 31 control
  candidates meet it); plateau area and the half-2 check do.
- **P-117 (per-half minimum):** half strength lets **one control candidate pass** (MSFT long
  `mr_ibs_after_new_high`) — a D-644 stop; full strength gives 0 but leaves MRNA 1H ichimoku no
  valid cell.
- **P-116 (failed cells):** "the grid's worst value" passes TMUS `mr_n_day_low` with 20 of 21
  half-1 cells failed; proposed min(worst, 0).
- **P-118:** 8 fine grids below 10 cells (7 of them 3 cells); 3 passes rest on one- or two-cell
  plateaus; proposed `min_plateau_cells` 3.
- **P-119:** only the two 1H ichimoku grids exceed 2,000; Sobol has no lattice neighbours, so the
  plan coarsens the lattice (amends D-639's last clause).

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

- **T14 waits for the word on the pilot** (then the full run, the control, the review).
- **On the user: turn on secret scanning and push protection** (the repository is public).
- **T11b, P-50** — parked (D-802); they resume when the user exports.
- **Obsolete branches (2026-09-29, the user's word):** deleted locally and on origin, each checked
  fully merged into `main` first — `a/stream-a-status`, `a/stream-a-idle-t13`, `a/T13-plan`
  (ancestors of `main`) and `a/docs-T12-plan` (its one commit is patch-identical to `6943204` on
  `main`). **Kept, because they hold commits `main` does not:** `a/fix-metrics-fixture-prices`
  (one commit, 2026-09-20: a fixture fix that scales prices — superseded by D-368's `qty` fix in
  #31, never merged) and `a/T11b-parity-tie` (seven A.md status commits of 2026-09-21/22,
  superseded by the A.md on `main`). Deleting either needs the user's word that unmerged work may
  go.

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
  the D-630 grid rule (2–4 values per parameter) in `components/base.py`.

### Next actions, in order

1. **T14 (stage 3)** — on the word: `s03_entry_1d`, `s03_entry_1h`, then their controls; **stop if
   any control candidate passes (D-644)**; then the review (the control first, then D-651's two
   findings), the acceptance commands, the acceptance reviewer, and the stop for "Approved".
2. **Next free ids:** D-807, P-122 (stream A); supervisor D-652.
3. `configs/universe.yaml` — no stream-B merge since #45/#46 moved a traded symbol, so D-394 owes
   no regeneration.
4. **T11b** when the user exports (D-802). **T15** owns the calibration list above.
