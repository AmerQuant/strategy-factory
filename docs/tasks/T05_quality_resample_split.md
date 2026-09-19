# T05 — Data quality, resampling and split manager

**Features:** F-0.1.6 (quality report), F-0.1.7 (resampling & day boundary), F-0.6.1 (split manager & holdout lock) · **Priority:** MVP · **Depends on:** T02, T04e, T03 (all on `main`)

Read first: `CLAUDE.md`, `docs/design.md` §5, the stage-0 decisions in `HANDOFF.md` §5 and §7, and the three features in `docs/features.md`.

## Fixed decisions
- Timestamps are UTC, bar-start. **Day boundary is 00:00 UTC.** For `fx`, `metal`, `energy_cfd` and `index_cfd`, the Sunday hours are **merged into Monday**; no daily bar is ever stamped on a Sunday.
- `us_equity` daily bars come from the Alpaca daily snapshots (not resampled). Hourly US bars follow `configs/calendars/nyse_sessions.csv`.
- 4H bars are built **only** for 24-hour markets (`fx`, `metal`, `energy_cfd`, `index_cfd`, `crypto`), in fixed UTC blocks 00–04, 04–08, …
- `broker_session` resampling exists **only for parity tests**. The session start comes from config (e.g. `17:00 America/New_York`).
- Holdout = the last 20 % of the time span, **at least 18 months**. Embargo = max indicator lookback + max holding period (in bars; both come from config for now). Holdout access is one-shot per candidate and is logged in the registry (T03).
- Every threshold lives in config (`configs/data/quality.yaml`, `configs/data/split.yaml`).

## Scope

### 1. Quality report (F-0.1.6, `data/quality.py`)
Checks per snapshot, each with a severity from config:

| Check | Description | Default severity |
|---|---|---|
| missing bars | Compared with the expected schedule of the asset class: NYSE sessions for `us_equity`; the weekday 24h schedule with the observed daily break for FX/metals/CFDs, learned from the data (the modal break hour) and reported | warning above x % |
| duplicates / high<low / non-positive | Already enforced by the schema; re-checked | critical |
| price spikes | Return beyond k × rolling MAD **and** reversing on the next bar | warning |
| stale prices | Runs of N identical OHLC bars | warning |
| zero volume | Share of zero-volume bars, skipped when `volume_quality` is `none` | info/warning |
| DST discontinuities | Only for exchange-local sources | warning |
| session violations | Bars outside the expected schedule | warning |

- Output: `SFAC_DATA_ROOT/_quality/<snapshot_hash>.json` plus a short markdown summary.
- Add a catalog field `quality_status` (`ok | warning | critical | unchecked`). A `critical` status blocks the snapshot from being used by the pipeline, with a clear error.
- CLI: `sfac data quality [--symbol] [--timeframe] [--all]`.

### 2. Resampling (F-0.1.7, `data/resample.py`)
- `resample(snapshot, target_tf, mode="research"|"broker_session")` returns a new snapshot.
- Aggregation:
  - OHLC: first / max / min / last;
  - `volume`, `trades`: sum;
  - `vwap`: volume-weighted;
  - `spread`: last.
- Partial periods at the start and end are dropped. Flag every aggregated bar whose count of source bars is below a threshold.
- Metadata: `derived_from` = parent snapshot key, plus the resampling mode and rules in `notes`. Stored through the T02 store and catalog.
- CLI: `sfac data resample --symbol X --from 1H --to 1D|4H [--mode broker_session]`.

### 3. Split manager (F-0.6.1, `data/split.py`)
- `SplitManager.compute(symbol, timeframe, snapshot) -> Split`: development end, embargo bars, holdout start/end, and a warning when the holdout would have fewer than 30 expected trades (the expected trade rate is an input; for now optional).
- The split is registered in the registry `splits` table (composite snapshot key).
- `DataAccess.bars(symbol, timeframe)` returns **development data only**.
- `SplitManager.open_holdout(candidate_id, symbol, timeframe)` is the **only** path to holdout bars. It calls the registry's `record_holdout_access`; a second call raises `HoldoutAccessError`.
- Local development needs Docker Postgres. Tests use the T03 fixtures and skip cleanly without a DB (CI runs them).

## Tests
- **Quality:** one synthetic snapshot per check type triggers exactly that check; a clean snapshot gives `ok`; a `critical` status blocks use.
- **Resampling:**
  - hand-computed 1H→1D;
  - Sunday merge (no Sunday stamps, Monday bar = Sunday evening + Monday);
  - 1H→4H blocks;
  - the `us_equity` 4H request is rejected;
  - `broker_session` alignment;
  - partial periods;
  - vwap weighting;
  - lineage metadata.
- **Split:**
  - 20 % vs 18-month minimum on short and long histories;
  - embargo applied;
  - `DataAccess` never returns holdout rows (property test over random splits);
  - second holdout access raises, via the DB.
- **Leakage:** resampled bar t uses only source bars inside its period.

## Acceptance
ruff, format, mypy (strict for `data`), pytest pass; CI green. Run `sfac data quality --all` on the snapshots that currently exist, and include the summary in the review.

## Review summary
Write it to `docs/reviews/T05_review.md`. Include:
- the thresholds chosen;
- the quality results on the real snapshots;
- the observed daily-break hours per Dukascopy symbol;
- deviations and open questions.
