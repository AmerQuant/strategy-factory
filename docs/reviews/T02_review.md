# T02 review — canonical bar schema, snapshot store and catalog

**Features:** F-0.1.1, F-0.1.8 · **Branch:** `feat/T02-schema-store` (based on `feat/T00b-raw-store`) · **Status:** done

## Files
| file | content |
|---|---|
| `src/strategy_factory/data/schema.py` | canonical columns/dtypes, `SeriesMetadata` + `RawRef` (frozen, `extra="forbid"`, `Literal` enums, validated timeframe, UTC-only datetimes), `ValidationIssue`, `validate_bars` |
| `src/strategy_factory/data/adapters/base.py` | `Adapter` Protocol (`to_canonical(raw_paths, **params)`) |
| `src/strategy_factory/data/hashing.py` | `normalize`, `content_hash` (Arrow IPC stream, uncompressed), `file_sha256` |
| `src/strategy_factory/data/store.py` | `SnapshotStore` (`write_snapshot`, `read_snapshot`, `scan_snapshot`, `read_metadata`), module-level `write_snapshot`/`read_snapshot`, `data_root()` (→ `ConfigError`), `safe_component` |
| `src/strategy_factory/data/catalog.py` | `Catalog` (`register`, `list_snapshots`, `set_reference`, `get_reference`, `has_reference`), events log; single-writer assumption documented in the module docstring |
| `src/strategy_factory/data/cli.py` + `cli.py` | `sfac data list [--symbol --timeframe --source]`, `sfac data show <symbol> <timeframe>` |
| tests | `tests/fixtures/bars.py`, `tests/unit/test_F_0_1_1_schema.py` (35), `test_F_0_1_8_store.py` (28), `test_F_0_1_8_cli_data.py` (4) |

## Dependencies
- **polars 1.44.2** (runtime) — expected by the task; data-layer DataFrame, Parquet I/O and the IPC stream for hashing.
- **tzdata 2026.4, Windows only** (`sys_platform == 'win32'`) — Polars converts UTC timestamps to Python `datetime` via `zoneinfo`, and Windows has no IANA database, so every `ts.min()`/`row()` failed with `ZoneInfoNotFoundError`. Linux CI uses the system database.
- **pyarrow: not added.** Polars writes the IPC stream and Parquet natively; verified that the IPC hash is identical across chunking, input row order and Parquet compressions (zstd/snappy/gzip/lz4/uncompressed).

## Design details
- **Schema:** required `ts: Datetime("us","UTC")`, `open/high/low/close/volume: Float64`; optional `vwap: Float64`, `trades: Int64`, `spread: Float64`. Canonical column order = that order.
- **Validation issues** (all `critical`): `missing_column`, `extra_column`, `wrong_dtype` (incl. `ts` not Datetime or not `us`), `ts_naive`, `ts_not_utc`, `ts_not_monotonic`, `ts_duplicate`, `high_lt_low`, `ohlc_outside_range`, `nonpositive_price` (skipped for `back_adjusted`), `nan_in_required` (NaN or null). Value checks run only on columns with the right dtype, so one wrong dtype gives one issue, not a cascade.
- **Hash:** `normalize` = canonical columns, canonical dtypes, rows sorted by `ts` then all other columns, one chunk → uncompressed IPC stream → sha256. The snapshot hash is the content hash only (metadata is not part of it).
- **Store:** `<root>/<source>/<symbol>/<timeframe>/<hash>.parquet` + `<hash>.meta.json`. The store sorts rows by `ts` before validating (so unsorted adapter output is accepted and stored in canonical order; duplicates stay critical). Parquet is written to a temp file, re-read and re-hashed, renamed, then set read-only; the sidecar likewise. Same content again → the stored metadata is returned and nothing is written. Symbols are made path-safe only in the path (`BTC/USDT` → `BTC_USDT`; Windows reserved names such as `AUX`, `CON` get a trailing `_`); metadata keeps the real symbol.
- **Catalog:** `catalog.parquet` = all metadata fields (`raw_refs` as JSON text) + `is_reference`; `catalog_events.parquet` = append-only `(ts, event, symbol, timeframe, snapshot_hash, previous_reference, note)` with events `register` and `set_reference`. Reference = exactly one per `(symbol, timeframe)`, across sources. Setting the current reference again is a no-op and is not logged. Atomic writes (temp + rename).

## Acceptance criteria and tests
| criterion | test(s) |
|---|---|
| F-0.1.1 validation catches each issue type — one test per issue | `test_F_0_1_1_missing_column`, `_extra_column`, `_wrong_dtype_price`, `_wrong_dtype_optional`, `_wrong_ts_time_unit`, `_naive_ts`, `_non_utc_ts`, `_non_monotonic_ts`, `_duplicate_ts`, `_high_below_low`, `_ohlc_outside_range`, `_nonpositive_price_rejected`, `_nan_in_required`, `_null_in_required`; clean frame → no issues (with and without optional columns) |
| `back_adjusted` allows negative prices; others do not | `test_F_0_1_1_back_adjusted_allows_negative_prices`, `_nonpositive_price_rejected` (split, raw) |
| metadata rejects invalid enums and timeframes | `test_F_0_1_1_metadata_rejects_invalid_enum` (6 enums), `_rejects_invalid_timeframe` (6 cases), `_accepts_valid_timeframes`, `_requires_fields_and_is_frozen`, `_rejects_naive_datetimes_and_bad_hash`, JSON round trip |
| same content → same hash regardless of row order / Parquet compression | `test_F_0_1_8_hash_independent_of_row_order`, `_of_column_order_and_chunks`, `_of_parquet_compression` (5 codecs, small row groups) |
| one changed value → different hash | `test_F_0_1_8_changing_one_value_changes_hash` (+1e-9 on one close) |
| writing twice is idempotent | `test_F_0_1_8_write_is_idempotent` (reversed rows + different notes → same stored meta, file not rewritten) |
| overwrite/modify fails; read-only after write | `test_F_0_1_8_snapshot_is_read_only_and_cannot_be_modified` (write and append raise `PermissionError` on parquet and sidecar) |
| catalog keeps exactly one reference and logs events | `test_F_0_1_8_set_reference_keeps_exactly_one_and_logs` (switch A→B, other symbol untouched, no-op not logged, `previous_reference` recorded) |
| `get_reference` without reference → `DataError` | `test_F_0_1_8_get_reference_without_reference_raises` |
| round trip write → read identical | `test_F_0_1_8_round_trip_identical`, `_catalog_round_trips_metadata` |
| missing `SFAC_DATA_ROOT` → `ConfigError` | `test_F_0_1_8_missing_data_root_is_config_error`, CLI `_list_without_data_root` |
| extra | critical issue blocks the write; unsorted input stored sorted; `columns/start/end` reads; path-safety cases; pinned hash of a reference fixture; CLI list/show/filter/no-reference |

## Acceptance commands (Windows)
`uv sync` ✅ · `sfac --version` ✅ `0.1.0` · `sfac info` ✅ (data root resolved from `.env`) · `sfac data list` ✅ ("catalog is empty") · `ruff check` + `ruff format --check` ✅ · `mypy src` ✅ (33 files; strict for `strategy_factory.data`) · `pytest` ✅ **127 passed** (also with `HYPOTHESIS_PROFILE=ci`) · `docker compose config` ✅.

## Deviations
- `ts_not_monotonic` is reported by `validate_bars` as critical, but `write_snapshot` sorts rows by `ts` first, so the store accepts unsorted input (required for the "row order independent" hash criterion to hold end-to-end). Duplicates remain critical.
- `read_snapshot` range semantics: `start <= ts < end` (the task did not specify).
- `asset_class` is a free non-empty string (the task lists no enumeration).
- Added `tzdata` (see Dependencies).

## Open questions
1. **Hash stability across Polars versions:** the Arrow IPC bytes come from Polars; a Polars upgrade could change them and therefore every snapshot hash. A test pins the hash of a fixture so this cannot happen silently. Accept this, or should the canonical serialization be library-independent (e.g. raw little-endian column buffers) before real snapshots are written?
2. Should `SeriesMetadata` get dedicated aux close-time fields now (T04c carries them in `notes` for the moment)?
