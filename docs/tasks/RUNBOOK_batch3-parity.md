# RUNBOOK — Batch 3-parity (stream A): T11

One task, and it is **critical (D-402)**.

## Branches

| Task | Branch | Base | Critical |
|---|---|---|---|
| T11 | `feat/T11-tradingview-parity` (worked as `a/T11-parity`, D-357) | `main` | **yes** — stop after the review, wait for "Approved" |
| T11b | `a/T11b-parity-tie` | `main` after T11 | **yes** — D-375; **the exports do not start until the supervisor has seen the script** (`docs/tasks/T11b_parity_tie_reentry.md`) |

The plan itself lives on `docs/batch3-parity`.

Stream A works in the main folder (`D:\AmerAndish\Projects\Trade\StrategyFactory`). **Never
switch the main folder to another branch** except as this table requires, and never to `main`
mid-batch. Stream B's worktree is `../StrategyFactory_B`; do not touch it (D-355).

## Before starting

1. **P-40 must be answered.** The parity references are OHLC only: there are no TradingView
   **trade lists**, no **manifest**, and no **Pine sources or settings**. Without the trade
   lists, D-011 cannot be evaluated. §1–§3 of the task can be built first; §4 cannot.
2. `main` must be green (it is: ruff, format, mypy 96 files, 1153 fast tests, 283 gate tests,
   21 db tests with 0 skipped).
3. Stream B is running batch 3-data in its own worktree. **Benchmarks only when it is idle**
   (D-355); T11 needs none.

## Order of work

1. §1 reference store + §2 parity config + their tests — independent of P-40.
2. §3 the two `BacktestSpec`s — needs the Pine sources (P-41). If a Pine rule has no registered
   component, **stop and report**; a new component is T07's contract, not T11's.
3. §4 comparison + the D-011 gate — needs the trade lists (P-40).
4. §5 the five `to_verify` items, including the two HANDOFF §8 checks (ATR warm-up entries,
   trailing ATR basis). A change to the engine's parity branch is a stream-A decision
   (**D-360 … D-379**) and must be recorded before it is implemented.
5. §6 report, then the `acceptance-reviewer` subagent, then `docs/reviews/T11_review.md`.

## Rules for this batch

- **IDs (D-355):** stream A uses **D-360 … D-379** and **P-40 … P-59**. Never write an ID
  outside that range.
- **Parity and leakage tests are never skipped, weakened or deleted** (CLAUDE.md rule 9). A
  tolerance change needs an ADR. While the references are incomplete the gate **fails**, it does
  not skip.
- **The raw store is read-only** (CLAUDE.md rule 11). The parity references are never modified,
  never re-bucketed and never ingested into the snapshot store; stream A does not write
  `SFAC_DATA_ROOT` (D-355).
- **Network runs are the user's** (D-031): any TradingView export or manifest script is written
  here and run by the user.
- Decision and pending edits go on stream A's own docs branch; a conflict in `decisions_log.md`
  or `pending.md` is resolved by **keeping every row in ID order**, one row per ID.

## At the end of the batch

1. Push `feat/T11-tradingview-parity` as soon as the review file is committed.
2. **Stop after the review** and wait for "Approved" (D-402).
3. Then open the PR with `gh` (body = the review), update `docs/streams/A.md`, and print the
   batch report. `HANDOFF.md` is updated by stream A **at the merge**, from `docs/streams/A.md`
   and `docs/streams/B.md`.
4. Merge only on "Approved. Merge …" with CI green (D-401), rebased onto `main`.
