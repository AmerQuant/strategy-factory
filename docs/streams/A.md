# Stream A — main folder

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory` (the repository's main worktree).
Governed by **D-355** and **D-357**; the full rules are in `docs/streams/PROTOCOL.md` and the
path ownership in `docs/streams/ownership.yaml`. This file is stream A's status; `HANDOFF.md`
(v7, 2026-09-22) is written **only by stream A**, at merges, from this file and
`docs/streams/B.md`. From D-802 on, this file lives on `main` (before, it lived on the
`a/T11b-parity-tie` branch only).

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
2. Read `HANDOFF.md` (v7) and this file; for T12 also `docs/streams/B_data_state.md`.
3. Work branches start from `origin/main`. `a/T11b-parity-tie` held only this file's updates
   while T11b waited; it is retired by D-802 (not deleted). `a/fix-metrics-fixture-prices` is
   obsolete (superseded by #31); deleting either needs the supervisor's word.
4. If `git worktree list` shows scratch entries under `AppData\Local\Temp\claude\…`, run
   `git worktree prune`. `StrategyFactory_dl` (detached) is not stream A's; leave it.

## Scope

1. Batch 2b, **T11** (#26), **D-368** (#31) — **merged**.
2. **T11b** — **parked (D-802)**; the plan stands in `docs/tasks/T11b_parity_tie_reentry.md`.
3. Stream and CI tooling — D-611/D-612 ownership, D-377 encodings, D-378 range, D-379 UTF-8
   output, D-800 Windows job, D-801 one `checks` run per PR update — **merged** (#33 … #43).
4. **T12 — stage 1, edge discovery** (D-611, critical per D-402) — ✅ **merged (#47)**.
5. **D-806 — pinned runner images, weekly Hypothesis back to 10×** — ✅ **merged (#48)**.
6. **Next: T13, stage 2** — plan first (D-403), stop for "Plan approved".

## ID ranges (D-355, D-378)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 (used up) and D-600 … D-699 | — |
| **stream A (this one)** | **D-360 … D-379** (used up) **and D-800 … D-899** | **P-40 … P-59** (used up) **and P-100 … P-149** (D-803) |
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 (used up) and P-80 … P-99 |

Stream A has used **D-360 … D-379**, **D-800 … D-806**, **P-40 … P-59** and **P-100 … P-106**
(all answered — stream A has no open question). **Next free here: D-807, P-107.** Supervisor rows
written by stream A: D-601 … D-621; next free supervisor id **D-622**. **Everything through D-806 is
on `main`** (#47 and #48).

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
  reads `SFAC_RAW_ROOT` read-only (D-028, rule 11). The one exception so far: `manifest.json` in
  the parity reference folder, written by `scripts/write_parity_manifest.ps1` on the
  supervisor's instruction.
- **`configs/universe.yaml` is stream A's (D-394).** After a stream-B merge that moves a symbol,
  run `sfac universe generate`.
- **Docs:** decision and pending edits go on stream A's own branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**, one row
  per ID (the most-resolved version wins). A row may be **amended in place** only within stream
  A's ranges or the supervisor's, never deleted (D-369).
- **Guard tests are mutation-checked against the real file**: break the thing on its real shape
  and watch the test fail before claiming the test catches it.
- **Runner images are pinned (D-806).** `ubuntu-24.04` and `windows-2025`; no job may use a
  `-latest` label (`tests/unit/test_F_X_9_pinned_runners.py`). Moving a pin is its own decision.
- **Encodings (D-377, D-379):** every text-mode subprocess and file access passes `encoding=`;
  the static guard fails otherwise. After a change to the `sfac` entry point, run `uv sync`.
  PowerShell scripts written from now on set `[Console]::OutputEncoding` to UTF-8 before
  calling `sfac`.
- **Benchmarks** run only when stream B is idle — they take every core.
- Every branch **rebases onto `main`** right before its merge; merges one at a time. D-401 and
  D-402 unchanged.
- **The venv can break silently.** If `mypy` suddenly reports `Failed to find builtin module
  "mypy_extensions"` or a wall of pydantic `import-untyped` errors: `uv sync --reinstall`.

## Status — 2026-09-28

**T12 is merged (#47, merge commit `8b9ebe0`) and D-806 is merged (#48, `3e2675c`). `main` is at
`3e2675c`; stream A has nothing open.** Next task: **T13, stage 2.**

> **The repository is public since 2026-09-28** (`private=False`, 07:34 UTC). Two consequences.
> **(1)** Actions minutes are free, which is what unblocked CI — GitHub had been refusing to start
> jobs with "recent account payments have failed or your spending limit needs to be increased"; both
> jobs of both PRs failed in ~2 s with no log until the repository went public, after which the same
> commits passed unchanged (nothing in the code was touched to fix it). **(2)** Everything pushed
> here is public immediately, and going private again would not undo it. **Turn on secret scanning
> and push protection** — free for public repositories, and it scans the history retroactively.

### The two merges

| PR | CI on the merged head | result |
|---|---|---|
| **#47** T12, stage 1 (critical, D-402; the review is the PR body) | `0f912a5`: `checks` 3 min, `windows-fast` 4 min, both green | merged `8b9ebe0`, pre-authorised for green CI, **no exception recorded** |
| **#48** D-806 runner pins + 10× weekly | rebased onto `main` as `d10f547`, re-run green | merged `3e2675c` |

The pins were verified on the merged run, not just from the docs: `checks` reports
`Image: ubuntu-24.04` and `windows-fast` reports `Image: windows-2025-vs2026` — the same images the
suite was already green on, so `windows-2025` is confirmed as the right label. The fast suite on the
rebased pin branch was **1,794 passed** (T12's suite plus the 6 new guards).

The supervisor approved the review **with two conditions; both are met** (review §14):

1. **`pytest -m db -rs` on the final code with 0 skipped** — done, **22 passed, 0 skipped**. The
   test named in the condition turned out to be **already** marked `db`; the real defect was that
   it called `make_engine` directly instead of a skipping fixture, so it *failed* where the others
   skipped. Fixed at that cause (`fixtures.registry_db.require_database`).
2. **P-106 → D-805: the stage-config hash is part of the candidate id**, so a T15 recalibration is
   a different candidate and can never overwrite this run's rows. Two tests, both failing if the
   hash is dropped.

### What is done

1. **Plan approved** (D-403) with P-55 … P-59 answered as **D-613 … D-617**; stream A's second
   pending range **P-100 … P-149** (D-803).
2. **Stage 1 built** (runbook steps 0–7): the statistics (`stats/edge.py`), the stage config and
   ESS, the `probe_q_value` gate criterion, the probe exits, the matched baseline, the stage
   framework (`RunContext` without a split manager), `s01_edge`, `sfac run` (stage 1 only), the
   random-walk control. **The engine is untouched** and no dependency was added.
3. **The pilot found a flaw in my own D-615 proposal** (P-100): a second disaster stop in the
   baseline made trend-following long probes look significant on market drift. **D-618** fixed
   it; both random-walk controls then passed 0 of 40, and the pilot's three 1H passes vanished.
   Also **D-619** (P-101) and **D-620** (P-102).
4. **Full run (step 9), all four runs complete.** Report: `docs/reviews/T12_review.md`; the pilot
   report `docs/reviews/T12_pilot.md` (§7–§13 supersede §1–§6).

   | run | profiles | passed | time |
   |---|---|---|---|
   | 1D | 1,944 | **14** (all mean reversion) | 22 min |
   | 1D control | 1,944 | 0 | 32 min |
   | 1H | 1,468 (3 skipped, D-008) | **4** (all TF long) | 42 min |
   | 1H control | 1,468 | 1 | 37 min |

5. **Wall-time mystery solved and fixed** (P-103 → **D-804**): Windows was scheduling runs onto
   this machine's four **efficiency cores** (3–4× slower: 6.5 s vs 21.1 s per symbol). Affinity
   and machine load were ruled out by measurement. `sfac run` and its workers now opt out of
   efficiency mode (config `efficiency_mode_opt_out`, default on, never able to stop a run).
6. **The acceptance reviewer ran and its findings are fixed** (see below).

### What the acceptance reviewer found, and what was fixed

It recomputed every number in the review from the artifacts, and they held. Its findings:

- **Blocking:** the stage's wiring of **D-602, D-613 (3), D-614 (1)** and the **D-615 control**
  had no test that would fail if it broke — it proved this by breaking each one while 105 tests
  still passed. Fixed: `tests/unit/test_F_1_5_stage_wiring.py` (9 tests), every one
  mutation-checked against exactly those breaks.
- The **leakage claim was overstated**: the test re-implemented the probe run with hard-coded
  settings. Fixed: one `probe_run` shared by the stage and the test, settings from
  `EngineConfig`; the claim reworded to what it proves.
- The **D-610 caveat reader had no test**. Fixed: `tests/unit/test_F_1_9_d610_caveats.py`
  against a real temporary catalog.
- The **stage config was in neither the run hash nor the registry**. Fixed: `stage_config_hash`
  on every trial; the candidate id is **P-106**.
- **D-354 (1):** a parity setting was silently ignored. Fixed: refused with a `ConfigError`.
- **Non-USD symbols aborted the run**, an undeclared rule. Fixed: skipped and listed (**P-105**).
- Undeclared deviations, stale text, literal values in code, an untested `sfac run` refusal, and
  the stage modules' reach into the writable catalog — all fixed (review §9, §12).
- **A re-run of the 1D pilot on the fixed code is identical** in all 40 profiles and in the
  index, so the full run's numbers still describe this code.

### Acceptance, as run on 2026-09-27 after the rebase

Everything green on the rebased tree, on Windows: fast suite **1,788 passed**;
parity + leakage + oracle **398**; **`-m db -rs` 22 passed, 0 skipped** (Docker up);
`-m slow` **20 passed**; ruff, `ruff format --check` (360 files), mypy `src` **and**
`--platform linux`, and `sfac streams check` clean.

No stage-1 behaviour changed over the rebase: stream B's #45 touches `data/split.py`, which stage
1 reads through `DataAccess`, but stage 1 takes no auxiliary series, so the four evidence runs
still describe this code.

### The pre-public secret audit (2026-09-27, supervisor request)

Asked for before the repository was made public: scan the **whole** history for secrets, and confirm
no workflow runs fork code with access to secrets. **The repository went public on 2026-09-28 on the
strength of this audit** — so if a future change adds a credential, it is public the moment it is
pushed. Keep it honest.

- **No secret has ever been committed; nothing to rotate.** 310 commits reachable from 115 refs
  **plus 225 unreachable** (rebase/force-push leftovers, from `git fsck --unreachable` and all
  reflogs) = 535 trees; 501 distinct paths; all 13 committed binaries decompressed and scanned
  (~54 M chars); every commit message. **No `.env` was ever committed**, and all four
  `.env.example` versions have `ALPACA_API_KEY=` / `ALPACA_API_SECRET=` **empty**. The only hits
  were `PKFAKEKEY1234567890` (a test fake), the local-dev `postgresql+psycopg://sfac:sfac@localhost`
  default (`.env.example`, `ci.yml`, `docker-compose.yml`) and a `FAKE_PASSWORD` fixture.
- `docs/reviews/T04a_review.md:98` says "revoke the old hard-coded key". That key was **never in
  this repository** (the script read the environment in its first and only versions, and no
  `PK…`/`AK…` literal exists in any tree) — it lived outside the repo, and whether it was actually
  revoked is not something this repository can show.
- **No workflow can leak a secret:** one workflow file has ever existed; **no `pull_request_target`
  and no `workflow_run`** in any version; **no `secrets.*` reference** in any version; and there is
  nothing to steal — 0 Actions secrets, 0 variables, 0 Dependabot secrets, 0 environments, 0 deploy
  keys, 0 self-hosted runners. Default `GITHUB_TOKEN` permission is **read**. The
  attacker-controlled `pull_request.head.ref` reaches the guard step through `env:` and quoted
  `"$BRANCH"`, never inlined in the script body.
- **Still to do when it is public:** GitHub secret scanning is **disabled** (API 404) and Advanced
  Security is unavailable while private, so GitHub has never scanned this history. **Turn on secret
  scanning + push protection as soon as it is public** (free there; it scans the history
  retroactively). While public, any key committed must be treated as leaked — going private again
  does not undo publication, and forks made meanwhile survive.
- Non-secret disclosure that comes with going public, flagged for the supervisor, not acted on: the
  Persian spec/design/features documents, the whole decisions log and every review (the method and
  the current findings), the Moneta cost profiles derived from a broker specification, ~24 MiB of
  TradingView and Dukascopy fixture exports (vendor-licence question), and local absolute paths.

### Open, and on whom

- **Nothing is open on stream A.** T12 (#47) and D-806 (#48) are merged, every P- question is
  answered, and the next task is **T13** (plan first, D-403).
- **On the user: turn on secret scanning and push protection** now that the repository is public.
- **P-104 … P-106 are answered** (D-621, D-805): the `auto`-budget question goes to **T15**;
  skipping and listing non-USD symbols stands until **T04j** lands the Dukascopy references; the
  stage-config hash is in the candidate id now.
- **Carried into T13 (D-621):** the **four 1H passes go to stage 2 flagged `unconfirmed`** —
  D-609 sends every pass forward, but stage 2 **reports them separately** and they never stand in
  for the daily mean-reversion finding. T13 is built knowing the **14 daily passes may move** when
  the battery is corrected at T15.
- **Not re-run, and it is the supervisor's call:** the four evidence runs predate D-805, so their
  candidate ids carry no stage-config hash. No number moves; a full re-run costs ≈ 1.6 h.
- **T11b, P-50** — parked (D-802); they resume when the user exports.
- **`a/fix-metrics-fixture-prices`**, **`a/T11b-parity-tie`**, **`a/docs-T12-plan`** — obsolete
  or folded in; deleting any of them needs the supervisor's word.

### What T15 must calibrate (from the full run; review §6)

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
   trial count. It does **not** inflate breadth.
5. **The reshuffled-returns control is conservative** (its percentiles average 28–46, not 50), so
   its 0–1 passes are a **lower bound**; the calibrated null is the synthetic random walk.
6. **Residual biases after D-618** (TF short slightly high, MR short low on synthetic data).

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
- **D-611 / D-612:** T12 is stream A's; `configs/gates/`, `metrics/`, `stages/`, `baseline/`,
  `components/`, `configs/stages/` are stream A's paths.

### Next actions, in order

1. **Merge this status branch.** The T12 and D-806 merges are done; the only thing not on `main` is
   this file's update plus `HANDOFF.md` **v8**, on `a/stream-a-status` (PR opened, CI green, waiting
   for "Approved. Merge"). Until it merges, `main`'s copy of this file still describes the blocked
   state of 2026-09-27 — merge it first so the next session reads the truth.
2. **T13** (stage 2) — plan first (D-403), stop for "Plan approved". It carries D-621's
   `unconfirmed` flag for the four 1H passes and is built knowing the 14 daily passes may move.
   **T15** owns the calibration list above.
3. `configs/universe.yaml` — checked at these merges: stream B's #45/#46 moved **no traded symbol**
   (they add `configs/universe/aux_yahoo.csv`, an aux-series list), so D-394 owes no regeneration.
4. **T11b** when the user exports (D-802).
