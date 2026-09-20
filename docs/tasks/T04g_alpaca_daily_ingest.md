# T04g — Alpaca 1D ingest: 6,711 symbols → snapshots, catalog and quality reports

**Features:** F-0.1.2 (Alpaca adapter), F-0.1.6 (quality report per symbol), F-0.1.8 (immutable snapshots, catalog), F-0.1.9 groundwork (split check) · **Priority:** MVP · **Depends on:** **T04f**, **T04i** (D-033 decided)
**Branch:** `feat/T04g-alpaca-daily-ingest` from `feat/T04i-phaseb-hourly`.

Read first: `CLAUDE.md`, decisions **D-010**, **D-021**, **D-022**, **D-028**, **D-029**, **D-033**
(decided in T04i — this task ingests with the decided value), and `docs/reviews/T04a_review.md`,
`docs/reviews/T05_review.md`.

**Do not start this task before D-033 is decided.** `session` is metadata and the content-addressed
store never rewrites the metadata of an existing snapshot (see T04i §"Why this runs before the 1D
ingest"); with 6,711 symbols a wrong label is not correctable.

## Input state (measured 2026-09-20, `SFAC_RAW_ROOT/us_equity/alpaca_sip_split/1D`)

- **6,711 symbol folders, complete**: every one of the eleven years 2016 … 2026 has a file for all
  6,711 symbols (2026 is the current partial year, `complete: false` in its manifests).
- `AAPL/2026.v2.parquet` exists next to `2026.parquet` — the immutable re-download versioning;
  `latest_chunks()` picks the newest version, which is the intended behaviour.
- `SFAC_RAW_ROOT/_reports/alpaca_missing_1D.csv` lists three symbols that returned no bars at all:
  `BHGE`, `FBHS`, `JEC`. They are expected to ingest as `no_data`.
- Cross-check files for the split check live in
  `SFAC_RAW_ROOT/us_equity/alpaca_sip_all/1D/us_<symbol>.csv` (6,711 files, the all-adjusted MS-US-1D
  copies, D-021: cross-check only).

## Scope

### 1. Ingest (existing code, run in chunks — D-385)
```
uv run sfac data ingest alpaca --timeframe 1D --set-reference --symbols <chunk>
```
- Symbol list = `configs/universe/us_equity_daily.csv` (6,711 rows) **minus**
  `configs/universe/us_equity_daily_excluded.csv` (`symbol, reason, evidence`), which T04i produces
  by applying D-383 (old name covered by the current name → excluded; ticker re-used by another
  company → excluded for now). Exclusions live in that committed file, never hard-coded, and a
  symbol that is a Moneta mapping target is **kept** and reported to stream A instead (D-388).
- Chunks of 250 symbols, one invocation per chunk, appended to a log with a timestamp per chunk.
  Idempotent and re-runnable (identical content → the stored snapshot is returned, `register` is a
  no-op for a known key, `set_reference` returns early).
- **Measured cost** (scratch store, five symbols with 11 year-files each): ≈ 0.5 s per symbol for
  adapter + hash + write, plus a catalog/events rewrite per symbol that grows with the catalog
  (0.02 s at 6,711 rows in a synthetic run, more with real `raw_refs`). Budget **1.5–3 hours** wall
  clock for the full set and say the real number in the review. Snapshot size ≈ 85 KB for a
  2,693-bar large cap → **≈ 0.4–0.6 GB** for the set. 165 GB free on `D:`.
- If the per-symbol catalog rewrite turns out to dominate, the allowed remedy is a **batched
  registration** API (`Catalog.register_many` / `set_reference_many`) that writes the catalog and the
  events file once per chunk. It must keep the same invariants: one reference per `(symbol,
  timeframe)`, an event row per change, atomic write, and the existing single-writer assumption. Any
  such change needs its own tests; it is **not** allowed to drop events or to skip the
  already-registered check.

### 2. Split check (F-0.1.9 groundwork, existing code)
`ingest_alpaca_symbol` already runs `check_splits` against the MS-US-1D cross-check and
`configs/data/known_splits.csv`, appending to
`SFAC_RAW_ROOT/_reports/alpaca_split_check_1D.csv`.

Report in the review:
- the verdict distribution (`adjusted`, `market_move_both`, `no_crosscheck`, `unexplained_ingested`,
  `unexplained_crosscheck`, `mismatch`, `missing`);
- **every known split** from `known_splits.csv` with its verdict — the T04e expectation is
  `adjusted`, including **AVGO 2024-07-15**. A known split that is not `adjusted` is a finding, not
  a rounding issue;
- the symbols carrying a split warning in their snapshot `notes`;
- how many symbols had **no** cross-check file.

### 3. Quality reports (F-0.1.6)
```
uv run sfac data quality --all
```
per chunk, with the T04f calendar in place.
- `missing_bars` and `session_violations` must be **executed**, never `skipped` (without the
  calendar they are silently skipped and the snapshot still reports `ok` — see T04f).
- `_quality/summary.md` will have ~7.5 k rows once the 1H set is included. If that is unwieldy,
  split it per timeframe; see **P-64**.
- Aggregate in the review: count per `quality_status`, the twenty worst `missing_pct`, every
  `critical`, and the count of snapshots whose `zero_volume` or `stale_prices` check failed
  (expected to be common among delisted micro caps — report, do not suppress).

### 4. Catalog and store integrity
After the run, assert and report:
- catalog row count = ingested symbols; exactly one `is_reference = true` per `(symbol, '1D')`;
- every catalog row has `hash_version = 2` and `source = 'alpaca'`, `asset_class = 'us_equity'`,
  `session` = the D-033 value, `adjustment = 'split'`, `feed = 'sip'`;
- every `snapshot_hash` has both a `.parquet` and a `.meta.json` in the store, both read-only;
- the catalog events file contains one `register` and one `set_reference` per symbol;
- re-running one chunk writes nothing and changes no catalog row.

## Out of scope
- Any download (D-031).
- Dukascopy and Yahoo ingest (deferred, see the runbook).
- Registering snapshots or splits in the PostgreSQL registry — see **P-63**.
- `SplitManager` development/holdout splits over the new snapshots (T05 code exists; running it over
  6,711 symbols is a separate decision).

## Acceptance
- Every symbol of `us_equity_daily.csv` minus the confirmed exclusions has a 1D snapshot and is its
  reference, or is reported as `no_data` (expected: `BHGE`, `FBHS`, `JEC`) or `failed` with a reason.
- Snapshot metadata carries the **decided D-033 `session`** value; proved by reading a `.meta.json`
  and the catalog.
- The split-check report is complete and every known split is `adjusted`, or each exception is
  explained in the review.
- Every 1D snapshot has a quality report and a recorded `quality_status`; **no** schedule check is
  `skipped`.
- Idempotence: re-running a chunk writes nothing and adds no catalog or event row.
- `uv run pytest -m "not slow"`, `tests/parity tests/leakage`, `uv run pytest -m db` (0 skipped),
  `ruff check`, `ruff format --check`, `mypy src` all pass; no network in tests.

## Review summary
`docs/reviews/T04g_review.md`: symbols ingested / no_data / failed / excluded with reasons; the
split-check verdict distribution and the known-split table; the quality aggregate and every
`critical`; the catalog-integrity assertions; wall-clock time and store size; whether batched
registration was needed and what it changed; deviations and open questions.
