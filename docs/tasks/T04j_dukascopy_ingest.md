# T04j — Dukascopy h1 full ingest: 29 FX / metal / energy / index CFD series, 1H and D-032 daily

**Features:** F-0.1.3 (Dukascopy adapter, mid + spread), F-0.1.6 (quality per snapshot), F-0.1.7
(resampling, D-010 / D-032), F-0.1.8 (immutable snapshots, catalog, references)
**Priority:** before FX/metals can enter any candidate universe (supervisor, 2026-09-22) ·
**Depends on:** T04e (the adapter, the pilots), T05 (the resampler) · **Branch:** `b/T04j-dukascopy-ingest`
from `main`.

> **T04j unblocks costs, not only data.** All 29 cost profiles for these symbols are
> `broker_scaled` (D-523): each resolves its hourly spread from the **Dukascopy 1H reference** of its
> symbol (`costs/cli.py:70`, `costs/arrays.py:266`). Until T04j ingests the 1H series, none of the 29
> has a usable cost, and none can run (rule 4).
>
> **T04j does not block T12 (D-715).** D-020's phasing is the order of work, not a prohibition: stage 1
> runs on US equities and ETFs now; FX, metals and index / energy CFDs join the candidate universe
> when T04j completes.

**Status:** plan approved 2026-09-22 (D-715, D-716, D-717). The coverage gate and the week-open
spread key are built. **D-657 (supervisor, 2026-09-29): the gate is per instrument** -- a complete
instrument is ingested now, a gapped one waits for its download; no instrument is ever ingested with
a gap. **D-661 amends it:** an incomplete instrument is ingested over its longest contiguous
complete window ending at the last complete month, if that window meets D-008 (measured by
`scripts/analysis/T04j_windows.py`; the ingest waits for the supervisor's review of that table).
Built for D-657: the per-instrument refusal in `sfac data ingest dukascopy`, the D-717
re-measure per instrument (`scripts/analysis/T04j_defects.py`, exit 1 on any family) and the single
resume command `uv run python scripts/pilots/T04j_resume.py` (coverage -> D-717 -> ingest 1H ->
1D -> quality -> costs, skipping instruments already done; `--dry-run` stops after D-717).
**2026-09-29: 0 of 29 instruments complete; the newest raw file is from 2026-09-22 16:05 UTC** --
the download has not written for a week, and every instrument still misses months (scattered
one-sided months on the near-complete ones: failed fetches a re-run fills). Nothing is ingested.

Read first: `CLAUDE.md` (rules 3, 7, 10, 11), D-010, D-020, D-026, D-028, D-031, D-032, D-323, D-350,
D-386, D-523, D-707, D-708, D-714, D-715, D-716, D-717; `docs/reviews/T04e_review.md`, `T05_review.md`, `T06b_review.md`,
`T04h_review.md` (the coverage gate this task copies).

## Why

No FX, metal, energy or index symbol can be researched today. The three Dukascopy references in the
store are the T04e **Q1-2024 pilots** (EURUSD, XAUUSD, USA500IDXUSD 1H, hash version 1), and the 29
cost profiles cannot resolve without the full 1H series (above).

## Measured input state (2026-09-22) — `scripts/analysis/T04j_coverage.py` → `docs/reviews/T04j_raw_coverage.csv`

Raw layout: `SFAC_RAW_ROOT/fx_metals_cfd/dukascopy/h1/<SYMBOL>/{bid,ask}/<YYYY-MM>.csv.gz`, one
immutable file per month and side, with a manifest (`row_count`, tool `dukascopy-node 1.50.0`, UTC
offset 0). Expected months: 2010-01 (`h1_start`) … 2026-08 (the last complete month); later for an
instrument that listed later (the index and energy CFDs: 2010-12 … 2018-08, per
`configs/universe/dukascopy.csv`).

| state | instruments |
|---|---|
| no file at all | **14**: USDCHF, AUDUSD, USDCAD, GBPJPY, EURGBP, EURCHF, USA30IDXUSD, USATECHIDXUSD, DEUIDXEUR, GBRIDXGBP, JPNIDXJPY, FRAIDXEUR, AUSIDXAUD, HKGIDXHKD |
| started, far from complete | USDJPY (to 2018-01), NZDUSD (from 2015-10), EURJPY (to 2022-12), AUDJPY (18 months), EURAUD (from 2018-01), LIGHTCMDUSD (1 month), BRENTCMDUSD (2), USA500IDXUSD (39), USSC2000IDXUSD (30, bid only) |
| near complete | EURUSD (14 months missing on one side), GBPUSD (16), GBPCHF (11), CADJPY (15), XAUUSD (6), XAGUSD (12) |

**0 of 29 instruments are complete. The download is still running**: the newest file was written
2026-09-22 11:39 UTC (USSC2000IDXUSD). The near-complete ones still miss months **on one side**, and
the adapter refuses a series with more than `max_one_sided_share` (0.1 %) of its bars on one side
only. So **today no instrument can be ingested**. The downloader is resumable (stored months are
skipped), so a re-run fills the holes.

## D-010 and D-032 — how they are applied and tested

Both already exist in the T05 resampler (`data/resample.py`) and are applied, not rebuilt:

- **D-010:** research mode, day boundary 00:00 UTC; the Saturday and Sunday bars of the 24x5 markets
  (`fx`, `metal`, `energy_cfd`, `index_cfd`) belong to **Monday**; no daily bar is ever stamped on a
  weekend. Tests: `test_F_0_1_7_sunday_merged_into_monday` (Sunday 22:00 and 23:00 open Monday; OHLC
  first/max/min/last, volume summed), `…_saturday_bars_also_go_to_monday`.
- **D-032:** the 1D series is **built from the ingested 1H snapshot**, never downloaded:
  `sfac data resample` writes a derived snapshot (`derived_from` the 1H key) with `spread` = the last
  hour's, drops the partial edge periods, and flags a day built from fewer than `min_source_fraction`
  of its expected bars (`_resample/<hash>.flags.csv`).
- **Measured on the six near-complete instruments, in memory:** FX has ≈ 2,150 Sunday bars (metals
  ≈ 1,360) and **0 Saturday bars**; after the merge **0 daily bars fall on a weekend**, and 17–23 thin
  days are flagged per instrument (holidays and the raw holes).
- **New in T04j, tested:** an end-to-end test that ingests fixture months of both sides, resamples to 1D
  and asserts `derived_from` the 1H reference, the Sunday bars inside Monday, no weekend stamp, and
  `spread` = the last hour's; and a test that the 1D reference moves only when the 1H one does.

## Do the T04k / T04l defect families apply? — `scripts/analysis/T04j_defects.py` → `docs/reviews/T04j_defects.csv`

Measured on the same six instruments (EURUSD, GBPUSD, GBPCHF, CADJPY, XAUUSD, XAGUSD; the months
present on both sides; ≈ 96,000 1H bars each), the way T04h/D-707 measured the Alpaca hourly set:

| family (the Alpaca arm) | Dukascopy h1 |
|---|---|
| frozen stretches (`frozen_cut`, D-398 (1)) | **0** on all six |
| re-use boundaries (`boundary_trim`, D-708: a gap ≥ 200 days) | **0**. The longest gap is 28–122 days, and each is a raw month still missing. An FX pair or a metal has no ticker to re-use |
| bad prints (`wick_clip`, the D-703/D-706 rule on the hourly mid) | **0** |
| extremes outside a session (`extreme_cap`) | not applicable: the feed is the market itself, 24x5 |
| spread | **spikes**: hours with a spread above 10× its 500-bar rolling median: EURUSD 1,145, GBPUSD 830, CADJPY 679, GBPCHF 590, XAUUSD 67, XAGUSD 32 (rollover and the Sunday open). Zero spread on 1 bar each of EURUSD and XAGUSD. **Negative: 0** (the adapter refuses them) |
| missing weekday hours | FX 70–97 per instrument; metals ≈ 1,800 — the metals' **daily 1-hour break**, a session feature the quality check learns (`learn_break`), not a defect |

**Decided (D-717):** no cleaning pass for Dukascopy, on the same grounds as D-707 — **on condition**
that `T04j_defects.py` is re-run on the **complete** set of 29 before the ingest, and **T04j stops and
raises** if any family appears there; nothing is absorbed. The spread spikes get **one line in the
review**: they matter only through D-523's hourly shape, which is a **median** per UTC hour
(`broker_scaled_table`), so they barely move it — the evidence is the per-hour median table
(`docs/reviews/T04j_spread_by_hour.csv`), which stays within 0.75–1.0× the overall median from 07 to
19 UTC although those hours hold spikes too.

## The broker universe (T06b, D-323)

- `configs/costs/moneta/dukascopy_map.csv` maps **all 29** research symbols to a Moneta CFD (e.g.
  EURUSD → `EURUSD+`, LIGHTCMDUSD → `USOUSD`, USA500IDXUSD → `SP500.r`, JPNIDXJPY → `Nikkei225`).
- `configs/costs/moneta/assignments.yaml` assigns each its own profile; all 29 are **`verified`,
  spread `broker_scaled`**.
- A profile resolves only against the 1H reference's `spread` column (top of this file). Stream A's
  `configs/costs/` is not touched.

## Costs of a daily run — the week open (D-716; T12 in stream A reads it)

**A median hides a rare extreme completely.** Before D-716 the 4–5× week-open spread appeared
nowhere in the cost table: the hour bucket's median dropped it rather than averaging it in. An
extreme that recurs at a known moment needs its own key.

**Every daily FX entry on a Monday lands on the widest spread of the week.** The bar that opens the
trading week (the Sunday open) is **4.0–5.4×** the median spread for FX and **1.3×** for metals, and
under D-010 it is the open of Monday's daily bar, the fill of every daily next-open entry signalled on
a Friday.

**Built in T04j** (`costs/arrays.py`, `costs/profile.py`; tests
`tests/unit/test_F_0_2_2_week_open_spread.py`):
- `week_open_mask(ts, timeframe)`: the first bar of each trading week (keyed from Saturday 00:00 UTC)
  that starts on a **Sunday**; at `1D`, the **Monday** bar.
- The spread table (`hourly_spread_table`, `broker_scaled_table`) takes those bars **out of their UTC
  hour** and keeps them as a separate key, `week_open` (median; scaled with the rest under D-523 and
  weighted by its bars, so the bar-weighted mean is still the broker spread).
- `SpreadHourly.week_open` carries it into the resolved profile; `build_cost_arrays` charges it to the
  week-open bar at 1H and to Monday's bar at 1D.
- A market without Sunday hours (US equities) gets no key and nothing changes. A profile without the
  key serialises exactly as before, so its content hash is unchanged (tested).
- The mandatory leakage gate `tests/leakage/test_F_0_2_2_broker_scaling_dev_only.py` still proves
  that the holdout never reaches the table. Its closing check (the bar-weighted mean of what each
  development bar is charged equals the broker spread, D-523) now charges the week-open bars their own
  key instead of their UTC hour. It also asserts that the week-open value is unchanged by the
  poisoned holdout. The invariant is the same, and it is checked on more. **Approved by the supervisor
  on 2026-09-22, no ADR (recorded in D-716).**

**Measured with the table itself** (`scripts/analysis/T04j_spread_hours.py` →
`docs/reviews/T04j_spread_by_hour.csv`: each key ÷ the instrument's median spread; six instruments,
≈ 800 week opens each):

| key | FX (EURUSD, GBPUSD, GBPCHF, CADJPY) | metals (XAUUSD, XAGUSD) |
|---|---|---|
| 00–06 | 1.0–1.1× | 0.98–1.03× |
| 07–19 | 0.75–1.0× | 0.93–1.0× |
| 20 | 2.3–2.5× | 1.5–1.7× |
| 21 | 3.0–3.44× | 1.7–1.9× |
| 22 | 1.5–1.85× | 1.3–1.4× |
| 23 (the 1D snapshot's `spread`) | 1.0–1.22× | 1.0–1.06× |
| **week_open** (the Sunday open = Monday's daily open) | **4.0–5.39×** | **1.27–1.31×** |

Taking the week opens out barely moves hour 21 (it was 3.0–3.7× with them). That bucket is a median,
and weekday 21:00, the rollover, is itself about 3×. The Sunday open never showed in it: before this
key, the 4–5× value existed nowhere in the table.

**What a daily cost consumer does (T12, stream A):**
1. Resolve the table from the symbol's **1H development segment** (as `sfac costs show` does,
   `SPREAD_TIMEFRAME = "1H"`), never from 1D bars. The 1D snapshot's `spread` is the 23:00 hour's,
   and the last hour is **not** the widest: the week open and 20–22 UTC are.
2. **Fill at a daily bar's open:** `build_cost_arrays(..., timeframe="1D")` already charges hour 0
   Tuesday to Friday and `week_open` on Monday.
3. **Fill inside a daily bar** (SL / TP / disaster stop; the hour is unknown): the profile's **broker
   spread**, which equals the table's bar-weighted mean by construction (D-523,
   `HourlySpread.bar_weighted_mean`). It is not the plain mean of the 24 hours.

## D-008 — how many would enter the candidate universe

- **Measured:** all six near-complete instruments split in **1H and 1D** (≈ 96,000 hourly, ≈ 4,000–4,200
  daily bars from 2010).
- **Projected for a complete download:** every one of the 29. The shortest history is USSC2000IDXUSD's
  (from 2018-08, ≈ 8 years ≈ 2,000 daily bars), well above the 18-month holdout plus embargo.
- **Today: 0**, because no instrument passes the coverage gate.
- The count is re-measured after the ingest, per timeframe, and reported like `B_data_state.md`.

## Scope

0. **The user completes the download** (D-031) with
   `powershell -ExecutionPolicy Bypass -File scripts\pilots\T04j_dukascopy_download.ps1`: step 1 is the
   resumable `sfac data download dukascopy --series h1` (stored months are skipped, so it is safe to
   re-run after a drop; a TLS error stops it and is reported as-is; failed months still go on to
   step 2); step 2 is the coverage gate, which prints the remaining gaps. Re-run until it prints
   `coverage gate: passed`.
1. **Coverage gate (D-386 copied):** *(built)*
   - `sfac data coverage dukascopy` writes `SFAC_RAW_ROOT/_reports/dukascopy_coverage_h1.csv` (per
     instrument and month: bid, ask, rows, required, missing) and exits 1 on a gap. A gap is a
     required month without a file on **either** side (the latest version of the month counts).
   - Required: from `h1_start` or the instrument's own start (`instrument_start`, parsed from the
     `h1 from` date already in `configs/universe/dukascopy.csv`'s notes), whichever is later, to the
     last complete month. The current month is never required.
   - `sfac data ingest dukascopy` refuses to run on a gap, before anything is written; there is no
     `--allow-gaps`.
   - The verdict rests on the files present, never on a manifest field (D-711); manifest rows are
     reported only. Tests: `tests/unit/test_F_0_1_3_dukascopy_coverage.py`.
2. **Re-measure the defect families** on the complete set (`T04j_defects.py`, all 29). **Stop and raise if a
   family appears** (D-717).
3. **Ingest 1H** for all 29 with `--set-reference`; the three pilots with `--rehash` (hash version
   1 → 2, reference moved, event note `rehash v1→v2`; T04e §1). Chunked and idempotent (D-385); a re-run
   writes nothing (test + store evidence, as T04h).
4. **Build 1D** (D-032) from each 1H reference with `sfac data resample --target 1D --mode research`,
   `--set-reference`. Per D-714, the derived layer is retired and re-derived once before the first
   reference moves, if it was written more than once.
5. **Quality reports** for all 58 snapshots (`missing_bars` and `session_violations` executed, not
   skipped; the daily-only checks skip on 1H, as for Alpaca).
6. **Costs:** `sfac costs show <symbol>` resolves for all 29 against the 1H development segment; the
   review lists each profile's scale factor and filled hours (D-350).
7. **Report:** references per timeframe, quality, D-008 splittable per timeframe, and the update of
   `docs/streams/B_data_state.md`.

## Out of scope

- m1 data (D-026: spread detail and intrabar resolution later, F-0.3.5).
- Yahoo auxiliary series (next task).
- Stage-1 inclusion of these symbols: stream A's T12; they join when T04j completes (D-715).
- Wiring the daily cost read into stage 1: stream A's T12 (D-716); the table and the per-bar
  charge are built here.
- Any change to `configs/costs/` (stream A).

## Acceptance

- The coverage report (§1) is in the review, and the gate passed on the complete set; otherwise the task
  stopped with nothing written.
- All 29 have a 1H reference (hash version 2) and a 1D reference `derived_from` it; the pilots are
  re-hashed and their old snapshots stay in the store.
- D-010 / D-032 tests as above; no daily bar on a weekend in the store (store evidence).
- The defect-family table re-measured on all 29 is in the review, with no family present (D-717);
  one line on the spread spikes and the per-hour median's insensitivity to them.
- Every snapshot has a quality report; no schedule check is `skipped`.
- `sfac costs show` resolves for all 29.
- A re-run of a chunk writes nothing.
- Gates green; `sfac streams check` clean.

## Open questions

None open. P-87 → D-716 (the daily cost read, T12's), P-88 → D-715 (no amendment of D-020).
