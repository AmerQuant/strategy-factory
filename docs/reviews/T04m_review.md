# T04m review — Yahoo auxiliary series: ingest, and the as-of join a filter reads

**Features:** F-0.1.4, **F-0.1.11**, F-0.1.6, F-0.1.8 · **Branch:** `b/T04m-yahoo-aux` (from `main`
`44bed56`) · **Decisions:** D-014, D-316, D-306, D-718, D-719, D-720, D-721 · **Status:** built,
all gates green, acceptance review run and its findings fixed. **Stopped here** (end of the task).

## What was built

1. **Close times verified (D-718).** Each series' daily value is final at the latest instant its
   provider's published schedule lets the day's value change. That is an upper bound, so it holds
   whichever snapshot Yahoo takes. `configs/universe/aux_yahoo.csv` now records `close_time_source`
   and `close_time_checked` next to each series.

   | series | final | status | source (checked) |
   |---|---|---|---|
   | VIX | 16:15 New York | verified | Cboe VIX FAQ (2026-09-19) |
   | **DXY** | **19:15 New York** | verified | ICE FX Indexes Methodology v3.0 §4.1: "The DXY Index is calculated and published until 7:15 PM ET"; the closing level is the last one calculated; every weekday is an index business day (2026-09-22) |
   | **NDX** | **17:15 New York** | verified | Nasdaq-100 Index Methodology (2026): the closing value "may change up until 17:15:00 ET" (2026-09-22) |
   | SPX, DJI | 24:00 New York + 1 day | to_verify | S&P DJI's methodology PDFs answer HTTP 403 to automated reads; a person can open them |
   | RUT | 24:00 New York + 1 day | to_verify | FTSE Russell defines a close as final by status (all constituent prices received), not by a clock time |
   | TNX | 24:00 Chicago + 1 day | to_verify | no Cboe document found that states its calculation hours |

   The documents were read as public documentation (WebSearch and WebFetch, extracted locally with
   a throw-away `pypdf` that is not added to the project); no market data was fetched (D-031).
2. **`data/auxiliary.py`** (the join, pure functions):
   - `final_instants`: a verified time in its zone. Otherwise 24:00 of the session date in the
     series' zone plus `unverified_extra_lag_days`, added in local days so DST cannot shift it. A
     "verified" series without a time is refused.
   - `nyse_calendar` / `weekday_calendar` and `consumer_calendar`: the consuming symbol's sessions
     with their ends. For the NYSE that is the close, early closes included; for the 24x5 markets,
     24:00 UTC.
   - `bar_sessions`: a Sunday FX hour belongs to Monday (D-010); an NYSE hourly bar belongs to its
     New York date.
   - `decision_instants`: the bar's end.
   - `asof_index`: the latest aux bar final **strictly before** the decision; `-1` when there is
     none, or when the value is more than `max_stale_sessions` traded sessions past the session in
     which it became usable (D-719).
   - `build_view` → `AuxView` (`key`, `traded`, the aux arrays, `final_us`, `idx`, `decision_us`,
     `at_bars`). Only aux bars final before the window's last decision are returned.
3. **Access** (`data/split.py`):
   - `DataAccess.aux(aux, traded, timeframe)` reads over the traded symbol's development window.
   - `SplitManager.open_holdout_with_inputs(candidate, symbol, tf, pairs=, aux=, stage=)` gives the
     conversion pairs and the aux series in **one** one-shot access. `open_holdout_with_conversion`
     now delegates to it.
   - `_refuse_aux` in `compute`, `registered` and `development_bars`: an aux series never gets a
     split, a development read or a holdout.
4. **Schedule checks on each series' own calendar (D-720).** `schedule.expected_aux` reads
   `aux_calendar=` from the snapshot notes: `nyse` (VIX, SPX, NDX, RUT, DJI); `nyse_bond`, which is
   NYSE sessions minus `configs/calendars/us_bond_market_closures.csv` (TNX); or `weekdays` (DXY).
   An aux snapshot without the note **fails**; it is never skipped. The closures file holds Columbus
   Day, plus Veterans Day on a weekday or the Monday after a Sunday, on NYSE sessions 2016–2026
   (20 days). It matches the data: all 18 such days in 2016–2025 are flat placeholder rows or
   missing in TNX, and on the two Saturday Veterans Days the Friday carries real values.
5. **Ingest** (`sfac data ingest yahoo`):
   - The reference moves only with `--set-reference`. The old "reference on first ingest" is gone.
   - A re-run with the same data writes nothing.
   - An aux symbol that is also a tradeable universe symbol is refused.
   - The notes carry `aux_calendar=`, `unit=` and the date the close time was checked.
   - `AuxSeries` gains `calendar`, `value_unit`, `close_time_source` and `close_time_checked`; the
     loader refuses a missing or unknown calendar.
6. **Universe:** `core/universe.py` takes an aux series' calendar from the `calendar` column
   (`weekdays` → `24x5`, otherwise `nyse`). **Stream A regenerates `configs/universe.yaml`** (D-394):
   TNX, SPX, NDX, RUT and DJI change from `24x5` to `nyse`, and nothing else changes (checked by
   diffing the generated universe).

## Files changed

- New: `src/strategy_factory/data/auxiliary.py`, `configs/calendars/us_bond_market_closures.csv`,
  `tests/unit/test_F_0_1_11_aux_asof.py`, `tests/leakage/test_F_0_1_11_aux_asof_leakage.py`,
  `scripts/analysis/T04m_join_check.py`, `docs/reviews/T04m_join_check.txt`.
- Changed:
  - Code: `src/strategy_factory/data/split.py`, `schedule.py`, `config.py` (`AuxAsOfConfig.
    max_stale_sessions`, `sessions_file`; `QualityConfig.bond_closures_file`), `cli_yahoo.py`,
    `adapters/yahoo.py`, `download/yahoo.py`, `src/strategy_factory/core/universe.py`.
  - Configs: `configs/universe/aux_yahoo.csv`, `configs/data/aux_series.yaml`.
  - Tests: `tests/unit/test_F_0_1_4_yahoo.py` (a verified close time now needs a cited source and a
    date checked).
- Docs: the task file, the decisions log (D-718 … D-721), `pending.md` (P-89 … P-92 answered),
  `RUNBOOK_batch3-data.md`, `B.md`, `B_data_state.md`.

No new dependency.

## Acceptance criteria → tests

| criterion (task file) | test | result |
|---|---|---|
| F-0.1.11 leakage: no bar reads an aux value final at or after its decision | `tests/leakage/test_F_0_1_11_aux_asof_leakage.py::test_F_0_1_11_no_bar_reads_a_value_not_yet_final` (Hypothesis: random calendars, close times, zones, lags, caps; equity and FX, 1D and 1H) | pass |
| F-0.1.11 truncation: cutting the aux series after any instant T and the bars after the last one decided by T changes nothing | `…::test_F_0_1_11_truncating_the_future_changes_nothing` (T drawn anywhere in the window) | pass |
| Addendum §5.3: equity at the close of d → VIX d−1 | `test_F_0_1_11_aux_asof.py::test_F_0_1_11_equity_at_the_close_of_d_sees_vix_of_d_minus_1` | pass |
| Addendum §5.3: FX daily of d → VIX d | `::test_F_0_1_11_fx_daily_of_d_sees_vix_of_d` | pass |
| Early close | `::test_F_0_1_11_early_close_uses_the_real_close` (2024-07-03, 2024-11-29) | pass |
| `to_verify` one day later; blank close time; zone | `::test_F_0_1_11_unverified_close_time_is_24h_local_plus_one_day`, `::test_F_0_1_11_final_instants_in_the_series_zone` | pass |
| DST on both sides | `::test_F_0_1_11_dxy_19_15_new_york_crosses_the_fx_day_end_with_dst`, `::test_F_0_1_11_hourly_bars_equity_and_fx` | pass |
| Staleness in traded sessions (D-719), independent of the window start | `::test_F_0_1_11_staleness_counts_traded_sessions`, `::test_F_0_1_11_staleness_does_not_depend_on_the_window_start`, `::test_F_0_1_11_value_final_before_the_calendar_start_is_stale` | pass |
| Aux refused as a traded symbol; no split row for an aux key | `::test_F_0_1_11_aux_is_never_a_candidate` | pass |
| The development read ends at `dev_end`'s decision | `::test_F_0_1_11_development_read_ends_at_dev_end` | pass |
| Holdout read only inside the one-shot access; the aux series never recorded; a failing input spends nothing | `::test_F_0_1_11_holdout_read_inside_the_one_shot_access`, `::test_F_0_1_11_a_failing_aux_input_keeps_the_holdout_access` | pass |
| Schedule checks on each series' own calendar, never skipped | `::test_F_0_1_11_aux_schedule_calendars`, `::test_F_0_1_11_bond_closures_follow_the_rule` | pass |
| Close-time provenance (D-718); TNX unit | `::test_F_0_1_11_aux_universe_close_time_provenance`, `test_F_0_1_4_yahoo.py::test_F_0_1_11_aux_universe_close_times`, `::test_F_0_1_11_aux_universe_rejects_a_bad_calendar` | pass |
| Ingest: reference only when asked; idempotent; collision guard | `::test_F_0_1_4_T04m_ingest_reference_only_when_asked_and_idempotent`, `::test_F_0_1_4_T04m_ingest_refuses_a_tradeable_symbol` | pass |
| Indicator on the aux bars read at `idx`; empty window | `::test_F_0_1_11_indicator_on_aux_bars_read_at_idx`, `::test_F_0_1_11_no_aux_value_final_in_the_window` | pass |
| Seven references, hash version 2, with quality reports | store evidence, below | done |

## Store evidence (2026-09-22, `SFAC_DATA_ROOT`)

- **Ingest:**
  - `sfac data ingest yahoo --set-reference` gave 7 snapshots (VIX 9,248 rows from 1990 · DXY
    14,146 from 1971 · TNX 16,166 from 1962 · SPX 24,796 from 1927 · NDX 10,321 · RUT 9,830 ·
    DJI 8,740; all to 2026-09-18).
  - All are `asset_class aux`, hash version 2, and each is the reference.
  - A second run added nothing: the catalog holds 14 events for them (7 `register`, 7
    `set_reference`).
- **Quality** (`sfac data quality --symbol … --timeframe 1D`): `missing_bars` and
  `session_violations` ran on every series, on its own calendar.

  | series | status | schedule findings (own calendar) | other warnings |
  |---|---|---|---|
  | VIX | warning | 2 rows on NYSE holidays: 2026-05-25, 2026-09-07 (real ranges) | 1 spike (2024-08-05, the real VIX spike); 4 daily wick outliers |
  | DXY | warning | 389 of 14,535 weekdays missing (2.68 %), almost all before 2016; since 2016 only 2016-10-10 and 2016-11-11 | 1 spike (1971); 1 stale run; zero volume |
  | TNX | warning | 17 rows on bond-market closures (the flat placeholders); 0 missing | 1 spike (2020-03-09); 35 stale runs; zero volume |
  | SPX | warning | none | zero volume on 22 % (the pre-1950 history) |
  | NDX | ok | none | — |
  | RUT | ok | none | 3 zero-volume bars (info) |
  | DJI | warning | none | 1 spike (2020-03-12) |

  **None is critical, and none is a defect of the series.** These are the calendar differences,
  now visible instead of exempt, and market events.
- **The join on real data** (`scripts/analysis/T04m_join_check.py`, output in
  `docs/reviews/T04m_join_check.txt`; in-memory split ledger, nothing written):
  - **AAPL 1D, development 2016-01-04 … 2023-07-28, 1,905 bars:** the last bar, Friday 2023-07-28,
    reads VIX, NDX and DXY of 07-27 (d−1), and SPX, RUT, DJI and TNX of 07-26 (d−2, unverified).
    Only the first one or two sessions of 2016 have no value: the value there is final before the
    NYSE calendar starts, so its age is unknown.
  - **AAPL 1H, 14,775 bars:** the same pattern.
  - **EURUSD 1H pilot:** Q1 2024 is too short for a split (D-008), so `DataAccess` refuses it until
    T04j; the join ran directly on its bars instead.
    - The 2024-01-10 23:00 UTC bar (ends 19:00 EST) reads VIX of 01-10 but DXY of 01-09, because
      DXY is final only at 19:15.
    - The 2024-03-13 19:00 UTC bar (ends 16:00 EDT) reads VIX of 03-12; the 20:00 bar reads VIX of
      03-13.

## The acceptance reviewer's findings and what was done

- **B1 (blocker, reproduced by the reviewer): fixed.** An aux view that failed after validation
  (e.g. holdout bars beyond the NYSE calendar file) raised **after** the one-shot access was
  recorded, so the candidate's holdout was lost.
  - `open_holdout_with_inputs` now builds the conversion windows and the aux views **before** the
    access. It uses the holdout's bar starts, the timestamps the split is computed from; no price
    is read.
  - It then checks that the bars it read match those starts.
  - Test: `test_F_0_1_11_a_failing_aux_input_keeps_the_holdout_access`.
- **S1: fixed.** An unverified series never uses a proposed time; it always gets 24:00 local + lag.
  A "verified" series without a time is refused (tested).
- **S2: fixed.** An aux snapshot without `aux_calendar=` raises instead of skipping the schedule
  checks (tested).
- **S3: recorded** in the task file's status line: the module is `auxiliary.py`, the stage-6
  method is `open_holdout_with_inputs`, and the cap is `max_stale_sessions`.
- **S4: done by this review,** `B_data_state.md` and `B.md`.
- **N1: fixed.** `MARKETS_24X5` is imported from `schedule`.
- **N2: fixed.** A value final before the consumer calendar's first day counts as stale (tested).
- **N3: fixed.** The truncation property cuts at an arbitrary instant T.
- **N4: accepted, not changed.** Catalog references are keyed by (symbol, timeframe), and the
  collision guard runs at the Yahoo ingest only. A later tradeable ingest of the same name would be
  refused by `DataAccess.aux` ("not an auxiliary series"): it fails safe.
- **N5: fixed.** The holdout test asserts that the aux series is never recorded.

## Gates

After the fixes:
- `uv run pytest -m "not slow"` — 1,587 passed, 0 skipped.
- `uv run pytest tests/parity tests/leakage tests/oracle` — 329 passed.
- `uv run pytest -m db` — 21 passed, 0 skipped.
- `ruff check`, `ruff format --check`, `mypy src` — clean.
- `sfac streams check` — ok.

## Deviations and open points

- **SPX, DJI, RUT and TNX stay conservative** (d−2 for a US equity at the close) until a provider
  document gives their time. S&P DJI's PDFs can be opened by a person; if the supervisor or the user
  provides them, SPX and DJI move to `verified` with no code change.
- **Stream A:**
  - regenerate `configs/universe.yaml` (five aux calendars);
  - keep `asset_class aux` out of stage 1's candidate list (the data layer refuses it);
  - record `AuxView.key` with a run that reads an aux series (rule 8).
- The **reference index per symbol** is stage 5's task (D-721).
