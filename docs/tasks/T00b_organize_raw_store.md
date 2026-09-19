# T00b — Organize the raw data store (copy only) + inventory of 1H futures

**Feature:** F-0.1.12 (extension) · **Priority:** MVP · **Depends on:** T00 and T01 merged into `main`

## Goal
Build one tidy, immutable raw data store next to the project, filled with **byte-identical copies** of the existing data that we will actually use. Source folders must stay untouched. First inventory the new 1H futures folder the same way T00 did.

## Locations
- Data root (outside the repo): `D:\AmerAndish\Projects\Trade\StrategyFactory_data\`
  - `raw\`   → `SFAC_RAW_ROOT`
  - `store\` → `SFAC_DATA_ROOT` (created empty here; filled by later tasks)
- Write both variables into the local `.env` (git-ignored) and keep `.env.example` in sync (names only, no values).

## Hard rules
- **Source folders are read-only.** Only read them. Never move, rename, modify or delete anything there.
- **Copy byte-for-byte in the original format.** No conversion, no re-encoding, no renaming of files. Conversion is the job of the adapters (T04x).
- Verify every copy with sha256 (source vs destination). Snapshot source file size+mtime before and after the run; if **any** source file changed, stop and report.
- Check free disk space before copying. Abort with a clear message if it is insufficient.
- Make copied files read-only. Re-running the task must be idempotent: identical existing files are skipped, and a differing existing file is an error, not an overwrite.

## Step 1 — Inventory the new futures folder (read-only)
Source: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\`

Extend `scripts/data_inventory.py` with this root (keep existing behaviour). Produce the same 16 points as T00 for the new group(s). Pay special attention to:
- the exporter (TradeStation / MultiCharts / other) and the evidence for it;
- the timezone and bar-start vs bar-end labels;
- continuous vs single contracts, back-adjustment (negative prices?), and roll evidence;
- the symbol list and date ranges;
- overlap with the old 15-minute MarketEdge set (`ME-FUT-15M`). Compare a few common symbols by resampling 15m to 1h over the common period and report the agreement.

Append the results to `docs/data_inventory.md` and `docs/data_inventory.json` as new group(s) (e.g. `ATM-FUT-1H`). Add any new questions to the "Questions for the user" list.

## Step 2 — Copy into the raw store
Use the group definitions in `docs/data_inventory.json` to select files.

| Source group / files | Destination under `raw\` |
|---|---|
| MS-US-1D (`MarketScanner\data\candles\us_*.csv`) | `us_equity\alpaca_sip_all\1D\` |
| MS-CRYPTO-1D | `crypto\binance\1D\` |
| MS-PIT-CRYPTO-1D | `crypto\binance_pit\1D\` |
| MS-IRAN-1D | `iran\tsetmc\1D\` |
| QP-REF (reference files) | `reference\quantplatform\` |
| `MarketScanner\data\symbols.csv`, `MarketScanner\data\iran_meta.csv` | `reference\marketscanner\` |
| New 1H futures (Step 1) | `futures\<exporter>\1H\` (e.g. `futures\tradestation\1H\`) |

**Not copied (decided):** QP IEX 1D/1H, Stooq hourly, QP crypto 1H (binanceus), old 15-minute futures. List them in the README under "Not imported" with the reason.

If a group contains files that do not fit its pattern, list them in the report instead of copying them.

## Step 3 — Manifest, README, empty targets
- `raw\_manifests\copy_manifest.parquet` + `.csv`: `group, src_path, dest_path, size_bytes, sha256, src_mtime, copied_at`.
- `raw\README.md` must document:
  - the folder convention `raw\<asset_class>\<source>_<variant>\<timeframe>\...`;
  - the immutability rules;
  - the provenance of each folder (T00 group id, original path);
  - the "Not imported" list;
  - the placeholders for future downloads.
- Create empty placeholder folders for the downloads in later tasks: `us_equity\alpaca_sip_split\1D`, `us_equity\alpaca_sip_split\1H`, `fx_metals_cfd\dukascopy\`, `aux\yahoo\1D`, `_reports\`.

## Deliverables
- Updated `scripts/data_inventory.py`, `docs/data_inventory.md`, `docs/data_inventory.json`
- New `scripts/organize_raw_store.py` (pathlib only, no hard-coded separators; reads roots from arguments or `.env`)
- The populated raw store (outside the repo)

## Acceptance
- The copy manifest row count equals the planned file count, and every sha256 matches.
- The source integrity check reports 0 changed, 0 added and 0 removed files.
- A re-run copies 0 files and reports everything as already present and identical.
- ruff, mypy and pytest still pass. Add unit tests for the copy/verify logic under `tests/unit/` using `tmp_path`: identical skip, differing existing file → error, read-only flag.

## Review summary
Include:
- the futures inventory findings;
- a table of copied groups (files, GB, destination);
- the free space before and after;
- the integrity results;
- anything that was not copied and why;
- new questions for the user.
