# T04b review — Dukascopy downloader (dukascopy-node) and adapter

**Features:** F-0.1.3, F-0.2.2 groundwork · **Branch:** `feat/T04b-dukascopy` (based on `feat/T04a-alpaca`) · **Status:** done — pilot h1 complete and ingested; pilot m1 4 of 6 month files (2 persistently throttled by Dukascopy, HTTP 429)

## Tool
- **dukascopy-node 1.50.0** (latest on npm on 2026-09-19), pinned in `tools/dukascopy/package.json` + `package-lock.json`, installed with `npm ci --ignore-scripts` (no install scripts run). Node.js v26.5.1 / npm 11.17.0 on this machine. `node_modules/` is git-ignored. Node is **not** a Python dependency; CI does not need it (tests mock the subprocess).
- Called as `node tools/dukascopy/node_modules/dukascopy-node/dist/cli/index.js` (the package `bin`), one **instrument × side × calendar month** per call. Exact flags (all from `configs/data/dukascopy.yaml`, recorded in every manifest):
  ```
  --instrument <id> --date-from YYYY-MM-01 --date-to <next month>-01   (date-to is exclusive: verified, 24 bars for one day)
  --timeframe h1|m1 --price-type bid|ask --utc-offset 0 --volumes --volume-units units
  --format csv --directory <temp> --file-name out --silent
  --batch-size 5 --batch-pause 2000 --retries 5 --retry-pause 5000
  ```
  Output verified on a probe: `timestamp,open,high,low,close,volume`, `timestamp` = epoch ms, UTC, **bar start** (first h1 bar of 2024-01-02 = 00:00 UTC).
- Wrapper retry on top of the tool's: a month whose call still ends in HTTP 429/5xx is re-run up to `call_retries` (3) times with backoff 30 s × 2^n.

## Instrument-id verification
All 29 ids exist in the pinned tool's own `instrumentMetaData` (`tools/dukascopy/list_instruments.js`); no id had to be corrected. `configs/universe/dukascopy.csv` is generated from that metadata by `tools/dukascopy/build_universe.py` (the notes carry name, tool version and the first h1/m1 dates).

| group | ids (symbol = upper-case id) | first h1 month (tool metadata) |
|---|---|---|
| FX majors | eurusd, gbpusd, usdjpy, usdchf, audusd, usdcad, nzdusd | 2003-05 / 2003-08 → h1 from **2010-01** |
| FX crosses | eurjpy, gbpjpy, eurgbp, eurchf, audjpy, euraud, gbpchf, cadjpy | 2003–2005 → **2010-01** |
| metals | xauusd, xagusd | 2003-05 → **2010-01** |
| energy CFD | lightcmdusd (WTI), brentcmdusd | **2011-09**, **2010-12** |
| index CFD | usa500idxusd, usatechidxusd, gbridxgbp, jpnidxjpy, fraidxeur | **2011-09** |
| | usa30idxusd, deuidxeur | **2013-09** |
| | hkgidxhkd | **2013-06** |
| | ausidxaud | **2014-06** |
| | ussc2000idxusd | **2018-08** |

Months before an instrument's first data are not requested.

## Files
| file | content |
|---|---|
| `src/strategy_factory/data/download/dukascopy.py` | `Tool.locate`, `build_command`, `fetch_month`, `run_dukascopy_download` (resume, never current month, empty report, throttle retry, TLS stop), `raw_pairs` |
| `src/strategy_factory/data/adapters/dukascopy.py` | `DukascopyAdapter.to_canonical` (bid/ask join, mid OHLC, spread, one-sided rule, negative spread, UTC-offset correction from the manifest) |
| `src/strategy_factory/data/cli_dukascopy.py` | `sfac data download dukascopy --series {h1,m1} [--instruments] [--from YYYY-MM] [--to YYYY-MM]`, `sfac data ingest dukascopy --series h1 [--instruments] [--set-reference]` |
| `src/strategy_factory/data/config.py` | `DukascopyConfig`, `DukascopyToolConfig`, `load_dukascopy_config` |
| `configs/data/dukascopy.yaml`, `configs/universe/dukascopy.csv` | settings and verified universe |
| `tools/dukascopy/{package.json,package-lock.json,list_instruments.js,build_universe.py}` | pinned tool + verification |
| tests | `tests/fixtures/dukascopy/h1/EURUSD/{bid,ask}/2024-03.csv.gz` + `make_fixtures.py`; `tests/unit/test_F_0_1_3_dukascopy.py` (15) |

## Design
- **Raw:** `raw/fx_metals_cfd/dukascopy/<series>/<INSTRUMENT>/<side>/<YYYY-MM>.csv.gz` = the tool's CSV, gzip with a fixed header (mtime 0, lossless). Manifest: tool version, exact command line (node path replaced by `dukascopy-node`), instrument/side/series/month, `utc_offset_minutes`, `volume_units`, `downloaded_at`, `row_count`, `sha256_uncompressed` (plus `sha256` of the stored gzip). Written via the shared immutable writer (hard link, read-only, `.vN` for re-downloads).
- **Resume:** a stored month (any version) is skipped; the last month requested is always ≤ the last complete month (UTC today), so the current month is never stored. Months that return only a header are stored (so they are not requested again) and listed in `raw/_reports/dukascopy_empty.csv`.
- **Adapter:** full join of bid and ask on `ts`; one-sided bars are counted and dropped; above `max_one_sided_share` (0.1 %) → critical `DataError`. OHLC = (bid + ask)/2 per field — **documented approximation for high/low**; `spread = ask_close − bid_close` (negative → critical); `volume` = bid volume. Metadata: `source=dukascopy`, `price_type=mid`, `session=24x5`, `bar_label=start`, `adjustment=raw`, `feed=none`, `volume_quality=partial`, `original_tz=UTC`, `timeframe=1H`, asset class from the universe file.
- **Ingest:** h1 only; m1 is kept raw for the later spread-profile task.

## Acceptance
| criterion | result |
|---|---|
| 1. previous acceptance commands | ✅ ruff, format, mypy (46 files), pytest **172 passed** |
| wrapper: command lines (subprocess mocked) | ✅ `test_F_0_1_3_command_line`, `_download_stores_gzip_with_manifest` (lossless gzip, manifest fields) |
| skips completed months; never stores current month; never overwrites | ✅ `_download_skips_completed_months_and_never_overwrites`, `_current_month_is_never_stored`, `_months_before_instrument_start_are_not_requested` |
| empty months reported; TLS stops; failures not stored; throttle retry | ✅ `_empty_months_are_reported`, `_tls_error_stops`, `_failed_call_is_reported_not_stored`, `_throttled_month_is_retried_with_backoff` |
| adapter: merge, mid/spread math, one-sided rule, UTC + bar-start, metadata | ✅ `_mid_and_spread_math`, `_one_sided_bars_rule` (1/73 dropped at a 2 % limit; critical at the default 0.1 %), `_negative_spread_is_critical`, `_utc_bar_start_and_weekend_gap` (Friday last bar 21:00, no Saturday, Sunday open 21:00 after US DST), `_utc_offset_from_manifest_is_corrected`, `_metadata` |
| 2. pilot (real network) | ✅ h1: 18/18 month files, ingested, `sfac data list` shows the 3 snapshots · ⚠️ m1 2024-03: 4/6 files; eurusd ask and xauusd bid failed with HTTP 429 after all retries (details below) |
| 3. full download not run; commands + estimates | ✅ below |

Fixtures are hand-built in the tool's CSV format (not recorded).

## Pilot results (eurusd, xauusd, usa500idxusd; h1 2024-01..03, m1 2024-03)
- **h1:** 18 month files stored (8,858 rows) in 25 s; 0 empty, 0 failed. Ingested → 3 snapshots, all set as reference (`sfac data list`):

| symbol | snapshot | rows | first ts | last ts | one-sided dropped |
|---|---|---|---|---|---|
| EURUSD | 899ac7451468 | 1,539 | 2024-01-01 22:00 UTC | 2024-03-31 23:00 UTC | 0 |
| XAUUSD | 4e135eb4225f | 1,447 | 2024-01-01 23:00 UTC | 2024-03-31 23:00 UTC | 0 |
| USA500IDXUSD | 4cf2fab5c95f | 1,443 | 2024-01-01 23:00 UTC | 2024-03-31 23:00 UTC | 0 |

- **Bars per ISO week** (2024-W01 … W13): EURUSD 98, 120 ×8, 121, 120 ×3 (24 × 5 = 120); XAUUSD 93, 115, 113, 115 ×4, 113, 115, 116, 115, 115, 92; USA500IDXUSD 93, 115, 111, 115 ×4, 111, 115, 116, 115, 115, 92 (23 h/day: daily 1-hour break; W01 = New Year, W13 = Good Friday 2024-03-29; shortened US-holiday sessions visible in W03 and W08).
- **EURUSD spread by UTC hour** (spread = ask_close − bid_close, pips; 64–65 bars per hour):

| UTC hour | 0–4 | 5–9 | 10–13 | 14 | 15–19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|
| mean | 0.24–0.26 | 0.29–0.32 | 0.25–0.27 | 0.36 | 0.21–0.25 | 0.58 | **1.89** | **1.36** | 0.31 |
| median | 0.2–0.3 | 0.3 | 0.2–0.3 | 0.3 | 0.2 | 0.3 | **1.4** | **1.2** | 0.3 |
| p90 | 0.3–0.4 | 0.4 | 0.3–0.4 | 0.8 | 0.3 | 1.3 | 3.4 | 2.3 | 0.4 |
| max | 0.4–0.9 | 0.4–1.0 | 1.2 | 1.2 | 0.9–1.6 | 6.4 | 7.2 | 3.7 | 0.7 |

  → tight during Asia/Europe/US sessions, widening around the 21:00–22:00 UTC rollover (as expected for the hourly spread profile).
- **m1 (2024-03):** 4 of 6 month files stored (109,540 rows: EURUSD bid, XAUUSD ask, USA500IDXUSD bid+ask; ≈ 350–390 KB gzip each). **EURUSD ask and XAUUSD bid failed with HTTP 429 (Too Many Requests)** on every attempt: first run with the default-like flags (batch 10, pause 1 s, 3 tool retries), then with batch 5 / pause 2 s / 5 × 5 s tool retries plus 3 wrapper retries (30/60/120 s, ≈ 13 min), then with batch 1 / pause 3 s / 10 × 10 s retries (scratch config). Not a TLS problem, so not a stop condition; nothing partial was stored and the months are simply requested again on the next run (resumable). m1 is not ingested now (spread-profile task).
- **Empty months:** none.

## Full download — commands and estimates
```bash
uv run sfac data download dukascopy --series h1          # all 29 instruments, 2010-01 (or start) .. last complete month
uv run sfac data download dukascopy --series m1          # all 29 instruments, last 24 complete months
uv run sfac data ingest dukascopy --series h1
```
| series | month files (calls) | size (gzip) | duration (estimate) |
|---|---|---|---|
| h1, 2010-01..2026-08 | 5,384 instrument-months × 2 sides = **10,768 calls** | ≈ 9.4 KB/file → **≈ 100 MB** | pilot ≈ 1.4 s/call → **≈ 4–5 h** |
| m1, 2024-09..2026-08 | 29 × 24 × 2 = **1,392 calls** | ≈ 367 KB/file → **≈ 0.5 GB** | ≈ 20–30 s/call without throttling → **≈ 8–12 h**; more if Dukascopy throttles (see below) |
Both are resumable: re-running the same command continues where it stopped.

## Deviations
- The task suggests `npx dukascopy-node --help`; the wrapper calls `node <package bin>` directly (npx on Windows needs a shell), with the version read from the pinned package.
- Tool flags were made gentler than the defaults (batch 5, pause 2 s, 5 retries × 5 s) and a wrapper-level throttle retry was added after the pilot hit HTTP 429 on m1.
- Empty months are stored as header-only files (so resume skips them) *and* reported.

## Open questions
1. **Dukascopy throttling of m1 (HTTP 429):** the full m1 download (1,392 month calls ≈ 40,000 daily artifacts) will hit the same limit. Options: run it slowly overnight with the gentle settings and re-run until complete (resumable), split m1 into weekly calls, or reduce the m1 universe to the instruments that need an hourly spread profile first. Which do you prefer?
2. **Canonical symbols:** I used the upper-case Dukascopy id (`EURUSD`, `XAUUSD`, `LIGHTCMDUSD`, `USA500IDXUSD`, …). Keep, or map to shorter names (e.g. `WTI`, `US500`)? Changing later means new snapshots.
3. Node.js on this machine is v26.5.1 (a "Current" release, not LTS). It works; should the documented prerequisite stay "Node.js LTS"?
4. Daily Dukascopy bars are built later from 1H (00:00 UTC boundary, Sunday → Monday merge, T05) — confirm no d1 download is wanted.
