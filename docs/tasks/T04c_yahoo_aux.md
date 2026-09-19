# T04c — Auxiliary series from Yahoo (yfinance)

**Features:** F-0.1.4 (Yahoo adapter), F-0.1.11 groundwork (aux close-time metadata) · **Priority:** P1 (built now) · **Depends on:** T00b, T02

## Decisions (fixed)
- Tool: **yfinance**, pinned version. Always call it with explicit `auto_adjust=False` and `actions=False`; record the yfinance version in every manifest.
- Daily only. Full available history.
- Series (`configs/universe/aux_yahoo.csv`, columns `ticker, symbol, description, close_time_local, close_tz, close_time_status`):
  `^VIX, DX-Y.NYB, ^TNX, ^GSPC, ^NDX, ^RUT, ^DJI`
- `close_time_local` is the time at which the daily value becomes final. This matters for leakage (see spec addendum §5.3).
  - Fill in the values you can document from official exchange/index sources; cite the source in `notes`.
  - Mark anything uncertain as `close_time_status = "to_verify"`. **Do not guess.**

## Scope
1. **Downloader:** `sfac data download yahoo [--tickers ...]`
   - Raw output: `SFAC_RAW_ROOT/aux/yahoo/1D/<SAFE_TICKER>/<download_date>.parquet`, stored exactly as returned, plus a manifest with the yfinance version, the call parameters and the sha256.
   - Every run is a new immutable file, since Yahoo history can be revised. Keep all versions.
   - Rate-limit politely; retry with backoff.
   - On a TLS error, stop and report. Do not disable verification.
2. **Adapter:** `data/adapters/yahoo.py` → canonical daily bars stamped at session date 00:00 UTC.
   - Metadata: `source="yahoo"`, `price_type="trade"`, `adjustment="raw"`, `volume_quality` = `none` for indices with no real volume.
   - Carry `close_time_local` and `close_tz` in `notes` until the catalog gets dedicated fields.
   - `sfac data ingest yahoo`.
3. **Revision check:** when a new raw version exists, report rows whose values differ from the previous version (count and max difference). This is a warning, not a block.

## Tests (no network)
- Mocked yfinance returning a small fixture frame.
- Verify:
  - the explicit `auto_adjust=False` call;
  - daily date stamping;
  - that raw versions are never overwritten;
  - that the revision diff works;
  - the metadata fields.

## Acceptance
1. All previous acceptance commands pass; CI green.
2. **Pilot (real network):** all 7 tickers, full history, then ingest and `sfac data list`. Report first/last dates, row counts and the close-time table with its sources.

## Review summary
yfinance version, pilot results, close-time table (verified vs to_verify), deviations, open questions.
