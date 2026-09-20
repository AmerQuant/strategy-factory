# Stream A — main folder

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory` (the repository's main worktree).
Governed by **D-355**. This file is stream A's status; `HANDOFF.md` is written **only by
stream A**, at merges, from this file and `docs/streams/B.md`.

## Scope

1. The **batch-2b merges**: `feat/T06b-moneta-costs` → `feat/T08-engine` →
   `feat/T10b-executor-metric-names`, each rebased onto `main` with CI green (D-401), the
   critical parts already approved (D-402, D-339).
2. Then **T11 — TradingView parity** (F-0.3.8, critical per D-402), on the references of D-348
   (`BATS:SPY` 1D and `OANDA:XAUUSD` 1H, run on the exported OHLC as-is). Open parity questions
   are listed in `HANDOFF.md` §8.

## ID ranges (D-355)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 | — |
| **stream A (this one)** | **D-360 … D-379** | **P-40 … P-59** |
| stream B | D-380 … D-399 | P-60 … P-79 |

Next free here: **D-360**, **P-40**.

## Rules that bind this stream (D-355)

- **Database:** `.env` here points at `sfac` on the shared Postgres (port 5433, D-305).
  Stream B uses `sfac_b` on the same server. Never point this `.env` at stream B's database.
- **Data root:** **stream A does not write to `SFAC_DATA_ROOT`.** Only stream B ingests and
  writes snapshots. Stream A reads the store and reads `SFAC_RAW_ROOT` read-only (D-028).
- **Docs:** decision and pending edits go on stream A's own docs branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**.
- **Benchmarks** (`scripts/bench_engine.py`, `scripts/bench_executor.py`) run only when stream
  B is idle — they take every core.
- Every branch **rebases onto `main`** before its merge. D-401 (merge only on "Approved.
  Merge …", CI green) and D-402 (critical tasks need supervisor review) are unchanged.

## Status (2026-09-21)

| item | state |
|---|---|
| T06b | done — P-28 closed by D-356, 548/548 mapped or unmappable. PR [#13](https://github.com/AmerQuant/strategy-factory/pull/13), branch at 8c2c28b. Needs a rebase onto `main` (a `pending.md` tail conflict) before merging. |
| T08 | approved, PR [#14](https://github.com/AmerQuant/strategy-factory/pull/14), stacked on T06b |
| T10b | approved, PR [#15](https://github.com/AmerQuant/strategy-factory/pull/15), stacked on T08 |
| docs/batch2b-3 | PR [#16](https://github.com/AmerQuant/strategy-factory/pull/16): D-355, D-356. Awaiting "Approved. Merge". |
| T11 | not started; starts after the batch-2b merges |
