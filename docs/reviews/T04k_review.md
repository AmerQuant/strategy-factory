# T04k review — the derived clean daily snapshot

**Task:** `docs/tasks/T04k_clean_daily_snapshot.md` · **Branch:** `b/T04k-clean-daily` from `main` (T04g merged, PR #24; rebased onto `b5a0bb4`, PR #25)
**Features:** F-0.1.6 (quality checks and report), F-0.1.8 (immutable and derived snapshots), F-0.1.2 (frozen stretches, re-use boundary), F-0.1.9 groundwork
**Decisions used:** D-008, D-023, D-033, D-383, D-384, D-392, D-395, D-396, D-397, D-398, D-399, **D-700** (new, supervisor — amends D-399)
**Status:** complete and **waiting for the supervisor's approval**. Per the supervisor's instruction the clean pass ran **without `--set-reference`**: all 6,707 references are still the raw snapshots.

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/clean_daily.py` | the four arms — `boundary_trim`, `frozen_cut`, `extreme_cap`, `wick_clip` — and `wick_outliers()`; pure |
| `src/strategy_factory/data/crosscheck.py` | the D-399 price test against MS-US-1D, reduced to what it can decide (§4) |
| `src/strategy_factory/data/name_evidence.py` | **D-700**: the company-name discriminator, with loaders for the assets file and the `NAME_CHANGE` feed |
| `src/strategy_factory/data/quality.py` | two checks, `daily_wick_outlier` and `daily_extreme_unsupported` (F-0.1.6, D-396) |
| `src/strategy_factory/data/cli_clean.py` | `sfac data clean`: one pass per symbol, a changed-bar log per symbol, a summary |
| `configs/data/quality.yaml`, `configs/data/alpaca.yaml` | every threshold (rule 1): `daily_wick_outlier.k1_atr/k2_pct`, `daily_extreme_unsupported.eps_bps`, `relisting.rename_window_days`, the two evidence paths |
| `scripts/analysis/T04k_report.py` | the aggregates below |
| `docs/reviews/T04k_boundaries.csv` | **the 280 re-use candidates**, each with its price-test and name-test verdict and what happened |
| `docs/reviews/T04k_changes_per_symbol.csv`, `…_per_date.csv` | changed bars per symbol and per date, by arm |
| `docs/reviews/T04k_incomplete_hourly_dates.csv` | the days the hourly series is not evidence, with symbol counts |
| tests | **53 new**: `test_F_0_1_6_clean_daily.py` (32), `test_F_0_1_9_crosscheck.py` (10), `test_F_0_1_2_name_evidence.py` (11); plus the check-set update in `test_F_0_1_6_quality.py` |

The per-bar logs — every changed bar with its old value, new value, arm and evidence — are in the store at
`<SFAC_DATA_ROOT>/_clean/<symbol>.csv` (226,305 rows over 3,250 symbols), beside the snapshots they describe.

## 2. The run

```
uv run sfac data clean            # no --set-reference, as instructed
```

| | symbols |
|---|---|
| daily snapshots processed | 6,707 |
| **cleaned** (a new derived snapshot) | **3,250** (48.5 %) |
| **unchanged** (the raw snapshot already is the clean series) | 3,457 |
| `unadjusted_split` (D-397 path) | **0** |
| failed | **0** |

**11,947,857 raw bars → 11,733,903 clean bars: 213,954 removed (1.79 %).** Changed-bar log rows by arm:

| arm | changed bars | symbols touched |
|---|---|---|
| `frozen_cut` (D-398 (1)) | **181,503** | 709 |
| `boundary_trim` (D-398 (2)/(3)) | 32,451 | 59 |
| `extreme_cap` (D-396, hourly evidence) | 6,925 | 795 |
| `wick_clip` (D-396, no hourly evidence) | 5,426 | 2,110 |

"Cleaned" is nearly half the universe, but it is two populations: **2,861 symbols** have at least one
extreme corrected (a handful of bars each), and **359** are touched only by padding removal. Bars
removed are 1.79 % of the total and almost all of it is padding.

**The daily range on the 12,325 bars an extreme arm changed**, in basis points of the close:

| | median | p90 | p99 | max |
|---|---|---|---|---|
| before | 496.5 | 8,523.1 | 18,905.2 | 252,352.9 |
| after | 307.5 | 2,534.8 | 6,560.0 | 32,771.4 |

The median barely moves; the tail collapses — the arms act on the bad prints, not on ordinary days.

## 3. The 280 re-use candidates — per arm, measured

This is the table the supervisor asked for: how many of the 280 the name evidence settles and how many
stay untrimmed.

| boundary reason | candidates | trimmed | **kept** (full history, listed) | how |
|---|---|---|---|---|
| `leading_padding` | 49 | **49** | 0 | D-398 (3): padding before a listing is not a re-use signature |
| `stale_run` | 162 | **5** | **157** | D-700 names: 141 `one_name`, 13 `disagrees`, 3 `ambiguous` |
| `trading_gap` | 69 | **5** | **64** | D-700 names: 53 `one_name`, 3 `disagrees`, 8 `ambiguous` |
| **total** | **280** | **59** | **221** | |

**The name evidence settles 10 of the 231 real re-use candidates (4.3 %).** The other 221 keep their full
history — minus their frozen padding, which D-398 (1) removes regardless — and are listed in
`docs/reviews/T04k_boundaries.csv` for the supervisor. **Nothing went to the D-397 path.**

The ten trimmed as re-used, with the evidence each rests on:

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

I checked each against its full `NAME_CHANGE` history; all ten are different entities. **None rests on a
near-identical pair** (`near_identical` is false for all ten).

**The five Moneta targets D-398 named** (D-388): `MBLY`, `SNOW`, `SE`, `CTRA` and `MARA` are all **kept**
(`one_name`) — none has a rename away from its ticker in the feed, and `CTRA` is not in the assets file at
all. `GRAB` is trimmed as leading padding. So `MARA` — the halt the supervisor worried about — now keeps
its 252 real pre-halt bars, which is right; but `MBLY`, `SE`, `SNOW` and `CTRA` keep their **pre-re-use**
history, joined to the new company across the gap the padding removal leaves. That is D-399 (4) working
as specified, and it is the main cost of the rule.

## 4. D-399's cross-check: what it can decide, measured

**The re-use half does not hold.** MS-US-1D is keyed by ticker, exactly like the Alpaca feed, so a re-used
ticker splices identically in both: `PX` goes 156.80 → 11.51 on 2021-10-21 in the cross-check too, with
the same frozen padding at 156.80 before it; `MBLY` is the same (62.67 → 28.97). A shared break proves the
break is in the data, never what caused it. The supervisor withdrew that half and D-700 moved the
discriminator to company names (§5). The price test now answers only `unadjusted_split` or `unsettled`.

**The split half needed three conditions the first version lacked.** It declared four symbols
`unadjusted_split`, and **all four were wrong**:

| symbol | what the first version compared | why it was wrong | condition added |
|---|---|---|---|
| `AMLX`, `ATAI` | the IPO bar with **itself** — MS-US-1D has no bar before the IPO and the nearest-bar fallback took the IPO bar for both sides, reporting a "continuous" 1.0000 | pre-IPO padding, not a split | the two cross-check bars must be **distinct and on their own sides** |
| `TBRG` | a **padded** ingested bar (a stale 13.31) against a cross-check that was trading near 9 | the "jump" measured the pad | compare the last **real** bar before the break, never a pad |
| `NRGZ` | a 0.693 move in both feeds | not a break at the 0.40 threshold in either | the ingested series must itself **break** at the compared dates |

After the fix the full pass found **no** unadjusted split among the 231, which is plausible: the known
unadjusted case, `AVGO`, is not in the store (D-397 kept it out in T04g). Three regression tests reproduce
the three shapes.

## 5. D-700: the name rule and its failure modes

**The rule** (`data/name_evidence.py`). The Alpaca assets file holds **one row per ticker** — the security
that holds it **today**. The name of the company that held a ticker **before** a break therefore exists
only when that company **renamed away** from it: its current name is the assets file's name for the
rename's destination. So a boundary is a re-use when a `NAME_CHANGE` row `ticker → dest` falls inside
`[break start − 7 days, boundary]` (`relisting.rename_window_days`) and the assets file's name for `dest`
and its name for `ticker` are **different strings**. Matching is **exact identity** after stripping
surrounding whitespace, nothing more (D-700 (4)).

**The feed.** I used the **full** raw `NAME_CHANGE` feed, `reference/alpaca/corporate_actions/
name_changes_20260920.json` (3,650 rows). `configs/universe/symbol_changes.csv` is a 30-row derivative
of it, filtered to the S&P point-in-time tickers; on its own it covers almost none of the 231 daily
candidates, which are mostly micro caps.

**One refinement, found on the data.** `PTN`: Palatin went `PTN→PTNT` on 2025-05-08 and came **back**
`PTNT→PTN` on 2025-11-12; an ETF then took `PTNT`. Comparing `PTN`'s name with `PTNT`'s *current* name
called Palatin a re-use of itself and would have **deleted 2,264 bars of its real history**. A destination
that was renamed away again afterwards no longer identifies the company that left, so the case is now
`ambiguous` and kept. This only removes trims — it enforces D-700's own "a rename of the same company is
not a re-use" in the direction D-399 (4) requires — but it is a rule I added, so it is flagged here for
the supervisor to confirm.

**Failure modes, stated plainly:**

1. **Most delistings leave one name.** An acquisition, a bankruptcy or a plain delisting produces no rename
   away from the ticker, so there is no second name and the case stays `one_name` — **194 of the 231**.
   This is why the name evidence settles so few. It is a coverage limit, not a wrong answer.
2. **Exact identity errs towards "different".** Two names for one company that differ in a suffix
   ("Inc." vs "Inc. Class A Common Stock") would read as a re-use and trim. It did not happen here — no
   trim rests on a near-identical pair, and the flag would have shown it — but the rule has no defence
   against it beyond that flag.
3. **The destination guard over-fires on temporary suffixes.** A rename to a Nasdaq reverse-split or
   deficiency suffix and back (`REED→REEDD→REED`, `PAPLF→PAPLD`, `AIMI→AIMID`) makes the case `ambiguous`
   even when the destination kept the same company. That errs towards **keeping** history.
4. **It misses real re-uses whose destination changed hands.** `HCP` (Healthpeak, `HCP→PEAK→DOC`) was
   genuinely re-used by HashiCorp, and `JAN` (JanOne, `JAN→ALTS→AIFC`) by Janus Living, but both stay
   `ambiguous` because the destination was renamed again.
5. **The names are today's.** The assets file is a 2026-09-20 snapshot; a company that has since changed
   its own name compares under the new one.
6. **Missing tickers.** `CTRA` (Coterra) is absent from the assets file, so its case cannot be settled even
   though the feed has both `CTRA→AMR` (Contura left) and `COG→CTRA` (Cabot arrived) on the right dates.

## 6. The `ohlc_outside_range` bug: the store's invariant is load-bearing

The first smoke run of the clean pass had the **store refuse 5 of 7 symbols** with
`bar validation failed: ohlc_outside_range`. Capping a daily high or low to the RTH hourly range looked
obviously safe — it only ever narrows a bar. It is not: the hourly feed can miss the day's move so that its
whole range sits **inside** the daily body, and because `open` and `close` are never changed, the capped
high fell below the close (`SPY`, `PX`, `DOW`, `FB`). The cap is now bounded by the body —
`high ≥ max(open, close)`, `low ≤ min(open, close)` — and two tests assert the OHLC invariant over the whole
clean frame.

The point worth keeping: **a correction rule that looked self-evidently safe was not, and the only thing
that caught it was the store refusing an impossible bar.** Without that check the clean snapshot would have
held bars whose close lies above their high — and the engine checks stops against that high.

## 7. A short hourly day is not evidence (supervisor, 2026-09-21)

T04i's completed-download re-run showed that `incomplete_hourly_day` is a property of Alpaca's SIP hourly
feed, not of an unfinished download. Both consequences are implemented and tested:

- On such a day (and on a `no_raw_hours` day) **the daily bar is left untouched**: no `extreme_cap`, and no
  `wick_clip` either — a short hourly day may not silently clean a bar through the other arm. Four tests,
  including the case where the one surviving hourly bar "agrees" with the daily range.
- `daily_extreme_unsupported` **never counts such a day as clean**: it reports `not_evidence_days`, their
  dates, and the bar count each held against the calendar's expectation (e.g. `2021-04-19: 1 of 7 hourly
  bars`).

**The worst dates** (`docs/reviews/T04k_incomplete_hourly_dates.csv`) — feed-wide events, not instruments:

| date | symbols | median hourly bars (of 7) |
|---|---|---|
| 2021-04-19 | 438 | 1 |
| 2021-10-25 | 401 | 1 |
| 2022-03-08 | 347 | 1 |
| 2022-01-24 | 279 | 2 |
| 2018-05-02 | 194 | 1 |
| 2018-05-03 | 194 | 1 |
| 2022-01-26 | 57 | 6 |

After these seven dates the next is 6 symbols: the defect is concentrated in a handful of feed-wide days.

## 8. Every changed bar says which arm changed it and why

Each log row carries `arm` and `evidence`: for `extreme_cap` the RTH range, its bar count against the
calendar, and "bounded by the body"; for `wick_clip` the ATR(14) multiple and the percentage; for
`frozen_cut` the run length and level; for `boundary_trim` the D-398 reason, the boundary and the D-700
verdict. A test asserts no row has an empty arm or evidence, and a replay test rebuilds the clean bars from
the raw bars and the log exactly.

## 9. Acceptance criteria

| criterion | proof | result |
|---|---|---|
| both checks from YAML, with a bad print, an extended-hours extreme and a volatile bar that must not flag | `test_F_0_1_6_D_396_*` (wick: bad print, wide-but-real, large ATR multiple alone, thresholds from config, low side; extreme: real breach, extended hours) | pass |
| a short hourly day changes nothing and is not reported clean, with its bar count | `test_F_0_1_6_T04k_a_short_hourly_day_*`, `…_the_extreme_check_never_counts_a_short_hourly_day_as_a_defect` | pass |
| every log row carries its arm and evidence | `test_F_0_1_6_T04k_every_log_row_names_its_arm_and_its_evidence` | pass |
| D-398 fixtures: padded stretch, leading pad, re-use boundary; too short **fails the split** | `…_a_frozen_stretch_is_cut…`, `…_the_history_starts_at_the_boundary…`, `…_a_trimmed_history_too_short_fails_the_split_not_the_universe` (against `compute_split`) | pass |
| D-399: four verdicts from four fixtures | **amended by D-700** — the price test yields two verdicts (§4), the names five (§5); `test_F_0_1_9_*` (10) and `test_F_0_1_2_name_evidence.py` (11), including that an ambiguous case never trims | pass, as amended |
| `daily_wick_outlier` runs without hourly data | `…_the_wick_check_runs_without_hourly_data`, `…_a_symbol_without_hourly_data_still_gets_its_wicks_clipped` | pass |
| the clean snapshot exists for every raw one, has `derived_from`, **is the reference**, raw untouched | `test_F_0_1_8_T04k_writing_the_clean_snapshot_leaves_the_raw_one_untouched` (bytes and mtime) | **partial — see §10** |
| the log accounts for every difference (replay) | `…_replaying_the_log_reproduces_the_clean_bars` | pass |
| `open`/`close`/`volume` identical | `…_open_close_and_volume_are_never_changed` | pass |
| re-running writes nothing new | real store: `catalog.parquet` sha256 `3153fe815fa0ac29` before and after a re-run, events 30,105 → 30,105 | pass |
| gates green, `sfac streams check` clean | §11 | pass |

## 10. Deviations

1. **The clean snapshot is not the reference yet.** The supervisor asked for the pass to run without
   `--set-reference` until T04k is approved. All 6,707 references are still the raw snapshots; on approval
   the switch is one command (`uv run sfac data clean --set-reference`), which writes no bars — every clean
   snapshot already exists, so it only moves 3,250 references.
2. **No separate snapshot for the 3,457 unchanged symbols.** Their clean series is byte-identical to the raw
   one, so the content hash is the same and the store returns the existing snapshot (rule 10); the raw
   snapshot *is* their clean reference. The summary records the hash for each.
3. **The boundary date is in the metadata of new snapshots, not of the 59 already written.** The note was
   extended after the pass that wrote them; their notes carry the `boundary_trim` bar count, and the
   boundary date and verdict are in the changed-bar log and `T04k_boundaries.csv`. The store never rewrites
   the metadata of existing content (D-392), so they cannot be amended in place.
4. **12 superseded clean snapshots.** The pass ran four times while the rules were corrected (§4, §5); 12
   derived snapshots from earlier passes remain in the store and the catalog (immutable, rule 10), none of
   them a reference. `PTN`'s wrongly trimmed series is one of them.
5. **The full `NAME_CHANGE` feed** is used, not only `configs/universe/symbol_changes.csv` (§5).

## 11. Acceptance commands

```
uv run pytest -m "not slow"                            1300 passed, 1 failed (below)
uv run pytest tests/parity tests/leakage tests/oracle    283 passed
uv run pytest -m db                                       21 passed, 0 skipped
uv run ruff check . / ruff format --check .             clean
uv run mypy src                                         no issues in 104 source files
uv run sfac streams check --base origin/main            ownership, ids (D-700 in range), alembic head: ok
```

The one failure is stream A's `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio`, answered as
their **D-368** and untouched here. No new dependency. Nothing under `configs/costs/` or
`configs/universe.yaml` changed; `SFAC_RAW_ROOT` was only read.

## 12. For the supervisor

- **Approve T04k**, and with it the switch to the clean snapshots as references.
- **221 of the 280 stay spliced** (minus padding) because the name evidence has one name for them. That
  includes four of the five Moneta targets D-398 named. If that is not acceptable, the next evidence would
  be CUSIPs — the `NAME_CHANGE` feed carries `old_cusip`/`new_cusip`, which identify the security rather
  than its name — but that is a new discriminator and yours to decide.
- **Confirm the destination guard** (§5). Measured against the pass before it: it removed **two** trims —
  `PTN` (a false re-use: 2,264 real bars saved) and `JAN` (a real re-use, now missed) — and relabelled
  eight cases from `one_name` to `ambiguous` (`AIB`, `AIM`, `HCAC`, `HCP`, `PAPL`, `QTI`, `REED`, `SEV`),
  which changes nothing for them. Both effects are in the direction of keeping history.
