# RUNBOOK — Batch 3-data (T04f → T04h → T04i → T04g)

Execute after the user writes **"Plan approved"**, in the worktree
`D:\AmerAndish\Projects\Trade\StrategyFactory_B` (stream B, the **only** stream that writes to
`SFAC_DATA_ROOT`). Read `CLAUDE.md` and `docs/decisions/decisions_log.md` first; this batch's
assumptions are **D-380 … D-387** (proposed) and its open questions are **P-60 … P-67** in
`docs/decisions/pending.md`.

One network run is needed, at the very start of T04f, and **the user runs it** (D-031). Everything
else is local.

## The order is not the order of the brief — and why

The brief lists (1) ingest, (2) calendar, (3) phase-B analysis. Three measured facts force a
different order:

1. **The 1H ingest cannot run without the calendar.** `AlpacaAdapter.sessions` raises
   `ConfigError: NYSE session calendar not found` for every symbol; `configs/calendars/nyse_sessions.csv`
   does not exist.
2. **The quality report is hollow without the calendar.** `expected_schedule()` falls back to the
   missing file and returns `skipped` for `missing_bars` and `session_violations`, and the snapshot
   is still reported `ok`. Verified on a scratch store.
3. **`session` is metadata, and metadata cannot be corrected later.** The snapshot hash covers
   content only; `SnapshotStore.write_snapshot` returns the *stored* metadata when the content hash
   already exists. `daily_session` is still `exchange` "decided in T04e phase B" (D-033, `proposed`).
   Ingesting 6,711 daily symbols before that decision locks in a label that cannot be changed
   without fabricating new content.

So: **reference data → 1H ingest → phase-B analysis (decides D-033) → 1D ingest.**

## Preconditions (stop if one fails)
1. The worktree is on `docs/batch3-data`, working tree clean, `.env` present with
   `SFAC_RAW_ROOT`, `SFAC_DATA_ROOT`, `SFAC_DB_URL` and the Alpaca keys.
2. `SFAC_RAW_ROOT/us_equity/alpaca_sip_split/1D` has 6,711 symbol folders × 11 years (verified
   2026-09-20).
3. Docker Postgres reachable on port 5433 (D-305); `uv run pytest -m db` runs with 0 skipped.
4. No other stream is running `pytest` or any `sfac` command against `SFAC_DATA_ROOT`.
5. Free space on `D:` ≥ 5 GB (the batch needs ≈ 1 GB; 165 GB free at planning time).

## Branching (stacked)
| Task | Branch | Based on | Critical (D-402) |
|---|---|---|---|
| — | `docs/batch3-data` (this plan) | `docs/batch2b` | |
| T04f | `feat/T04f-alpaca-reference` | `docs/batch3-data` | no |
| T04h | `feat/T04h-alpaca-hourly-ingest` | T04f | no |
| T04i | `feat/T04i-phaseb-hourly` | T04h | **yes in effect** — it closes **D-033**; stop after its review and wait for **"Approved"** before T04g |
| T04g | `feat/T04g-alpaca-daily-ingest` | T04i | no |

`docs/batch3-data` is based on `docs/batch2b`, not on `main`, because the decisions log on `main`
stops at D-346 and this batch appends after D-350. If batch 2b merges first the stack rebases onto
`main` with no conflict.

## Per-task loop
1. Read the task file and every document it cites.
2. Anything ambiguous or conflicting with `CLAUDE.md`, the decisions log or an ADR: **stop, ask**,
   and add it to `pending.md` using **P-60 … P-79** only.
3. Tests from the acceptance criteria first, then the implementation.
4. Acceptance commands, all green:
   ```
   uv run pytest -m "not slow"
   uv run pytest tests/parity tests/leakage tests/oracle
   uv run pytest -m db            # 0 skipped
   uv run ruff check . && uv run ruff format --check .
   uv run mypy src
   ```
5. Run the `acceptance-reviewer` subagent on the task; fix its findings.
6. Commit with feature IDs in the messages; write `docs/reviews/<task>_review.md`.
7. **T04i: stop** after its review and wait for **"Approved"** — T04g depends on its decision.

## Sequence

### Step 0 — the one network run (the user)
Claude Code writes `scripts/pilots/T04f_reference.ps1` and stops. The user runs, from the repo root:

```bash
powershell -ExecutionPolicy Bypass -File scripts\pilots\T04f_reference.ps1
```

and replies **"reference done"**. The script fetches the Alpaca calendar and the `NAME_CHANGE`
corporate actions into `SFAC_RAW_ROOT/reference/alpaca/` (immutable, with manifests), writes
`configs/calendars/nyse_sessions.csv` and `configs/universe/symbol_changes.csv`, and rebuilds the
universe files with `--use-latest-pit` (no new PIT download — the 827-symbol hourly set is already
downloaded against `fja05680_sp500_20260919.csv`).

A TLS/certificate error **stops the batch** and is reported verbatim. No CA-bundle workaround (D-031).

### Step 1 — T04f (reference data + the metadata guard)
Validates the calendar, reproduces the calendar-vs-`nyse_early_closes.yaml` difference report,
deletes the YAML, collapses the 15 rename pairs in the hourly universe, and adds the
material-metadata guard to the store (D-384).

### Step 2 — T04h (1H ingest, 827 → ~812 symbols)
**Gate first.** The 1H raw set is incomplete (2021 and 2022 missing for all 827 symbols; 2020 for
137; 2023 for 620; no symbol has all eleven years). The task refuses to ingest behind that gate
unless `--allow-gaps` is given (D-386, **P-62**). Expect this step to **stop and report** if the
download has not finished by then.

### Step 3 — T04i (phase-B analysis, closes D-033) — **stop for "Approved"**
Writes no snapshots. Produces the RTH-vs-exchange breach evidence, the bars-per-day table, the META
evidence, the split-check verdicts and the relisted-ticker candidate list; sets `daily_session` in
`configs/data/alpaca.yaml`.

### Step 4 — T04g (1D ingest, 6,711 symbols)
Runs with the decided `daily_session`, in chunks of 250, plus the split check and the quality
reports.

## Deferred — planned here, executed in a later batch
| Item | Why deferred | Prerequisite |
|---|---|---|
| **T04j — Dukascopy h1 full ingest** (29 instruments from 2010, bid+ask → mid+spread) | The download is still running: only 7 of 29 instruments have raw h1 (`EURJPY, EURUSD, GBPUSD, NZDUSD, USA500IDXUSD, USDJPY, XAUUSD`), and the catalog still holds only the three **Q1-2024 pilot** snapshots | the user reports the Dukascopy download finished |
| **Dukascopy pilot re-hash v1 → v2** (T04e §1) | The three pilot snapshots (`EURUSD`, `XAUUSD`, `USA500IDXUSD` 1H) are still `hash_version = 1` in the catalog; T04e's "re-ingest and move the reference, event note `rehash v1→v2`" never ran | folds naturally into T04j |
| **Yahoo aux ingest** (7 series, F-0.1.4/F-0.1.11) | Raw downloaded (`DX-Y.NYB, ^DJI, ^GSPC, ^NDX, ^RUT, ^TNX, ^VIX`), never ingested; the batch brief scopes phase B to the hourly data | a short follow-up task |
| **Registry `data_snapshots` population** | No CLI writes the catalog into PostgreSQL today; the table is filled by run writers | **P-63** |
| **1H re-ingest after the download completes** | If T04h runs with `--allow-gaps`, the gapped snapshots must be superseded and the reference moved | D-386 |

## Dependencies
No new third-party dependency is expected in this batch. If one becomes necessary it is listed in
the review with its reason, per `CLAUDE.md`.

## Stop conditions
- A TLS or network error in step 0.
- The 1H coverage gate trips and the supervisor has not answered **P-62**.
- D-033 cannot be decided from the evidence (for example the breaches are frequent but tiny) —
  report the numbers and ask; do **not** pick a value to keep going.
- An acceptance command fails and the fix is outside the task's scope.
- Any change would touch raw data, holdout data, parity fixtures or tolerances.

## End of batch
1. Open the PR(s) with `gh`, body = the reviews (stacked, one per task).
2. Update `HANDOFF.md`: the data status table (Alpaca 1D/1H **ingested**, the calendar **generated**),
   the T04e row (phase B closed for the hourly part), and the deferred items above.
3. Print one combined report: status per task, links to the reviews, merged open questions, and the
   merge order `docs/batch3-data` → T04f → T04h → T04i → T04g.
4. Merge only after **"Approved. Merge …"** and green CI (D-401).
