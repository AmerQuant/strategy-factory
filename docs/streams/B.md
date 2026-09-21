# Stream B — worktree `StrategyFactory_B`

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory_B` (a git worktree of the same
repository, created with `git worktree add ../StrategyFactory_B -b docs/batch3-data main`).
Governed by **D-355**. This file is stream B's status; it is **not** `HANDOFF.md` — stream A
folds it into `HANDOFF.md` at merges.

## Scope

1. **Data**, in this order:
   - ingest the completed Alpaca **1D** and **1H** downloads into the snapshot store;
   - generate the **NYSE session calendar** `configs/calendars/nyse_sessions.csv` from the
     Alpaca calendar fetch (**D-025**);
   - the **T04e phase-B pilot** analysis, which was waiting for the hourly download.
2. Then **T12 — stages 1–3**, whose acceptance carries **D-354**: stage code takes the engine
   settings only from `PipelineConfig.engine` (`DEFAULT_ENGINE_CONFIG` forbidden in stage code,
   grep test); a stage passes its stage id from its own constant (grep test: the literal
   `"s06_robust"` only in `data/split.py` and the stage-6 module); F-0.7.4 stays partial until
   the bit-identical rerun through `RunContext` is proven.

## ID ranges (D-355)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 (used up), **D-600 … D-699** | — |
| stream A | D-360 … D-379 | P-40 … P-59 |
| **stream B (this one)** | D-380 … D-399 (**used up**), **D-700 … D-799** | **P-60 … P-79** |

Next free here: **D-714**, **P-87**. Pending range **P-80 … P-99** granted 2026-09-21 and in `ownership.yaml` (stream A, D-376, PR #27). The range **D-700 … D-799** is merged into
`docs/streams/ownership.yaml` (stream A, **D-372**, PR #25) and the guard accepts it; **D-700** is
the first row (the supervisor's amendment of D-399).

## Rules that bind this stream (D-355)

- **Database:** this worktree has its **own `.env`** pointing at **`sfac_b`** on the shared
  Postgres server (port 5433, D-305); the schema is migrated to head. Stream A keeps `sfac`.
  `docker compose` is owned by stream A — do not start or stop containers from here.
- **Data root:** **stream B is the only writer of `SFAC_DATA_ROOT`.** Snapshots are immutable:
  never overwrite one, always write a new one (CLAUDE.md rule 10). `SFAC_RAW_ROOT` is
  **read-only** for both streams (D-028, CLAUDE.md rule 11).
- **Network runs are the user's** (D-031): Claude Code writes the PowerShell script, the user
  runs it.
- **Docs:** decision and pending edits go on stream B's own docs branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**.
  `HANDOFF.md` is never edited here.
- **Benchmarks** run only when stream A is idle.
- Every branch **rebases onto `main`** before its merge. D-401 and D-402 are unchanged.

## Status (2026-09-21, amended the same day: T04i merged, T04g done)

Batch 3-data was **approved on 2026-09-21**. Plan on `docs/batch3-data`:
`docs/tasks/RUNBOOK_batch3-data.md` and `T04f`, `T04h`, `T04i`, `T04g`, `T04k`; decisions
**D-380 … D-398** (section I of the log); **P-60 … P-67, P-71 … P-73 closed**, **P-68 … P-70** and
**P-74** open. Task branches use the `b/` prefix (D-357). Order (D-358, D-396):
**T04f ✅ → T04i ✅ → T04g ✅ → T04k ⏳ → T04h**. T04h stays blocked until the 1H download is complete
(D-386).

**Current position:** **T04l implemented and run without `--set-reference`; stopped for the review**
— branch `b/T04l-cusip-reuse`, pushed, no PR. Review: `docs/reviews/T04l_review.md`.
Decisions this round: **D-712** (the feed is not point-in-time; two re-keying rules, the CTRA example;
no evidence before 2020 by construction), **D-713** (P-85: a derived snapshot from the last unsettled
boundary becomes the reference — not a read-side rule; the 169 1D series too short after it were never
usable).

Result on the store: 317 boundaries on 304 symbols — **45 trims, 17 kept** (no unadjusted split),
**255 unsettled**; derived 287 1D (45 trim, 242 research window) and 27 1H (4 trim, 23 window); bases
marked `full_history`, windows `research_window`; **no reference moved**.

**Blocked on the supervisor:** approval of T04l, and **P-86** — three derived snapshots (`CA` 1H,
`PCL` 1D/1H) carry first-run notes after the hourly-date fix; recommendation: retire and quarantine
them (plus the superseded `CA` 1D) with the D-702 tools, re-run, then `--set-reference`.

**For stream A:** when T04l's references move (after approval), 314 references (287 1D, 27 1H) change
to derived snapshots, listed in `docs/reviews/T04l_references_moved.csv`; stage 1 can read the marker
through `DataAccess.splices()` (a read-only method added to `data/split.py`). Nothing is computed from
them yet.

**What a fresh session needs to know about T04k:**
- **D-700** (supervisor, amends D-399): the re-use discriminator is the **company name** in
  `reference/alpaca/alpaca_assets_2026-09-20.v2.csv`, linked across the break by the raw
  `NAME_CHANGE` feed (`reference/alpaca/corporate_actions/name_changes_20260920.json`, 3,650 rows).
  D-399's cross-check half was withdrawn for re-use because MS-US-1D is ticker-keyed and splices a
  re-used ticker identically.
- Code: `data/clean_daily.py` (four arms), `data/crosscheck.py`, `data/name_evidence.py`,
  `data/cli_clean.py` (`sfac data clean`), two checks in `data/quality.py`.
- Store outputs: `<SFAC_DATA_ROOT>/_clean/clean_daily_summary.csv`, `short_hourly_days.csv`, and
  `_clean/<symbol>/<clean hash>.csv|json` per clean snapshot. The clean pass reads the **raw**
  snapshot (`derived_from` empty), never the reference.
- **References:** the 3,239 clean snapshots (set 2026-09-21); the 3,469 unchanged symbols keep their raw one.
- Earlier passes' derived snapshots and first-layout flat logs were retired and moved to
  `_quarantine/` (D-702); the catalog holds only the current 3,239 derived 1D snapshots.

| item | state |
|---|---|
| worktree | on `b/T04k-clean-daily`; `uv sync` done |
| database | `sfac_b` created, `sfac db upgrade` → `0001_initial`, `pytest -m db` 15 passed, 0 skipped |
| batch 3-data plan | **approved** 2026-09-21; order changed by **D-358** to T04f → T04i → T04g → T04h |
| T04f | **done**, PR [#19](https://github.com/AmerQuant/strategy-factory/pull/19) — calendar (2,765 sessions, 0 differences vs the YAML, which is deleted), symbol changes with the D-383 exclusion rule, hourly universe 827 → 806, material-metadata guard. Review: `docs/reviews/T04f_review.md`. P-68 … P-70 remain open but do not block |
| Alpaca **1D** raw | **complete**: 6,711 symbols × 11 years (2016–2026); 3 symbols returned no bars (`BHGE`, `FBHS`, `JEC`) |
| Alpaca **1H** raw | ✅ **complete** (verified 2026-09-21). All **806** hourly universe symbols have a file for every year 2016 … 2026 — **0 missing symbol-years of 8,866** — and the final pass without `--end` covers 2026. `CCE` has **0 bars in all eleven years** → `no_data` in T04h. **D-386's coverage gate is satisfied; T04h is unblocked.** |
| Alpaca 1D / 1H ingest | **1D done** (T04g); **1H done** (T04h, 805 references, PR open) |
| NYSE calendar (D-025) | **done in T04f** (PR #19): `configs/calendars/nyse_sessions.csv`, 2,765 sessions, 0 differences against the deleted `nyse_early_closes.yaml` (D-393); `configs/universe/symbol_changes.csv` written from the 42-row `NAME_CHANGE` feed |
| T04e phase-B pilot | **hourly part closed by T04i** (D-395). The Yahoo part (first/last dates, `^TNX` scale) and the Dukascopy v1→v2 re-hash stay open — see the runbook's "Deferred" |
| snapshot store | **6,710 snapshots**: 6,707 Alpaca 1D (`hash_version = 2`, `session = exchange`, all read-only, one reference each) + the 3 Dukascopy Q1-2024 pilots, which are still `hash_version = 1` (the T04e v1→v2 re-hash is deferred to T04j) |
| T04i | **merged** — PR [#21](https://github.com/AmerQuant/strategy-factory/pull/21). **D-395** (D-033: `daily_session` stays `exchange`), **D-396** (P-71 → the new task **T04k**), **D-397** (P-72 → `--refresh`), **D-398** (P-73: a frozen stretch is removed whatever caused it; a re-used ticker with an identifiable boundary is **trimmed, not excluded**). Findings: **17,648** unsupported daily extremes classified; **AVGO's 10:1 split of 2024-07-15 unapplied in both timeframes**; the re-swept relisting artefact has **797 symbols — 280 trimmed to a boundary, 517 padding-only, 0 exclusions**, 11 of them Moneta targets, all kept (D-388). **P-74** raised (blocks T04k's trims, not T04g). Review: `docs/reviews/T04i_review.md` |
| T04k | ⏸ **approved; PR open, stopped for "Approved. Merge"** — `b/T04k-clean-daily`. 3,239 clean snapshots derived **and set as references**; the 280 re-use candidates: 59 trimmed, 221 kept (T04l). Review: `docs/reviews/T04k_review.md`. Decisions D-396, D-398, D-399, **D-700 … D-706**; nothing open (P-80 answered; the guard waits on stream A's P-8x range) |
| T04g | ✅ **merged** — PR [#24](https://github.com/AmerQuant/strategy-factory/pull/24). **6,707 of 6,711** daily symbols ingested in **16.8 min** (27 chunks of 250, 0.35 GB); `no_data` `BHGE` `FBHS` `JEC`; **`AVGO` not ingested** — D-397 fired on its unadjusted 2024-07-15 split and the run continued; **0 failed**. Quality: 4,002 ok, 2,705 warning, **0 critical**, `missing_bars` and `session_violations` executed for all. Catalog integrity and idempotence verified. Review: `docs/reviews/T04g_review.md` |
| T04h | ✅ **merged** — PR [#30](https://github.com/AmerQuant/strategy-factory/pull/30). 805 1H references; `docs/reviews/T04h_review.md`; P-81 → D-707, P-82 → D-708 |
| T04l | ⏸ **stopped for the review** — `b/T04l-cusip-reuse`; run without `--set-reference`: 45 trims, 255 unsettled (research windows), 17 kept; P-86 open |
| T12 | not started |

## ACTION FOR STREAM A — regenerate `configs/universe.yaml` (D-394)

**T04f is merged into `main` (PR #19, 2026-09-21).** It changed
`configs/universe/us_equity_hourly.csv` (827 → 806 rows, new `pit_symbol` column) and added
`configs/universe/symbol_changes.csv` and the rejections in `symbol_changes_manual.csv`.
`configs/universe.yaml` is stream A's file and was **deliberately not regenerated** by stream B,
so it is now **stale**: it still lists the 26 removed tickers (`ABC` is the visible one, with
`timeframes: [1D, 1H]`) and lacks the 5 added ones.

Stream A: run `uv run sfac universe generate` and commit the result. Until then
`sfac universe validate` and anything reading the registry see the old symbol set; a validate
failure caused only by this staleness is expected, not a defect.

## Symbols for stream A (D-394)

`configs/universe/` is stream B's; **`configs/universe.yaml` is stream A's and is not regenerated
here**. Every symbol a stream-B rule adds to or removes from `configs/universe/*.csv` is listed
below so stream A can run `sfac universe generate` after the merge. Until then
`configs/universe.yaml` is knowingly stale.

The feed arrived on 2026-09-20 (42 `NAME_CHANGE` rows). Per-symbol evidence:
`docs/reviews/T04f_symbol_changes_accounting.csv`; regenerate with
`uv run python scripts/analysis/T04f_symbol_change_evidence.py`.

`configs/universe/us_equity_hourly.csv`: **827 → 806** after the D-383 exclusion rule.
The daily universe is unchanged at 6,711 rows.

| change | count | symbols |
|---|---|---|
| **removed** (confirmed rename; the destination carries `pit_symbol`) | 26 | `ABC ADS ANTM BK BLL CDAY CHK CTL FB FBHS FI FLT GPS HCP HFC JEC MMC NLOK PEAK PKI RE SATS UTX WLTW WRK WYND` |
| **added** (rename destinations) | 5 | `BFH DINO FBIN GAP TNL` — the user began their hourly download 2026-09-20 17:18 (P-70) |
| kept although the feed renames them (different company) | 11 | `BBBY BBT CBS COG EQR IR LLL MNK PX VIAC XL` |

`EQR` and `IR` are Moneta targets kept under D-388; `FISV` (broker `FI`, D-356) stays because the
chain `FISV→FI→FISV` resolves back to it.

## The 1H re-run (2026-09-21) — two findings

The user confirmed the hourly download complete, including a pass without `--end`. Coverage was
re-verified (above) and the T04i sweeps were regenerated:

1. **The breach evidence grew and D-395 held.** 826 symbols, **1,956,214** compared days,
   **18,580** breach days (0.95 %) against 17,648 (0.982 %) on the incomplete set. More hourly data
   only ever adds breaches, so `daily_session = exchange` is now demonstrated rather than argued.
2. **`incomplete_hourly_day` is a feed defect, not a download artefact — T04i predicted the
   opposite.** The class barely moved (2,896 → **3,017**) although every symbol-year is now
   present, and its median is still **1 hourly bar against 7 expected**, over **665 symbols and 784
   dates** (2021-04-19: 438 symbols, 2021-10-25: 401, 2022-03-08: 347). T04k must keep treating
   such a day as "not evidence", never as a defect of the daily bar.

Also closed: the two 1H `no_data_on_split_date` rows (`GOOGL` 2022-07-18, `TSLA` 2022-08-25) now
come back **`adjusted`**, so the 1H known-split table matches the 1D one and **T04h inherits no
open split question**. `AVGO` is still `unadjusted` in **both** timeframes — the refresh below is
still needed.

## FOR STREAM A — one request and two notes from T04g

1. **Stream B's new decision range `D-700 … D-799` is with stream A** (asked 2026-09-21).
   Stream A is confirming the grant with the supervisor before widening
   `docs/streams/ownership.yaml`; stream B does not touch that file. Until it lands
   `sfac streams check` rejects any `D-7xx` row, so **stream B is holding all new decisions** —
   nothing else of stream B's is blocked on it.
2. **The brittle `HEAD~1` assumption in `test_F_X_9_d369_removed_rows_reads_real_git_output` is
   resolved by stream A's PR #23** — the test now builds a throw-away repository in `tmp_path`, so
   it says the same thing on every branch. Stream B had edited the range on
   `b/T04g-alpaca-daily-ingest` before #23 existed; **that edit is dropped**, the branch is rebased
   onto `48ba1ac` and takes main's file wholesale. The finding is kept here only as the record of
   what happened.
3. **Two independent fixes to the same stream-A file happened once and must not happen again.**
   While T04g ran, answering P-74 tripped `sfac streams check` with "P-74: duplicate id"; stream B
   implemented the `removed_rows` exemption, then found stream A had already merged exactly that as
   **D-369** (PR #22). Stream B reverted. This is the collision `D-357` exists to prevent, and the
   rule stream B now follows without exception: **a stream-A file is reported here and waited on,
   never edited.** `src/strategy_factory/core/streams.py`, `cli_streams.py` and
   `tests/unit/test_F_X_9_stream_guards.py` carry **only** stream A's code.
4. **Answered by stream A (2026-09-21), recorded here so a fresh session does not re-open them:**
   the metrics property failure `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio` is
   stream A's **P-44**, answered as **D-368**: `tests/fixtures/metrics_runs.py` is wrong and is
   fixed by scaling **`qty`** rather than `entry_price`, so prices stay physical and the invariant
   is untouched; D-368 also pins any falsifying example as an explicit `@example` (because
   `.hypothesis/` is git-ignored and the per-PR job is derandomized, so CI finds it only by
   chance), keeps the per-PR job derandomized and adds a weekly randomized job that reports without
   gating. It is queued as its own task after T11. **Stream B never touches that file.** Stream A's
   **D-371** (on `a/T11-parity`, unmerged) closes P-45 and touches nothing of stream B's.
5. **`configs/universe.yaml` needs no regeneration for T04i or T04g.** No symbol was added to or
   removed from `configs/universe/*.csv` by either task; the new file
   `configs/universe/us_equity_daily_excluded.csv` is **empty** (D-398). The outstanding
   regeneration is still the T04f one below.

## For the user — one network run, before T04g

**AVGO's 10:1 split of 2024-07-15 is not applied** in either timeframe (unadjusted from 2016 to
2024-07-12; see `docs/reviews/T04i_review.md` §4 and §6b). **T04g confirmed it against the real
feed and left AVGO out of the store** (D-397), so it is missing from the daily universe until this
runs. From this worktree:

```
uv run sfac data download alpaca --timeframe 1D --symbols AVGO --start 2016-01-01 --end 2024-12-31 --refresh
uv run sfac data download alpaca --timeframe 1H --symbols AVGO --start 2016-01-01 --end 2024-12-31 --refresh
```

`--refresh` (D-397) writes a new version file beside each old one; nothing is overwritten.

**No other symbol needs a refresh** on today's evidence: 10 of the 11 known splits are `adjusted`,
the two 1H `no_data_on_split_date` rows (`GOOGL` 2022-07-18, `TSLA` 2022-08-25) were the download
gap and only need the check re-run in T04h, and the 29 `reverse_split_suspect` rows of
`docs/reviews/T04i_relisting_verdicts.csv` are decided by the MS-US-1D cross-check first
(**P-74**), not by a download.

**The hourly download is still running.** Counted at 2026-09-20 19:18 local: 2016–2019 832 of 832
symbols, 2020 829, 2021 806, 2022 806, **2023 787**, 2024–2026 827. 2023 is the only short year
(it was 237 at the T04i sweep). When the user confirms it is complete, the breach counts in
`docs/reviews/T04i_review.md` §3 are regenerated with
`uv run python scripts/analysis/T04i_daily_session.py` — the review keeps its run timestamp until
then. More hourly data can only add breach days, so D-395 cannot be overturned by it.

## For stream A

- **D-398 (supervisor, closing P-73) changes what happens to a re-used ticker: it is trimmed, not
  excluded.** Any frozen stretch — identical close **and zero true range**, ≥ 10 sessions
  (`relisting.frozen_min_sessions` in `configs/data/alpaca.yaml`) — is removed whatever caused it;
  where the re-use boundary is identifiable the series is kept **from that boundary onward**;
  leading pre-listing padding is trimmed and the symbol stays; only an unidentifiable boundary
  excludes. A symbol whose remaining history is then too short for a split fails `SplitManager`
  with `HistoryTooShortError` (D-008) and drops out that way — it is never hand-excluded.
- **D-388, T04i: eleven affected symbols are Moneta mapping targets and every one is KEPT.**
  The re-sweep over all 6,711 daily symbols (`docs/reviews/T04i_relisting_verdicts.csv`, column
  `moneta_target`) gives:

  | symbol | verdict | boundary | dropped → kept bars | why it is kept |
  |---|---|---|---|---|
  | `MBLY` | trim | 2022-10-26 | 1,716 → 977 | Mobileye N.V. acquired 2017; Mobileye Global re-listed Oct 2022 |
  | `SNOW` | trim | 2020-09-16 | 1,006 → 1,509 | Snowflake IPO Sept 2020 |
  | `SE` | trim | 2017-10-20 | 454 → 2,239 | Spectra Energy merged 2017; Sea Limited listed Oct 2017 |
  | `CTRA` | trim | 2021-10-04 | 728 → 1,152 | Contura → AMR; Coterra took `CTRA` Oct 2021 |
  | `MARA` | trim | 2017-10-30 | 252 → 2,233 | same company, a long halt |
  | `GRAB` | trim | 2020-12-01 | 570 → 1,456 | leading pre-listing padding |
  | `DOW` | padding cut | — | 396 frozen bars → 2,297 | pre-spin-off padding, no level break |
  | `CHPT` `DKNG` `HYLN` `VFS` | padding cut | — | 10–19 frozen bars each | short interior pads |

  All eleven are live and broker-tradable and stay in the universe with a shorter, honest history.
  The trimming itself is **T04k**-shaped work. Nothing under `configs/costs/` was touched.
- **No universe symbol is added or removed by T04i.** `configs/universe/us_equity_daily_excluded.csv`
  is written and **empty**, so stream A's `configs/universe.yaml` needs no change from this task —
  the T04f regeneration listed below is still the outstanding one.

- **D-388 (broker mapping boundary), re-run against the real feed on 2026-09-20.** Two Moneta
  research targets are removed by the raw builder output and are **kept** under D-388:
  - **`EQR`** (broker `EQR`, override "same company"): the feed has `EQR → VMRK` 2026-08-18, but
    `VMRK` has **no daily raw data**, is not in the daily universe and is not in the map, while
    `EQR` runs continuously 2016-01-04 → 2026-08-17.
  - **`IR`** (broker `IR`, `ticker_exact`): the feed has `IR → TT` 2020-03-02, but `IR` and `TT`
    are **0 % identical over their 956 shared pre-change days** and both run to 2026-09-18 — two different live
    companies (Ingersoll Rand Inc. kept the ticker when Ingersoll-Rand plc became Trane).
  - Surviving targets that are rename destinations need no action: `COR`, `LUMN`, `META`, `RTX`,
    `MRSH` (broker `MMC`), `BNY` (broker `BK`), `TFC`, `FISV` (broker `FI`).
  - **`GAP`** (broker `GPS`) is a Moneta target that is now an hourly universe row **without 1H raw
    data** — see P-70.
  - **Nothing under `configs/costs/` was modified.**
- **`HANDOFF.md`** still says "Alpaca 1H (827 symbols) — downloading" and lists batch 2b as next;
  the 1H coverage table above is the current fact for the data-status section.
