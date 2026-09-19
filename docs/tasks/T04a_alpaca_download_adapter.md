# T04a — Alpaca SIP downloader and adapter (US equities)

**Features:** F-0.1.2 (Alpaca adapter), F-0.1.9 (split consistency check — pulled forward) · **Priority:** MVP · **Depends on:** T00b, T02

Read first: `CLAUDE.md`, `docs/design.md` §5, `docs/data_inventory.md` (groups MS-US-1D, QP-US-EQ-1H), features F-0.1.1/F-0.1.2/F-0.1.9, and the decisions below.

## Decisions (fixed — do not change)

| Item | Decision |
|---|---|
| Client library | **alpaca-py** (official SDK), wrapped in a thin module so it can be swapped later |
| Feed | **SIP** for both daily and hourly (historical data older than 15 min) |
| Adjustment | **`split` only** (TradingView-like price basis) |
| Daily universe | every symbol present in the raw copy of MS-US-1D (`SFAC_RAW_ROOT/us_equity/alpaca_sip_all/1D/us_*.csv`, 6711 incl. delisted) |
| Hourly universe | **S&P 500 point-in-time members since 2016-01-01 + main ETFs** (~1000 symbols) |
| History start | 2016-01-01 |
| Hourly session | keep bars labelled **09:00–15:00 America/New_York** only (drop 08:00, 16:00 and any other extended-hours bars). The 09:00 bar contains 09:00–09:30 pre-market; record this in metadata (`session = "RTH_hour_aligned"`, note text) |
| Daily stamp | session date at 00:00 UTC (Alpaca returns midnight New York → convert to the session date) |
| Existing data | the raw copy of MS-US-1D (SIP, adjustment=all) is **cross-check only**, never reference. Read existing data **only from `SFAC_RAW_ROOT`**, never from the old project folders |

## Secrets & network

- Credentials only from environment variables `ALPACA_API_KEY` and `ALPACA_API_SECRET` (loaded via `.env`, which is git-ignored). Add both names to `.env.example` with empty values.
- **Never** read keys from any other project, never print or log them, and never put a default value in code.
- This machine intercepts TLS. If requests fail with certificate errors, **stop and report**. Do not disable certificate verification and do not add a CA/truststore workaround on your own. The supervisor will present the options.

## Scope

### 1. Universe files (`configs/universe/`)
- `us_equity_daily.csv`: symbols from the file names in `SFAC_RAW_ROOT/us_equity/alpaca_sip_all/1D/`. Columns: `symbol, source_of_listing`.
- `us_equity_hourly.csv`: the S&P 500 point-in-time members since 2016 + ETFs.
  - **Point-in-time members:** first inspect **read-only** how `MarketScanner/scripts/host_download_us_pit.py` built its PIT list (source, method). Report it, then reuse that source/method in our own code. If it depends on scraping or on a file that no longer exists, **stop and ask** before choosing another source.
  - **ETFs:** the symbols under `market_slug` `etfs`, `indices` and `commodities` in `SFAC_RAW_ROOT/reference/marketscanner/symbols.csv`.
  - Columns: `symbol, reason (sp500_pit|etf), first_member_date, last_member_date` (empty for ETFs).
- Record provenance (source, date built) in a comment header or a sidecar `.meta.json`.

### 2. Downloader (`data/download/alpaca.py`)
- `sfac data download alpaca --timeframe {1D,1H} --universe <csv> [--start 2016-01-01] [--end <date>] [--symbols AAPL,MSFT]`
- Uses alpaca-py `StockHistoricalDataClient` with multi-symbol requests, `feed=SIP`, `adjustment=SPLIT`.
- **Rate limiting:** stay under 180 requests/min with a token bucket. Retry with exponential backoff and jitter on 429/5xx. Give up on a request after N retries and continue with the next symbol, logging the failure.
- **Resumable:** keep a manifest of completed (symbol, year) chunks. Re-running skips completed chunks.
- **Raw output (immutable):** `SFAC_RAW_ROOT/us_equity/alpaca_sip_split/<timeframe>/<SYMBOL>/<YEAR>.parquet`, stored exactly as returned (UTC timestamps, all bars including extended hours, all columns). Next to each file goes a manifest JSON with request parameters, download time, row count and sha256. Never overwrite a completed raw file. A re-download goes to a new file name with a suffix, and the old one is kept.
- Symbols with no data (delisted before 2016, renamed) are logged in `SFAC_RAW_ROOT/_reports/alpaca_missing_<timeframe>.csv`, not treated as errors.

### 3. Adapter (`data/adapters/alpaca.py`, F-0.1.2)
- `to_canonical(raw_paths)` → canonical frame + `SeriesMetadata` (`source="alpaca"`, `feed="sip"`, `adjustment="split"`, `volume_quality="full"`, `price_type="trade"`, `bar_label="start"`, `raw_refs` with sha256).
- Daily: stamp → session date 00:00 UTC. Hourly: session filter as in the decisions table. Keep `vwap` and `trades`.
- Deduplicate overlapping raw chunks deterministically. If two chunks disagree on the same timestamp, flag it as critical instead of silently keeping one.
- `sfac data ingest alpaca --timeframe {1D,1H} [--symbols ...]`: raw → snapshots via the T02 store. It sets the new snapshot as reference only if there is no reference yet or `--set-reference` is passed.

### 4. Split consistency check (F-0.1.9)
- For each ingested symbol, compare day-over-day close ratios with the raw copy of MS-US-1D (cross-check source) around known splits. Also detect any overnight move beyond ±40% that is not explained in both sources.
- Output `SFAC_RAW_ROOT/_reports/alpaca_split_check_<timeframe>.csv` with symbol, date, ratio, verdict. A mismatch is a warning in the catalog notes. It does not block ingest.

## Tests (no network in tests)
- Mock the alpaca-py client with recorded fixture responses (small, committed under `tests/fixtures/alpaca/`), including a delisted symbol, a split (AAPL 2020-08-31), a half-day and a DST change week.
- **F-0.1.2:**
  - Daily stamps map to the correct session date across DST.
  - Hourly keeps only 09:00–15:00 NY bars and there are 4 bars on a 13:00 half-day.
  - Metadata fields are correct.
  - Duplicate-chunk handling works, including the disagreement → critical case.
- **Downloader:**
  - Resume skips completed chunks.
  - Rate limiter never exceeds the budget (simulated clock).
  - Retries on 429.
  - Raw files are never overwritten.
  - Missing symbols are reported.
- **F-0.1.9:** a synthetic unadjusted split is detected; an adjusted one passes.
- **Secrets:** a test asserts no log line contains the key values (use fake keys).

## Acceptance
0. If `ALPACA_API_KEY`/`ALPACA_API_SECRET` are not set, build and test everything with mocks, skip the pilot, and say so in the review summary.
1. All previous acceptance commands pass; CI green.
2. **Pilot run (real network)** with `--symbols AAPL,MSFT,NVDA,AVGO,TSLA,SPY,QQQ,GLD` plus one delisted S&P member you identify from the PIT list: download 1D and 1H, then ingest.
   - The split check table shows **adjusted** for AAPL 2020, NVDA 2021 and 2024, TSLA 2020 and 2022, and **AVGO 2024-07-15**.
   - Hourly bars per regular day = 7.
   - `sfac data list` shows the snapshots.
3. **Do not** run the full universe download. Report the exact commands the user should run for it and an estimate of request count and duration.

## Review summary
Files, dependencies (alpaca-py version and anything it pulled in), how the PIT list was built (source and method), pilot results (tables), the full-download commands and estimate, deviations, open questions.
