# T04k — Unsupported daily extremes: quality checks and the derived clean daily snapshot

**Features:** F-0.1.6 (data-quality checks and report), F-0.1.8 (immutable snapshots, derived snapshots), F-0.1.9 groundwork · **Priority:** MVP · **Depends on:** **T04g** (the raw 1D snapshots) and ideally **T04h** (hourly coverage) · **Must be done before:** the first real stage-1 run (**T12**)
**Branch:** `b/T04k-clean-daily` from `b/T04g-alpaca-daily-ingest` (or from `main` once T04g is merged).

Read first: `CLAUDE.md` (rules 1, 10, 11), **D-395**, **D-396** (the decision this task implements),
D-033, D-023, D-522, and `docs/reviews/T04i_review.md` — T04i measured the problem, this task fixes it.

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

## Scope

### 1. Two quality checks (F-0.1.6, D-396 part 1)

**`daily_extreme_unsupported`** — where hourly data exists. A day is flagged when the daily high or
low lies outside the **full raw hourly range** (extended hours included) of that session date by
more than a configured epsilon. Reuse `strategy_factory.data.daily_session` from T04i, which
already computes this and distinguishes `extended_hours`, `unexplained`, `incomplete_hourly_day`
and `no_raw_hours`. A day whose hourly side is incomplete is **never** flagged as a defect.

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

### 2. The derived clean daily snapshot (D-396 part 2)

A **new** snapshot per symbol, never an overwrite (rule 10):

- `derived_from` = the raw 1D snapshot key, so the lineage is in the catalog and reproducible;
- on a flagged day, **cap** the high and low to the RTH hourly range where hourly data exists;
- otherwise **clip** a flagged wick to the body extreme (max/min of open and close);
- `open` and `close` are **never** changed — only the extremes;
- a **changed-bar log** beside the snapshot lists every touched bar with the old and the new value
  and which rule applied. Without it the transformation is not auditable and must not ship;
- the metadata says what was applied: the rule, the config hash of the thresholds, and the counts.
  The material-metadata guard (D-384/D-392) means this must be right at the first write.
- **The clean snapshot becomes the research reference** for `(symbol, 1D)`; the raw snapshot stays
  in the store and in the catalog, and a run can still name it explicitly.

CLI: `sfac data clean daily [--symbols ...] [--set-reference]`, chunked and idempotent like the
ingests (D-385).

### 3. Report

`docs/reviews/T04k_review.md` plus a committed CSV of every changed bar, aggregated per symbol and
per date. Compare the before/after distribution of the daily range, and state how many symbols were
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
were capped versus clipped; the before/after range distribution; the changed-bar log's location and
its replay test; deviations and open questions.
