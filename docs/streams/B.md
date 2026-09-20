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

Next free here: **D-389**, **P-68**.

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

Batch 3-data is **planned**, awaiting "Plan approved". Plan on `docs/batch3-data`:
`docs/tasks/RUNBOOK_batch3-data.md` and `T04f`, `T04h`, `T04i`, `T04g`; decisions **D-380 … D-388**
(section I of the log), questions **P-60 … P-67** (P-61, P-62, P-67 answered 2026-09-21).

| item | state |
|---|---|
| worktree | on `docs/batch3-data` at `main`; `uv sync` done |
| database | `sfac_b` created, `sfac db upgrade` → `0001_initial`, `pytest -m db` 15 passed, 0 skipped |
| batch 3-data plan | **drafted**, awaiting "Plan approved" |
| Alpaca **1D** raw | **complete**: 6,711 symbols × 11 years (2016–2026); 3 symbols returned no bars (`BHGE`, `FBHS`, `JEC`) |
| Alpaca **1H** raw | **incomplete** as of 2026-09-20: 2021 and 2022 missing for all 827 symbols, 2020 for 137, 2023 for 620; **no symbol has all eleven years**. The user is refilling 2020–2023. (This corrects the earlier "downloads complete" note.) |
| Alpaca 1D / 1H ingest | not started — T04g is gated on D-033, T04h on the 1H download (D-386, no `--allow-gaps`) |
| NYSE calendar (D-025) | not started; the T04e fetch was never run, so `configs/calendars/nyse_sessions.csv`, `configs/universe/symbol_changes.csv` and the raw calendar/corporate-action files are all missing. T04f §1 is the user's PowerShell run |
| T04e phase-B pilot | not started; scoped to the hourly data in **T04i**, which closes **D-033** |
| snapshot store | untouched: 3 Dukascopy Q1-2024 pilot snapshots, all still `hash_version = 1` (the T04e v1→v2 re-hash never ran) |
| T12 | not started |

## For stream A

- **D-388 (broker mapping boundary).** The D-383 exclusion rule for renamed/re-used tickers was
  checked against `main` (T06b merged as PR #13). Affected Moneta research targets — `COR`,
  `LUMN`, `META`, `RTX`, `MRSH` (broker `MMC`, D-356) and `BNY` (broker `BK`, D-356) — are all
  current names and survive the rule. The one near-miss is **`EQR`**: a row-count heuristic paired
  `EQR/VMRK`, but `EQR` has continuous daily bars 2016→2026 and `VMRK` has **no daily raw data**, so
  the rule does not exclude it. **No change is needed under `configs/costs/`**; stream B will not
  edit it. If the Alpaca `NAME_CHANGE` feed contradicts the `EQR` finding, stream B stops and
  reports rather than excluding it.
- **`HANDOFF.md`** still says "Alpaca 1H (827 symbols) — downloading" and lists batch 2b as next;
  the 1H coverage table above is the current fact for the data-status section.
