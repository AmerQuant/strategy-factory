# T04c review — Auxiliary series from Yahoo (yfinance)

**Features:** F-0.1.4, F-0.1.11 groundwork · **Branch:** `feat/T04c-yahoo` (based on `feat/T04b-dukascopy`) · **Status:** partial — built and tested with mocks; **pilot blocked by a TLS certificate error → batch stopped (runbook stop condition)**

## Tool
- **yfinance 1.7.0**, pinned exactly (`yfinance==1.7.0` in `pyproject.toml`). It pulled in: `curl-cffi 0.16.3` (its HTTP transport), `cffi`, `pycparser`, `beautifulsoup4`, `soupsieve`, `lxml`, `peewee`, `protobuf`, `multitasking`, `platformdirs`. mypy: yfinance ships no type information → one per-module `ignore_missing_imports` override for `yfinance`.
- Always called as `yfinance.Ticker(t).history(period="max", interval="1d", auto_adjust=False, actions=False)` (parameters from `configs/data/yahoo.yaml`, recorded in every manifest together with the yfinance version).

## Files
| file | content |
|---|---|
| `src/strategy_factory/data/download/yahoo.py` | `YFinanceClient` (edge: pandas → Polars without pyarrow), `run_yahoo_download` (pause, retry with backoff, immutable versions, revision check), `revision_diff`, TLS detection incl. errors yfinance only logs |
| `src/strategy_factory/data/adapters/yahoo.py` | `YahooAdapter.to_canonical` (session date 00:00 UTC, raw `Close`, volume quality, close-time notes) |
| `src/strategy_factory/data/cli_yahoo.py` | `sfac data download yahoo [--tickers]`, `sfac data ingest yahoo [--tickers] [--set-reference]` |
| `src/strategy_factory/data/config.py` | `YahooConfig`, `load_yahoo_config` |
| `configs/data/yahoo.yaml`, `configs/universe/aux_yahoo.csv` | settings; the 7 series with close-time metadata |
| `tests/unit/test_F_0_1_4_yahoo.py` | 9 tests (mocked yfinance module) |

## Design
- **Raw:** `raw/aux/yahoo/1D/<SAFE_TICKER>/<download_date>.parquet` (`^` → `_`, e.g. `_VIX`; `.vN` for another run the same day) — every run is a new immutable file, all versions kept. The yfinance frame is stored as returned: the index becomes the `Date` column with its original time zone and nanosecond instant; columns `Open, High, Low, Close, Adj Close, Volume` unchanged. The pandas → Polars conversion uses NumPy (not `pl.from_pandas`, which needs pyarrow for tz-aware columns) and normalises pandas 3's microsecond index to nanoseconds explicitly (bug found and fixed during testing).
- **Revision check:** a new version is joined with the previous one on `Date`; changed rows (any of Open/High/Low/Close/Adj Close), max |diff|, added/removed rows → `raw/_reports/yahoo_revisions.csv` + a warning; never blocks.
- **Adapter:** `ts` = session date (local date of Yahoo's midnight-exchange-time stamp) at 00:00 UTC; prices from `Close` (raw, never `Adj Close`); `volume_quality="none"` when all volume is 0 (indices), otherwise `partial`; `source=yahoo`, `price_type=trade`, `adjustment=raw`, `session=exchange`, `feed=none`, `bar_label=start`, `asset_class=aux_index`, `original_tz` = Yahoo's time zone. `close_time_local`, `close_tz`, `close_time_status` are carried in `notes` (`close_time_local=16:15; close_tz=America/New_York; close_time_status=verified; yfinance 1.7.0, auto_adjust=False, actions=False`).
- **TLS:** yfinance logs transport errors (including certificate failures) and returns an empty frame instead of raising. The client captures the `yfinance` logger during each call; certificate markers (`curl: (60)`, `unable to get local issuer certificate`, `CertificateVerifyError`, …) raise `TLSVerificationError` → the command stops with `STOP: …`, nothing is written.

## Close-time table (`configs/universe/aux_yahoo.csv`)
| ticker | symbol | close_time_local | close_tz | status | source / note |
|---|---|---|---|---|---|
| ^VIX | VIX | 16:15 | America/New_York | **verified** | Cboe VIX FAQ (cboe.com/tradable_products/vix/faqs/, read 2026-09-19): spot VIX calculated 3:15–9:25 a.m. ET (GTH) and 9:30 a.m.–4:15 p.m. ET (RTH) → final after 16:15 ET. (Yahoo does not document that its daily close is exactly this value.) |
| DX-Y.NYB | DXY | — | — | to_verify | ICE index computed almost 24 h; which snapshot Yahoo uses is undocumented |
| ^TNX | TNX | — | — | to_verify | Cboe dashboard gives no calculation hours; quote scale to check on data |
| ^GSPC | SPX | — | — | to_verify | proposal 16:00 ET (official close from closing auctions shortly after) — confirm with S&P DJI methodology |
| ^NDX | NDX | — | — | to_verify | proposal 16:00 ET — confirm with Nasdaq methodology |
| ^RUT | RUT | — | — | to_verify | proposal 16:00 ET — confirm with FTSE Russell methodology |
| ^DJI | DJI | — | — | to_verify | proposal 16:00 ET — confirm with S&P DJI methodology |
No time is filled in for `to_verify` rows (a test enforces this).

## Acceptance
| criterion | result |
|---|---|
| 1. previous acceptance commands | ✅ ruff, format (115 files), mypy (49 files), pytest **181 passed** |
| explicit `auto_adjust=False` call | ✅ `test_F_0_1_4_explicit_auto_adjust_false_call` (exact kwargs incl. `actions=False`) |
| daily date stamping | ✅ `test_F_0_1_4_adapter_daily_stamps_and_metadata` (session dates at 00:00 UTC on both sides of both 2024 US DST switches) |
| raw versions never overwritten | ✅ `test_F_0_1_4_raw_versions_are_never_overwritten` (`2026-09-01`, `.v2`, `2026-09-02`; read-only), `_raw_is_stored_as_returned` |
| revision diff | ✅ `test_F_0_1_4_revision_diff_is_reported` (1 changed row, max diff 0.2, report CSV) |
| metadata fields | ✅ `_adapter_daily_stamps_and_metadata`, `_adapter_uses_close_not_adj_close` |
| retries / TLS stop | ✅ `_retry_and_tls_stop`, `_tls_error_logged_by_yfinance_stops` |
| close-time table rules | ✅ `test_F_0_1_11_aux_universe_close_times` |
| 2. pilot (real network, 7 tickers) | ❌ **blocked** — see below |

## Pilot result — TLS stop
`uv run sfac data download yahoo` → yfinance's transport (curl_cffi / libcurl with its own CA bundle) fails certificate verification on this machine:
```
Cookie/crumb fetch failed (CertificateVerifyError), continuing without crumb
Failed to get ticker '^DJI' reason: Failed to perform, curl: (60) SSL certificate OpenSSL verify result:
unable to get local issuer certificate (20).
```
The first run reported this only as "empty response" for all 7 tickers (yfinance swallows the error); after the fix the command stops with `error: STOP: TLS verification failed for ^VIX: … curl: (60) … unable to get local issuer certificate (20)` (exit 1). **No raw file was written.** Per the runbook this is a stop condition; I did not disable verification or add any CA/truststore setting. Ingest and `sfac data list` for Yahoo could therefore not run.

Pilot commands for after the TLS decision:
```bash
uv run sfac data download yahoo
uv run sfac data ingest yahoo
uv run sfac data list --source yahoo
```
(7 requests, a 2 s pause between tickers; a few MB in total.)

## Deviations
- `configs/universe/aux_yahoo.csv` has an extra `notes` column for the sources the task asks to cite.
- pandas → Polars at the edge without pyarrow (manual conversion; see Design).
- Adapter `asset_class="aux_index"` and `session="exchange"` (not specified by the task).

## Open questions
1. **TLS (blocking):** yfinance/curl_cffi does not use the Windows certificate store, so the intercepting proxy's CA is rejected. Options for the supervisor: point curl_cffi at the corporate CA bundle (`CURL_CA_BUNDLE` / a session with `verify=<bundle>`), use `truststore`-style system trust, or download on a network without interception. Same issue as HANDOFF §8.8 for alpaca-py (`requests`/`certifi`).
2. Confirm or supply official close times for DX-Y.NYB, ^TNX, ^GSPC, ^NDX, ^RUT, ^DJI (and whether Yahoo's daily ^VIX close is the 16:15 value).
3. Add dedicated close-time fields to `SeriesMetadata`/catalog (now in `notes`)?
