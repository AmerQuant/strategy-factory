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
4. **T12 — stage 1, edge discovery** (D-611, critical per D-402) — **planning** (D-403).

## ID ranges (D-355, D-378)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 (used up) and D-600 … D-699 | — |
| **stream A (this one)** | **D-360 … D-379** (used up) **and D-800 … D-899** | **P-40 … P-59** (used up) **and P-100 … P-149** (D-803) |
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 (used up) and P-80 … P-99 |

Stream A has used **D-360 … D-379**, **D-800 … D-803**, **P-40 … P-59** and **P-100 … P-102**.
**Next free here: D-804, P-103.** Supervisor rows written by stream A: D-601 … D-617; next free
supervisor id **D-618**. (D-803 and D-613 … D-617 are on `a/T12-edge-discovery`, not yet on `main`.)

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
- **Encodings (D-377, D-379):** every text-mode subprocess and file access passes `encoding=`;
  the static guard fails otherwise. After a change to the `sfac` entry point, run `uv sync`.
  PowerShell scripts written from now on set `[Console]::OutputEncoding` to UTF-8 before
  calling `sfac`.
- **Benchmarks** run only when stream B is idle — they take every core.
- Every branch **rebases onto `main`** right before its merge; merges one at a time. D-401 and
  D-402 unchanged.
- **The venv can break silently.** If `mypy` suddenly reports `Failed to find builtin module
  "mypy_extensions"` or a wall of pydantic `import-untyped` errors: `uv sync --reinstall`.

## Status — 2026-09-22

**#44 (D-802) is merged** (`main` at `44bed56`). **T12 is at its step-8 stop** (the pilot),
before step 9, as the supervisor required: branch `a/T12-edge-discovery` (pushed, no PR yet).

- **Plan approved** with P-55 … P-59 answered: D-613 (amends D-601/D-606), D-614 (probe
  exits; the parity harness keeps its own copy), D-615 … D-617; stream A's second pending
  range P-100 … P-149 (D-803, in `ownership.yaml` with tests).
- **Built (steps 0–7):** stats helpers, the stage config and ESS, the `probe_q_value` gate
  criterion, the probe exits, the matched baseline, the stage framework (no split manager in
  `RunContext`), `s01_edge`, `sfac run`, the random-walk control, and their tests
  (fast 1,737, parity/leakage/oracle 396, db 22 with 0 skipped; ruff, format, mypy clean).
- **Pilot (step 8):** `docs/reviews/T12_pilot.md`. 10 symbols; reproduced exactly on a second
  run; the projected full run with controls is about 1.6 h. **Found a bias in the D-615
  baseline**: a second disaster stop in the baseline inflates TF long probes under drift (the
  permuted 1H control passes 2 of 40, both TF long). This is raised as **P-100** with an
  amendment. P-101 (TF probes below the trade minimum, the §11 trigger) and P-102 (two
  uninformative warnings) are also open.

### Open, and on whom

- **P-100 … P-102** — on the supervisor. P-100 blocks step 9: the pilot is re-run after it.
- **Step 9 (the full run)** — only after the supervisor has seen the pilot (and P-100).
- **T11b, P-50** — parked (D-802); resumes when the user exports.
- **`a/fix-metrics-fixture-prices`**, **`a/T11b-parity-tie`**, **`a/docs-T12-plan`** —
  deleting needs the supervisor (the plan branch is folded into `a/T12-edge-discovery`).

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

1. The supervisor answers P-100 … P-102.
2. Apply the P-100 answer, add the drifted TF uniformity case, re-run the pilot, report again.
3. Step 9 on the supervisor's word: the full MVP scope on 1D and 1H plus the random-walk
   control (`configs/pipeline/s01_broker_{1d,1h}[_control].yaml`); then the review, the
   acceptance reviewer, the PR, and the stop for "Approved" (D-402).
4. T11b when the user exports (D-802).
