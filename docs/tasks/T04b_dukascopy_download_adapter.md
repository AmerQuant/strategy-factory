# T04b — Dukascopy downloader (dukascopy-node) and adapter

**Features:** F-0.1.3 (Dukascopy adapter), F-0.2.2 groundwork (spread data) · **Priority:** P1 (built now, run later) · **Depends on:** T00b, T02

## Decisions (fixed)
| Item | Decision |
|---|---|
| Download tool | **dukascopy-node** (Node CLI), run as an external tool from a thin Python wrapper. Node is **not** a dependency of the Python package |
| Price sides | **bid and ask**, downloaded separately |
| Research series | **1H** bid+ask from 2010-01-01 (or instrument start, if later) to the latest complete month |
| Spread series | **m1** bid+ask for the **last 24 complete months** only (hourly spread profile; later intrabar resolution) |
| Timezone | UTC (tool default; verify) |
| Daily bars | not downloaded; built later from 1H with the 00:00 UTC boundary and Sunday→Monday merge (T05) |

## Instruments (`configs/universe/dukascopy.csv`)
Create this file with columns `instrument_id, symbol, asset_class, notes`. Verify **every** id against the tool's instrument list (`npx dukascopy-node --help` / its docs). Report ids that do not exist and propose the correct ones. Do not guess silently.

- **FX majors:** eurusd, gbpusd, usdjpy, usdchf, audusd, usdcad, nzdusd
- **FX crosses:** eurjpy, gbpjpy, eurgbp, eurchf, audjpy, euraud, gbpchf, cadjpy
- **Metals:** xauusd, xagusd
- **Energy CFDs:** lightcmdusd (WTI), brentcmdusd
- **Index CFDs:** usa500idxusd, usa30idxusd, usatechidxusd, ussc2000idxusd, deuidxeur, gbridxgbp, jpnidxjpy, fraidxeur, ausidxaud, hkgidxhkd

## Prerequisite check
- Run `node --version` and `npx --version`. If Node is missing, **stop this task** and tell the user to install Node.js LTS, then continue with the next task in the runbook.
- Pin the dukascopy-node version (e.g. a local `tools/dukascopy/package.json` + lockfile, installed with `npm ci`). Do not use a floating `npx dukascopy-node@latest`.

## Scope

### 1. Download wrapper (`data/download/dukascopy.py`)
`sfac data download dukascopy --series {h1,m1} [--instruments ...] [--from ...] [--to ...]`
- Calls the pinned CLI via `subprocess`, **one instrument × side × calendar month** per call. Use the tool's own options for retries, pauses between batches and volumes (check `--help`; record the exact flags used).
- **Raw output (immutable):** `SFAC_RAW_ROOT/fx_metals_cfd/dukascopy/<series>/<INSTRUMENT>/<side>/<YYYY-MM>.csv.gz`. The tool's CSV is gzip-compressed losslessly after download. Next to it goes a manifest JSON with the tool version, the exact command line, the download time, the row count and the sha256 of the uncompressed CSV.
- **Resumable:** completed months are skipped. The **current, incomplete month is never stored**.
- Empty months (instrument not yet listed, or holidays) are recorded in `SFAC_RAW_ROOT/_reports/dukascopy_empty.csv`.
- **TLS:** if downloads fail with certificate errors, stop and report. Do not disable certificate verification.

### 2. Adapter (`data/adapters/dukascopy.py`)
- `to_canonical(raw_paths, series)` merges bid and ask on timestamp:
  - `mid = (bid + ask) / 2` for OHLC. **Document** that the mid-OHLC high/low is an approximation.
  - `spread = ask_close − bid_close`.
  - `volume` is taken from the bid side, with `volume_quality="partial"` because it is Dukascopy's own volume.
- Metadata:
  - `source="dukascopy"`, `price_type="mid"`, `session="24x5"`, `bar_label` verified as bar-start, `adjustment="raw"`.
  - The instrument's asset class comes from the universe file.
- Critical issues:
  - a timestamp present on one side only (count them; critical if more than 0.1% of bars);
  - a negative spread.
- `sfac data ingest dukascopy --series h1 [--instruments ...]` writes snapshots through the T02 store. m1 is **not** ingested now (it is used later by the spread profile task).

## Tests (no network)
- Fixtures: tiny gzip CSVs for bid and ask (committed), including a DST week and a weekend gap.
- Wrapper: builds the correct command lines (the subprocess call is mocked); skips completed months; never stores the current month; never overwrites.
- Adapter: bid/ask merge, mid and spread math, the one-sided timestamp rule, UTC and bar-start, metadata.

## Acceptance
1. All previous acceptance commands pass; CI green (CI does not need Node — the tests mock the subprocess).
2. **Pilot (real network):**
   - eurusd, xauusd and usa500idxusd;
   - h1 for 2024-01 to 2024-03, m1 for 2024-03;
   - ingest h1, then `sfac data list`.
   
   Report bars per week, the spread statistics per hour for eurusd, and any empty months.
3. **Do not** run the full download. Report the exact commands and an estimate of calls, duration and disk size (gzip) for the full h1 history and 24 months of m1.

## Review summary
Include the tool version and flags, the instrument-id verification table, the pilot results, the full-download commands with their estimates, deviations and open questions.
