# T04f review — Alpaca reference data: NYSE session calendar and symbol changes

**Task:** `docs/tasks/T04f_alpaca_reference_calendar.md` · **Branch:** `b/T04f-alpaca-reference` (stream B, D-355)
**Features:** F-0.1.2 (Alpaca adapter, session filter), F-0.1.6 (quality: schedule checks)
**Decisions used:** D-024, D-025, D-028, D-031, D-033, D-355, D-357, D-358, D-383, D-384, D-388, D-392, D-393, D-394
**Network run:** the user, 2026-09-20 13:21–13:22 UTC, log `SFAC_RAW_ROOT/_reports/T04f_reference_20260920T132152Z.log`

## 1. What was built

| File | What |
|---|---|
| `scripts/pilots/T04f_reference.ps1` | the user's PowerShell run: calendar, symbol changes, universe rebuild (D-031) |
| `configs/calendars/nyse_sessions.csv` | **new** — 2,765 sessions 2016-01-04 → 2026-12-31 (D-025) |
| `configs/calendars/nyse_early_closes.yaml` | **deleted** (T04e §6, D-393) with `EarlyCloses`, `load_early_closes`, `compare_with_early_closes` and the CLI comparison block |
| `configs/universe/symbol_changes.csv` | **new** — 30 effective name changes for the 745 PIT tickers (D-024) |
| `configs/universe/symbol_changes_manual.csv` | 11 **rejections** (empty `new_symbol`), each with its reason (D-383) |
| `configs/universe/us_equity_hourly.csv` | rebuilt: `pit_symbol` column, **827 → 806** rows |
| `configs/universe/us_equity_daily.csv` | unchanged (6,711 rows; it does not come from the PIT list) |
| `src/.../alpaca_reference.py` | rejection marker in `build_symbol_changes`; `current_symbol` ignores an empty `new_symbol` |
| `src/.../cli_alpaca.py` | `alpaca-symbol-changes --from-raw` (rebuild from a stored raw answer, no network) |
| `src/.../store.py` | `MATERIAL_FIELDS` + `_check_material`: the material-metadata guard (D-384, D-392) |
| `scripts/analysis/T04f_symbol_change_evidence.py` | regenerates the accounting CSV below; local, no network, writes no snapshot |
| `docs/reviews/T04f_symbol_changes_accounting.csv` | **one row per symbol the feed renames**, with the evidence |

## 2. The calendar (D-025) — and why the YAML could be deleted

```
calendar: 2765 sessions 2016-01-01..2026-12-31 -> configs\calendars\nyse_sessions.csv
          0 difference(s) vs nyse_early_closes.yaml
```

- 2,765 sessions, first `2016-01-04`, last `2026-12-31`; **every** session opens at `09:30`.
- **23 early closes**, all at `13:00`: 2016-11-25, 2017-07-03, 2017-11-24, 2018-07-03, 2018-11-23,
  2018-12-24, 2019-07-03, 2019-11-29, 2019-12-24, 2020-11-27, 2020-12-24, 2021-11-26, 2022-11-25,
  2023-07-03, 2023-11-24, 2024-07-03, 2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28, 2025-12-24,
  2026-11-27, 2026-12-24.
- **Difference report (T04e §6 deliverable): empty.** `SFAC_RAW_ROOT/_reports/calendar_vs_early_closes.csv`
  contains only its header. The hand-written list had all 23 dates, no date the calendar lacks, and
  no date where the two disagree on the close time. The T04a open question ("please verify the NYSE
  early-close list") is therefore **closed: the list was correct.**

Because the report shows no unexplained disagreement, **D-393** allows the deletion, which is done.
The hourly adapter already reads each day's close from `nyse_sessions.csv`, so no adapter change was
needed.

## 3. Symbol changes (D-024) and the exclusion rule (D-383)

The feed returned **42** `NAME_CHANGE` rows touching the PIT tickers. `build_hourly_universe`
follows every chain, which took the hourly universe **827 → 800**. That was **more than the ≤ 15 I
predicted while planning**: my estimate came from a row-count heuristic that only sees pairs where
*both* tickers were already among the 827, and it missed every rename whose destination was new.

### The test

`scripts/analysis/T04f_symbol_change_evidence.py` follows each chain the way `current_symbol` does —
so the effective date is the one of the **hop actually taken** — and compares the two symbols' daily
closes on the days **strictly before** that date:

- **>= 99.5 % identical -> `rename_confirmed`**, the same series;
- **< 90 % identical -> `different_company`**; between the two -> `inconclusive` (none occurred);
- **the destination has no prices at all -> `destination_no_data`**;
- **no shared trading day before the change -> `rename_confirmed_no_overlap`.** There is nothing to
  compare, which is what a rename looks like when Alpaca stops serving the old ticker. It is a
  **weaker** verdict than `rename_confirmed` and is reported separately. Three rows land here --
  `CDAY->DAY`, `FBHS->FBIN`, `JEC->J` -- and all three are removals, so they rest on the feed alone.
  `FBHS` and `JEC` are two of the three symbols that returned no bars at all
  (`_reports/alpaca_missing_1D.csv`), so there is no series to compare by construction.
- a mismatch alone does not settle it: the old row is kept only if the **old symbol's own series
  covers its own index-membership window**. If it does not, Alpaca serves some other company under
  that ticker and nothing for the membership period, so the old row is useless and the rename is
  followed.

The pre-change window matters. `FB→META` is **100 % identical before 2022-06-09 and 0 % after**:
that is D-383's second clause seen from the other side — the rename is real and the **old** ticker
was re-used afterwards (`FB` 2026 closes 42.0–45.6 against `META` 526–738). Comparing the whole
overlap instead would have rejected a correct rename. `HCP→DOC` is the same shape (99.9 % / 0 %).

### Result

The accounting CSV has **38 rows** -- one per PIT ticker the raw feed would move -- which resolve
to **26 removals** from the hourly universe (`FISV` resolves back to itself; the 11 rejections keep
their row).

| verdict | rows | action |
|---|---|---|
| `rename_confirmed` | 24 | exclude the old row, keep the destination |
| `rename_confirmed_no_overlap` | 3 (`CDAY`, `FBHS`, `JEC`) | exclude the old row -- on the feed alone |
| `different_company` | 7 | **keep the old row**, drop the destination |
| `destination_no_data` | 3 | **keep the old row**, drop the destination |
| `old_symbol_has_no_data_in_its_membership_window` | 1 (`FI`) | exclude the old row, keep the destination |

One row's verdict and action deliberately disagree: `PX->RPC` is `rename_confirmed` and is
nonetheless rejected -- see **P-69** in section 9.

**11 rejections**, written to `configs/universe/symbol_changes_manual.csv` with their reason:
`BBBY`, `BBT`, `CBS`, `COG`, `EQR`, `IR`, `LLL`, `MNK`, `PX`, `VIAC`, `XL`.

Worked examples:
- `LLL→JXG` — 0 % identical over 1,704 days. L3's real successor is LHX; `JXG` is an unrelated
  company that took the ticker.
- `BBT→TFC` — 0 % over 990 days. Truist's whole history is under `TFC`; Alpaca's `BBT` is another
  live instrument.
- `MNK→MNKTQ`, `BBBY→NXH`, `EQR→VMRK` — the destination has no price data at all.
- `FI→FISV` — **not** rejected. `FI` was Fiserv's interim ticker (membership 2023-06-07 → 2025-11-04),
  but Alpaca's `FI` series is Expro's and **ends 2022-12-30**, i.e. 0 days inside its own membership
  window. Fiserv's full history is under `FISV`, which the chain `FISV→FI→FISV` resolves back to.
  My first pass rejected `FI` on a 0 % mismatch measured against the **wrong** effective date
  (2021-10-04, the `FI→XPRO` row) and that removed `FISV` — a Moneta target — from the universe.
  `FI` is the only symbol in this feed with more than one feed row, and the evidence script now
  always uses the hop actually taken.

### The mechanism

`symbol_changes_manual.csv` could only *re-target* a rename; a self-map would make `current_symbol`
loop. A manual row with an **empty `new_symbol`** now means "reject": `build_symbol_changes` drops
the hop from the chain graph and does not write it to `symbol_changes.csv`, so the old symbol keeps
its own universe row. `current_symbol` also skips empty destinations defensively.

### Universe

**827 → 806**: 26 removed, 5 added (`BFH`, `DINO`, `FBIN`, `GAP`, `TNL`). The daily universe is
unchanged at 6,711 rows. The intermediate figure **800** quoted above is the builder's output
*before* the rejections; **806** is what is committed.

## 4. D-388 — the Moneta-target check, re-run against the real feed

Against `main`'s `configs/costs/moneta/symbol_map.csv` (515 mappings) and `symbol_overrides.csv`:

- **Moneta targets removed from the hourly universe: none.**
- **`EQR`** (broker `EQR`) and **`IR`** (broker `IR`) would have been removed by the raw builder
  output and are **kept**: `EQR→VMRK` has no destination data and `EQR` runs to 2026-08-17;
  `IR→TT` is 0 % identical over its 956 shared pre-change days and both run to 2026-09-18 (Ingersoll Rand Inc. kept the
  ticker when Ingersoll-Rand plc became Trane Technologies).
- `FISV` (broker `FI`, D-356) is present — see the `FI` note above.
- Surviving targets that are rename destinations: `COR`, `LUMN`, `META`, `RTX`, `MRSH` (broker
  `MMC`), `BNY` (broker `BK`), `TFC`.
- **`GAP`** (broker `GPS`) is now an hourly row; its hourly raw was missing and the user began
  downloading it (P-70).
- **Nothing under `configs/costs/` was modified** (D-388).

`configs/universe.yaml` was **not** regenerated (D-394). Every added and removed symbol is listed in
`docs/streams/B.md` for stream A.

## 5. Material-metadata guard (D-384, D-392)

Tests: `test_F_0_1_8_material_metadata_mismatch_raises`,
`test_F_0_1_8_material_metadata_error_names_both_values`,
`test_F_0_1_8_non_material_metadata_never_raises`, and the existing
`test_F_0_1_8_write_is_idempotent` (unchanged behaviour for a repeat write with the same material
metadata).

`SnapshotStore.write_snapshot` returns the stored metadata when the content hash already exists, so
a re-ingest with corrected metadata was a silent no-op. It now compares `source`, `source_symbol`,
`asset_class`, `price_type`, `adjustment`, `session`, `feed`, `volume_quality`, `original_tz`,
`bar_label` and `hash_version` and **raises** `DataError` naming the field and both values.
`notes`, `raw_refs`, `downloaded_at`, `created_at` and `derived_from` are not material. This is what
makes the D-358/D-381 ordering enforceable rather than a convention.

## 6. Acceptance criteria

| Criterion | Status | Proof |
|---|---|---|
| Script delivered, user's run completed without a TLS error | ✅ | `scripts/pilots/T04f_reference.ps1`; the log shows three steps, exit 0 |
| `nyse_sessions.csv` exists, 2016-01-04 → the current year | ✅ | §2; 2,765 rows |
| Schedule checks no longer skipped for `us_equity` | ✅ | `test_F_0_1_2_us_equity_schedule_is_not_skipped_with_the_committed_calendar` (and `test_F_0_1_2_committed_nyse_calendar_is_usable`); T04g/T04h report it on real snapshots |
| `symbol_changes.csv` exists, contains `FB → META (2022-06-09)` | ✅ | §3; `test_F_0_1_2_symbol_changes_for_pit_tickers_with_manual_override` |
| Hourly universe has `pit_symbol`, no `FB` row, `META` carries `pit_symbol = FB` | ✅ with a note | `test_F_0_1_2_committed_hourly_universe_applies_the_exclusion_rule` runs on the **committed** file. The value is `FB` + pipe + `META`, not bare `FB`, because **both** tickers are PIT members and the builder merges them with its documented pipe separator; the criterion's literal wording predates that case |
| `nyse_early_closes.yaml` deleted, no code path references it | ✅ | §2; `grep` clean |
| Difference report reproduced in the review | ✅ | §2 (empty) |
| D-383 applied, every removal has a verdict | ✅ | §3; the accounting CSV has 38 rows covering all 26 removals and all 11 rejections |
| D-388 re-check in the review, `configs/costs/` untouched | ✅ | §4; `git status` clean under `configs/costs/` |
| `configs/universe.yaml` unchanged, symbols listed for stream A | ✅ | §4; `docs/streams/B.md` |
| Acceptance commands pass | ✅ | §7 |

## 7. Acceptance commands

```
uv run pytest -m "not slow"                  1057 passed, 1 warning in 71.02s
uv run pytest tests/parity tests/leakage     280 passed in 5.80s
uv run pytest -m db                          16 passed, 0 skipped (1041 deselected)
uv run ruff check .                          All checks passed
uv run ruff format --check .                 239 files already formatted
uv run mypy src                              no issues in 94 source files
```

No new dependency. The one warning is a pre-existing `websockets.legacy` `DeprecationWarning`
raised from `tests/unit/test_F_0_1_2_alpaca_download.py`, not from this task.
Tests added by T04f: **8** — 4 for the rejection marker (including the hop-scoped one), 3 for the
metadata guard, and `test_F_0_1_2_committed_hourly_universe_applies_the_exclusion_rule` — plus 2
that pin the committed calendar. One test was deleted with the code it covered (deviation 3).

## 8. Acceptance-reviewer findings

The `acceptance-reviewer` subagent ran on this branch against `docs/batch3-data` and found no
violation of the non-negotiable rules (nothing under `configs/costs/`, `configs/universe.yaml`
untouched, no parity/leakage test touched, no new dependency, no secrets). It raised, and this
review now reflects, the following, all fixed before the PR:

1. **P-68 described a state that was never committed** (11 rejections *including* `FI`, result 807).
   Rewritten to the implemented state: `FI` is not rejected, `PX` is, result **806**.
2. **`scripts/pilots/T04f_reference.ps1` still referenced the deleted YAML** and read
   `calendar_vs_early_closes.csv`, which the CLI no longer writes. The comment is now historical and
   the dead summary block is gone, so re-running the script does what it says.
3. **An undisclosed fourth branch in the evidence script.** When two symbols share no pre-change
   trading day, the verdict silently defaulted to `rename_confirmed`. It is now its own verdict,
   `rename_confirmed_no_overlap`, documented in the module docstring and in section 3, and the three
   rows it covers (`CDAY`, `FBHS`, `JEC`) are named.
4. **The `META` `pit_symbol` claim was wrong** — it is `FB` + pipe + `META`, and the test cited ran
   on a fixture. A new test, `test_F_0_1_2_committed_hourly_universe_applies_the_exclusion_rule`,
   asserts the **committed** file.
5. **Six numbers in this review were wrong**: `IR` (2,581 → 956 shared pre-change days), `PX`
   (710 → 1,080), `BBT` (989 → 990), the symbol map (516 lines → 515 mappings), "37 removals" → 26
   removals over 38 candidate rows, and the pytest warning (`rich` → `websockets.legacy`). Several
   quoted the membership-window count where the pre-change day count belonged.
6. **P-70 asked about `RPC`**, which the `PX` rejection had already removed from the universe, and
   the CSV's `dest_has_1H_raw` had since flipped to `True`. Both corrected.
7. **`DataError` named only a hash prefix**; it now names the snapshot path (`store.py`).
8. **A rejection was keyed on `old_symbol` alone**, so it would silently drop *every* hop for a
   ticker the feed renames twice. It is now scoped by `effective_date`, with
   `test_F_0_1_2_rejection_with_a_date_cuts_only_that_hop`. Latent before (`FI` was the only
   multi-row symbol), but it would have bitten the next feed.
9. **The two percentages were module constants** (CLAUDE.md rule 1). They are now CLI options with
   the documented defaults, printed on every run, and they are what P-68 asks the supervisor to
   confirm.
10. `identical_pct` gained a zero-denominator guard, and the script no longer writes a scratch file
    into the repo root (so the `.gitignore` entry it needed is gone too).

Not changed, and why: `configs/universe/us_equity_daily.csv.meta.json` has a new `built_at` although
the CSV is byte-identical — that is a true record of the rebuild. The daily half of D-383
(`us_equity_daily_excluded.csv`) is **T04i's** work under D-358 and is not started; section 9 says so.

## 9. Deviations

1. **The symbol-changes fetch was pulled into T04f** — planned, answered as **P-61 / D-383**.
2. **`alpaca-symbol-changes --from-raw`** was added so the universe could be rebuilt after the
   rejections without a second network run. Small, tested, and it keeps D-031 intact.
3. **`compare_with_early_closes` and its unit test were deleted** with the YAML. Once the YAML is
   gone nothing can call the helper; its result is archived in the raw report and reproduced in §2.
   No parity or leakage test was touched.
4. **The evidence lives in a committed script**, not only in this review, so the verdicts can be
   re-derived after the next feed.

## 10. Open questions

- **P-68** — confirm the evidence rule (pre-change identity ≥ 99.5 % / < 90 %, the no-overlap branch and the
  membership-window test) and the empty-`new_symbol` rejection marker. Implemented as proposed.
- **P-69** — **`PX → RPC` is the one row where the mechanical verdict and the action disagree.**
  The test says `rename_confirmed` (100 % identical over its 1,080 shared pre-change days), but only
  because `RPC` had *already* taken the ticker: `RPC`'s own series starts 2021-10-21, years before
  the feed's row, while `PX`'s membership is Praxair 2016-01-01 → 2018-10-25. I rejected it, so `PX`
  keeps its row and `RPC` is dropped — but `PX`'s series is then **spliced** (Praxair to 2018, RPC
  from 2021). It should be excluded at ingest; T04i's relisted-ticker list is the right place, and
  I have flagged it there.
- **P-70** — the five rename destinations that had no hourly raw (`BFH`, `DINO`, `FBIN`, `GAP`,
  `TNL`; the sixth, `RPC`, left the universe with the `PX` rejection). The user began downloading
  them on 2026-09-20 17:18, so the accounting CSV already reports `dest_has_1H_raw = True` for all
  five — the folders exist but hold only part of the history. T04h's coverage gate is what confirms
  completeness; P-70 needs only closing.
- `FI`'s own raw series (Expro, 2016 → 2022-12-30) stays in the **daily** universe under `FI`. It is
  a different company from the `FI` of 2023–2025 and belongs on T04i's relisted-ticker list.
