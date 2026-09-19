# T04e — Data-layer follow-up (review fixes, TLS bundle, renames, calendar, pilots)

**Features:** F-0.1.1, F-0.1.2, F-0.1.4, F-0.1.8, F-0.1.11 (groundwork) · **Priority:** MVP · **Depends on:** batch 1 merged into `main` (T00b, T02, T04a, T04b, T04c)
**Branch:** `feat/T04e-data-followup` from `main`.

Read first: `CLAUDE.md`, the five reviews in `docs/reviews/`, and this file. These are **supervisor decisions** from the review of batch 1 — implement them, do not reopen them.

## 0. Network runs happen outside Claude Code (supervisor finding)
Diagnosis showed that the Windows machine has **no TLS interception**: `requests` and `curl_cffi` connect fine from the user's PowerShell. The certificate errors, `SSLKEYLOGFILE` and `NODE_EXTRA_CA_CERTS` come from **Claude Code's own sandbox network proxy**. Consequences:
- **No CA-bundle workaround** is needed or wanted. The earlier `SFAC_CA_BUNDLE` idea is dropped. Keep the existing behaviour: a TLS error stops the command, and verification is never disabled.
- **You do not make real network calls in this task.** Everything that needs the network (pilots, the Alpaca calendar, the corporate-actions fetch, the PIT refresh) goes into one PowerShell script that the **user** runs outside Claude Code (section 8). Afterwards you analyse the files it produced.
- No `SSLKEYLOGFILE` guard in code.

## 1. Library-independent content hash (F-0.1.8)
- Replace the Arrow-IPC-based `content_hash` with a serialization that we own and that does not depend on any library:
  - a header (UTF-8 JSON, keys sorted): `{"hash_version": 2, "columns": [[name, dtype], ...], "rows": n}`;
  - then, for each canonical column in canonical order, its values as **little-endian** bytes: `ts` as int64 microseconds since the epoch (UTC), Float64 as IEEE-754 float64, Int64 as int64;
  - nulls: a validity bitmap per column (1 byte per row, 0/1), written before the values; the value slot of a null is 0;
  - NaN normalized to a single canonical NaN bit pattern.
- Add `hash_version: int` to `SeriesMetadata` (default 2) and to the catalog.
- **Existing pilot snapshots** (the 3 Dukascopy h1 ones) were written with version 1. Do not modify or delete them. Re-ingest the pilot data, which creates new version-2 snapshots, and move the references to them (catalog event note: `rehash v1→v2`).
- Tests:
  - identical hash across row order, column order, chunking and Parquet codecs (keep the existing tests);
  - a **pinned golden hash** of a fixture computed from the specification above; also compute it once independently in the test using `struct`/NumPy, not the implementation, so the specification itself is tested;
  - NaN and null handling;
  - any single value change changes the hash.

## 2. `asset_class` becomes a fixed enumeration (F-0.1.1)
- `Literal["us_equity", "fx", "metal", "energy_cfd", "index_cfd", "futures", "crypto", "iran_equity", "aux"]`.
- Update the adapters:
  - Alpaca → `us_equity`;
  - Dukascopy → from `configs/universe/dukascopy.csv`, mapped to fx / metal / energy_cfd / index_cfd;
  - Yahoo → `aux` (not `aux_index`).
- Tests reject any other value.

## 3. Close-time fields for auxiliary series (F-0.1.11 groundwork)
- New optional `SeriesMetadata` fields `value_final_time_local` (HH:MM), `value_final_tz` (IANA) and `value_final_status` (`verified` | `to_verify`), stored in the catalog. The Yahoo adapter fills them from `configs/universe/aux_yahoo.csv` instead of `notes`.
- Decided rule, to be written into config now and used later by the as-of join (F-0.1.11): **a series whose status is `to_verify` is used with one extra day of lag.** Config key `aux.unverified_extra_lag_days: 1`. Only `verified` series (currently ^VIX, 16:15 America/New_York) use the normal as-of rule.

## 4. (dropped — see section 0)

## 5. Symbol changes in the S&P 500 point-in-time list (F-0.1.2)
- Source: **Alpaca corporate actions**. First check **offline**, in the installed alpaca-py source and its models, whether the corporate-actions API returns symbol/name changes with old symbol, new symbol and date. Report what you find.
  - If it does: implement the fetch (it is run by the user's pilot script) and build `configs/universe/symbol_changes.csv` (`old_symbol, new_symbol, effective_date, source`) for all PIT tickers. Add `configs/universe/symbol_changes_manual.csv` (same columns, initially empty) for overrides; manual rows win.
  - If it does not provide them: **stop and report**, with the alternatives you found.
- Hourly universe: download under the **current** symbol and keep membership dates from the PIT list. Record both symbols in the universe file (`symbol`, `pit_symbol`). Snapshot metadata keeps `source_symbol` = the requested symbol, with the historical ticker in `notes`.
- In the pilot, verify that Alpaca returns pre-rename history under the new symbol (META before 2022-06-09).

## 6. NYSE calendar from Alpaca (replaces the hand-written early-close list)
- Implement a fetch, via alpaca-py's trading calendar endpoint (run by the user's pilot script), of open/close times for every session day 2016-01-01 → the end of the current year. Store it raw (immutable), then generate `configs/calendars/nyse_sessions.csv` (`date, open_local, close_local`).
- The hourly adapter uses this file (the close time decides the last bar). Compare it with the existing `nyse_early_closes.yaml` and report the differences. Then delete the YAML.

## 7. Dukascopy scope
- The full download is **h1 only** (bid + ask). m1 stays implemented but is not part of the standard run. Document it as "only for F-0.3.5 intrabar resolution, run slowly when needed".
- The hourly spread profile (F-0.2.2, later) is built from h1 bid/ask closes. Note this in the Dukascopy config comments.
- The prerequisite in README is "Node.js 20 or newer".

## 8. Pilots — two phases

**Phase A (you):** write `scripts/pilots/T04e_pilots.ps1`. It runs from the repo root in the user's PowerShell, stops on the first error, and appends all output to `SFAC_RAW_ROOT/_reports/pilot_T04e_<timestamp>.log`. In order, it:
1. fetches the Alpaca calendar (section 6) and the symbol changes (section 5), and refreshes the universe files;
2. **Alpaca:** downloads and ingests 1D and 1H for `AAPL, MSFT, NVDA, AVGO, TSLA, SPY, QQQ, GLD, ALXN, META`;
3. **Yahoo:** downloads and ingests all 7 tickers. Yahoo may answer HTTP 429 — rely on the existing backoff, with a pause of at least 5 s between tickers;
4. **Dukascopy:** re-ingests the h1 pilot (version-2 hash);
5. runs `sfac data list`.

Then **stop and tell the user** to run it:
```
powershell -ExecutionPolicy Bypass -File scripts\pilots\T04e_pilots.ps1
```
and to reply "pilots done". Do not continue until then.

**Phase B (you, after "pilots done"):** read the log, `raw/_reports/*` and the catalog, and report:
- **Alpaca:**
  - the split-check table (expected `adjusted` for the known splits, including AVGO 2024-07-15);
  - hourly bars per regular day (7) and per half-day (4);
  - META history before 2022-06-09;
  - the **daily session decision**: compare the daily high/low with the max/min of that day's RTH hourly bars. If the daily range always stays within RTH, set `session="RTH"` for 1D; otherwise keep `exchange` and report how often and by how much it differs. This may require re-ingesting 1D, which you can do yourself because ingest is local.
- **Yahoo:** the first and last dates, and the ^TNX quote scale.
- **Dukascopy:** the new version-2 snapshots and the references moved to them.
- **Calendar:** the difference report from section 6.

If the user reports a TLS or network error from phase A, stop and report it. Add no workaround.

## Acceptance
- ruff, format, mypy (strict for `data`), pytest all pass. CI green (no network in tests).
- Phase A script delivered; phase B analysis complete, or the task stopped with a precise report.
- **No full downloads.** Give the final commands for the user:
  - Alpaca 1D and 1H;
  - Dukascopy h1;
  - Yahoo.

## Review summary
Write it to `docs/reviews/T04e_review.md`. Include:
- the hash specification and the golden-hash value;
- how renames are handled (and what the API returns);
- the calendar difference report;
- the pilot tables;
- the daily-session decision with its evidence;
- deviations and open questions.
