# T05 review — Data quality, resampling, split manager

**Features:** F-0.1.6, F-0.1.7, F-0.6.1 · **Branch:** `feat/T05-quality-resample-split` (stacked on `docs/batch2a`) · **Status:** done, with open questions below

## What was built
| module | content |
|---|---|
| `data/schedule.py` | expected bar schedules: the 24x5 week in New York local time (`SUN 17:00`–`FRI 17:00`), the **daily break learned from the data**, crypto 24x7, NYSE sessions from `nyse_sessions.csv`. `period_start()`: research (00:00 UTC, Sat/Sun → Monday for 24x5, fixed UTC 4H blocks) and broker_session (from the configured session start; daily bar stamped with its trading date). |
| `data/quality.py` | 7 checks, JSON + markdown report, catalog status, `ensure_usable()` gate |
| `data/resample.py` | `resample_bars()` (pure), `resample()` (store + catalog + flags file) |
| `data/split.py` | `compute_split()` (pure), `SplitManager`, `DataAccess`, `SplitLedger` protocol + `RegistryLedger` |
| `data/cli_prep.py` | `sfac data quality [--symbol] [--timeframe] [--all]`, `sfac data resample --symbol X --from 1H --to 1D\|4H [--mode broker_session] [--set-reference]` |
| `data/schema.py` | `SnapshotKey` (catalog key); `SeriesMetadata.derived_from` and `.key()` |
| `data/catalog.py` | columns `derived_from` (JSON) and `quality_status` (default `unchecked`, also for catalogs written before T05); `get`, `quality_status`, `set_quality_status` (logged as a `quality` event) |
| `registry/queries.py` | `get_split(engine, key)` |
| `data/config.py` + `configs/data/{quality,resample,split}.yaml` | every threshold (below) |

## Thresholds chosen (all in config; defaults = YAML values)
| config | key | value |
|---|---|---|
| quality | weekly window (24x5) | `SUN 17:00` → `FRI 17:00` America/New_York |
| quality | break detection | local hour missing on ≥ 50 % of trading days; only gaps ≤ 3 h count (holidays excluded) |
| quality | missing bars | info ≤ 2 %, warning > 2 % |
| quality | schema (duplicates, high<low, OHLC out of range, non-positive, NaN) | critical |
| quality | price spikes | trailing 50 log returns; \|r − median\| > 15 × MAD **and** next return reverses ≥ 50 % → warning |
| quality | stale prices | ≥ 5 identical OHLC bars in a row → warning |
| quality | zero volume | info ≤ 5 %, warning > 5 % (skipped if `volume_quality: none`) |
| quality | DST | ±10 days around each transition → warning |
| quality | session violations | warning |
| resample | `min_source_fraction` | 0.5 (flag bars with < 50 % of the expected source bars) |
| resample | broker session | 17:00 America/New_York |
| split | holdout | 20 %, minimum 18 months |
| split | embargo | `max_lookback_bars` 200 + `max_holding_bars` 50 = 250 bars |
| split | expected-trades warning | < 30 |

## Quality results on the real snapshots (`sfac data quality --all`)
Only the three Dukascopy pilot snapshots (1H, Q1 2024) are in the catalog; no US-equity snapshots exist yet.

| symbol | status | missing | break (local / modal UTC) | failed checks |
|---|---|---|---|---|
| EURUSD | ok | 0 of 1539 | none (continuous) | — |
| XAUUSD | ok | 27 of 1474 (1.83 %) | **17:00 New York / 22:00 UTC** (share 0.98) | missing_bars: info |
| USA500IDXUSD | **warning** | 31 of 1474 (2.10 %) | **17:00 New York / 22:00 UTC** (share 0.95) | missing_bars: warning |

The missing bars are US holidays (Jan 15 MLK, Feb 19 Presidents' Day, Mar 28–29 Good Friday). There are no session violations, spikes or stale runs. The DST check is skipped because Dukascopy data is UTC. Reports are in `SFAC_DATA_ROOT/_quality/<hash>.json|.md` and `_quality/summary.md`.

**Observed daily-break hours:** XAUUSD and USA500IDXUSD: 17:00–18:00 New York, which is 22:00 UTC in winter and 21:00 UTC in summer (the pilot covers the switch on Mar 10). EURUSD: no daily break.

## How each criterion is tested
| criterion | test |
|---|---|
| F-0.1.6 each check type triggers exactly that check | `test_F_0_1_6_quality.py`: missing (warning/info), session violation, 3 schema errors (critical), spike (+ a level shift is *not* a spike), stale, zero volume (+ skipped for `none`), DST (exchange-local only; skipped for UTC). Each asserts the set of failed checks. |
| clean snapshot → ok | `_clean_snapshot_is_ok`, `_no_break_for_continuous_market`, `_break_learned_in_local_time_across_dst` |
| us_equity schedule | `_us_equity_schedule_from_sessions_file` (early close 13:00; bar after the early close = violation; no calendar → skipped) |
| critical blocks use | `_critical_status_blocks_use` (`ensure_usable`), `test_F_0_6_1_critical_quality_blocks_data_access` (`DataAccess.bars` and `open_holdout` refuse) |
| report for every symbol, catalog status, CLI | `_report_files_and_catalog_status`, `_cli_quality_all`, `_old_catalog_rows_are_unchecked` |
| F-0.1.7 hand-computed 1H→1D | `test_F_0_1_7_hand_computed_1h_to_1d` (OHLC + volume sum) |
| no Sunday daily bars; Monday = Sunday evening + Monday | `_sunday_merged_into_monday`, `_saturday_bars_also_go_to_monday` |
| 1H→4H fixed UTC blocks | `_1h_to_4h_fixed_utc_blocks` |
| us_equity 4H (and 1D) rejected | `_us_equity_4h_and_daily_rejected` |
| broker_session alignment | `_broker_session_alignment` (winter 22:00 UTC and summer 21:00 UTC session start, Monday stamp), `_broker_session_4h_blocks_follow_session_start` |
| partial periods; flags | `_partial_periods_dropped`, `_bars_with_few_source_bars_are_flagged` |
| vwap weighting | `_vwap_trades_spread` |
| lineage metadata | `_lineage_metadata_and_store`, `_cli_resample` |
| leakage: bar t only uses source bars of its period | `tests/leakage/test_F_0_1_7_resample_leakage.py`: truncation invariance (Hypothesis, both modes, 4H/1D) and perturbing later periods leaves earlier bars unchanged |
| F-0.6.1 20 % vs 18 months | `_short_history_uses_18_month_minimum`, `_long_history_uses_20_percent` |
| embargo applied | `_embargo_applied` (exactly `lookback + holding` bars between dev end and holdout start) |
| DataAccess never returns holdout rows | `_data_access_never_returns_holdout_rows` (Hypothesis over n, fraction, months, lookback, holding, 1D/1H) |
| second holdout access raises, via the DB | `test_F_0_6_1_split_registered_and_second_holdout_access_raises` (`@pytest.mark.db`: split row with composite key, snapshot mirrored as reference, second access raises, also from a second engine, exactly 1 `holdout_access` row) |
| access recorded before any holdout bar is read | `_holdout_access_logged_before_reading` |
| moved boundaries refused | `_register_once_and_refuse_moved_boundaries` |

## Acceptance
| command | result |
|---|---|
| `ruff check .` / `ruff format --check .` | ✅ / ✅ 150 files |
| `mypy src` (strict for `data`) | ✅ 61 files |
| `pytest` | ✅ **278 passed** (47 new) |
| `pytest tests/parity tests/leakage` | ✅ 2 passed (the new leakage tests) |
| `pytest -m db` | ✅ 13 passed, **0 skipped** (JUnit check) |
| `sfac data quality --all` | ✅ see above |

## Deviations and decisions to confirm
1. **The daily break is learned in New York local time,** not as a fixed UTC hour. The task says "learned from the data (the modal break hour)". In UTC the break moves between 22:00 and 21:00 with US DST, so a single UTC hour would flag half the year as missing or violating. The report gives both the local hour and the modal UTC hour.
2. **The 24x5 week window is Sunday 17:00 to Friday 17:00 New York time** (config). This matches all three pilots. It is an assumption for the other Dukascopy instruments.
3. **Resampling is limited to fx, metal, energy_cfd, index_cfd and crypto.** us_equity is rejected, because daily bars come from Alpaca and 4H is only for 24h markets. futures, iran_equity and aux are rejected too: there is no day rule for them yet.
4. **Saturday bars of 24x5 markets are also merged into Monday.** The task mentions only Sunday, but a Saturday daily bar should not exist either.
5. **Resampled 4H bars may start on Sunday** (e.g. the 20:00–24:00 UTC block). The "never on a Sunday" rule applies to daily bars only.
6. **A third config file, `configs/data/resample.yaml`,** holds `min_source_fraction` and the broker session. The task names only quality.yaml and split.yaml.
7. **Flagged resampled bars are listed in `SFAC_DATA_ROOT/_resample/<hash>.flags.csv`,** with their count in the snapshot notes. The bar schema has no flag column, and extra columns are critical.
8. **The broker_session mode is recorded as `mode=broker_session` in the notes.** The quality schedule reads it from there. broker_session snapshots never become the reference.
9. **Split boundaries are inclusive bar timestamps.** Recomputing a registered split with different boundaries raises an error (a moved boundary would leak holdout bars). As a result, changing `max_lookback_bars` or `max_holding_bars` for an already split snapshot needs a new snapshot or an explicit reset, which does not exist yet.
10. **`SplitManager` takes a `SplitLedger`.** Production uses `RegistryLedger` (PostgreSQL). The Hypothesis property test uses an in-memory ledger that has the same one-shot and foreign-key rules, so it runs without a database. The DB test proves the real one-shot behaviour.
11. **The registry requires the candidate to exist** before a holdout access (FK from T03). `open_holdout` therefore only works for registered candidates.
12. **Tests-first was not followed strictly.** I explored the real pilot data and wrote the modules first, then the tests from the acceptance criteria. The tests found three real issues, all fixed: two wrong expectations of mine, and the registry tzinfo bug in the next item.
13. **Registry timestamps are normalized to `datetime.UTC`.** psycopg returns an `Etc/UTC` tzinfo that Polars refuses to compare with `UTC` columns.

## Open questions
1. **F-0.6.1 says holdout access is allowed "only from stage 6".** `open_holdout` has the task's signature `(candidate_id, symbol, timeframe)` and does not check the stage. I propose enforcing the stage in `RunContext` (T10) by passing the split manager only to stage 6. Is that acceptable, or should `open_holdout` take a stage argument now?
2. **`configs/calendars/nyse_sessions.csv` is not in the repo** (T04e phase B was not run here). us_equity missing and session checks are skipped with a clear reason until it exists.
3. **The embargo defaults (200 + 50 bars) are placeholders** until the component registry reports lookbacks and holding periods. Please confirm or change them.
4. **Quality thresholds:** missing 2 %, spikes k = 15 × MAD, stale ≥ 5 bars, zero volume 5 %. Please confirm. USA500 is at 2.10 % because of three US holidays in one quarter. A holiday-aware schedule for index CFDs could come later.
