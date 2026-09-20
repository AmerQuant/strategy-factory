# Stream B — worktree `StrategyFactory_B`

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory_B` (a git worktree of the same
repository, created with `git worktree add ../StrategyFactory_B -b docs/batch3-data main`).
Governed by **D-355**. This file is stream B's status; it is **not** `HANDOFF.md` — stream A
folds it into `HANDOFF.md` at merges.

## Scope

1. **Data**, in this order:
   - ingest the completed Alpaca **1D** and **1H** downloads into the snapshot store;
   - generate the **NYSE session calendar** `configs/calendars/nyse_sessions.csv` from the
     Alpaca calendar fetch (**D-025**);
   - the **T04e phase-B pilot** analysis, which was waiting for the hourly download.
2. Then **T12 — stages 1–3**, whose acceptance carries **D-354**: stage code takes the engine
   settings only from `PipelineConfig.engine` (`DEFAULT_ENGINE_CONFIG` forbidden in stage code,
   grep test); a stage passes its stage id from its own constant (grep test: the literal
   `"s06_robust"` only in `data/split.py` and the stage-6 module); F-0.7.4 stays partial until
   the bit-identical rerun through `RunContext` is proven.

## ID ranges (D-355)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 | — |
| stream A | D-360 … D-379 | P-40 … P-59 |
| **stream B (this one)** | **D-380 … D-399** | **P-60 … P-79** |

Next free here: **D-380**, **P-60**.

## Rules that bind this stream (D-355)

- **Database:** this worktree has its **own `.env`** pointing at **`sfac_b`** on the shared
  Postgres server (port 5433, D-305); the schema is migrated to head. Stream A keeps `sfac`.
  `docker compose` is owned by stream A — do not start or stop containers from here.
- **Data root:** **stream B is the only writer of `SFAC_DATA_ROOT`.** Snapshots are immutable:
  never overwrite one, always write a new one (CLAUDE.md rule 10). `SFAC_RAW_ROOT` is
  **read-only** for both streams (D-028, CLAUDE.md rule 11).
- **Network runs are the user's** (D-031): Claude Code writes the PowerShell script, the user
  runs it.
- **Docs:** decision and pending edits go on stream B's own docs branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**.
  `HANDOFF.md` is never edited here.
- **Benchmarks** run only when stream A is idle.
- Every branch **rebases onto `main`** before its merge. D-401 and D-402 are unchanged.

## Status (2026-09-21)

| item | state |
|---|---|
| worktree | created on `docs/batch3-data` at `main` (b98e98d); `uv sync` done |
| database | `sfac_b` created, `sfac db upgrade` → `0001_initial`, `pytest -m db` 15 passed, 0 skipped |
| Alpaca 1D / 1H ingest | **not started** (downloads complete, nothing ingested) |
| NYSE calendar (D-025) | not started |
| T04e phase-B pilot | not started |
| T12 | not started |
