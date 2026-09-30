# T04j review — Dukascopy h1: eight instruments ingested over their complete windows

**Features:** F-0.1.3 (Dukascopy adapter, mid + spread), F-0.1.6 (quality per snapshot), F-0.1.7
(resampling, D-010 / D-032), F-0.1.8 (immutable snapshots, catalog, references), F-0.2.2 (the
week-open spread key, D-716). **Branch:** `b/T04j-dukascopy-ingest`. **Stream B.**

**Decisions:** D-715, D-716, D-717 (the plan), **D-657** (the gate is per instrument), **D-661**
(the complete window), **D-672** (a verified market event; the D-717 stop is per instrument),
**D-673** (the bounded OHLC repair) — the last four the supervisor's, on the user's choices.
P-87, P-88, P-94, P-95 answered. **Open, not blocking: P-96** (whether a series is extended month
by month; the resume command does not, see below).

**The task is partial by decision.** The download is still running. D-657 and D-661 let the complete
instruments in now, and the rest follow through one command as their downloads complete (below).
**8 of 29** instruments are in the store; 21 wait.

## What was built

1. **The coverage gate, per instrument (D-386 copied; D-657).** `sfac data coverage dukascopy`
   reports per instrument and month; a gap is a required month without a file on either side.
   `sfac data ingest dukascopy` never writes an instrument across a gap and has no `--allow-gaps`.
2. **The complete window (D-661).** `coverage.dukascopy_windows`: per instrument, the longest
   contiguous complete run of months that ends at the last complete month, the gap that bounds it
   and the months missing before it. The ingest reads **only** the window's months, checks
   **D-008** on the window's 1H bars and on their D-032 daily series (in memory, `compute_split`)
   **before writing**, and leaves a window too short to split waiting. A partial window's snapshot
   carries `D-661 window <first>..<last>: <n> month(s) missing before it, the latest <gap>` in its
   notes. A window that grows is a new versioned snapshot; the references move; nothing is
   overwritten.
3. **Reading alongside the download.** `rawfiles.is_settled`: the writer links a finished payload,
   then its manifest, so a month counts only once both exist and no `.partial` is left. The gate,
   the window, the measurements and `raw_pairs` (what the ingest reads) all read settled months only.
4. **D-717, per instrument (D-672).** `scripts/analysis/T04j_defects.py` re-measures the T04k /
   T04l defect families over each window. Any family holds **that** instrument; the clean ones
   proceed. A bar listed in `verified_events` (`configs/data/dukascopy.yaml`) is reported, never a
   stop (`coverage.verified_flags`).
5. **The bounded OHLC repair (D-673).** In the adapter, per side and before the mid, a bar whose
   open or close lies outside its own high/low by at most `ohlc_repair_max` (0.00002) has the high
   or low widened just enough; no open or close ever changes; a larger excess is left for the
   store's bar validation to refuse. The count goes into the snapshot notes per side and month.
6. **The single resume command.** `uv run python scripts/pilots/T04j_resume.py` (`--dry-run`,
   `--symbols`): windows → status → D-008 → D-717 → ingest 1H (a hash-version-1 pilot with
   `--rehash`) → 1D (`sfac data resample --to 1D --set-reference`) → quality → `sfac costs show`.
   Its per-instrument state is `data/window_state.reference_state`:
   - `ingested`: nothing to do, so a re-run writes nothing;
   - `incomplete`: the 1D or a quality report is missing, so derive without a new ingest;
   - `absent`, `pilot` (hash version 1) or `grown`: ingest. `grown` means a gap closed and the
     window now starts earlier than the reference.

   A new month at the end of the window does **not** re-derive (P-96). The ingest gets
   `--expect-window` set to the windows D-717 measured; if the download moved one in between, it
   refuses that instrument and writes nothing, so D-717 always covers exactly what is written. The
   download script ends by naming the command.
7. **The download script** checks Node.js and `tools/dukascopy/node_modules/dukascopy-node` before
   step 1 and prints the `npm ci` step (exit 3), instead of failing inside the download.
8. **The week-open spread key (D-716)**, built in the plan phase: `week_open_mask`,
   `SpreadHourly.week_open`, charged by `build_cost_arrays` at 1H and on Monday at 1D.

## The window table at ingest time (2026-09-30 06:25 UTC; `docs/reviews/T04j_windows.csv`)

Last complete month 2026-08. "Kept" = the window's share of the instrument's required months
(from 2010-01, or its own later start). D-008 is tested on the window's actual bars.

| instrument | window | years | kept | bounding gap | missing before | 1H bars | 1D bars | D-008 1H / 1D | state |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 2010-01 … 2026-08 | 16.67 | 100 % | — | 0 | 103,935 | 4,345 | ✅ / ✅ | **ingested** (pilot re-hashed) |
| GBPUSD | 2010-01 … 2026-08 | 16.67 | 100 % | — | 0 | 103,920 | 4,345 | ✅ / ✅ | **ingested** |
| USDJPY | 2010-01 … 2026-08 | 16.67 | 100 % | — | 0 | 103,925 | 4,345 | ✅ / ✅ | **ingested** |
| USDCHF | 2010-01 … 2026-08 | 16.67 | 100 % | — | 0 | 103,916 | 4,345 | ✅ / ✅ | **ingested** (D-672 event) |
| GBPCHF | 2013-03 … 2026-08 | 13.5 | 81 % | 2013-02 | 11 | 84,126 | 3,520 | ✅ / ✅ | **ingested** (D-661) |
| AUDUSD | 2014-06 … 2026-08 | 12.25 | 74 % | 2014-05 | 2 | 76,362 | 3,194 | ✅ / ✅ | **ingested** (D-661) |
| USDCAD | 2016-04 … 2026-08 | 10.42 | 63 % | 2016-03 | 11 | 64,938 | 2,716 | ✅ / ✅ | **ingested** (D-661; see deviations) |
| XAUUSD | 2019-12 … 2026-08 | 6.75 | 41 % | 2019-11 | 6 | 39,891 | 1,751 | ✅ / ✅ | **ingested** (D-661, pilot re-hashed) |
| XAGUSD | 2026-01 … 2026-08 | 0.67 | 4 % | 2025-12 | 12 | 3,921 | 171 | ❌ / ❌ | waits: shorter than D-008 |
| DEUIDXEUR | 2026-03 … 2026-08 | 0.5 | 4 % | 2026-02 | 11 | 2,959 | 130 | ❌ / ❌ | waits |
| CADJPY | 2026-06 … 2026-08 | 0.25 | 2 % | 2026-05 | 15 | 1,584 | 65 | ❌ / ❌ | waits |
| NZDUSD | 2026-07 … 2026-08 | 0.17 | 1 % | 2026-06 | 107 | 1,056 | 44 | ❌ / ❌ | waits |
| USSC2000IDXUSD | 2026-07 … 2026-08 | 0.17 | 2 % | 2026-06 | 95 | 1,008 | 44 | ❌ / ❌ | waits |
| EURAUD | 2026-08 | 0.08 | 0.5 % | 2026-07 | 113 | 507 | 21 | ❌ / ❌ | waits |
| 15 more | — | 0 | 0 % | 2026-08 | 73–200 | — | — | ❌ | waits: no window (2026-08 not downloaded yet) |

The 15 without a window: EURJPY, GBPJPY, EURGBP, EURCHF, AUDJPY, LIGHTCMDUSD, BRENTCMDUSD,
USA500IDXUSD, USA30IDXUSD, USATECHIDXUSD, GBRIDXGBP, JPNIDXJPY, FRAIDXEUR, AUSIDXAUD, HKGIDXHKD.
The download is working through them; most gaps are months not reached yet, not failures.
Per-instrument state: `docs/reviews/T04j_instrument_status.csv`.

### XAUUSD — a window that a later download may extend

**XAUUSD's window (2019-12 … 2026-08, 6.75 y of 16.67) is bounded by scattered one-sided months
that look like failed fetches**. Each month is missing on one side only, while the other side is
present: the ask for 2011-03, 2013-10, 2014-12 and **2019-11**, and the bid for 2011-11 and 2014-09. A later download pass may fill them and
extend the window to the full history. When it does, `scripts/pilots/T04j_resume.py` re-derives
XAUUSD over the longer window **as a new versioned snapshot** (D-661): the 1H reference no longer
spans the current window, so it is not *done*. The old snapshots stay; the references move.
**Stream A must regenerate `configs/universe.yaml` after that merge (D-394).** The same holds for
GBPCHF, AUDUSD and USDCAD, whose windows are also bounded by earlier gaps.

### USDCHF — the SNB day is kept (D-672)

The D-717 re-measure flagged **one** bar on USDCHF: **2015-01-15 09:00 UTC**, O 1.02128, H 1.02202,
**L 0.72705**, C 0.87536, spread 0.00539 (about 50× the hours around it). This is the hour the
**Swiss National Bank removed the EUR/CHF floor** (09:30 UTC). The next hours trade 0.848–0.906 and
the price never returns to 1.02: a real repricing, not a print that reverts. It is kept
**unchanged** and listed in `configs/data/dukascopy.yaml` (`verified_events`: instrument, bar,
family, source, decision), so a re-derive reports it and does not stop. Any other flag still
stops. A backtest must face this kind of day. The disaster stop exists for it, and 2015-01 is
already one of stage 6's crisis periods (D-150). **Correcting or removing such a bar would make
every backtest on CHF optimistic.**

## D-717 re-measured over the windows (`docs/reviews/T04j_defects_ingest.csv`)

| instrument | 1H bars | frozen | long gaps | wick flags | verified events | spread spikes | zero spread | Sunday bars | weekday holes (h) | weekend 1D bars |
|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 103,935 | 0 | 0 | 0 | — | 1,187 | 1 | 2,320 | 88 | 0 |
| GBPUSD | 103,920 | 0 | 0 | 0 | — | 864 | 0 | 2,306 | 89 | 0 |
| USDJPY | 103,925 | 0 | 0 | 0 | — | 1,580 | 0 | 2,310 | 89 | 0 |
| USDCHF | 103,916 | 0 | 0 | 0 | 2015-01-15 09:00 | 769 | 0 | 2,308 | 89 | 0 |
| GBPCHF | 84,126 | 0 | 0 | 0 | — | 587 | 0 | 1,870 | 92 | 0 |
| AUDUSD | 76,362 | 0 | 0 | 0 | — | 93 | 0 | 1,696 | 71 | 0 |
| USDCAD | 64,938 | 0 | 0 | 0 | — | 134 | 0 | 1,443 | 56 | 0 |
| XAUUSD | 39,891 | 0 | 0 | 0 | — | 25 | 0 | 579 | 1,059 | 0 |

**No family is present** on any ingested instrument: 0 frozen stretches, 0 long gaps, 0 unverified
bad prints. Saturday bars: 0 everywhere. XAUUSD's weekday holes are the metals' **daily 1-hour
break**, which the quality check learns (`break_utc 21`), not a defect.

**Spread spikes (one line, as D-717 asks):** hours above 10× their 500-bar rolling median (rollover
and the Sunday open) occur, but they reach costs only through D-523's per-UTC-hour **median**
(`broker_scaled_table`), which they barely move (`docs/reviews/T04j_spread_by_hour.csv`). The
Sunday open, which the median would hide, has its own key (D-716).

## The OHLC repair (D-673)

Measured on **every** settled raw month file (29 instruments, both sides): the defect exists in
**four files, all 2024-10**. The store refused EURUSD and USDCHF on the first run
(`ohlc_outside_range`), and nothing was written for them until D-673.

| instrument | side | month | bars widened | largest excess |
|---|---|---|---|---|
| EURUSD | bid | 2024-10 | 13 | 0.00001 |
| EURUSD | ask | 2024-10 | 28 | 0.00001 |
| USDCHF | bid | 2024-10 | 14 | 0.00001 |
| EURAUD | ask | 2024-10 | 5 | 0.00002 (not ingested yet) |

The counts are in the snapshot notes: EURUSD `41 side bar(s) … 2024-10: bid 13, ask 28`; USDCHF
`14 side bar(s) … 2024-10: bid 14, ask 0`. **It is not an optimistic repair:**
- A wider range is harsher on stops: a stop inside it is hit, never spared. It can also fill a
  take-profit or limit order the source high/low did not reach, but only up to the bar's own open
  or close, a price that did print in that hour. The effect is at most 0.00002 on about 55 bars.
- No open or close moves; those are the prices a backtest fills at and marks to.
- Re-downloading would not fix it: the 2024-10 files fetched on 2026-09-19, -21 and -29 agree bar
  for bar, so the defect is in the source.
- **Units:** D-673's wording says "two pips". The limit that applies is the config value, 0.00002,
  which is 2 *pipettes* (0.2 pip) on a 5-decimal pair like EURUSD. The observed excesses are
  0.00001, a tenth of a pip.
- `_REPAIR_SLACK = 1e-9` in the adapter is a floating-point comparison slack, not a threshold.

The six other ingested instruments needed no repair, so their notes, data and hashes are exactly
what they were before D-673. The five ingested on 2026-09-29 kept the same snapshot hashes.

## Store evidence (2026-09-30, `SFAC_DATA_ROOT`)

| instrument | 1H reference | hash v | quality | 1D reference | 1D bars | quality | 1D derived from the 1H | weekend 1D bars | notes |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | `71436af94075` | 2 | warning | `d8c863a810e7` | 4,345 | ok | ✅ | 0 | D-673 repair; `rehash v1→v2` from `899ac7451468` |
| GBPUSD | `9a8936a8cdf8` | 2 | warning | `2c330a87b631` | 4,345 | ok | ✅ | 0 | |
| USDJPY | `762c42fd732d` | 2 | warning | `c6c66e065581` | 4,345 | ok | ✅ | 0 | |
| USDCHF | `04d00dd4c0ee` | 2 | warning | `feda9208ac70` | 4,345 | ok | ✅ | 0 | D-673 repair; D-672 event kept |
| GBPCHF | `20e4b3b5d018` | 2 | warning | `25d1ed75f4c8` | 3,520 | ok | ✅ | 0 | D-661 window |
| AUDUSD | `2cd53e627030` | 2 | warning | `271a4e3d9e7d` | 3,194 | ok | ✅ | 0 | D-661 window |
| USDCAD | `edef48d99005` | 2 | warning | `432d7ca43c97` | 2,716 | ok | ✅ | 0 | D-661 window |
| XAUUSD | `97d84911f9a8` | 2 | warning | `c6c9d2fa236c` | 1,751 | ok | ✅ | 0 | D-661 window; `rehash v1→v2` from `4e135eb4225f` |

- **References:** 16 (8 × 1H + 8 × 1D), plus the USA500IDXUSD pilot (hash v1, still the reference,
  since its window does not exist yet). The EURUSD and XAUUSD v1 pilots stay in the store, no
  longer referenced (T04e §1). 19 Dukascopy snapshots in all.
- **Quality:** every snapshot has a report, and no reference is `critical`.
  - 1H is `warning` on every instrument: `missing_bars:info` (holidays, about 0.4 %),
    `price_spikes:warning`, and `session_violations:warning` on EURUSD, GBPUSD, USDJPY, USDCHF and
    GBPCHF (a handful of Sunday 21:00 UTC opens in 2010's winter weeks).
  - 1D is `ok` on every instrument (`missing_bars:info` only).
  - The schedule checks `missing_bars` and `session_violations` **executed** on all 16.
  - The only skipped checks: `dst` (the source is UTC), and on 1H the daily-only checks
    (`daily_wick_outlier`, `daily_extreme_unsupported`).
  - On 1D, `daily_extreme_unsupported` is skipped with "no hourly series for this symbol" although
    these instruments have one. The T04i check looks only for the Alpaca hourly series (see the
    deviations).
- **A re-run writes nothing:** after the ingest, `T04j_resume.py --dry-run` reports all eight as
  *ingested* with nothing to do, and the resume run of 2026-09-30 left the five ingested on
  2026-09-29 untouched. Tested at chunk level and at resume-state level (below).
- **D-008 splittable (the candidate universe):** all **8** instruments, in **both** 1H and 1D.

## Costs (`sfac costs show`, the 1H development segment, D-523 / D-350)

| instrument | profile | broker spread | scale factor | filled hours | week open (unscaled) |
|---|---|---|---|---|---|
| EURUSD | moneta_EURUSD+ | 0.0000261 | 0.608 | 0 of 24 | 0.00014 |
| GBPUSD | moneta_GBPUSD+ | 0.0000418 | 0.350 | 0 of 24 | 0.00038 |
| USDJPY | moneta_USDJPY+ | 0.00436 | 0.872 | 0 of 24 | 0.016 |
| USDCHF | moneta_USDCHF+ | 0.000074 | 0.555 | 0 of 24 | 0.00047 |
| GBPCHF | moneta_GBPCHF+ | 0.0000882 | 0.328 | 0 of 24 | 0.00119 |
| AUDUSD | moneta_AUDUSD+ | 0.0000622 | 0.560 | 0 of 24 | 0.00022 |
| USDCAD | moneta_USDCAD+ | 0.0000203 | 0.158 | 0 of 24 | 0.00046 |
| XAUUSD | moneta_XAUUSD+ | 0.0752 | 0.199 | 0 of 24 | 0.4615 |

All eight resolve, every profile is `verified`, and every UTC hour has data, so none is filled
(D-350). The scale factor is Moneta's spread divided by Dukascopy's bar-weighted mean. Every
factor is below 1: the broker quotes tighter than the Dukascopy mid-feed spread. USDCAD (0.158)
and XAUUSD (0.199) are the largest adjustments.

## Acceptance criteria → tests

| criterion (task file, as amended by D-657 / D-661 / D-672 / D-673) | evidence |
|---|---|
| Coverage report in the review; the gate passed on what is ingested, otherwise nothing written | table above; `test_F_0_1_3_T04j_a_complete_set_passes_and_the_current_month_is_not_required`, `…_a_month_on_one_side_only_is_a_gap`, `…_months_before_the_instrument_start_are_not_required`, `…_the_latest_version_of_a_month_counts`, `…_the_verdict_ignores_manifest_fields`, `…_the_ingest_refuses_a_gapped_set_and_writes_nothing`, `…_the_coverage_command_reports_and_exits_on_a_gap` |
| Per instrument (D-657) | `…_D657_a_complete_instrument_is_ingested_while_one_without_window_waits`, `…_D657_a_waiting_instrument_named_alone_is_refused_and_writes_nothing` |
| The window (D-661): only its months; D-008 before writing; a closed gap → a new versioned snapshot | `…_D661_the_window_ends_at_the_last_complete_month_after_the_last_gap`, `…_D661_a_missing_last_month_leaves_no_window`, `…_D661_a_complete_instrument_has_the_whole_span`, `…_D661_a_gapped_instrument_is_ingested_over_its_window_only`, `…_D661_a_window_shorter_than_D008_waits_and_writes_nothing`, `…_D661_a_closed_gap_re_derives_a_new_versioned_snapshot` |
| Never read a month still being written | `…_a_month_still_being_written_is_not_counted` (3 cases), `…_the_ingest_reads_only_settled_months` |
| Each ingested instrument has a v2 1H reference and a 1D reference derived from it; pilots re-hashed, old snapshots kept | store evidence; `…_end_to_end_ingest_then_the_D032_daily_reference` |
| D-010 / D-032; no daily bar on a weekend | `test_F_0_1_7_sunday_merged_into_monday`, `…_saturday_bars_also_go_to_monday`, `…_end_to_end_ingest_then_the_D032_daily_reference` (Sunday opens Monday, no weekend stamp, spread = the last hour's); store: 0 weekend 1D bars |
| The 1D reference moves only when the 1H one does | `…_the_1D_reference_moves_only_when_the_1H_one_does` |
| D-717 re-measured, no family present; the spread-spike line | the D-717 table above |
| D-672: the verified event reported, any other flag stops; per instrument | `…_D672_a_verified_event_is_reported_and_any_other_flag_still_stops`, `…_D672_the_usdchf_snb_bar_is_listed_with_its_source`; the run: USDCHF reported, not held |
| D-673: widen within the limit, never a price, larger refused, counted per month | `test_F_0_1_3_D673_an_excess_within_the_limit_widens_the_range_and_keeps_every_price`, `…_an_excess_above_the_limit_is_left_for_the_store_to_refuse`, `…_the_adapter_counts_the_repair_per_month_in_the_notes` (an untouched series keeps its notes) |
| Every snapshot has a quality report; no schedule check `skipped` | store evidence |
| `sfac costs show` resolves | costs table |
| A re-run writes nothing | `…_D657_a_rerun_of_an_ingested_instrument_writes_nothing`; `…_D661_resume_state_absent_incomplete_ingested_and_a_rerun_is_done`; store: the dry re-run shows all eight done |
| The resume re-derives a closed gap, not a new month; a pilot is re-hashed | `…_D661_resume_re_derives_a_closed_gap_but_not_a_new_month`, `…_D661_resume_state_of_a_pilot` |
| D-717 covers exactly what is written, while the download runs | `…_D717_the_ingest_refuses_a_window_that_moved_since_it_was_measured` |
| The week-open key (D-716), and the leakage gate still passes | `tests/unit/test_F_0_2_2_week_open_spread.py` (6 tests); `tests/leakage/test_F_0_2_2_broker_scaling_dev_only.py` |

## Files changed

- `src/strategy_factory/data/coverage.py`: the Dukascopy coverage frame (settled months),
  `Window` / `dukascopy_windows` (D-661), `verified_flags` (D-672).
- `src/strategy_factory/data/cli_dukascopy.py`: `coverage dukascopy`; `ingest dukascopy` per
  instrument over the window, with `d008_short` before writing and `--expect-window`.
- `src/strategy_factory/data/window_state.py` (new): `reference_state`, the resume command's
  per-instrument state.
- `src/strategy_factory/data/adapters/dukascopy.py`: `repair_ohlc` and its note (D-673).
- `src/strategy_factory/data/download/rawfiles.py`: `is_settled`.
  `src/strategy_factory/data/download/dukascopy.py`: `raw_pairs` reads settled months only.
- `src/strategy_factory/data/config.py`: `VerifiedEvent`, `DukascopyConfig.verified_events` and
  `ohlc_repair_max`. `configs/data/dukascopy.yaml`: both values.
- `src/strategy_factory/costs/{arrays,profile,cli}.py`: the week-open key (D-716, plan phase).
- `scripts/analysis/T04j_{coverage,defects,spread_hours,windows}.py`,
  `scripts/pilots/T04j_resume.py`, `scripts/pilots/T04j_dukascopy_download.ps1`.
- Tests: `tests/unit/test_F_0_1_3_dukascopy_coverage.py`, `tests/unit/test_F_0_1_3_dukascopy.py`,
  `tests/unit/test_F_0_2_2_week_open_spread.py`,
  `tests/leakage/test_F_0_2_2_broker_scaling_dev_only.py` (D-716, approved).
- Docs: this review, the task file, the CSVs under `docs/reviews/T04j_*`, the decisions log, the
  pending questions, `docs/streams/B.md`.
- No new dependency. Nothing under `configs/costs/` or any stream-A path.

## Deviations and open points

1. **USDCAD was ingested although the instructions named seven.** Between the two resume runs the
   download completed USDCAD's window (2016-04 … 2026-08, 10.42 y). It meets D-008 and is clean
   (0 families, no repair), so D-661 admits it. The resume script had no instrument filter and
   ingested every eligible instrument. Snapshots are immutable, so it stays unless the supervisor
   wants it retired; a `--symbols` filter now exists for a limited run.
2. **A changed test:** `test_F_0_1_3_T04j_the_verdict_ignores_manifest_fields` (previously
   `…_ignores_the_manifest`). A data file whose manifest is not yet written is now **not yet
   settled**, so it counts as a gap. D-711 still holds: no manifest **field** decides coverage.
3. **`daily_extreme_unsupported` does not see a Dukascopy 1H series.** The T04i daily check skips
   the eight 1D snapshots ("no hourly series for this symbol"). It is not a schedule check, and a
   Dukascopy daily bar is **built from** its own hourly bars (D-032), so it cannot be unsupported by
   them. It is left as is and noted here rather than changed inside T04j.
4. **P-93** (the aux/tradeable name collision) remains open and is not T04j's.
5. **For stream A** (T12, D-716): read a daily FX cost from the **1H development segment**;
   `build_cost_arrays(..., timeframe="1D")` charges `week_open` on Monday and hour 0 Tuesday to
   Friday; a fill inside a daily bar uses the broker spread. **After this merge:**
   - regenerate `configs/universe.yaml` (D-394): eight Dukascopy instruments now have references;
   - regenerate it again after any later resume run that adds an instrument or re-derives one.

## The acceptance reviewer's findings and what was done

No blockers. Should-fix:

1. **The D-717 measurement and the ingest could see different windows** while the download runs,
   and an unmeasured window could then become the reference. **Fixed:** the resume command passes
   the measured windows with `--expect-window`, and the ingest refuses an instrument whose window
   moved, writing nothing for it. Tested.
2. **The resume re-derived on a new month as well as a closed gap**, which D-661 does not say.
   **Fixed:** `reference_state` re-derives only when the window starts earlier (a gap closed); a new
   month at the end, or a month not yet downloaded, leaves an ingested instrument `ingested`.
   Tested. The question itself is raised as **P-96** (not blocking).
3. **`d008_short` and the two analysis scripts used `ResampleConfig()` defaults.** **Fixed:** they
   use `load_resample_config()`. The YAML equals the defaults today, so no number changed.
4. **No tests for the resume state.** **Fixed:** the logic moved to `data/window_state.py`, with
   three tests (absent → incomplete → ingested; a closed gap versus a new month; a pilot).
5. **The review's gates were empty and it said "nothing open".** **Fixed:** below and at the top.

Nits:
- **Done:** `VerifiedEvent.ts` is an `AwareDatetime`, so a naive time in YAML is refused at load
  rather than silently never matching. An instrument with no required month no longer raises
  `KeyError` in the ingest. `list[Instrument]` replaces the `type: ignore`. The TP / limit
  argument and the pip units are stated in the D-673 section.
- **Left, with the reason:**
  - `T04j_defects.py` keeps cwd-relative paths; it is run from the repo root like every
    `scripts/analysis` script.
  - `T04j_defects.py` still upserts its measurement CSV under a dry run: it is a measurement, not
    the store. The ingest-time copy is the one committed.
  - `SPREAD_SPIKE_X` is measurement only, as its comment says.
  - `week_open_mask` on a slice that starts after the real week open marks the next bar, which is
    pessimistic, not look-ahead.
  - `paths` is not re-checked against both sides inside the ingest: the running download never
    writes a `--refresh` version.

## Gates

Final run on the branch rebased onto `main` `1413069` (#58 and #60 in):

| gate | result |
|---|---|
| `ruff check .`, `ruff format --check .`, `mypy src` | clean |
| `pytest -m "not slow"` | 2,575 passed, 1 failed (the local-only case below) |
| `pytest tests/parity tests/leakage` | 866 passed |
| `pytest -m db -rs` | 24 passed, 0 skipped |
| `sfac streams check --base origin/main` | ok (ownership, ids, one Alembic head) |

**One local-only failure, expected:** `test_F_X_9_repo_alembic_heads_matches_alembic_itself` runs
`uv run alembic heads`. That tries to re-sync the venv, which cannot replace `.venv/Scripts/sfac.exe`
while the user's Dukascopy download holds it. The code is not at fault:
- `uv run --no-sync alembic heads` gives the single head `0001_initial`, which is what the test
  asserts;
- CI runs the test on a clean venv.

The dependency `arch`, which #60 added, was installed at its locked version (8.0.0), and
`uv sync --dry-run` shows the venv matching the lock except for the editable project itself.
