# T04k — Unsupported daily extremes: quality checks and the derived clean daily snapshot

**Features:** F-0.1.6 (data-quality checks and report), F-0.1.8 (immutable snapshots, derived snapshots), F-0.1.2 (frozen stretches and the re-use boundary, D-398), F-0.1.9 groundwork · **Priority:** MVP · **Depends on:** **T04g** (the raw 1D snapshots) and ideally **T04h** (hourly coverage) · **Must be done before:** the first real stage-1 run (**T12**)
**Branch:** `b/T04k-clean-daily` from `b/T04g-alpaca-daily-ingest` (or from `main` once T04g is merged).

Read first: `CLAUDE.md` (rules 1, 10, 11), **D-395**, **D-396**, **D-398**, **D-399** and **D-700** (the
decisions this task implements), D-033, D-023, D-008, D-383, D-397, D-522, and
`docs/reviews/T04i_review.md` — T04i measured both problems, this task fixes them.

## Why

The engine checks stops against the **daily high and low**. T04i showed that on **15,559 of
1,617,247** session days (0.96 %) the daily extreme is a price the hourly feed does not support:

- 10,521 `extended_hours` — a real trade outside 09:30–16:00, which the broker cannot reach either
  (**528 of 548** Moneta US shares and ETFs trade RTH only, 20 mega-caps from 07:05, none after the
  close);
- 2,860 `unexplained` — no hourly bar at any hour reaches it. `SPY` 2026-02-02 has a daily low of
  **69.005** against a 695.41 close; `MRK` 15.32 against 76.27; `VZ` 10.60 against 40.57; `NVDA`
  2024-06-10 a high of 195.95 in a week trading 117–132.

Either way a stop placed there fires on a price the strategy could never have traded. **D-396**
says a warning alone is not enough: the data the pipeline reads must be corrected, through a
**derived, versioned** snapshot — never by editing raw and never by overwriting a snapshot.

Only **826 of 6,711** daily symbols have hourly data, so the correction has two arms and the
cheaper one must work for every symbol.

## How much of the universe this is — measured, not assumed

T04g ingested 6,707 daily snapshots and ran the quality checks over all of them: **4,002 `ok`,
2,705 `warning`, 0 `critical`**. The 2,705 warnings partition as follows (each snapshot counted
once, in the first bucket it falls into; source `docs/reviews/T04g_quality_1D.csv` joined to
`docs/reviews/T04i_relisting_verdicts.csv`):

| bucket | snapshots | share of the warnings | what T04k does with it |
|---|---|---|---|
| **A1.** a D-398 finding, verdict `frozen_removed` | **517** | 19.1 % | cut the frozen stretch (§1b (1)) |
| **A2.** a D-398 finding, verdict `trim_to_boundary` | **280** | 10.4 % | settle it under **D-399** (§1c), then trim, refresh or keep |
| **B.** `stale_prices` or `zero_volume`, **no** D-398 finding | **954** | 35.3 % | the padding signature **below** the 10-session threshold, or zero volume without a frozen price — §1b cuts nothing here; the checks keep reporting it |
| **C.** `missing_bars` without a padding signature | **23** | 0.9 % | nothing; a genuinely sparse series |
| **D.** `price_spikes` only | **931** | 34.4 % | the **`daily_wick_outlier`** arm (§1, D-396): this is the bucket the wick clip is for |

So the two arms are about the same size and they barely overlap: **797 snapshots (29.5 %)** are the
D-398 padding/re-use family and **931 (34.4 %)** are spike-only. Bucket **B** is the one to watch —
it is the largest single bucket and **T04k changes none of it**, because the frozen runs there are
shorter than `relisting.frozen_min_sessions`. If the review finds bucket B is dominated by runs of
5–9 sessions, that is an argument for lowering the threshold, and it is a **supervisor decision**,
not a task-level one.

### The delisted tail, measured separately

The supervisor asked how many of the 2,705 warnings are the **delisted-tail family** — a company
that stopped trading years ago while the feed still returns a bar near the end of the window, so the
snapshot spans eleven years and holds a few hundred real bars. Defined as **span > 3 years and
fewer than 75 % of that span's sessions traded** (`row_count / (span_years × 252)`), measured
against the catalog's own `first_ts` / `last_ts` / `row_count`:

| | snapshots | share of the 2,705 | `missing_pct` median | p90 | max |
|---|---|---|---|---|---|
| **delisted tail** | **76** | **2.8 %** | **60.7 %** | 84.3 % | 94.0 % |
| **everything else** | **2,629** | 97.2 % | 0.0 % | 0.0 % | 39.3 % |

It is a **small, sharply separated** family, not the bulk of the warnings — worth saying plainly,
because the T04g review's "twenty worst `missing_pct`" table makes it look larger than it is. The
two groups do not overlap at all on the metric that matters: the tail's median is 60.7 % missing,
the rest's p90 is 0 %.

- **55 of the 76** also carry a D-398 finding, so §1b/§1c already reach them; the other 21 are
  sparse without a padding signature and **T04k changes nothing about them**.
- The tail's density runs p10 **0.16** to p90 **0.67**, median **714** real bars over a median span
  of **10.7 years**. The worst: `MDA` 135 bars over 2017-10-05 … 2026-09-18 (94.0 % missing), `POM`
  294 (89.1 %), `NPT` 295, `XE` 273, `CAM` 302, `MOBI` 314.
- **All 76 are `warning`; none is `ok`** — no `ok` snapshot in the whole store is tail-shaped, so
  the quality status already separates them cleanly.
- Of the **187** warning snapshots failing `missing_bars`, **76 are the tail** and **111 are
  ordinary gappy series** (density 0.83–0.97, a few per cent missing) that need nothing.

**What this means for T04k's scope.** The wick-outlier arm (931 spike-only snapshots) and the
D-398 padding/re-use arm (797) are each **an order of magnitude larger** than the delisted tail.
T04k should not be designed around the tail; it is a by-product that §1b's padding removal and
§1c's boundary rule already cover for 55 of its 76 members.

## Scope

### 1. Two quality checks (F-0.1.6, D-396 part 1)

**`daily_extreme_unsupported`** — where hourly data exists. A day is flagged when the daily high or
low lies outside the **full raw hourly range** (extended hours included) of that session date by
more than a configured epsilon. Reuse `strategy_factory.data.daily_session` from T04i, which
already computes this and distinguishes `extended_hours`, `unexplained`, `incomplete_hourly_day`
and `no_raw_hours`.

### A short hourly day is not evidence, in either direction (supervisor, 2026-09-21)

T04i predicted that completing the hourly download would empty the `incomplete_hourly_day` class.
**It did not**: with every symbol-year present the class grew, 2,896 → **3,017**, median still
**1 hourly bar against 7 expected**, over **665 symbols and 784 dates**. So these are **gaps in
Alpaca's SIP hourly feed**, not an artefact of an unfinished download, and they are permanent. Two
rules follow and both are acceptance criteria:

1. **Never cap a daily high or low from a short hourly day**, and **never mark the day clean
   because the hourly range "agrees"** — agreement with one surviving bar is not agreement. On a
   day classified `incomplete_hourly_day` (or `no_raw_hours`) the daily bar is **left untouched**
   and the quality report **states it**, with the bar count it saw against the calendar's
   expectation. A silent pass is the failure mode to avoid: it would read as "checked and clean"
   when nothing was checked.
2. **The clustering is the signal.** `incomplete_hourly_day` clusters by **date**, not by symbol —
   2021-04-19 (438 symbols), 2021-10-25 (401), 2022-03-08 (347), 2022-01-24 (279), 2018-05-02
   (194) — which points at feed-wide events rather than at any instrument. The **T04k review lists
   the worst such dates** with their symbol counts, so a later reader can recognise the shape.

**`daily_wick_outlier`** — for **every** symbol, hourly data or not. A day is flagged when a high or
low lies beyond the bar's **body** (max/min of open and close) by more than **both**

- `k1 × ATR(14)` of that bar, and
- `k2` % of the close.

Both thresholds live in `configs/data/quality.yaml` with documented defaults, never in code
(non-negotiable rule 1). Requiring **both** keeps a genuinely volatile day from being flagged: a
wide-but-real bar exceeds the percentage and not the ATR multiple, a bad print exceeds both.

Both checks report **counts per symbol and per date** — T04i showed the date-wide clusters
(2019-10-31: 75 symbols; 2019-08-12: 64; 2025-03-06: 55, all one-sided) that point at the feed
rather than at a symbol. Severity is a config value; neither check is `critical` by default,
because the clean snapshot (§2) is the remedy, not refusing the data.

### 1b. Frozen stretches and the re-use boundary (D-398)

**D-398** (the P-73 answer, which amends D-383) is applied here too, on the same derived snapshot,
because it is the same kind of correction — the raw bars stay, the research series is honest:

- **every frozen stretch is cut** — consecutive bars with an identical close and **zero true range**
  (`high == low == close`), at least `relisting.frozen_min_sessions` (config, 10) long — whatever
  caused it. It is feed padding, not data;
- where a ticker was re-used and **the boundary is identifiable**, the series **starts at that
  boundary**; the boundary and the dropped span go into the changed-bar log and the metadata. The
  symbol is **not** excluded;
- **leading** pre-listing padding is trimmed and the symbol stays;
- only an **unidentifiable** boundary excludes a symbol, through
  `configs/universe/us_equity_daily_excluded.csv` (T04i wrote it **empty**: no symbol in the 6,711
  falls into that case).

The detector is `strategy_factory.data.relisting.analyse_series`, already committed and tested in
T04i; the per-symbol verdicts are `docs/reviews/T04i_relisting_verdicts.csv` (797 symbols: 280
`trim_to_boundary`, 517 `frozen_removed`). **Re-run the sweep here** rather than reading that CSV as
input — it is evidence, not a config.

**A symbol whose remaining history is then too short is not touched further** (D-008, D-398):
145 of the 280 trims keep fewer than 650 bars and 61 fewer than 250, and they simply fail
`SplitManager` with `HistoryTooShortError` when a stage tries to split them. Do **not** add them to
the exclusion file and do not shorten the split rules for them.

### 1c. No trim on an ambiguous signature — D-399, amended by D-700

**A trim is never applied on an ambiguous signature** (D-399 (4), which stands). A frozen stretch
or a gap with a level break is equally what an **unadjusted (reverse) split**, a **long trading
halt** and a **re-used ticker** look like.

**D-399 asked the MS-US-1D cross-check to separate all three. T04k measured that it can separate
only the first.** MS-US-1D is keyed by **ticker**, exactly like the Alpaca feed, so a re-used
ticker splices identically in both (`PX`: 156.80 → 11.51 on 2021-10-21 in both, with the same
frozen padding before it). The supervisor therefore withdrew D-399's cross-check half for the
re-use case and moved the discriminator to the **company name** — **D-700**. A boundary is now
decided in this order; the first rule that decides wins:

| step | evidence | outcome |
|---|---|---|
| 1 | the boundary ends a **leading** pad | padding before a listing, not a re-use signature: **trim** (D-398 (3)) |
| 2 | MS-US-1D is **continuous** between two **real** bars where the ingested series jumps | **unadjusted split** → the **D-397** path: no clean snapshot, history untouched, listed with its `--refresh` command |
| 3 | a `NAME_CHANGE` rename **away** from the ticker inside `[break start − 7 d, boundary]`, and the assets file's name for the destination is a **different string** from the ticker's current name | **re-use** → **trim** at the boundary (D-398 (2)) |
| — | anything else: one name only, the rename disagrees with the boundary, two renames, or the destination changed hands again | **keep the full history** and list the symbol for the supervisor |

Name matching is **exact identity** (D-700 (4)). Two conditions were added because the data
refuted a simpler version, both in the conservative direction:

- **The cross-check compares real bars, never a pad.** A first version called `AMLX`, `ATAI`,
  `NRGZ` and `TBRG` unadjusted splits; all four were wrong (the cross-check had no pre-IPO bar and
  the fallback compared the IPO bar with itself; the ingested "jump" measured a stale pad; neither
  feed broke the threshold).
- **A destination that changed hands again is not evidence.** `PTN`: Palatin went `PTN → PTNT` and
  came **back**; an ETF then took `PTNT`, so `PTNT`'s current name called Palatin a re-use of
  itself — 2,264 real bars would have gone.

The frozen-stretch cut (D-398 (1)) is unaffected by all of this and needs no evidence: padding is
removed wherever it is.

### 2. The derived clean daily snapshot (D-396 part 2)

A **new** snapshot per symbol, never an overwrite (rule 10):

- `derived_from` = the raw 1D snapshot key, so the lineage is in the catalog and reproducible;
- on a flagged day, **cap** the high and low to the RTH hourly range where hourly data exists;
- otherwise **clip** a flagged wick to the body extreme (max/min of open and close);
- `open` and `close` are **never** changed — only the extremes;
- **D-398** additionally **removes bars**: the frozen stretches and everything before the
  boundary. Removal is logged bar for bar like a cap, and the metadata carries `boundary_date`,
  `dropped_bars` and `frozen_bars_cut` so the shorter series is self-explaining;
- a **changed-bar log** beside the snapshot lists every touched bar with the old and the new
  value, **which arm changed it** (`extreme_cap`, `wick_clip`, `frozen_cut`, `boundary_trim`)
  **and the evidence that arm acted on** — for `extreme_cap` the hourly range and its bar count
  against the calendar; for `wick_clip` the ATR(14) multiple and the percentage; for
  `frozen_cut`/`boundary_trim` the stretch or gap and the D-398/D-399 verdict. Without it the
  transformation is not auditable and must not ship;
- the metadata says what was applied: the rule, the config hash of the thresholds, and the counts.
  The material-metadata guard (D-384/D-392) means this must be right at the first write.
- **The clean snapshot becomes the research reference** for `(symbol, 1D)`; the raw snapshot stays
  in the store and in the catalog, and a run can still name it explicitly.

CLI: `sfac data clean daily [--symbols ...] [--set-reference]`, chunked and idempotent like the
ingests (D-385). The extreme correction (D-396) and the frozen/boundary correction (D-398) are
one pass over the symbol and one derived snapshot, not two.

### 3. Report

`docs/reviews/T04k_review.md` plus a committed CSV of every changed bar, aggregated per symbol and
per date, **and the worst `incomplete_hourly_day` dates with their symbol counts** (§1) so the
feed-wide events are on the record. **Re-measure the five buckets above after the clean snapshots exist** and say which ones
moved: A1 and A2 should empty, D should shrink to the wicks the clip did not touch, and B should be
unchanged — if B moved, something cut more than D-398 allows. Compare the before/after distribution of the daily range, and state how many symbols were
touched at all — if the clean snapshot differs from the raw one for only a small minority, say so
plainly, because that is the argument for making it the default reference.

## Out of scope
- Whether a stop may trigger on an `extended_hours` extreme at all: that is an engine and cost
  decision (**T08 / stream A**), and this task only makes the data say which days those are.
- Editing raw (rule 11) or any 1H snapshot.
- `configs/universe.yaml` and anything under `configs/costs/` (D-394, D-388).

## Acceptance
- Both checks are implemented, configured from YAML, and each has tests on a fixture with a planted
  bad print, a planted extended-hours extreme and a genuinely volatile bar that must **not** flag.
- **A short hourly day changes nothing** (§1): a fixture whose hourly side holds 1 bar of 7 and
  whose daily high lies outside it leaves the bar **untouched**, is **not** reported clean, and
  appears in the quality report with its bar count. A second fixture where the short day's hourly
  range happens to *contain* the daily range is also left untouched and is **not** marked clean.
- Every row of the changed-bar log carries its arm and that arm's evidence; a test asserts no row
  has an empty arm or empty evidence.
- **D-398:** a fixture symbol with a padded stretch, one with a leading pad and one with a re-use
  boundary each produce the right clean series; the frozen bars are gone, the boundary is in the
  metadata, and a symbol whose trimmed history is too short **fails the split** rather than being
  excluded (test against `SplitManager`).
- **D-399:** four fixtures — a continuous cross-check (unadjusted split), a halt, a genuine
  re-use and an unsettleable case — give the four verdicts of §1c. A test asserts that a symbol
  whose cross-check is continuous or missing keeps **every** bar of its history, so an ambiguous
  signature can never trim.
- `daily_wick_outlier` runs for a symbol with **no** hourly data.
- The clean snapshot exists for every raw 1D snapshot, has `derived_from` set, is the reference, and
  the raw snapshot is untouched and still in the catalog (test: the raw parquet's hash and mtime are
  unchanged).
- The changed-bar log accounts for **every** difference between raw and clean; a test asserts that
  replaying the log on the raw bars reproduces the clean bars exactly.
- `open`/`close`/`volume` are identical between raw and clean (test).
- Re-running the command writes nothing new (idempotence).
- Acceptance commands green; `sfac streams check` clean.

## Review summary
`docs/reviews/T04k_review.md`: the flagged counts per check, per symbol and per date; how many bars
were capped versus clipped; **how many were removed as padding and how many symbols were trimmed to
a boundary (D-398), the MS-US-1D verdict for each of the 29 suspects (D-399) with the resulting
`--refresh` list and the symbols kept untrimmed for the supervisor**; how many trimmed symbols now fail the split (D-008); the before/after range
distribution; the changed-bar log's location and its replay test; deviations and open questions.
