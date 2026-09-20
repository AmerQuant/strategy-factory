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
| supervisor | D-355 … D-359 | — |
| **stream A (this one)** | **D-360 … D-379** | **P-40 … P-59** |
| stream B | D-380 … D-399 | P-60 … P-79 |

Next free here: **D-360**, **P-40**.

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

## Status (2026-09-21)

**Batch 2b is closed.** All six PRs are on `main`: #11, #12, #16 (docs) and #13 (T06b),
#14 (T08), #15 (T10b). `main` at `f3deae4`: ruff ✅, format ✅, mypy ✅ 96 files,
`pytest -m "not slow"` **1153 passed**, parity + leakage + oracle **283**, `-m db -rs`
**21, 0 skipped**.

| item | state |
|---|---|
| T06b | ✅ merged (#13) — P-28 closed by D-356, 548/548 mapped or unmappable |
| T08 | ✅ merged (#14) |
| T10b | ✅ merged (#15) |
| D-355/D-356 | ✅ merged (#16) |
| **T11 parity** | **next** — Phase 1 (plan) on `docs/batch3-parity` |

### Owed to stream B

- **D-394 after #19 (T04f): done** on `a/universe-regen`. `configs/universe.yaml` regenerated
  from the T04f symbol lists: 26 symbols lost `1H` and 5 gained it, exactly stream B's list;
  no symbol entered or left the universe; hourly symbols 856 -> 835. `costs validate` 6742
  assigned / 521 profiles and `universe validate` 6749 symbols both unchanged.
- Next stream-B merge: run `sfac universe generate` again (D-394).
- Nothing under `configs/costs/` needs changing for D-388 (checked against the merged T06b).
