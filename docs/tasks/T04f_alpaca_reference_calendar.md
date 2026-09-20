# T04f — Alpaca reference data: NYSE session calendar and symbol changes

**Features:** F-0.1.2 (Alpaca adapter, session filter), F-0.1.6 (quality: schedule checks) · **Priority:** MVP · **Depends on:** T04e on `main` (the fetch/build code already exists) · **Blocks:** T04h, T04i, T04g
**Branch:** `b/T04f-alpaca-reference` from `docs/batch3-data`.

Read first: `CLAUDE.md`, decisions **D-024**, **D-025**, **D-028**, **D-031**, **D-033**, and `docs/tasks/T04e_data_followup.md` §5 and §6 (this task finishes the two items whose network run never happened).

## Why this is the first task of the batch

The fetch/build code was delivered by T04e but **was never run**, so the two artefacts do not exist:

| Artefact | State on disk (checked 2026-09-20) |
|---|---|
| `SFAC_RAW_ROOT/reference/alpaca/calendar/*.json` | missing |
| `configs/calendars/nyse_sessions.csv` | missing |
| `SFAC_RAW_ROOT/reference/alpaca/corporate_actions/name_changes_*.json` | missing |
| `configs/universe/symbol_changes.csv` | missing (only the empty `symbol_changes_manual.csv` exists) |
| `configs/universe/us_equity_hourly.csv` | **old format**: columns `symbol, reason, first_member_date, last_member_date`, no `pit_symbol` |

Consequences measured on the current tree, which is why nothing else in the batch can go first:

1. **The 1H ingest cannot run at all.** `AlpacaAdapter.sessions` → `load_sessions()` raises
   `ConfigError: NYSE session calendar not found` for every symbol
   (`src/strategy_factory/data/adapters/alpaca.py:80`, `download/alpaca_reference.py:96`).
2. **The quality report is hollow without the calendar.** `expected_schedule()` falls back to
   `cfg.sessions_file`; when the file is absent it returns `ExpectedSchedule(None, "NYSE session
   calendar not found")`, so `missing_bars` and `session_violations` are **skipped** and the
   snapshot is still reported `status: ok`
   (`src/strategy_factory/data/schedule.py:268`, verified on a scratch store: five Alpaca 1D
   snapshots came back `ok` with both schedule checks `skipped`).
3. **Renamed tickers would be ingested twice, and one of the two series is spliced across two
   different companies.** Alpaca serves the pre-rename history under **both** the old and the new
   ticker, and it serves current bars of a *re-used* ticker under the old name. Measured on the raw
   files:

   | symbol | 2016 daily | 2020 daily | 2026 daily |
   |---|---|---|---|
   | `FB`   | 252 bars, close 94.16–133.28 | 253 bars, close 146.01–303.91 | 179 bars, close **41.99–45.55** |
   | `META` | 252 bars, close 94.16–133.28 | 253 bars, close 146.01–303.91 | 179 bars, close **525.72–738.31** |

   `FB` 2016–2020 is Meta; `FB` 2026 is a different instrument. Ingesting `FB` produces a single
   "continuous" series with a ~12× level break in the middle. The same fingerprint (identical
   2016–2019 row counts under two tickers) appears for **15 pairs / 30 of the 827 hourly symbols**:
   `ABC/COR`, `ANTM/ELV`, `BALL/BLL`, `CHK/EXE`, `CPAY/FLT`, `CTL/LUMN`, `ECHO/SATS`, `EG/RE`,
   `EQR/VMRK`, `FB/META`, `MMC/MRSH`, `PKI/RVTY`, `RTX/UTX`, `SW/WRK`, `WLTW/WTW`.
   D-024 already decides the rule (download under the **current** symbol); this task supplies the
   `symbol_changes.csv` that lets the rule be enforced.

## Scope

### 1. The network run (the user executes it — D-031)
Write `scripts/pilots/T04f_reference.ps1`, run from the repo root, `$ErrorActionPreference = "Stop"`,
appending to `SFAC_RAW_ROOT/_reports/T04f_reference_<timestamp>.log`. In order:

```powershell
uv run sfac data reference alpaca-calendar --start 2016-01-01        # end defaults to 31 Dec this year
uv run sfac data reference alpaca-symbol-changes --start 2016-01-01
uv run sfac data universe us-equity --use-latest-pit                 # rebuilds both universe files
```

- No new network code. All three commands exist and were delivered by T04e.
- `--use-latest-pit` reuses `raw/reference/sp500_pit/fja05680_sp500_20260919.csv` (sha256 in
  `us_equity_hourly.csv.meta.json`); **do not** re-download the PIT list, because a newer PIT list
  would change the 827-symbol universe that has already been downloaded.
- A TLS or certificate error **stops the batch and is reported as-is**. No CA-bundle workaround,
  no `--no-verify`, no retry with verification disabled (D-031).

Then stop and wait for the user to reply **"reference done"**.

### 2. Calendar → `configs/calendars/nyse_sessions.csv` (D-025)
The CLI writes it from the raw JSON (`build_sessions_csv`). After the run, verify and report:

- row count and the first/last session date; `2016-01-04` is present and the last row is in the
  current year;
- every row parses as `date, open_local, close_local` in `America/New_York`;
- the number of sessions whose `close_local != "16:00"` (early closes) per year;
- the difference report the CLI writes to `SFAC_RAW_ROOT/_reports/calendar_vs_early_closes.csv`
  (`compare_with_early_closes`), **reproduced in full in the review** — it is the T04e §6 deliverable.

Then **delete `configs/calendars/nyse_early_closes.yaml`** (T04e §6) together with its loader path,
and check that nothing else reads it. Deletion happens **after** the diff report is in the review,
and only if the report shows no unexplained disagreement (**D-393**); an unexplained difference
stops the task and is reported.

`configs/calendars/nyse_sessions.csv` is committed (it is a config, not data).

### 3. Symbol changes → `configs/universe/symbol_changes.csv` and the hourly universe (D-024)

**P-61 answered 2026-09-21: yes — the symbol-changes fetch is in scope and runs in the same
PowerShell run as the calendar (the user runs it, D-031).**

**Exclusion rule (answer to P-61/P-67, recorded as D-383):**
- an **old-name** series is excluded entirely when the **current-name** series covers its history;
- a ticker **re-used by another company** is excluded for now;
- the two cases are decided from the Alpaca `NAME_CHANGE` feed plus the series evidence (identical
  history under both names → rename; a level break with no known split → re-use);
- a symbol that neither rule covers is **kept** and listed in the review.

**Guard (D-388): never edit `configs/costs/moneta/*`.** If the rule would remove a symbol that is a
**target** of the T06b mapping, keep the symbol, change nothing under `configs/costs/`, and report
it to stream A in the review and in `docs/streams/B.md`.

Checked while planning against **`main`** (T06b merged as PR #13; `configs/costs/moneta/symbol_map.csv`,
515 rows, and `symbol_overrides.csv`, 109 rows — byte-identical to the merged branch):

| Moneta research target | broker symbol | status under the rule |
|---|---|---|
| `COR`, `LUMN`, `META`, `RTX` | `COR`, `LUMN`, `META`, `RTX` | current names — survive |
| `MRSH` | `MMC` | current name (D-356 successor `MMC→MRSH`) — survives |
| `BNY` | `BK` | current name (D-356 successor `BK→BNY`) — survives |
| `EQR` | `EQR` | **near-miss:** the row-count heuristic paired `EQR/VMRK`, but `EQR` has continuous daily bars 2016→2026 (close 58.8–81.5 in 2016, 58.0–70.2 in 2026) and **`VMRK` has no daily raw data at all**, so the current-name series does **not** cover `EQR`'s history and the rule does **not** exclude it. Confirm against the `NAME_CHANGE` feed; if the feed contradicts this, stop and report to stream A rather than excluding `EQR`. |

No old name of the 15 candidate pairs is a Moneta target, so on today's evidence the rule causes no
collision. Re-run this check after the feed arrives and put the result in the review.

`build_symbol_changes` + `build_hourly_universe` already implement the mechanics; this task runs
them and validates the outcome:

- `configs/universe/symbol_changes.csv` exists with `old_symbol, new_symbol, effective_date, source`
  and contains `FB → META` with `effective_date = 2022-06-09`.
- `configs/universe/us_equity_hourly.csv` is rebuilt in the **new format**, with a `pit_symbol`
  column, and the old ticker of each confirmed rename is **no longer a row of its own**; its
  historical ticker appears in `pit_symbol` of the surviving row (pipe-separated for chains).
- **Report the reconciliation of the 15 measured pairs** (table above): for each pair say whether the
  Alpaca `NAME_CHANGE` feed confirms it, and which side the rule keeps. Worked evidence from the
  daily raw, to be reproduced on the real feed:
  - `BLL/BALL` — `BLL` files for 2025 and 2026 exist but hold **0 rows**, `BALL` continues; textbook
    old-name case, `BLL` excluded.
  - `FB/META` — identical 2016–2020, then `FB` 2026 at close 42.0–45.6 against `META` 526–738;
    re-used ticker, `FB` excluded.
  - `ECHO/SATS` — identical 2016–2025, both live in 2026 at 104–142 with different bar counts;
    **undecided from the series alone**, the feed decides.
  - `EQR/VMRK` — see the Moneta table above: `EQR` is continuous and `VMRK` has no daily data;
    the rule keeps `EQR`.
- A pair the feed does not confirm is **not** silently merged: it is listed in the review, the
  symbol is kept, and the question goes to `pending.md`. A pair that is a rename but is missing from
  the API goes into `configs/universe/symbol_changes_manual.csv` (manual rows win) only with the
  supervisor's confirmation.
- The raw folders of dropped tickers are **not touched** (raw is immutable, D-028); they are simply
  not ingested.
- **`configs/universe.yaml` is not regenerated and not edited (D-394).** It is stream A's generated
  registry; rebuilding the hourly universe makes it stale (for example `ABC` currently sits in it
  with `timeframes: [1D, 1H]` and this task removes the hourly row). Instead, every symbol added or
  removed goes into the **"Symbols for stream A"** table of `docs/streams/B.md`, with the reason, so
  stream A runs `sfac universe generate` after the merge. If `sfac universe validate` fails only
  because of that staleness, report it — do not fix it here.

Acceptance check to write as a test on a fixture: given a changes list containing `FB → META`,
`build_hourly_universe` emits exactly one row for `META` with `pit_symbol = FB` and no `FB` row.

### 4. Material-metadata guard in the store (new, see **D-384 / P-65**)
The snapshot hash covers **content only** (`SnapshotStore.write_snapshot` → `content_hash(normalize(df))`).
When a snapshot with the same content already exists, `write_snapshot` returns the **stored**
metadata and writes nothing (`src/strategy_factory/data/store.py:100`). That is correct for
immutability (rule 10, F-0.1.8) but it means a **later re-ingest with corrected metadata is silently
a no-op** — the `session`, `pit_symbol` note, `feed` or `adjustment` of the first ingest wins
forever. This is the reason for the ordering in the runbook, and it needs a guard so a mistake is
loud instead of silent:

- In `SnapshotStore.write_snapshot`, when `pq_path.exists()`, compare the stored metadata with the
  incoming one on the **material** fields `source`, `source_symbol`, `asset_class`, `price_type`,
  `adjustment`, `session`, `feed`, `volume_quality`, `original_tz`, `bar_label`, `hash_version`.
  Any difference raises `DataError` naming the field, the stored value and the incoming value, and
  pointing at the snapshot path. `notes`, `raw_refs`, `downloaded_at`, `created_at` and
  `derived_from` are **not** material and never raise.
- Tests: identical content + identical material metadata returns the stored metadata unchanged
  (existing behaviour, keep the existing test); identical content + a different `session` raises;
  identical content + a different `notes` does not raise.
- This changes no existing snapshot and adds no dependency.

## Out of scope
- Any ingest (T04g, T04h) and any analysis (T04i). **T04f does not wait for the 1H download**
  (P-62): it runs as soon as the plan is approved.
- Any edit under `configs/costs/` — that is stream A's T06b (D-388).
- `sfac universe generate` and any edit of `configs/universe.yaml` — stream A's (D-394).
- Re-downloading the PIT list or any price data.
- Dukascopy and Yahoo reference data.

## Acceptance
- `scripts/pilots/T04f_reference.ps1` delivered; the user's run completed without a TLS error.
- `configs/calendars/nyse_sessions.csv` exists, covers 2016-01-04 → the current year, and
  `sfac data quality` no longer reports `missing_bars: skipped` for a `us_equity` snapshot
  (proved on one 1H snapshot built in T04h, or on a fixture here).
- `configs/universe/symbol_changes.csv` exists and contains `FB → META (2022-06-09)`.
- `configs/universe/us_equity_hourly.csv` has a `pit_symbol` column, has no `FB` row, and its
  `META` row carries `pit_symbol = FB`.
- `configs/calendars/nyse_early_closes.yaml` is deleted and no code path references it.
- The calendar-vs-YAML difference report is reproduced in the review.
- The exclusion rule (D-383) is applied, each of the 15 pairs has a stated verdict, and the
  re-run of the Moneta-target check (D-388) is in the review. Nothing under `configs/costs/` is
  modified by this task.
- `configs/universe.yaml` is unchanged (D-394), and `docs/streams/B.md` lists every symbol this task
  added to or removed from `configs/universe/`.
- `uv run pytest -m "not slow"`, `uv run pytest tests/parity tests/leakage`, `ruff check`,
  `ruff format --check`, `mypy src` all pass; no network in tests.

## Review summary
`docs/reviews/T04f_review.md`: the calendar statistics and the full difference report; the symbol-change
table with the 15 measured pairs and their verdicts; the universe row counts before/after; the
material-metadata guard with its tests; deviations and open questions.
