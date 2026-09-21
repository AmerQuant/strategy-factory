# T04h review — Alpaca 1H ingest

**Task:** `docs/tasks/T04h_alpaca_hourly_ingest.md` · **Branch:** `b/T04h-alpaca-hourly-ingest` from `main` (`5babc6e`, T04k merged)
**Features:** F-0.1.2 (Alpaca adapter, coverage gate), F-0.1.6 (quality report per symbol), F-0.1.8 (immutable snapshots, catalog)
**Decisions used:** D-010, D-022, D-023, D-024, D-025, D-028, D-029, D-383, D-385, D-386, D-391, D-104/D-150 (how 1H is used), D-396/D-398/D-700…D-706 (what T04k does and does not cover)
**Open for the supervisor:** **P-81** (does 1H need its own cleaning pass), **P-82** (the re-use sweep misses a long gap without a price break — found here)
**Status:** complete; PR open, **waiting for "Approved. Merge"**.

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/coverage.py` | the raw coverage table per symbol and year (latest file version, manifest `row_count`, `required`, `missing`) and the gap list |
| `src/strategy_factory/data/cli_alpaca.py` | `sfac data coverage alpaca --timeframe …` → `SFAC_RAW_ROOT/_reports/alpaca_coverage_<tf>.csv`, exit 1 on a gap; `sfac data ingest alpaca` **refuses** a gapped set for `coverage.gate_timeframes` and writes nothing. No `--allow-gaps` (P-62) |
| `src/strategy_factory/data/config.py`, `configs/data/alpaca.yaml` | `coverage.gate_timeframes: [1H]`, `coverage.require_from: first_data_year` (rule 1) |
| `scripts/ingest/T04h_ingest_hourly.py` | runs the coverage gate, then one `sfac data ingest alpaca --timeframe 1H --set-reference` per chunk of 100 (D-385), logged to `<store>/_logs/T04h_ingest_1H.log` |
| `scripts/analysis/T04h_verify.py` | every figure in §3–§6, read from the **written snapshots** |
| `docs/reviews/T04h_short_sessions.csv` | every session with fewer bars than the calendar implies (13,520 rows) |
| `docs/reviews/T04h_hourly_wick_flags.csv` | hourly bars the D-703/D-706 wick rule flags, per symbol (P-81 (c), report only) |
| `docs/reviews/T04h_long_gaps.csv` | every gap ≥ `gap_days` in every current 1D and 1H reference, with its price move (P-82) |
| tests | `tests/unit/test_F_0_1_2_coverage.py`, 8 new |

Nothing is cleaned: **the hourly snapshots are the raw hourly series** (task, "Update 2026-09-21").

## 2. Coverage gate (§1)

```
uv run sfac data coverage alpaca --timeframe 1H --universe configs/universe/us_equity_hourly.csv
```

| year | files | missing | empty files | bars |
|---|---|---|---|---|
| 2016 | 806 | 0 | 57 | 1,638,477 |
| 2017 | 806 | 0 | 61 | 1,636,399 |
| 2018 | 806 | 0 | 63 | 1,683,370 |
| 2019 | 806 | 0 | 73 | 1,684,618 |
| 2020 | 806 | 0 | 77 | 1,836,714 |
| 2021 | 806 | 0 | 77 | 1,812,917 |
| 2022 | 806 | 0 | 81 | 1,787,325 |
| 2023 | 806 | 0 | 93 | 1,761,943 |
| 2024 | 806 | 0 | 94 | 1,836,670 |
| 2025 | 806 | 0 | 92 | 1,906,138 |
| 2026 (partial, never required) | 806 | 0 | 98 | 1,424,458 |

**Gate passed: 0 required years missing.** An "empty" file is present — the download asked and the
feed had nothing (a symbol before its listing or after its delisting). `CCE` has **no bar in any
year** and ends as `no_data`. The full table is `SFAC_RAW_ROOT/_reports/alpaca_coverage_1H.csv`.

## 3. The ingest (§2)

`uv run python scripts/ingest/T04h_ingest_hourly.py` — 9 chunks (8 × 100 + 6), **5.1 min**, every chunk
`rc=0`:

| | symbols |
|---|---|
| hourly universe (post-T04f, D-383 applied) | 806 |
| **ingested, reference for `(symbol, 1H)`** | **805** |
| `no_data` | 1 (`CCE`) |
| `unadjusted_split` / failed / excluded | 0 / 0 / 0 |

Store: **805 snapshots, 371.4 MB**, all `hash_version = 2`. Split-check warnings (`unexplained_*`,
`mismatch`) are logged per symbol, as in T04g; none is an unadjusted known split — T04i had already
shown the 1H known-split table matches the 1D one.

**No snapshot for a dropped old ticker:** none of the **26** tickers T04f removed (D-383) has a 1H
snapshot; `FB` has none; `META`'s notes record `Historical (S&P 500 PIT) ticker: FB|META`.

**Idempotence.** Re-running chunk 1 (100 symbols) and chunk 9 (6) with `--set-reference`: every
symbol reported `ingested` (the stored snapshot returned), and `catalog.parquet` (sha256
`3f4e0be4b6e0a982…`), `catalog_events.parquet` (**81,852** rows, `69f08e995ff51326…`) and the 805 1H
parquet files were **identical before and after**.

## 4. The session filter on the real data (§3, D-023)

- **New-York hours kept: exactly 09, 10, 11, 12, 13, 14, 15** (1.91–1.93 M bars each).
- **Bars outside the session: 0**; sessions with **more** bars than the calendar: **0**.
- Bars per session against `nyse_sessions.csv`:

  | calendar | 1 bar | 2 | 3 | 4 | 5 | 6 | 7 |
  |---|---|---|---|---|---|---|---|
  | early close (4 expected) | 13 | 12 | 28 | **14,997** | — | — | — |
  | regular (7 expected) | 2,611 | 1,402 | 1,123 | 1,420 | 2,276 | 4,635 | **1,903,885** |

- **13,520 short sessions on 689 symbols**, every one in `T04h_short_sessions.csv`. The worst dates are
  the feed defects T04i and T04k already named: 2021-04-19 (446 symbols), 2021-10-25 (405),
  2022-03-08 (363), 2022-01-24 (346), 2018-05-03 (197), 2018-05-02 (196). **AAPL 2018-05-02 and
  2018-05-03 have 1 bar each**, as the task predicted. They are data, not a bug: they appear in the
  quality reports as `missing_bars`.

## 5. Quality (§4, F-0.1.6, D-391)

```
uv run sfac data quality --all --timeframe 1H
```

| status | 1H references |
|---|---|
| ok | 381 |
| warning | 424 |
| **critical** | **0** |

(The run covered 808 snapshots: the 805 plus the three Dukascopy 1H pilots, whose reports did not change.)

- **`missing_bars` and `session_violations` ran on all 805** — neither is `skipped` anywhere.
  **`session_violations`: 0 symbols.**
- `skipped` on all 805, as expected: `dst` ("source is UTC, not exchange-local" — the DST check is for
  exchange-local sources) and the two daily-only T04k checks ("not a daily series"). None is a
  schedule check.
- **The ten worst `missing_pct`:** `PCL` 98.65, `CAM` 89.66, `POM` 89.54, `SPLS` 81.31, `CSRA` 78.51,
  `Q` 74.28, `NFX` 70.58, `CA` 68.31, `EMC` 67.44, `APC` 60.76. **They are spliced tickers, not thin
  feeds** — see §6 and P-82.
- **D-391:** the run wrote `summary_alpaca_1H.md` and the index; **`summary_alpaca_1D.md` is
  byte-identical** (md5 `f3b0e4f1…` before and after), and so is `summary_dukascopy_1H.md`
  (`4a137629…`).

## 6. What T04k does not cover for 1H — P-81, and a finding — P-82

**P-81.** 1H is a research timeframe (D-104, D-150), so the daily clean reference does not protect it.
Measured on the hourly data (task, "Update 2026-09-21"): **frozen stretches do not exist in the hourly
feed** (4 RTH bars on the 11,180 days T04k cut from 20 hourly symbols' daily series); the **RTH-extreme
cap does not apply** (the hourly series *is* RTH); **bad prints are rare** — the D-703/D-706 rule flags
**156 bars on 105 of the 805 references** (`PARA` 17, `STI` 6, `LLL` 5, …); **re-use boundaries do
matter**. T04h builds no cleaning; P-81 recommends no general hourly pass, and that T04l applies its
boundaries to 1H too.

**P-82 (new).** The hourly worst-`missing_pct` list is a list of re-used tickers: `PCL` has 231 hourly
bars in 2016 (Plum Creek, ~40 USD) and 22 in 2025–26 (a new listing, ~50 USD); `Q` (2016–17, then
2025–26), `CSRA`, `CAM`, `POM` likewise. `CAM` and `POM` are T04k re-use candidates (kept,
`one_name`), but **`PCL`, `Q` and `CSRA` never became candidates**: the sweep (D-383/D-398,
`relisting.py`) needs a gap of `gap_days` **and** a price-level break above `jump_threshold`
(40 %), and these re-listed near the old price. Over every current reference
(`T04h_long_gaps.csv`):

| gap ≥ 200 days | 1D gaps / symbols | 1H gaps / symbols |
|---|---|---|
| with a level break (T04k candidates) | 199 / 195 | 23 / 23 |
| **without** a level break | **92 / 87** | **4 / 4** (`CSRA`, `DOW`, `EMC`, `Q`) |

Of the 92 daily ones, 70 (65 symbols) are gaps left where T04k cut frozen padding and 22 are raw gaps
(`PCL` 3,451 days, `AYA` 3,199, `CSRA` 3,053, `Q` 2,911, `HAWK` 2,884, …). These references splice two
companies today. P-82 proposes widening T04l's candidates to every gap of `gap_days` or more and
letting the CUSIP decide. **Nothing was changed** — it is a rule of the merged T04k pass, not of T04h.

## 7. Acceptance criteria

| criterion | proof | result |
|---|---|---|
| the coverage report exists and is in the review | §2; `_reports/alpaca_coverage_1H.csv` | pass |
| gate passed or stopped with nothing written; no `--allow-gaps` | §2 (passed); `test_F_0_1_2_T04h_the_1h_ingest_refuses_a_gapped_set_and_writes_nothing` (refusal, no snapshot, no such option), `…_a_missing_year_is_a_gap`, `…_an_empty_file_is_present_not_a_gap`, `…_a_later_listing_does_not_trip_the_gate`, `…_a_symbol_without_any_file_misses_every_year`, `…_the_partial_year_is_not_required`, `…_the_latest_version_of_a_year_is_read`, `…_the_coverage_command_writes_the_report…` | pass |
| every universe symbol has a snapshot, is the reference, `hash_version = 2` | §3: 805 of 806 (`CCE` `no_data`, no bar in any year), all references, all v2 | pass |
| hours exactly 09–15; bars per session match the calendar with every exception listed | §4 | pass |
| no snapshot for a dropped old ticker; `FB` none; `META` records `FB` | §3 | pass |
| every 1H snapshot has a report and `quality_status`; no schedule check `skipped` | §5 | pass |
| a re-run of a chunk writes nothing and changes no catalog row | §3, two chunks, byte-identical catalog and events | pass |
| gates green | §9 | pass |

## 8. Deviations

1. **`CCE` has no 1H snapshot** — the feed returned no bar in any year; `no_data`, as the plan expected.
2. The coverage report is written to `SFAC_RAW_ROOT/_reports/`, as the task says, beside the other
   generated reports there (`alpaca_missing_1H.csv`, …); no source file is touched (rule 11).
3. The idempotence proof is a real re-run on the store (two chunks), not a unit test; the unit-level
   property (identical content returns the stored snapshot, `register` is a no-op) is T04g's and
   T04a's, unchanged.
4. `sfac data quality --all --timeframe 1H` also re-ran the three Dukascopy 1H pilots; their summary is
   byte-identical.

## 9. Acceptance commands

```
uv run pytest -m "not slow"                            see PR
uv run pytest tests/parity tests/leakage tests/oracle  see PR
uv run pytest -m db                                     see PR
uv run ruff check . / ruff format --check .            clean
uv run mypy src                                        clean
uv run sfac streams check --base origin/main           ok (P-81, P-82 in range)
```

No new dependency. Nothing under `configs/costs/` or `configs/universe.yaml`; `SFAC_RAW_ROOT` read,
plus the one report under `_reports/`.

## 10. For the supervisor

- **"Approved. Merge"** for this PR.
- **P-81**: no general hourly cleaning pass; T04l applies its boundaries to 1H too.
- **P-82**: widen T04l's candidates to every long gap, with or without a price break — 87 daily and 4
  hourly references splice across one today.
- Then **T04l** (CUSIP), before T12.
