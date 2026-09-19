# T00 — Data inventory (read-only)

**Feature:** F-0.1.12 · **Priority:** MVP · **Depends on:** nothing (runs before T01)

## Goal

Build a factual inventory of the market data the user has already downloaded, so the supervisor can finalize the stage-0 data decisions (adapters, canonical schema mapping, reference source per symbol). You are **documenting**, not converting.

## Hard rules

- **READ-ONLY.** Do not modify, move, rename, copy, delete or re-save any file in the source folders. Open files for reading only.
- Do not start T01. Do not create `pyproject.toml` or the package yet.
- Work only inside the repo folder for your own outputs.
- If a folder is huge, sample intelligently (see "Performance") — do not load multi-GB files fully into memory.

## Source folders

```
D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data
D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\
D:\AmerAndish\Projects\Trade\SourceCodes\MarketEdge\Data\Futures\
<DUKASCOPY_PATH>        # the user fills this in before running
```

If `<DUKASCOPY_PATH>` is still a placeholder, ask the user for it before scanning.

## Tooling

- Write one script: `scripts/data_inventory.py` (Python 3.12, `pathlib`, no hard-coded separators).
- Run it without a project environment:
  `uv run --no-project --python 3.12 --with polars --with pyarrow --with pandas python scripts/data_inventory.py`
- If `uv` is not installed, stop and tell the user (installation is step 1 of their checklist).

## What to capture

Walk every folder recursively. Group files that share a pattern (same folder structure / naming scheme / columns). For **each group**:

1. **Location & pattern:** root path, filename pattern, file count, total size, extensions (csv, parquet, json, feather, zip, bi5, ...).
2. **Probable source** (Alpaca, Dukascopy, Yahoo, TradingView export, broker/MT5, exchange/futures vendor, unknown) — with the **evidence** (column names, filename conventions, folder names, value patterns).
3. **Symbols:** list (or count + first 30 if many). Note naming convention (e.g. `USA30IDXUSD`, `AAPL`, `ES`).
4. **Asset class guess:** US equity / ETF / index CFD / FX / metal / commodity / futures / crypto.
5. **Timeframe:** infer from the median difference between consecutive timestamps (not from filenames alone). Report if mixed.
6. **Date range:** first and last timestamp per symbol (table), or min/median/max across symbols if many.
7. **Schema:** column names, dtypes, and whether OHLCV / vwap / trades / bid / ask / spread columns exist.
8. **Raw samples:** first 5 rows and last 3 rows **verbatim** for one representative file of the group.
9. **Timestamp format & timezone evidence:** string with offset? naive? epoch seconds/ms? Bar-start or bar-end (check the first bar of a day / session)? Any DST jumps?
10. **Session evidence (US equities/indices):** are there bars between 08:00–13:30 UTC or after 20:00 UTC (pre/after-market)? For daily bars: which weekday/holiday patterns appear?
11. **Weekend / Sunday bars (FX, metals, CFDs):** present? What hours?
12. **Price type evidence:** bid/ask/mid/trade; for Dukascopy check whether bid and ask are separate files/columns.
13. **Adjustment evidence (equities):** look for large overnight gaps around known split dates for a few well-known tickers present in the data (e.g. AAPL 2020-08-31 4:1, TSLA 2020-08-31 5:1, NVDA 2024-06-10 10:1). Report adjusted / unadjusted / unknown per group.
14. **Futures specifics:** single contracts vs continuous series; roll method evidence (price jumps at roll dates, back-adjusted negative prices, etc.).
15. **Quality quick-scan:** duplicate timestamps, missing bars (count of gaps larger than 3× the timeframe during expected sessions), rows with high < low, zero/negative prices, zero volume share.
16. **Overlaps:** symbols that appear in more than one group/source — list them (these need a "reference source" decision).

## Performance

- Parquet: use `polars.scan_parquet` for min/max/counts; read only needed columns.
- CSV: read head/tail directly; for min/max/count use `polars.scan_csv` with lazy aggregation; if a file > 500 MB, sample the first and last 200k lines and mark results as "sampled".
- Stop scanning a group after 50 files for per-file stats; extrapolate counts and say so.

## Deliverables

1. `scripts/data_inventory.py`
2. `docs/data_inventory.md` — human-readable report, one section per group, plus:
   - a **summary table**: group · source · asset class · #symbols · timeframe · date range · format · timezone · price type · adjustment · notes;
   - an **overlap table**;
   - a **"Questions for the user"** list (everything you could not determine from the files).
3. `docs/data_inventory.json` — the same facts in machine-readable form (one object per group).

## Review summary (end of task)

Finish with a short summary for the supervisor: groups found, anything surprising, files you could not read and why, and confirmation that no source file was modified.
