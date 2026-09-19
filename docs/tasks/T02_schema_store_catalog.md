# T02 — Canonical bar schema, snapshot store and catalog

**Features:** F-0.1.1 (canonical schema & adapter interface), F-0.1.8 (storage & versioning) · **Priority:** MVP · **Depends on:** T01 (merged)

Read first: `CLAUDE.md`, `docs/design.md` §4–§5, features F-0.1.1 and F-0.1.8 in `docs/features.md`, and the "Stage-0 data decisions" section below.

## Stage-0 data decisions (context — do not change them)

- Price basis for equities: **split-adjusted only** (`adjustment = "split"`), TradingView-like.
- Timestamps: UTC, **bar-start**. Daily bars are stamped at the **session date 00:00 UTC**.
- Raw downloads are immutable files under `SFAC_RAW_ROOT`; canonical snapshots live under `SFAC_DATA_ROOT`. Both roots are outside the repo.
- Every snapshot must be traceable to the raw files it was built from.

## Scope

### 1. `data/schema.py`
- Canonical Polars schema:
  - required: `ts: Datetime("us", "UTC")`, `open, high, low, close, volume: Float64`
  - optional: `vwap: Float64`, `trades: Int64`, `spread: Float64`
- `SeriesMetadata` (frozen Pydantic model):
  `source, source_symbol, symbol, asset_class, timeframe, price_type (trade|bid|ask|mid), adjustment (raw|split|all|back_adjusted|unknown), session (RTH|RTH_hour_aligned|ETH|24x5|24x7|exchange), feed (sip|iex|none), volume_quality (full|partial|none), original_tz, bar_label (start|end), raw_refs (list of {path, sha256}), downloaded_at, notes`
  plus fields filled by the store: `snapshot_hash, row_count, first_ts, last_ts, created_at`.
  Enumerations are `Literal`s; timeframe is a validated string (`1m, 5m, 15m, 1H, 4H, 1D`).
- `validate_bars(df, meta) -> list[ValidationIssue]`: missing or extra columns, wrong dtypes, non-UTC or naive `ts`, non-monotonic or duplicate `ts`, `high < low`, OHLC outside `[low, high]`, non-positive prices (allowed only when `adjustment == "back_adjusted"`), NaNs in required columns. It returns issues and does not raise; the store raises if any issue has severity `critical`.

### 2. `data/adapters/base.py`
- `Adapter` Protocol: `to_canonical(raw_paths: list[Path], **params) -> tuple[pl.DataFrame, SeriesMetadata]`. Concrete adapters come in T04a and later.

### 3. `data/hashing.py`
- `content_hash(df) -> str`: sha256 of a **canonical serialization** of the normalized table: sorted by `ts`, fixed column order, fixed dtypes, via the Arrow IPC stream. It is independent of Parquet write settings.
- Also add a helper `file_sha256(path)` for raw files.

### 4. `data/store.py`
- Layout: `SFAC_DATA_ROOT/<source>/<symbol>/<timeframe>/<snapshot_hash>.parquet`, plus a sidecar `<snapshot_hash>.meta.json` holding the full `SeriesMetadata`.
- `write_snapshot(df, meta) -> SeriesMetadata`: validates, computes the hash, and writes atomically (temp file + rename). It then sets the file read-only, and returns meta with the store fields filled.
  - If a snapshot with the same hash already exists, it returns the existing metadata (idempotent) and writes nothing.
  - Never overwrite or modify an existing snapshot.
- `read_snapshot(source, symbol, timeframe, snapshot_hash, columns=None, start=None, end=None) -> pl.DataFrame`, lazy with `scan_parquet` and filter pushdown.
- A missing `SFAC_DATA_ROOT` raises `ConfigError` with a clear message.

### 5. `data/catalog.py`
- `SFAC_DATA_ROOT/catalog.parquet` has one row per snapshot: the metadata fields plus `is_reference: bool`.
- Also `SFAC_DATA_ROOT/catalog_events.parquet`, an append-only log with columns `(ts, event, symbol, timeframe, snapshot_hash, previous_reference, note)`.
- API:
  - `register(meta)`
  - `list_snapshots(symbol=None, timeframe=None, source=None)`
  - `set_reference(symbol, timeframe, snapshot_hash, note)`: exactly one reference per (symbol, timeframe); every change is logged as an event.
  - `get_reference(symbol, timeframe) -> SeriesMetadata`: raises `DataError` if there is none.
- Writes are atomic. There is a single writer; document this assumption in the module docstring.

### 6. CLI
- `sfac data list [--symbol] [--timeframe] [--source]`: prints the catalog as a table.
- `sfac data show <symbol> <timeframe>`: prints the reference metadata, row count and first/last ts.

## Out of scope
Adapters for real sources (T04a+), quality report (T05), resampling (T05), split manager (T05).

## Dependencies
- `polars` is expected. Add `pyarrow` only if Polars cannot do the IPC-based hashing or Parquet I/O you need, and justify it in the review summary.

## Tests (names start with the feature ID)
- **F-0.1.1:**
  - Validation catches each issue type on small synthetic frames. There is one test per issue.
  - `back_adjusted` allows negative prices; other adjustments do not.
  - Metadata rejects invalid enum values and invalid timeframes.
- **F-0.1.8:**
  - Same content → same hash, regardless of row order in the input and of Parquet compression.
  - Changing one value → a different hash.
  - Writing the same snapshot twice is idempotent.
  - Attempting to overwrite or modify a stored snapshot fails.
  - The snapshot file is read-only after writing.
  - Catalog `set_reference` keeps exactly one reference and logs the event.
  - `get_reference` without a reference raises `DataError`.
  - Round trip: write → read gives an identical frame.
- Use `tmp_path` for `SFAC_DATA_ROOT` in tests. Never touch real data folders.

## Acceptance
All T01 acceptance commands still pass. New tests pass on Windows and in CI. mypy strict is clean for `strategy_factory.data`.

## Review summary
Files, dependencies (and why), how each acceptance criterion of F-0.1.1 and F-0.1.8 is tested, deviations, open questions.
