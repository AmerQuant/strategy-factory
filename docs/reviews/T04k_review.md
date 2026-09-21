# T04k review — the derived clean daily snapshot

**Task:** `docs/tasks/T04k_clean_daily_snapshot.md` · **Branch:** `b/T04k-clean-daily` from `main` (T04g merged, PR #24; rebased onto `b5a0bb4`, PR #25)
**Features:** F-0.1.6 (quality checks and report), F-0.1.8 (immutable and derived snapshots), F-0.1.2 (frozen stretches, re-use boundary), F-0.1.9 groundwork
**Decisions used:** D-008, D-023, D-033, D-383, D-384, D-392, D-395, D-396, D-397, D-398, D-399, **D-700** (new, supervisor — amends D-399)
**Open for the supervisor:** **P-75** (six implementation rules, all conservative), **P-76** (the official close counted as unsupported)
**Status:** complete and **waiting for "Approved"**. As instructed, every pass ran **without `--set-reference`**: all 6,707 references are still the raw snapshots.

The acceptance reviewer ran twice. The first round found three real defects (§7) and the fixes
exposed a fourth, which I found on the full pass (§7.4). Every number below is from the final pass.

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/clean_daily.py` | the four arms — `boundary_trim`, `frozen_cut`, `extreme_cap`, `wick_clip` — and `wick_outliers()`; pure |
| `src/strategy_factory/data/crosscheck.py` | the D-399 price test against MS-US-1D, reduced to what it can decide (§4) |
| `src/strategy_factory/data/name_evidence.py` | **D-700**: the company-name discriminator and its loaders |
| `src/strategy_factory/data/quality.py` | `daily_wick_outlier` and `daily_extreme_unsupported` (F-0.1.6, D-396) |
| `src/strategy_factory/data/cli_clean.py` | `sfac data clean`: raw snapshot in; clean snapshot, per-hash log and provenance, and the quality report out |
| `configs/data/quality.yaml`, `configs/data/alpaca.yaml` | every threshold (rule 1): `k1_atr`, `k2_pct`, `eps_bps`, `rename_window_days`, `crosscheck_window_days`, the two evidence paths |
| `scripts/analysis/T04k_report.py` | every aggregate below, reproducible |
| `docs/reviews/T04k_boundaries.csv` | the 280 re-use candidates, each with both verdicts and its outcome |
| `docs/reviews/T04k_changes_per_symbol.csv`, `…_per_date.csv` | changed bars by arm |
| `docs/reviews/T04k_short_hourly_dates.csv` | every short or missing hourly day, per date |
| `docs/reviews/T04k_split_after_trim.csv`, `T04k_suspects.csv` | D-008 after trimming; T04i's 29 suspects |
| tests | **69 new** across `test_F_0_1_6_clean_daily.py`, `test_F_0_1_8_clean_pass.py`, `test_F_0_1_9_crosscheck.py`, `test_F_0_1_2_name_evidence.py`; plus the check-set update in `test_F_0_1_6_quality.py` |

In the store: `<SFAC_DATA_ROOT>/_clean/<symbol>/<clean hash>.csv` (every changed bar: old, new,
arm, evidence) and `.json` (provenance: config hash, arms, boundary, verdicts), one pair per clean
snapshot; `_clean/clean_daily_summary.csv`; `_clean/short_hourly_days.csv`.

## 2. The run

```
uv run sfac data clean            # no --set-reference, as instructed
```

| | symbols |
|---|---|
| raw daily snapshots processed | 6,707 |
| **cleaned** (a new derived snapshot) | **3,250** |
| **unchanged** (the raw snapshot already is the clean series) | 3,457 |
| `unadjusted_split` (D-397 path) | 0 |
| `exclude_boundary_unidentifiable` (D-398 (4)) | 0 |
| failed | **0** |

**11,947,857 raw bars → 11,733,903 clean: 213,954 removed (1.79 %), almost all padding.**

| arm | changed bars | symbols |
|---|---|---|
| `frozen_cut` (D-398 (1)) | **181,503** | 709 |
| `boundary_trim` (D-398 (2)/(3)) | 32,451 | 59 |
| `extreme_cap` (D-396, where hourly data exists) | 6,925 | 795 |
| `wick_clip` (D-396, only where it does not) | 5,336 | 2,059 |

"Cleaned" is 48 % of the universe but it is three populations: **2,854** symbols with at least one
extreme corrected (a handful of bars each), **365** touched only by padding removal and **31** only
by a boundary trim.

**The daily range on the 12,239 bars an extreme arm changed** (bps of the close):

| | median | p90 | p99 | max |
|---|---|---|---|---|
| before | 484.3 | 8,513.6 | 18,829.3 | 252,352.9 |
| after | 305.9 | 2,523.4 | 6,560.0 | 32,771.4 |

The median barely moves; the tail collapses.

## 3. The 280 re-use candidates — per arm, measured

| boundary reason | candidates | trimmed | **kept** (full history, listed) | how |
|---|---|---|---|---|
| `leading_padding` | 49 | **49** | 0 | D-398 (3): padding before a listing, not a re-use signature |
| `stale_run` | 162 | **5** | **157** | D-700: 141 `one_name`, 13 `disagrees`, 3 `ambiguous` |
| `trading_gap` | 69 | **5** | **64** | D-700: 53 `one_name`, 3 `disagrees`, 8 `ambiguous` |
| **total** | **280** | **59** | **221** | |

**The name evidence settles 10 of the 231 re-use candidates (4.3 %).** The 221 kept lose their frozen
padding (D-398 (1)) and nothing else; every one is listed in `T04k_boundaries.csv`.

| symbol | reason | bars dropped | before the break | after the break |
|---|---|---|---|---|
| `BIOS` | stale_run | 1,529 | Option Care Health (`BIOS→OPCH` 2020-02-03) | BioPlus Acquisition Corp. |
| `CLBR` | stale_run | 1,186 | GrabAGun Digital Holdings (`CLBR→PEW` 2025-07-16) | Colombier Acquisition Corp. III |
| `FB` | trading_gap | 1,620 | Meta Platforms (`FB→META` 2022-06-09) | ProShares S&P 500 Dynamic Buffer ETF |
| `GRI` | stale_run | 1,259 | ALPS REIT Dividend Dogs ETF (`GRI→RDOG` 2020-01-02) | GRI Bio (arrived from `VLON` 2023-04-24) |
| `ISRL` | stale_run | 2,680 | Israel Acquisitions Corp (`ISRL→ISRLF` 2025-12-04) | Tidal Trust Defiance KSM Israel ETF |
| `LIFE` | trading_gap | 2,119 | aTyr Pharma (`LIFE→ATYR` 2024-06-05) | Ethos Technologies |
| `LION` | stale_run | 2,104 | SMX (Security Matters) (`LION→SMX` 2023-03-21) | Lionsgate Studios |
| `LWAC` | trading_gap | 125 | eFFECTOR Therapeutics (`LWAC→EFTR` 2021-09-01) | LightWave Acquisition Corp. (a new SPAC) |
| `RUBI` | trading_gap | 1,131 | Magnite (`RUBI→MGNI` 2020-07-01) | Rubico Inc. |
| `SZZL` | trading_gap | 516 | Critical Metals (`SZZL→CRML` 2024-02-28) | Sizzle Acquisition Corp. II |

All ten were checked against their full `NAME_CHANGE` history (six of them independently by the
acceptance reviewer); all are different entities, and none rests on a near-identical pair.

- **The five Moneta targets D-398 named** (D-388): `MBLY`, `SNOW`, `SE`, `CTRA`, `MARA` are **kept**
  (`one_name`); `GRAB` is trimmed as leading padding. `MARA` — the halt — keeps its 252 real pre-halt
  bars, which is right; `MBLY`, `SE`, `SNOW` and `CTRA` keep their **pre-re-use** history, joined to
  the new company across the gap the padding cut leaves. That is D-399 (4) as specified, and it is the
  main cost of the rule.
- **D-008 after trimming: 21 of the 59 trimmed series have no split** (`T04k_split_after_trim.csv`),
  from `ISRL` (13 bars) to `SUPX` (608). Per D-398 none is excluded; each fails `compute_split` with
  `HistoryTooShortError` and drops out of the candidate universe that way.
- **T04i's 29 `reverse_split_suspect` trims** (`T04k_suspects.csv`): **none** is an unadjusted split;
  1 is trimmed as a re-use, 28 kept (24 `one_name`, 2 `disagrees`, 2 `ambiguous`).

## 4. D-399's cross-check: what it can decide, measured

**The re-use half does not hold.** MS-US-1D is keyed by ticker exactly like the Alpaca feed, so a
re-used ticker splices identically in both (`PX` 156.80 → 11.51 on 2021-10-21, with the same frozen
padding; `MBLY` 62.67 → 28.97). The supervisor withdrew that half, and **D-700** moved the
discriminator to company names. The price test now answers only `unadjusted_split` or `unsettled`.

**The split half needed conditions the first version lacked.** It declared four symbols
`unadjusted_split`, and **all four were wrong**:

| symbol | what was compared | why it was wrong | condition added |
|---|---|---|---|
| `AMLX`, `ATAI` | the IPO bar with **itself** — MS-US-1D has no bar before the IPO, and the nearest-bar fallback took the IPO bar for both sides | pre-IPO padding, not a split | each cross-check bar looks **only outward from its own date**, so the two are always distinct |
| `TBRG` | a **padded** ingested bar (a stale 13.31) against a cross-check trading near 9 | the "jump" measured the pad | compare the last **real** bar before the break, never a pad |
| `NRGZ` | a 0.693 move in both feeds | not a break at 0.40 in either | the ingested series must itself **break** at the compared dates |

The window is `split_check.crosscheck_window_days` (7). Regression tests reproduce the four shapes
and the short-gap variant the reviewer found (S2).

## 5. D-700: the name rule and its failure modes

**The rule.** The assets file holds **one row per ticker**: today's holder. The pre-break company's
name therefore exists only when it **renamed away** from the ticker, and its current name is then the
assets file's name for the rename's destination. A boundary is a re-use when a `NAME_CHANGE` row
`ticker → dest` lies in `[break start − 7 days, boundary]` and the two names are **different strings**
(exact identity after stripping surrounding whitespace). I used the full raw feed
(`name_changes_20260920.json`, 3,650 rows); `configs/universe/symbol_changes.csv` is a 30-row
derivative filtered to the S&P point-in-time tickers and covers almost none of these micro caps.

**One rule added, found on the data** (P-75 (a)). `PTN`: Palatin went `PTN→PTNT` and came **back**
`PTNT→PTN`, and an ETF then took `PTNT`, so `PTNT`'s current name called Palatin a re-use of itself —
**2,264 real bars** would have gone. A destination renamed away again afterwards is now `ambiguous`.
Measured against the pass before it, it removed **two** trims — `PTN` (false, saved) and `JAN` (a
real re-use, now missed) — and relabelled eight `one_name` cases as `ambiguous`, which changes nothing
for them.

**Failure modes:**

1. **Most delistings leave one name.** An acquisition, bankruptcy or plain delisting produces no rename
   away from the ticker: **194 of the 231** are `one_name`. A coverage limit, not a wrong answer.
2. **Exact identity errs towards "different"**, the direction that trims. It did not happen here (no
   trim rests on a near-identical pair, and the flag would show one), but the rule has no other
   defence.
3. **The destination guard over-fires on temporary suffixes** (`REED→REEDD→REED`, `PAPLF→PAPLD`), in
   the direction of keeping history.
4. **It misses a real re-use whose destination changed hands**: `JAN` (JanOne, `JAN→ALTS→AIFC`).
5. **The names are today's** (a 2026-09-20 snapshot).
6. **Missing tickers**: `CTRA` (Coterra) and `HCP` are not in the assets file, although the feed has
   the right renames (`CTRA→AMR` and `COG→CTRA`; `HCP→PEAK`). Both stay kept for that reason.

## 6. The `ohlc_outside_range` bug: the store's invariant is load-bearing

The first smoke run had the **store refuse 5 of 7 symbols** with `ohlc_outside_range`. Capping a
daily extreme to the RTH hourly range looked obviously safe — it only ever narrows a bar. It is not:
the hourly feed can miss the day's move so that its whole range sits **inside** the daily body, and
because `open` and `close` are never changed, the capped high fell below the close (`SPY`, `PX`,
`DOW`, `FB`). The cap is now bounded by the body, and two tests assert the OHLC invariant over whole
clean frames.

**A correction rule that looked self-evidently safe was not, and the only thing that caught it was the
store refusing an impossible bar.** Without that check the clean snapshots would hold bars whose close
lies above their high — and the engine checks stops against that high.

## 7. What the acceptance review found, and what the full pass found after it

1. **`wick_clip` fired where the hourly series is the evidence (V1).** A day with no breach row fell
   through to the clip arm, so **54 extremes a full 7-bar hourly day supported** (`URBN` 2020-11-09)
   and **5 on short hourly days** were clipped — the second directly against the supervisor's rule.
   `wick_clip` now runs **only for a symbol with no hourly series**, which is D-396's own wording: "cap
   where hourly data exists, otherwise clip". Verified on the final pass: **0** clips on hourly
   symbols.
2. **A short hourly day that did not breach was invisible (V2)**, because `breaches()` only returns
   breach days, and the pass never wrote the quality report with the hourly evidence. The check now
   takes the hourly **coverage** and states every short or missing day whatever the daily bar did,
   and the pass writes the report for the clean series in the same run.
3. **A re-run after `--set-reference` would have cleaned the clean series (V3)** — 233 symbols, 302
   more clips, because clipping lowers ATR(14). The pass now always reads the **raw** snapshot.
4. **Found on the full pass after those fixes: the clean series was judged on the raw bars'
   breaches.** 632 snapshots moved `ok → warning`, 620 of them hourly symbols failing
   `daily_extreme_unsupported` for extremes `extreme_cap` had already corrected. The check now
   recomputes the breaches on the series it judges, and a regression test pins it (a capped extreme
   breaches once on raw and never on clean).
5. Also fixed: ATR(14) measured on the bars that survive the removals (S3); thresholds and the refresh
   start date from config (V5); `EXCLUDE` recorded, never silent (S5); logs and provenance keyed by
   the clean hash (S6); every short day written, not only the breaching ones (S8); P-75 for the rules
   no decision states (V6).

## 8. A short hourly day is not evidence

Both of the supervisor's consequences hold on the final pass. No short or missing hourly day is
capped, clipped or counted clean (four arm tests and three report tests), and every clean-series report states them: across the 825
hourly symbols the reports list **13,748 short and 12,319 no-hourly-bar days** as not evidence, each
with its bar count against the calendar.

**The worst dates** (`T04k_short_hourly_dates.csv`: every short or missing day, per raw daily
session):

| date | symbols | of which no hourly bar | median hourly bars (of 7) |
|---|---|---|---|
| 2021-04-19 | 472 | 26 | 1 |
| 2022-03-08 | 466 | 104 | 1 |
| 2021-10-25 | 433 | 29 | 1 |
| 2022-01-24 | 370 | 24 | 2 |
| 2018-05-02 | 201 | 3 | 1 |
| 2018-05-03 | 201 | 2 | 1 |
| 2022-01-26 | 118 | 24 | 6 |

After these seven dates the next is 35 symbols: feed-wide events, not instruments. T04i's breach-only
table showed 438, 401 and 347 for the first three; counting every short day, not only the breaching
ones, raises them.

## 9. The quality of the clean series — and P-76

The pass writes the quality report of every symbol's clean series with both T04k checks. Against the
T04g raw reports:

| raw (T04g) → clean series | snapshots |
|---|---|
| ok → ok | 3,370 |
| warning → warning | 2,674 |
| warning → ok | 31 |
| **ok → warning** | **632** |

The 632 are **not cleaning making series worse**; T04g's reports never ran these two checks:

- **572** fail `daily_extreme_unsupported` on a **residual the cap cannot remove**. Over the 825 hourly
  symbols, **8,750 of 15,563** correctable breach days remain (43.8 % resolved), on 753 symbols. In a
  150-symbol sample **every** residual (1,495 of 1,495) is on the **close**, 99.3 % `extended_hours`,
  median **2.8 bps**, 75 % under 5 bps. The official daily close is the **16:00 closing-auction
  print**, which the hourly feed files in the 16:00 bar — the bar D-023's 09:00–15:00 window drops —
  so the close sits a few bps outside the RTH range. The cap correctly stops at the body, and the
  check then reports a traded price as unsupported. **P-76** asks whether an extreme equal to the open
  or the close should ever be flagged.
- **86** fail `daily_wick_outlier` on hourly symbols, whose wicks the hourly evidence keeps. D-396 asks
  for that check on every symbol, so it reports them.

## 10. Every changed bar says which arm changed it and why

Each log row carries `arm` and `evidence`: for `extreme_cap` the RTH range, its bar count against the
calendar and "bounded by the body"; for `wick_clip` the ATR(14) multiple and the percentage; for
`frozen_cut` the run and its level; for `boundary_trim` the D-398 reason and the D-700 verdict. A test
asserts no row has an empty arm or evidence, and a replay test rebuilds the clean bars from raw and
the log.

## 11. Acceptance criteria

| criterion | proof | result |
|---|---|---|
| both checks from YAML; a bad print, an extended-hours extreme, a volatile bar that must not flag | `test_F_0_1_6_D_396_*` | pass |
| a short hourly day changes nothing, is not reported clean, appears with its bar count | `…_a_short_hourly_day_*`, `…_never_counts_a_short_hourly_day_as_a_defect`, `…_a_short_day_that_does_not_breach_is_still_stated`, `…_no_hourly_bar_is_stated_too` | pass |
| every log row carries its arm and evidence | `…_every_log_row_names_its_arm_and_its_evidence`; store: 0 empty of 226,215 | pass |
| D-398: padded stretch, leading pad, re-use boundary; boundary in the metadata; too short fails the split | `…_frozen_stretch_is_cut…`, `…_a_leading_pad_is_trimmed_without_any_name_evidence`, `…_a_re_use_by_name_trims…`, `…_each_clean_snapshot_has_its_own_log_and_provenance` (notes and JSON), `…_too_short_fails_the_split…` | pass |
| D-399 as amended by D-700: an ambiguous signature never trims | `test_F_0_1_9_*`, `test_F_0_1_2_name_evidence.py`, `…_one_name_keeps_the_history…` | pass |
| `daily_wick_outlier` runs without hourly data | `…_the_wick_check_runs_without_hourly_data` | pass |
| a clean snapshot for every raw one, `derived_from`, **the reference**, raw untouched | raw untouched: `…_leaves_the_raw_one_untouched` (bytes and mtime); reference **deferred as instructed** (§12.1) | partial, by instruction |
| replaying the log reproduces the clean bars | `…_replaying_the_log_reproduces_the_clean_bars` | pass |
| `open`/`close`/`volume` identical | `…_open_close_and_volume_are_never_changed`; store: 0 differences | pass |
| re-running writes nothing new | `…_the_input_is_the_raw_snapshot_even_after_set_reference`; store: `catalog.parquet` sha256 `b3b6cda7f280ac2b` before and after a re-run, 16,752 non-quality events before and after (a re-run does append `quality` events: the checks run again) | pass |
| gates green, `sfac streams check` clean | §13 | pass |

## 12. Deviations

1. **The clean snapshots are not the references yet**, by instruction. On approval,
   `uv run sfac data clean --set-reference` reads raw, finds every clean snapshot already stored,
   writes no bar and moves 3,250 references.
2. **No separate snapshot for the 3,457 unchanged symbols**: identical content has the same hash, so
   the raw snapshot *is* their clean series (rule 10).
3. **82 superseded clean snapshots** from the passes that ran before the fixes remain in the store and
   the catalog (immutable, rule 10); none is a reference. The first-layout flat logs
   `_clean/<symbol>.csv` remain beside them; the report reads only the current layout.
4. **Some clean snapshots' metadata predates the provenance notes.** Where a clean series is
   byte-identical to one an earlier pass wrote, the store returns the stored metadata (D-392: no
   correction path), so its notes lack the config hash. Every current clean snapshot has the full
   provenance in its `_clean/<symbol>/<hash>.json`, written by the final pass.
5. `short_hourly_days.csv` counts per **raw** daily session, including padded days later cut; the
   quality reports count per clean session.
6. The full `NAME_CHANGE` feed is used, not only `configs/universe/symbol_changes.csv` (§5).

## 13. Acceptance commands

```
uv run pytest -m "not slow"                            1317 passed, 1 failed (below)
uv run pytest tests/parity tests/leakage tests/oracle    283 passed
uv run pytest -m db                                       21 passed, 0 skipped
uv run ruff check . / ruff format --check .             clean
uv run mypy src                                         no issues in 104 source files
uv run sfac streams check --base origin/main            ownership, ids (D-700 in range), alembic head: ok
```

The one failure is stream A's `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio` (their
D-368), untouched. No new dependency. Nothing under `configs/costs/` or `configs/universe.yaml`
changed; `SFAC_RAW_ROOT` was only read.

## 14. For the supervisor

- **Approve T04k**, and with it `--set-reference`.
- **P-75**: confirm the six implementation rules, all conservative.
- **P-76**: the closing-auction residual behind 572 `warning`s.
- **221 of the 280 stay spliced** (minus padding), four of the five named Moneta targets among them.
  The next evidence would be **CUSIPs** — the `NAME_CHANGE` feed carries `old_cusip`/`new_cusip`,
  which identify the security rather than its name — but that is a new discriminator and yours to
  decide.
