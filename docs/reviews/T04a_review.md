# T04a review — Alpaca SIP downloader and adapter (US equities)

**Features:** F-0.1.2, F-0.1.9 · **Branch:** `feat/T04a-alpaca` (based on `feat/T02-schema-store`) · **Status:** partial — everything built and tested with mocks; **pilot skipped** (`ALPACA_API_KEY`/`ALPACA_API_SECRET` not set; runbook skip condition)

## Files
| file | content |
|---|---|
| `src/strategy_factory/data/config.py` | Pydantic config models + loaders: `AlpacaConfig` (history start, feed, adjustment, rate limit, retry, batch sizes, hourly session, split check), `EarlyCloses`, `KnownSplit` |
| `configs/data/alpaca.yaml`, `configs/data/known_splits.csv`, `configs/calendars/nyse_early_closes.yaml` | all decision numbers and calendars (no numbers in code) |
| `src/strategy_factory/data/download/ratelimit.py` | `TokenBucket`, `call_with_retry` (exp. backoff + jitter), error classes incl. `TLSVerificationError` |
| `src/strategy_factory/data/download/rawfiles.py` | immutable raw writer: temp file + hard link (never overwrites), `.vN` versions, sha256 manifest, read-only; `raw_root()` |
| `src/strategy_factory/data/download/alpaca.py` | `BarsClient` protocol, `AlpacaPyClient` (thin alpaca-py wrapper), `run_download` (year chunks, multi-symbol batches, resume, missing report) |
| `src/strategy_factory/data/adapters/alpaca.py` | `AlpacaAdapter.to_canonical` (daily session-date stamp, hourly 09:00–15:00 NY filter with early closes, dedupe/conflict check, metadata) |
| `src/strategy_factory/data/split_check.py` | F-0.1.9 check and report |
| `src/strategy_factory/data/universe.py` | daily universe from the raw MS-US-1D copy; hourly = S&P 500 PIT + ETFs; PIT CSV download into the raw store |
| `src/strategy_factory/data/ingest.py` | raw → adapter → split check → store → catalog (reference only if none, or `--set-reference`) |
| `src/strategy_factory/data/cli_alpaca.py` | `sfac data download alpaca`, `sfac data ingest alpaca`, `sfac data universe us-equity` |
| `configs/universe/us_equity_daily.csv` (+`.meta.json`) | 6,711 symbols |
| `configs/universe/us_equity_hourly.csv` (+`.meta.json`) | 827 symbols = 745 S&P 500 PIT members since 2016-01-01 + 82 ETFs |
| tests | `tests/fixtures/alpaca/{daily_2020,hourly_2024}.json` + `make_fixtures.py`, `tests/fixtures/alpaca_helpers.py`, `tests/unit/test_F_0_1_2_alpaca_adapter.py` (9), `test_F_0_1_2_alpaca_download.py` (12), `test_F_0_1_2_universe.py` (3), `test_F_0_1_9_split_check.py` (6) |

## Dependencies
- **alpaca-py 0.44.0** (runtime; the decided client). It pulled in: `requests 2.34.2`, `urllib3 2.8.0`, `certifi 2026.7.22`, `charset-normalizer`, `idna`, `pandas 3.0.6`, `numpy 2.5.3`, `python-dateutil`, `pytz`, `six`, `msgpack`, `websockets 17.1`, `sseclient-py`. pandas is only used inside alpaca-py; our data layer stays Polars-only (we request `raw_data=True`).

## How the S&P 500 point-in-time list was built
- **MarketScanner (inspected read-only):** `MarketScanner/scripts/host_download_us_pit.py` downloads `S&P 500 Historical Components & Changes (Updated).csv` from the public GitHub dataset **fja05680/sp500** (`raw.githubusercontent.com`), keeps snapshots from 2015-12-01 and takes the union of tickers. No scraping, and the source still exists → reused.
- **Ours:** `sfac data universe us-equity` downloads the same CSV (stdlib `urllib`, default certificate verification) into `raw/reference/sp500_pit/fja05680_sp500_20260919.csv` (immutable, manifest with sha256 `36326709…0d54`). Method: the snapshot in force on 2016-01-01 plus every change snapshot after it; union of tickers; `first_member_date` = first snapshot date (clipped to 2016-01-01), `last_member_date` = last snapshot date listing the ticker (for current members the dataset's latest date, 2026-08-18). Result: 745 tickers.
- ETFs: `market_slug` ∈ {etfs, indices, commodities} of `raw/reference/marketscanner/symbols.csv` → 82 after de-duplication (none overlap with the PIT list).
- Daily universe: file names `us_<SYM>.csv` of the raw MS-US-1D copy; MarketScanner encoded `.` as `_` (`safe()` in its script), so `_` → `.` (`us_BRK_B.csv` → `BRK.B`).

## Design
- **Requests:** one calendar year per request, many symbols per request (batch 100 for 1D, 10 for 1H, in config), `feed=SIP`, `adjustment=SPLIT`, `end` = year end − 1 s.
- **Rate limit:** a `TokenBucket` with capacity `burst` (10) and refill `(180 − 10)/60 s` bounds any 60 s window at 180. One token is taken per **real HTTP request**: `AlpacaPyClient` replaces alpaca-py's private `requests.Session` with a budgeted subclass, so SDK pagination is counted. alpaca-py's own retry is set to 0, so ours is the only retry policy.
- **Retries:** 429/5xx/network → exponential backoff with jitter (base 2 s, cap 60 s, 5 retries); then the batch is logged as failed and the run continues (exit code 2 at the end). 4xx → no retry. **Certificate errors stop the run** (`TLSVerificationError`), verification is never disabled.
- **Raw:** `raw/us_equity/alpaca_sip_split/<tf>/<SYMBOL>/<YEAR>.parquet` holds the JSON fields exactly as returned (`t` RFC-3339 string, `o h l c v n vw`, including extended hours) + `<YEAR>.parquet.manifest.json` (request, client version, downloaded_at, row_count, sha256, `complete`). A chunk is `complete` only if it spans the whole year and the year is over; complete chunks are skipped on re-runs; an incomplete (current) year is re-downloaded to `<YEAR>.v2.parquet` etc. Symbols without any bars → `raw/_reports/alpaca_missing_<tf>.csv` (not an error; their empty chunks are complete, so they are not requested again).
- **Adapter:** daily `ts` = session date (from midnight New York) at 00:00 UTC; hourly keeps bars with New-York start ≥ 09:00 and end ≤ close (16:00, or 13:00 on dates in `nyse_early_closes.yaml`) → 7 bars on regular days, 4 on half-days. `vwap`, `trades` kept. Ingest uses the **latest version per year**; within the given files identical duplicate rows are dropped and differing values for one timestamp raise a critical `DataError`.
- **Split check (F-0.1.9):** on each known split date (`known_splits.csv`) the ingested day-over-day ratio must be ≈1 (`adjusted`); ≈1/split → `unadjusted`. Any other day with a move > ±40 % in either series is classified `market_move_both` (same move in both, |ln ratio| ≤ 0.02) or `unexplained_ingested` / `unexplained_crosscheck` / `mismatch`. Report `raw/_reports/alpaca_split_check_<tf>.csv`; warnings go into the snapshot notes, never block.

## Acceptance
| criterion | result |
|---|---|
| 0. no keys → build + test with mocks, skip pilot | ✅ keys not set in environment or `.env`; `sfac data download alpaca` exits 1 with a clear message; pilot skipped |
| 1. previous acceptance commands | ✅ `ruff check`, `ruff format --check` (102 files), `mypy src` (43 files, strict for `data`), `pytest` **157 passed**, `sfac data --help` |
| F-0.1.2 daily stamps across DST | ✅ `test_F_0_1_2_daily_stamp_is_session_date_across_dst` (raw 04:00Z EDT / 05:00Z EST → 00:00 UTC session dates) |
| hourly 09:00–15:00 only; 4 bars on a 13:00 half-day | ✅ `_hourly_keeps_0900_to_1500_ny_on_both_sides_of_dst` (7 bars, EST and EDT, UTC first bar 14:00 vs 13:00), `_hourly_half_day_has_four_bars` (2024-11-29 → 09,10,11,12) |
| metadata fields | ✅ `_metadata_fields` |
| duplicate chunks incl. disagreement → critical | ✅ `_identical_duplicate_chunks_are_deduplicated`, `_conflicting_duplicate_chunks_are_critical`, `_latest_version_is_used_for_ingest` |
| downloader: resume, rate limit (simulated clock), 429 retry, never overwrite, missing report | ✅ `_resume_skips_completed_chunks`, `_incomplete_year_is_redownloaded_to_new_version`, `_rate_limiter_never_exceeds_budget` (1,000 acquisitions, worst 60 s window ≤ 180), `_retries_on_429_then_succeeds`, `_gives_up_after_retries_and_continues`, `_backoff_is_exponential_with_jitter_and_capped`, `_permanent_error_is_not_retried`, `_tls_error_stops_the_download`, `_raw_files_are_never_overwritten`, `_missing_symbols_are_reported` |
| F-0.1.9 synthetic unadjusted split detected; adjusted passes | ✅ `test_F_0_1_9_synthetic_unadjusted_split_is_detected`, `_adjusted_split_passes`, plus unexplained/market-move/report-merge cases |
| secrets never logged | ✅ `_credentials_only_from_env_and_never_logged` (fake keys; builds the real alpaca-py client; scans all log records and written JSON) |
| end-to-end ingest + `sfac data list` | ✅ `test_F_0_1_2_ingest_end_to_end` (fixture raw → snapshot → reference → split report `adjusted` for AAPL 2020-08-31 → CLI list) |
| 2. pilot (real network) | ⏭️ **skipped — no API keys** |
| 3. full download not run; commands + estimate | ✅ below |

**Fixtures are hand-built, not recorded** (no key was available): same JSON shape as alpaca-py `raw_data=True`, plausible split-adjusted prices; covers a split (AAPL 2020-08-31), a delisted symbol (no data), a half-day (2024-11-29) and a DST week (2024-03-08/11) plus a daily DST switch (2020-10-30/11-02). Regenerate with `tests/fixtures/alpaca/make_fixtures.py`.

## Pilot and full download — commands for the user
Prerequisites: `ALPACA_API_KEY` and `ALPACA_API_SECRET` in `.env`; see the TLS note below.

Pilot (ALXN = S&P 500 member until its 2021 acquisition, present in the PIT list and the MS-US-1D copy):
```bash
uv run sfac data download alpaca --timeframe 1D --symbols AAPL,MSFT,NVDA,AVGO,TSLA,SPY,QQQ,GLD,ALXN
uv run sfac data download alpaca --timeframe 1H --symbols AAPL,MSFT,NVDA,AVGO,TSLA,SPY,QQQ,GLD,ALXN
uv run sfac data ingest alpaca --timeframe 1D --symbols AAPL,MSFT,NVDA,AVGO,TSLA,SPY,QQQ,GLD,ALXN
uv run sfac data ingest alpaca --timeframe 1H --symbols AAPL,MSFT,NVDA,AVGO,TSLA,SPY,QQQ,GLD,ALXN
uv run sfac data list
```
Expected: split check `adjusted` for AAPL 2020-08-31, NVDA 2021-07-20 and 2024-06-10, TSLA 2020-08-31 and 2022-08-25, AVGO 2024-07-15 (`raw/_reports/alpaca_split_check_1D.csv`); 7 hourly bars per regular day.

Full download:
```bash
uv run sfac data download alpaca --timeframe 1D --universe configs/universe/us_equity_daily.csv
uv run sfac data download alpaca --timeframe 1H --universe configs/universe/us_equity_hourly.csv
uv run sfac data ingest alpaca --timeframe 1D
uv run sfac data ingest alpaca --timeframe 1H
```
Estimate (2016-01-01 → yesterday ≈ 11 calendar years, 180 requests/min):
| | calls | HTTP requests (pages of 10,000 bars) | duration at 180/min | raw size (zstd parquet) |
|---|---|---|---|---|
| 1D, 6,711 symbols, batch 100 | 68 × 11 ≈ 750 | ≈ 750–2,300 (≤ 25,200 bars per call → ≤ 3 pages; many delisted/short histories) | ≈ 5–15 min | ≈ 0.2–0.4 GB |
| 1H, 827 symbols, batch 10 | 83 × 11 ≈ 913 | ≈ 3,700 (≈ 4,000 extended-hours bars per symbol-year → ≈ 4 pages) | ≈ 20–30 min + transfer time | ≈ 1–2 GB |
Re-runs are resumable; only the current year is re-requested.

## Deviations
- **Daily `session` = `exchange`:** the task does not define the daily session, and whether Alpaca's SIP daily bar is RTH-only or includes extended hours is not verified; the note says "as delivered". (Question 3.)
- **Early closes** come from `configs/calendars/nyse_early_closes.yaml` (2016–2026, written from NYSE's published schedules; please verify) — needed for "4 bars on a 13:00 half-day".
- **Raw columns** are Alpaca's JSON field names (`t,o,h,l,c,v,n,vw`), i.e. "exactly as returned" in raw mode.
- **Ingest picks the latest version per year**; the conflict check applies to whatever files are passed.
- **Cross-check file name** for the split check: `us_<SYM with . and / → _>.csv` in the raw MS-US-1D copy.
- **Config paths are relative to the working directory** (run `sfac` from the repo root).
- `universe.py` downloads with stdlib `urllib` (not alpaca-py/requests); it verifies certificates against the platform trust store by default.

## TLS / environment findings (important for the pilot)
1. **`SSLKEYLOGFILE` is set in this environment** (probably by a debugging/proxy tool). With it, Python's `ssl` crashes the process on this machine (`OPENSSL_Uplink … no OPENSSL_Applink`). I unset it only for my own `sfac data universe` command; nothing in code or on the system was changed. You may need to unset it (or run in a shell without it) for every Python download.
2. The PIT download over stdlib `urllib` verified fine (Windows trust store). **alpaca-py uses `requests` + `certifi`**, which does *not* use the Windows store; on a TLS-intercepting network the pilot will likely fail with a certificate error → the downloader stops with `STOP: TLS certificate verification failed` as required. The options (e.g. `truststore`, `REQUESTS_CA_BUNDLE` pointing to the corporate CA) are for the supervisor to present (HANDOFF §8.8); I did not add any workaround.

## Open questions
1. **Keys:** add `ALPACA_API_KEY`/`ALPACA_API_SECRET` to `.env` (and revoke the old hard-coded key), then run the pilot.
2. **TLS for alpaca-py** (see above): which option should be used on this machine?
3. **Daily bar session:** is Alpaca's SIP daily bar the regular session (09:30–16:00) or all hours? Decide `session` for 1D (`RTH` vs `exchange`) after the pilot (compare daily high/low with the hourly bars).
4. **Ticker changes in the PIT list** (e.g. `FB` → `META`, `ANTM` → `ELV`): the list uses historical tickers; Alpaca may return data only under the current symbol. The missing report will show them; should we map renames (source for a rename table?) or accept the gaps?
5. Please verify the NYSE early-close list (2016–2026) in `configs/calendars/nyse_early_closes.yaml`.
6. 2 hourly-universe symbols have no MS-US-1D cross-check file (split check reports `no_crosscheck`); acceptable?
