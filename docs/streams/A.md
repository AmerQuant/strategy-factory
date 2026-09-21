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
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 (used up) and P-80 … P-99 |

Next free here: **D-376**, **P-51**.

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

### T11 parity — answers applied; waiting on CI, then "Approved. Merge"

The supervisor read the review and answered P-46 … P-49 (**D-373 … D-375**); D-371 is amended.

| reference | matched (union, D-373) | net profit difference | D-011 |
|---|---|---|---|
| MR — `BATS:SPY` 1D | 462 / 462 (D-374 fixed the five one-share quantities) | −26.66 USD | PASS |
| TF long — `OANDA:XAUUSD` 1H | 519 / 519 | −0.03 USD | PASS |
| TF short — `OANDA:XAUUSD` 1H | 400 / 400 | +0.02 USD | PASS |

- **D-373** (trade share over the union) and **D-374** (parity sizing on the tick-rounded close)
  are implemented, tested, oracle-checked and mutation-checked.
- **T11 merges with the `to_verify` ledger at 3 of 5** (D-375). D-335 (stop-first, tie) and
  D-336 are tracked in **T11b**; **the merge of T11 does not close them**.
- **A correction of mine:** D-374 cited my claim that the five quantity trades carried −18.09 of
  MR's −25.70 USD. Wrong — with D-374 every quantity is right and the difference is −26.66. It
  is **fill rounding** (TradingView fills at the tick-rounded open), reproduced to the cent on all
  462 MR trades: **P-50**, open, engine unchanged. D-374's row carries the correction.

### T11b — planned, waiting on the supervisor to see the script

`docs/tasks/T11b_parity_tie_reentry.md`: the Pine script (a TF variant, no `flat` gate), the
export instructions, and parameters chosen by running the engine on the committed charts
(0.3 / 0.3 ATR, one-bar time exit: hundreds of stop-first bars, 7 SPY ties, 59 D-336
re-entries), plus a prediction to test (two SPY tie dates where the engine's float comparison
takes the target). **The user does not export until the supervisor has seen the script.**

### Blocked, and on whom

- **T11 merge — on the supervisor**: CI green, then "Approved. Merge" (D-401).
- **P-50 — on the supervisor** (fill rounding; does not block the merge).
- **T11b exports — on the supervisor** (the script), then on the user (the exports).
- **D-368** (P-44) — its own task after T11.

### For stream B (relayed by the supervisor — D-357, no direct messages)

- **P-80 … P-99 is stream B's own second pending range** (D-376, PR on `a/stream-b-pending-range`),
  granted because `P-60 … P-79` ran out and stream B's branch was red on the ID guard. Closed
  to stream A; `ownership.yaml`'s `streams.B.pending` is now a list of ranges
  (`((60, 79), (80, 99))`), exactly as `decisions` became under D-372.

- **D-700 … D-799 is stream B's own second decision range** (#25, D-372, on `main` at
  `b5a0bb4`). It is closed to stream A; only the supervisor's ranges are open to both.
  Pending stays P-60 … P-79, and `P-700` is refused from both streams.
- `ownership.yaml`'s `streams.B.decisions` is now a list of ranges; code or tests that read it
  as one `(lo, hi)` pair get `((380, 399), (700, 799))`. The out-of-range message names both.
- Stream A sent this to stream B directly on 2026-09-21. That was the wrong channel — the
  supervisor's correction: cross-stream communication goes through these status files and the
  supervisor. It is recorded here so the content has a proper home.

### Next actions, in order

1. CI green on the T11 PR → "Approved. Merge" → merge; rebase anything open.
2. After the merge: `HANDOFF.md` from this file and `docs/streams/B.md`.
3. T11b once the supervisor has seen the script and the user has exported.
4. Plan the D-368 task.
5. Owed to stream B: `sfac universe generate` after a stream-B merge that moves a symbol (D-394).

### ID ranges used so far

Stream A decisions **D-360 … D-375** used (next free **D-376**); pending **P-40 … P-50** used
(next free **P-51**). The supervisor keeps D-355 … D-359 (used up) and D-600 … D-699.
