# Stream A — main folder

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory` (the repository's main worktree).
Governed by **D-355** and **D-357**; the full rules are in `docs/streams/PROTOCOL.md` and the
path ownership in `docs/streams/ownership.yaml`. This file is stream A's status; `HANDOFF.md` is
written **only by stream A**, at merges, from this file and `docs/streams/B.md`.

New branches here carry the **`a/`** prefix. Run the guards locally with
`uv run sfac streams check --base origin/main`.

## Scope

1. The **batch-2b merges** — **done** (2026-09-21).
2. **T11 — TradingView parity** (F-0.3.8, critical per D-402), on the references of D-348
   (`BATS:SPY` 1D and `OANDA:XAUUSD` 1H, run on the exported OHLC as-is). The open parity
   questions are in `HANDOFF.md` §8.

## ID ranges (D-355)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 (used up) and D-600 … D-699 | — |
| **stream A (this one)** | **D-360 … D-379** | **P-40 … P-59** |
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 |

Next free here: **D-373**, **P-50**.

## Rules that bind this stream (D-355)

- **Database:** `.env` here points at `sfac` on the shared Postgres (port 5433, D-305).
  Stream B uses `sfac_b` on the same server. Never point this `.env` at stream B's database.
- **Data root:** **stream A does not write to `SFAC_DATA_ROOT`.** Only stream B ingests and
  writes snapshots. Stream A reads the store and reads `SFAC_RAW_ROOT` read-only (D-028).
- **`configs/universe.yaml` is stream A's (D-394).** After every stream-B merge, stream A runs
  `sfac universe generate` from the symbol list in `docs/streams/B.md`.
- **Docs:** decision and pending edits go on stream A's own docs branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**, one row
  per ID (the most-resolved version of a repeated ID wins).
- **Benchmarks** (`scripts/bench_engine.py`, `scripts/bench_executor.py`) run only when stream
  B is idle — they take every core.
- Every branch **rebases onto `main`** before its merge. D-401 (merge only on "Approved.
  Merge …", CI green) and D-402 (critical tasks need supervisor review) are unchanged.

## Status — 2026-09-21

**T11 is at its stop for "Approved" (D-402).** Branch `a/T11-parity` (pushed); the review is
`docs/reviews/T11_review.md`. Nothing of stream A's is open on `main`. Read this with
`HANDOFF.md`; together they are enough to resume this stream from scratch.

### Merged (nothing outstanding)

| PR | content |
|---|---|
| #13 #14 #15 #16 #17 | batch 2b: T06b, T08, T10b, D-355/D-356, HANDOFF v6 |
| #18 | D-357 stream protocol, `ownership.yaml`, the three CI guards |
| #20 | D-394 universe regeneration after T04f, plus the supervisor range D-600…D-699 |
| #22 | D-357 (1) amended: every session in its own worktree; `sfac streams session`; D-369 |
| #23 | the `removed_rows` test no longer depends on the repo's history |
| #25 | D-372: stream B's own second decision range, D-700 … D-799 |

### T11 parity — done, waiting on "Approved" (critical, D-402)

| reference | matched | net profit difference | D-011 |
|---|---|---|---|
| MR — `BATS:SPY` 1D | 457 / 462 = 98.92 % (5 one share off in quantity) | −25.70 USD | PASS |
| TF long — `OANDA:XAUUSD` 1H | 519 / 519 | −0.03 USD | PASS |
| TF short — `OANDA:XAUUSD` 1H | 400 / 400 | +0.02 USD | PASS |

- The TF re-export (D-600) is in: fixtures, manifest (`superseded` / `duplicate_of` notes),
  and `xauusd_tf_1h_long.yaml` / `xauusd_tf_1h_short.yaml` replacing the two-sided config.
- **The `to_verify` criterion is NOT met: 3 of 5.** D-327, D-349 (a), D-349 (h) are closed by
  construction (D-371). D-335 is confirmed only in its target-first case (P-46). **D-336 is
  not verified by any reference (P-49)** — the earlier claim that MR confirmed it, which D-371
  repeats, was my error.
- The acceptance reviewer found real problems in the first version; all are fixed, each
  verified first and mutation-checked (review §7): D-364 was decided rather than flagged; the
  classifier had the D-335 case backwards and three reasons could not fire; the oracle never
  ran D-366/D-367; no leakage test for the D-370 signal; several quoted numbers untested.
- Before the reviewer, I found two of my own: the engine open-trade flag was never read, and
  the comparison never compared quantity (which showed MR's 462/462 was really 457/462).

### Blocked, and on whom

- **T11 merge — on the supervisor**: "Approved" (D-402), then the PR, CI, "Approved. Merge".
- **P-46, P-47, P-48, P-49 — on the supervisor** (all raised in T11; none blocks the D-011
  result, but P-46 and P-49 decide the `to_verify` criterion).
- **D-368** (P-44) — queued as its own task **after** T11: the metrics fixture scales `qty`;
  falsifying examples pinned as `@example`; a weekly randomized Hypothesis job.

### For stream B (relayed by the supervisor — D-357, no direct messages)

- **D-700 … D-799 is stream B's own second decision range** (#25, D-372, on `main` at
  `b5a0bb4`). It is closed to stream A; only the supervisor's ranges are open to both.
  Pending stays P-60 … P-79, and `P-700` is refused from both streams.
- `ownership.yaml`'s `streams.B.decisions` is now a list of ranges; code or tests that read it
  as one `(lo, hi)` pair get `((380, 399), (700, 799))`. The out-of-range message names both.
- Stream A sent this to stream B directly on 2026-09-21. That was the wrong channel — the
  supervisor's correction: cross-stream communication goes through these status files and the
  supervisor. It is recorded here so the content has a proper home.

### Next actions, in order

1. On "Approved": open the T11 PR (body = the review), CI green, stop for "Approved. Merge".
2. After the merge: `HANDOFF.md` from this file and `docs/streams/B.md`.
3. Plan the D-368 task.
4. Owed to stream B: `sfac universe generate` after each stream-B merge that moves a symbol
   (D-394). Nothing outstanding — stream B reports T04i and T04g moved none.

### ID ranges used so far

Stream A decisions **D-360 … D-372** used (next free **D-373**); pending **P-40 … P-49** used
(next free **P-50**). The supervisor keeps D-355 … D-359 (used up) and D-600 … D-699.
