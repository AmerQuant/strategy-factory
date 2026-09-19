# T00b review — raw data store + 1H futures inventory

**Feature:** F-0.1.12 (extension) · **Branch:** `feat/T00b-raw-store` (based on `docs/batch1`) · **Status:** done

## What was built
- `scripts/data_inventory.py` extended (existing behaviour unchanged):
  - new optional root `--atm-futures` (default `SFAC_SRC_ATM_FUTURES` from env/`.env`; no drive letter in code) with groups `ATM-FUT-1H`, `ATM-FUT-1440`, `ATM-FUT-DAILY`;
  - a `.csv`/`.txt` twin check (sha256) and a classification of files that do not fit the pattern;
  - a 15m→1H resample comparison between `ME-FUT-15M` and `ATM-FUT-1H`;
  - generic futures interpretation (the old text hard-coded `[Dec23]` and "+15 min");
  - fix: the "first bar of each session" detection now scales with the bar size (for 15m the threshold is unchanged, so old results are identical).
- `docs/data_inventory.md` / `.json` regenerated with the new groups, sections and questions (integrity 0/0/0).
- New `scripts/organize_raw_store.py`: plans from `docs/data_inventory.json`, copies byte-for-byte via temp file + sha256 verify + rename, sets read-only, idempotent, free-space check, source size+mtime snapshot before/after, manifest (parquet + csv), `raw/README.md`, run report under `raw/_reports/`.
- `tests/unit/test_F_0_1_12_raw_store_copy.py` (6 tests).
- `.env` (local, git-ignored): `SFAC_RAW_ROOT`, `SFAC_DATA_ROOT` (→ `D:\AmerAndish\Projects\Trade\StrategyFactory_data\{raw,store}`), `SFAC_SRC_ATM_FUTURES`. `.env.example`: the same names, values blank.

## Futures inventory findings (`F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\`)
- **388 files**: 64 symbols × {`60min`, `1440min`, `Daily`} × {`.csv`, `.txt`}. All **192 `.csv`/`.txt` pairs are byte-identical** (sha256). Plus 4 odd files: `@AD, 60min - Copy.csv` and `@NG, 60min - Copy.txt` (header block stripped, manual edits) and their `.bak` backups.
- **Exporter: TradeStation**, via the same "Data Exporter v3.0" indicator as the old 15-minute set (`@` continuous symbols, `$/Big Point`, `S.Start`/`S.End` header).
- **Range:** 2006-01-09 → 2025-07-09 02:00 (exported 2025-07-09). `@ED` ends 2023-05-19 (Eurodollar delisted, not stale). `@BTC` starts 2017-12.
- **Timezone / labels:** naive **exchange-local time** (US/Central for CME/CBOT/NYMEX/COMEX), **bar-end** labels. Evidence: bars labelled at `S.End` exist and at `S.Start` never; @ES's first bar of every session is `18:00` in both winter and summer (17:00 CT open + 1 h), so DST is followed; Sunday bars = Globex open. ICE softs (US/Eastern) still to confirm.
- **Continuous, additively back-adjusted:** descriptions say "Continuous Contract [Sep25]" (tags Jul25–Dec25 depending on the root); 8 roots go to prices ≤ 0 (@HO 74,994 bars, @RB 59,741, @SM 21,166, @S 10,439, @CT 4,656, @OJ 3,768, @CL 640, @QM 641); closes stay on the tick grid; the largest jumps do not cluster in roll windows (median share 0.15 vs ≈0.13 base rate) → roll gaps removed. Roll rule unknown.
- **Overlap with ME-FUT-15M:** 61 common roots (only old: @BTM, @QH, @QN, @QU; only new: @MES.D, @MNQ.D, @RTY.D). 15m resampled to 1H vs new 1H over 2006-01 → 2023-11-01:

| symbol | 1H bars (ATM) | labels matched | hours compared | modal close diff | share at modal diff | range equal | volume equal |
|---|---|---|---|---|---|---|---|
| @ES | 105,050 | 100% | 102,200 | 417.0 | 0.9992 | 1.0 | 0.9975 |
| @NQ | 105,025 | 100% | 100,484 | 1668.0 | 0.9994 | 1.0 | 0.9990 |
| @CL | 104,323 | 100% | 103,669 | −10.9 | 0.9997 | 1.0 | 0.9996 |
| @GC | 103,856 | 100% | 103,001 | 239.8 | 0.9996 | 1.0 | 0.9993 |
| @TY | 104,104 | 100% | 102,600 | 2.0625 | 0.9992 | 0.9995 | 0.9990 |
| @EC | 105,196 | 100% | 105,032 | 0.0343 | 0.9997 | 1.0 | 0.9995 |

  → same feed and settings; closes differ only by the back-adjustment offset between the `[Dec23]` and `[Sep25]` anchors. The new 1H set supersedes the old 15-minute set for 1H research.
- `1440min` and `Daily` differ (e.g. @ES 2025-07-07 close 6263.25 vs 6276.00; `Daily` looks like settlement prices). Not copied (see questions).

## Copied groups (`SFAC_RAW_ROOT = D:\AmerAndish\Projects\Trade\StrategyFactory_data\raw`)

| source group | files | GB | destination |
|---|---|---|---|
| MS-US-1D (`us_*.csv`) | 6,711 | 0.513 | `us_equity\alpaca_sip_all\1D\` |
| MS-CRYPTO-1D (`crypto_*.csv`, `gold_*.csv`) | 102 | 0.007 | `crypto\binance\1D\` |
| MS-PIT-CRYPTO-1D (`pit_*.csv`) | 601 | 0.038 | `crypto\binance_pit\1D\` |
| MS-IRAN-1D (`iran_*.csv`) | 2,365 | 0.108 | `iran\tsetmc\1D\` |
| QP-REF (assets, marketcap) | 5 | 0.001 | `reference\quantplatform\` (sub-folders kept) |
| MarketScanner `symbols.csv`, `iran_meta.csv` | 2 | 0.001 | `reference\marketscanner\` |
| ATM-FUT-1H (`Data Export,@SYM, 60min.csv`) | 64 | 0.276 | `futures\tradestation\1H\` |
| **total** | **9,850** | **0.944** | |

Empty placeholders created: `us_equity\alpaca_sip_split\{1D,1H}`, `fx_metals_cfd\dukascopy`, `aux\yahoo\1D`, `_reports`; `store\` (= `SFAC_DATA_ROOT`) created empty.

## Acceptance
| criterion | result |
|---|---|
| manifest rows = planned files, every sha256 matches | ✅ 9,850 / 9,850; 0 mismatches (re-hashed from disk after copy); 0 read-only violations |
| source integrity 0 changed / 0 added / 0 removed | ✅ 34,901 source files checked (all four roots + the two MarketScanner reference files), 0/0/0; the inventory run also 0/0/0 |
| re-run copies 0 files | ✅ `copied 0, already present+identical 9850`, exit 0; `copied_at` kept from the first run |
| ruff, format, mypy, pytest | ✅ all pass; 49 tests |
| unit tests (identical skip, differing → error, read-only) | ✅ `test_F_0_1_12_*`: byte-identical copy + verify, read-only (write raises `PermissionError`, source untouched), identical skip (not rewritten), differing existing file → `CopyConflictError` and not overwritten (also same size/different content), integrity snapshot detects changed/added/removed |

**Free space** (D:): 180.69 GB before, 179.73 GB after.

## Not copied (and why)
QP-US-EQ-1D / QP-US-EQ-1H (Alpaca IEX), QP-STOOQ-1H, QP-CRYPTO-1H (binanceus), ME-FUT-15M (superseded by ATM-FUT-1H) — as decided. Additionally: ATM `1440min`/`Daily` (only 1H was decided), the 192 `.txt` twins (byte-identical duplicates), and the 4 `- Copy`/`.bak` files (do not fit the pattern). All listed in `raw\README.md` → "Not imported" and in the run report (`raw\_reports\organize_raw_store_*.json`, `not_copied_in_group_roots`).

## Deviations
- `.env.example`: `SFAC_DATA_ROOT` example value removed (the task asks for names only); `SFAC_SRC_ATM_FUTURES` added so the inventory needs no drive letter in code.
- Manifest and README in `raw\` are regenerated on each run (they are indexes, not data); data files are read-only. The manifest keeps the original `copied_at` for unchanged files.
- The copy tool imports polars only for writing the manifest; run it with `uv run --with polars ...` until T02 adds polars as a project dependency.

## New questions for the user
1. Confirm the TradeStation settings of the futures exports: back-adjustment on (data shows additive back-adjustment), roll rule (volume-based or N days before expiry), time zone = exchange time. (Needed before T04d.)
2. `1440min` vs `Daily` futures: should one of them be imported, and which is the daily reference (settlement vs last trade)?
3. ICE softs (@CC, @CT, @KC, @OJ, @SB): confirm US/Eastern timestamps.
4. The `- Copy` files for @AD and @NG (header removed): were they edited for a reason (data fixes) or are they scratch copies that can be ignored?
