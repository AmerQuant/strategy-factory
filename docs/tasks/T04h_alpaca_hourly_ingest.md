# T04h — Alpaca 1H ingest: raw → snapshots, catalog and quality reports

**Features:** F-0.1.2 (Alpaca adapter), F-0.1.6 (quality report per symbol), F-0.1.8 (immutable snapshots, catalog) · **Priority:** MVP · **Depends on:** **T04f**, **T04g** (D-358: T04h is now last) · **Blocks:** nothing
**Branch:** `b/T04h-alpaca-hourly-ingest` from `b/T04g-alpaca-daily-ingest`.

Read first: `CLAUDE.md`, decisions **D-010**, **D-022**, **D-023**, **D-024**, **D-025**, **D-028**, **D-029**, and `docs/reviews/T04a_review.md`, `docs/reviews/T05_review.md`.

This task runs existing code at scale. It adds **no new adapter logic**; what it adds is chunking,
a progress/gap report and the evidence that the result is sound.

## Input state (measured 2026-09-20, `SFAC_RAW_ROOT/us_equity/alpaca_sip_split/1H`)

827 symbol folders, one parquet per calendar year. Coverage is **incomplete**:

| year | symbols with a file | missing |
|---|---|---|
| 2016 | 827 | 0 |
| 2017 | 827 | 0 |
| 2018 | 827 | 0 |
| 2019 | 827 | 0 |
| 2020 | 690 | **137** |
| 2021 | **0** | **827** |
| 2022 | **0** | **827** |
| 2023 | 207 | **620** |
| 2024 | 827 | 0 |
| 2025 | 827 | 0 |
| 2026 | 827 | 0 (partial year, `complete: false` in the manifests) |

**No symbol has all eleven years.** The newest file was written 2026-09-20 12:42 and no download
process was running at planning time, so the download is either finished with gaps or interrupted.
Ingesting this as-is produces snapshots with a two-year hole in the middle of the sample, which
would corrupt every later split (D-008 holdout is the last 20 % of the span) and every metric.

**P-62 answered 2026-09-21: no `--allow-gaps`. T04h waits until the 1H download is complete**
(the user is refilling the missing years 2020–2023). The task starts by re-checking the table above
with its own coverage report; if any year inside `[history_start, today)` is still missing for any
symbol of the universe, it **stops and reports** rather than writing snapshots that would have to be
superseded. T04f is not blocked by this and runs as soon as the plan is approved.

## Scope

### 1. Coverage gate and gap report (new, small)
- `sfac data ingest alpaca --timeframe 1H --report-only` (new flag, or a separate
  `sfac data coverage alpaca --timeframe 1H`): for every raw symbol, the years present, the years
  missing and the manifest `row_count` per year; written to
  `SFAC_RAW_ROOT/_reports/alpaca_coverage_1H.csv` and summarized on stdout.
- The ingest **refuses to run** (exit 1, clear message naming the symbols and years) when a year
  inside `[history_start, today)` is missing for any symbol of the universe. There is **no
  `--allow-gaps` escape hatch** (P-62): a gapped 1H set is not ingested at all. The current partial
  year is expected and is not a gap.
- The only tolerance is configurable in `configs/data/alpaca.yaml`, not in code (non-negotiable
  rule 1): which years count as in-range, and the per-symbol listing start (a symbol that listed in
  2019 has no 2016 file and must not trip the gate).

### 2. Ingest (existing code, run in chunks — D-385)
```
uv run sfac data ingest alpaca --timeframe 1H --set-reference --symbols <chunk>
```
- Symbol list = `configs/universe/us_equity_hourly.csv` **after T04f** (exclusion rule D-383
  applied, with `pit_symbol`). Do **not** use `raw_symbols()`, which would pick up the dropped old
  tickers (`FB`, `BLL`, …) whose series splice two different companies — see T04f §3.
- Chunks of 100 symbols, one CLI invocation per chunk, output appended to a log. The operation is
  idempotent: an identical snapshot is returned from the store, `catalog.register` is a no-op for a
  known key and `set_reference` returns early when the reference is unchanged. An interrupted chunk
  is simply re-run.
- Expected cost (measured on a scratch store: 2 symbols, 8 year-files each, ≈ 0.15 s/symbol after
  interpreter start-up; catalog rewrite ≈ 0.05 s/symbol at 7 k rows): **well under an hour** for
  827 symbols. Snapshot size ≈ 400 KB per symbol at 13.5 k bars → ≈ **330 MB**. 165 GB free on `D:`.

### 3. Verify the adapter's session filter on the real data (F-0.1.2, D-023)
Report, from the written snapshots (not from the raw files):

- the New-York hours kept: must be exactly `[9, 10, 11, 12, 13, 14, 15]`;
- the bars-per-session distribution: **7** on a regular day, **4** on a 13:00 early-close day
  (the early-close dates come from `nyse_sessions.csv`; on the scratch run with a synthetic
  all-16:00 calendar AAPL gave 7 bars on 1,938 of 1,940 days, which is the expected shape once the
  real early closes are applied);
- every day with fewer bars than its session implies, with the count. A known real gap to expect:
  **AAPL 2018-05-02 and 2018-05-03 have a single hourly bar each** in the Alpaca SIP feed. Such days
  are data, not a bug, and must appear in the quality report rather than be silently accepted;
- that no bar starts before 09:00 or ends after the session close (the `session_violations` check).

### 4. Quality reports (F-0.1.6)
```
uv run sfac data quality --all
```
run per chunk (`--symbol` loop) or once at the end; it writes `_quality/<hash>.json|.md` per snapshot
and records `quality_status` in the catalog.

**Summary layout (D-391):** implemented in **T04g**, which now runs first (D-358). T04h only adds
the `alpaca / 1H` group; check that the run leaves the `alpaca / 1D` summary byte-identical.

- With the T04f calendar in place, `missing_bars` and `session_violations` must be **executed**, not
  `skipped`. A `skipped` schedule check anywhere in the 1H set is a **failure of this task**.
- Produce an aggregate table in the review: count per `quality_status` (`ok | warning | critical`),
  the ten worst `missing_pct`, and the symbols with `session_violations`.
- Any snapshot with a **critical** status is named in the review; the pipeline cannot use it
  (`ensure_usable`, D-008 path). Do not "fix" it by relaxing the config.

## Out of scope
- Re-downloading anything (D-031: the user runs downloads).
- 1D ingest (T04g), which must wait for the **D-033** decision made in T04i.
- Dukascopy and Yahoo ingest.
- Registering the snapshots in the PostgreSQL registry (`data_snapshots`) — see **P-63**.

## Acceptance
- The coverage report exists and is reproduced in the review.
- The coverage gate passed (no missing year for any universe symbol), **or** the task stopped at
  the gate with a precise report and nothing was written. `--allow-gaps` does not exist (P-62).
- When it ran: every symbol of the post-T04f hourly universe has a snapshot, is the reference for
  `(symbol, 1H)`, and is listed in the catalog with `hash_version = 2`.
- The kept New-York hours are exactly 09–15, and the bars-per-session distribution matches the
  calendar (7 regular / 4 early close), with every exception listed.
- No snapshot exists for a dropped old ticker. The exact list is the one T04f produced from the
  Alpaca `NAME_CHANGE` feed; `FB` must not have a snapshot, and `META` must have one whose
  `pit_symbol`/`notes` record `FB`.
- Every 1H snapshot has a quality report and a recorded `quality_status`; **no** schedule check is
  `skipped`.
- Re-running the ingest for a chunk writes nothing and changes no catalog row (idempotence test).
- `uv run pytest -m "not slow"`, `tests/parity tests/leakage`, `ruff check`, `ruff format --check`,
  `mypy src` all pass; no network in tests.

## Review summary
`docs/reviews/T04h_review.md`: the coverage table; symbols ingested / skipped / failed; the
hours-kept and bars-per-day evidence; the quality aggregate plus every `warning`/`critical`; the
idempotence proof; run time and store size; deviations and open questions.
