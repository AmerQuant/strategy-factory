# T04l review — re-used tickers decided by CUSIP

**Task:** `docs/tasks/T04l_cusip_reuse.md` · **Branch:** `b/T04l-cusip-reuse` from `main` (`d2ebc6a`)
**Features:** F-0.1.2 (re-use boundary, evidence fetch), F-0.1.6 (quality: `known_splice`), F-0.1.8 (derived snapshots, catalog marker)
**Decisions used:** D-008, D-392, D-397, D-398, D-399 (4), D-700, D-702, D-704, **D-705 … D-714**
**Open for the supervisor:** none (P-86 answered as **D-714**).
**Status:** complete. The T04l layer was retired and re-derived once (D-714), asserted clean (0 stale),
and **the 329 derived snapshots are the references** (302 1D, 27 1H). PR open, waiting for
**"Approved. Merge"**.

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/download/alpaca_reference.py` | `fetch_corporate_actions` (every type but `name_change`, no row cap), `check_truncation` (D-711), `latest_action_files`, `action_date` |
| `src/strategy_factory/data/cli_alpaca.py` | `sfac data reference alpaca-corporate-actions` (runs the truncation check in-process) and `alpaca-corporate-actions-check` (offline) |
| `src/strategy_factory/data/cusip_evidence.py` | the CUSIP on each side of a break with **D-712's two rules**; the issuer relation incl. `mixed`; the feed's split records; pure |
| `src/strategy_factory/data/reuse.py` | candidate gaps (D-708), the **known-split test** and the action per boundary (D-709), the plan per symbol (D-713); pure |
| `src/strategy_factory/data/cli_reuse.py` | `sfac data reuse [--symbols] [--set-reference]` |
| `src/strategy_factory/data/catalog.py` | catalog column `splices`, `Splice`, `Catalog.splices()` / `mark_splices()` (a `splice` event per change) |
| `src/strategy_factory/data/quality.py`, `configs/data/quality.yaml` | check `known_splice` (severity from config) |
| `src/strategy_factory/data/cli.py` | `sfac data show` prints the marker |
| `src/strategy_factory/data/split.py` | `DataAccess.splices()` — **one read-only method** beside the split manager (D-402 critical): reads the catalog, touches no bar, split or holdout (test) |
| `src/strategy_factory/data/config.py`, `configs/data/alpaca.yaml` | `reuse.corporate_actions_dir`; `KnownSpliceConfig` |
| `scripts/pilots/T04l_corporate_actions.ps1` | the user's download (D-031); the verdict is the tested command's |
| `scripts/analysis/T04l_feed_scope.py`, `T04l_coverage.py`, `T04l_report.py` | scope check, per-type coverage, the aggregates below |
| `scripts/ingest/T04l_rederive_quarantine.py`, `scripts/analysis/T04l_assert.py` | D-714: retire and quarantine the T04l layer (moved, never deleted, a manifest); assert 0 stale, one config hash, every base and marker |
| tests | `test_F_0_1_2_corporate_actions.py` (14), `test_F_0_1_2_cusip_evidence.py` (12), `test_F_0_1_8_reuse.py` (16), `test_F_0_1_8_splices.py` (6); check-set update in `test_F_0_1_6_quality.py` |

## 2. The evidence (D-710, D-711, D-712)

The user's download (v2, 387,840 rows) passes the tested truncation check (rows per year 24,401 …
47,871, none on a page boundary); market-wide (28,039 symbols; the AVGO, GOOGL, TSLA splits present).

- **Before 2020 there is no evidence, by construction** (mergers from 2019–20, worthless removals 2023,
  dividend CUSIPs blank 2016–18). **38 unsettled boundaries are before 2020 and can never be settled by
  this feed.** A missing row is never read as evidence, at any date.
- **The feed is not point-in-time** (≈ 5 % of rows under a later ticker). D-712's rules, as implemented:
  (1) a CUSIP's rows under a ticker dated more than `rename_window_days` before that CUSIP renamed
  **into** it are dropped; (2) the arriving holder — a rename into the ticker, an `id` row inside the
  window before the resumption (never before the break's start), and any row of a CUSIP renaming in
  **at this break** — counts on the after side; a rename away or a cessation counts on the before side
  **up to and including** the resumption date. `CTRA` is a test in both directions.
- **Relation, by issuer:** the same issuers on both sides → same CUSIP / same issuer; none in common →
  different issuer; some in common and some not → **mixed**, a disagreement, never "same".

## 3. The decisions (`docs/reviews/T04l_decisions.csv`)

317 boundaries on 304 symbols — 221 T04k kept, 96 found only by D-708. Each is judged on the rows
between its neighbouring breaks only.

| action | T04k kept | long gap only | all |
|---|---|---|---|
| **trim** (different issuer) | 25 | 21 | **46** |
| **keep** (same CUSIP/issuer **and no price jump**) | 1 | 1 | **2** (`REED`, `GDEV`) |
| **unsettled** | 195 | 74 | **269** |

Unsettled by reason: after only 118, no CUSIP 94, before only 43, **same issuer with a jump no recorded
split explains 11**, mixed 3 (`BNKD`, `NRGD`, `QH`). **Unadjusted splits: 0** — the known-split test
(below) found no jump that matches a recorded split.

**D-709 change 1, the known-split test** (`T04l_same_issuer.csv`): for a same-CUSIP or same-issuer break,
the close ratio across it is compared with the splits the feed records for those CUSIPs between the two
bars — no jump → keep; a jump matching the recorded factor → the D-397 path; any other jump →
unsettled (`same_issuer_split_unsettled`). The D-399 cross-check runs as a second witness. Of the 13
such breaks, 2 show no jump; **11 jump by amounts no recorded split explains** (`AIM` ×107, `WW` ×160,
`QTI` ×15, `DBGI` ×4.5, `CHK` ×3.8, …) — they are unsettled and marked, never kept.

Named: `CTRA` **trim** (Alpha/Contura `020764106` → Coterra `127097103`), `GORO` **trim** (its old
CUSIP ceases on the day the new one resumes); `MBLY`, `SE`, `SNOW`, `AYA`, `CSRA`, `HAWK` unsettled (no
CUSIP); `PCL`, `Q`, `DOW`, `EMC`, `CIVI` unsettled (after only).

## 4. What each symbol gets (`docs/reviews/T04l_references_moved.csv`)

| timeframe | trim | research window | total |
|---|---|---|---|
| 1D | 46 | 256 | 302 |
| 1H | 4 (`BBBY`, `CTRA`, `INFO`, `LB`) | 23 | 27 |

- **1D** is re-derived **from raw** exactly as T04k derives it — `clean_daily` with every arm, the T04l
  start as the boundary — `derived_from` the raw snapshot; the T04k clean reference it replaces is the
  **base**, named in the notes ("Base snapshot …", looked up by full key), and keeps the full history.
- **1H** is the raw hourly series from the start on, `derived_from` it.
- Each derived snapshot has its log `_reuse/<tf>/<symbol>/<hash>.csv` and provenance JSON (the decision
  of every boundary, the evidence files' hashes, the config hash).
- **Markers:** the base carries `full_history` (its unsettled boundaries, with `break_start`); the derived
  snapshot carries `research_window` naming only the boundary it starts at; the base's quality report
  fails `known_splice` at `warning`; `sfac data show` and `DataAccess.splices()` show it.
  In the store: 512 1D and 46 1H catalog rows carry a marker — one base and one window for each of
  the 256 + 23 research windows.

### D-008: 182 of the 302 daily series fall below the minimum once cut — they were never usable

**182 of the 302 derived daily series are too short for a development / embargo / holdout split
(D-008) once they start at their boundary; 120 can still be split.** They keep 202,726 of their
407,621 bars. `SplitManager` rejects the 182 with `HistoryTooShortError`, so they leave the research
set by the ordinary D-008 path — nobody excludes them by hand.

**This is not a loss (D-713).** Each of those 182 histories runs across a break where the ticker may
belong to two different companies — for 46 of all 302 it is proven, for the rest it cannot be shown
not to be. The long history they appeared to have was never a history of one security; we only
believed it was. **Do not "recover" them** by reading the full-history snapshot, lowering D-008's
minimum for them, or re-joining the halves: the full-history snapshot carries a `full_history` marker
precisely so that a reader of the store sees why it must not be used. If new identity evidence later
proves a break to be one company, `sfac data reuse` restores the full history itself (test) — that is
the only way back.

### References

**All 329 derived snapshots are the references now** (302 1D, 27 1H; `reference_moved` in
`T04l_references_moved.csv`; 329 `set_reference` events noted "T04l re-use"). Every alpaca
`(symbol, timeframe)` still has exactly one reference (6,708 1D, 805 1H). The bases — the full-history
T04k clean or raw snapshots — stay in the store and the catalog (rule 10). Moving a reference affects
only future runs: a run pins the snapshot hashes it read (D-709). Nothing had been run on the old
references (registry `sfac_b` empty, T12 not started).

## 5. Acceptance criteria (task file)

| criterion | proof | result |
|---|---|---|
| coverage table in the review before any rule applied | task file "Update 2026-09-21 (2)" and the full-download section; `T04l_coverage_by_type.csv` | pass |
| a CUSIP change of issuer trims | `test_F_0_1_2_D_709_the_actions`; end to end (REUSE); store: 46 | pass |
| the same CUSIP across a halt keeps | `test_F_0_1_2_D_709_the_same_cusip_across_a_halt_keeps` (no jump); end to end (SAME) | pass |
| one side only keeps and lists | `test_F_0_1_2_D_712_absence_is_never_evidence`, `…_the_arriving_window_never_reaches_before_the_break`; end to end (UNS: marker + window) | pass |
| CUSIP and names disagreeing keeps and lists | `test_F_0_1_2_D_709_the_actions` — both directions (`same_company` + different issuer; `re_use` + same issuer) | pass |
| issuer-prefix reorganisation classified as the rule states | `…_same_issuer_is_a_new_cusip_of_the_same_issuer`, `…_the_known_split_test`, `…_a_split_test_that_cannot_tell_is_never_no_split` | pass |
| derived snapshots: `derived_from`, config hash, boundary, replayable log; previous reference kept | end-to-end tests (replay, raw re-derivation); store: 0 bases removed | pass |
| before/after for `MBLY`, `SE`, `SNOW`, `CTRA` | §3; `T04l_references_moved.csv` | pass |
| 1H follows 1D (D-707, D-708) | end to end (UNS 1H); store: 27 | pass |
| a re-run never derives from its own output; new evidence can undo | `…_set_reference_moves_and_a_rerun_derives_from_the_base`, `…_new_evidence_that_settles_a_break_undoes_the_move` | pass |
| gates green, `sfac streams check` clean | §7 | pass |

## 6. Acceptance review (one round) — findings and fixes

| finding | fix |
|---|---|
| **B1** a split check that cannot tell was taken as "no split" (17 same-issuer breaks kept, jumps up to ×160) | the known-split test (§3); no jump → keep, matching recorded split → D-397 path, anything else → unsettled `same_issuer_split_unsettled`; test |
| **B2** a cessation on the resumption day counted as after (`GORO` read same CUSIP) | cessation and rename away count before up to and including the resumption; test; `GORO` now trims |
| S1 same CUSIP won over a different issuer on the same side (`QH`) | relation `mixed` → unsettled `cusip_mixed`; test |
| S2 the marker lost `break_start` and the planned reason | `Splice.break_start`; reasons `cusip_mixed`, `same_issuer_split_unsettled`, `unadjusted_split` |
| S3 unrecorded rules: hourly dating, 1D from the clean reference, cessation/unsettled as settled | hourly gaps dated by the daily break (§6.1 below, test); **1D now re-derived from raw** (D-713 "exactly as T04k"); B1/B2 |
| `--set-reference` could move to a stale snapshot | refused, noted in the summary; test |
| a re-run could not undo a move | a plan that no longer cuts restores the base and clears its marker; test |
| rule 2 could reach before a short break; rule 1 dropped the arriving holder's own rows; a later holder's rows judged an earlier break | window bounded by the break start; rule 1 spares rows inside the window; rows limited to between neighbouring breaks; tests |
| the window marker listed boundaries already cut away | it names only its own boundary; test |
| `sfac data show` did not print the marker | it does; test |
| duplicated loader in `T04l_feed_scope.py` | uses `latest_action_files` |

Fixing S1 exposed one more of my own: "a CUSIP that renames into the ticker is the arriving holder"
also caught a holder that had renamed in at an **earlier** break (`AACI`'s SPAC shares, 2024), making ten
real re-uses read `mixed`. Restricted to a rename-in at this break; test. Against the first review the
decisions now differ exactly where the fixes intend: 11 same-issuer keep → unsettled, 3 keep → mixed,
`GORO` keep → trim.

### 6.1 Other deviations

1. **D-714 (P-86) — the T04l layer was retired and re-derived once.** The pass ran four times while
   the fixes landed; identical bars keep the first writer's notes (D-392), so 280 current snapshots
   carried an earlier run's notes and 37 were superseded. All **366** T04l snapshots (339 1D, 27 1H;
   none a reference, now or ever) were retired and moved to
   `<store>/_quarantine/T04l_D-714_20260922T080918Z/` (**2,196 files**, `manifest.csv`, nothing deleted;
   left for the supervisor and the user to empty). One re-run; `T04l_assert.py`: **0 stale**, one config
   hash (`eabc6a72917ff7db`), the layer is exactly the 329 snapshots this run wrote, every base and marker
   in place; then `--set-reference`. The general rule — retire and re-run before the first reference of
   **any** derivation pass — is in `RUNBOOK_batch3-data.md`, "Derivation passes".
2. **An hourly gap is dated as the daily break it overlaps** (`PCL`: 1D 2025-08-01, 1H 2025-09-12 — judged
   at the later date the new holder's first rows fell on the before side). Test.
3. **A base is found by its full key** (identical bars share a hash across symbols; found in testing).
4. **Latent weakness in merged T04k code — written finding, not changed.**
   `scripts/analysis/T04k_assert_provenance.py:68` builds `by_hash = {snapshot_hash: row}` over every
   alpaca 1D catalog row and looks rows up by hash alone (lines 80, 106, 116). The store is
   content-addressed per symbol, so **two symbols with identical bars share a hash** — two share classes
   or tickers of one fund with the same prices, or two series that are pure padding. **Evidence today:
   no hash is shared across symbols** — 0 of the 11,084 catalog rows (checked 2026-09-22, after T04l),
   so every result the assertion gave was about the right symbol. **What would break if one ever did:**
   the dict keeps whichever row came last, so the assertion would check symbol A's clean snapshot against
   symbol B's catalog row — its notes, `derived_from` and config hash. That can **fail falsely** (B's notes
   lack A's config hash or arms) or, worse, **pass falsely** (B's row happens to satisfy the checks while
   A's own row is stale). The same shape broke T04l's first `_base` lookup in a test (fixed there by the
   full key). The fix, when that script is next touched, is to key by `(source, symbol, timeframe,
   snapshot_hash)`.
5. The pass re-runs quality on what it touches, so a re-run appends `quality` events (as T04k's does).
6. `PAGE_SIZE` (1,000) and `ISSUER_LEN` (6) are constants: properties of the endpoint and of the CUSIP
   format, not thresholds (rule 1).

## 7. Acceptance commands

Rebased onto `main` `f5522a7` (stream A's #31 D-368 fix and #32 T12 task file).

```
uv run pytest -m "not slow"                            1505 passed, 2 failed (below)
uv run pytest tests/parity tests/leakage tests/oracle  327 passed
uv run pytest -m db                                     21 passed, 0 skipped
uv run ruff check . / ruff format --check .            clean
uv run mypy src                                        clean
uv run sfac streams check --base origin/main           crashes on Windows (below); with PYTHONUTF8=1: ok, ok, ok
```

**The two failures are not this branch's, and CI is not affected.** Both are
`tests/unit/test_F_X_9_stream_guards.py` (`…_streams_check_cli_on_this_branch`,
`…_streams_check_cli_fails_on_a_foreign_path`), and `sfac streams check` fails the same way: stream A's
`core/cli_streams.py:_git` reads `git show` output with `text=True` and no encoding, i.e. the Windows
locale codec (cp1252), and `main`'s own `decisions_log.md` now contains "log₁₀" (D-60x, `₁` = UTF-8
`E2 82 81`; `0x81` is undefined in cp1252). It fails on a plain checkout of `main` on Windows too. With
Python's UTF-8 mode (`PYTHONUTF8=1`, an environment setting, no code change) the guard is clean and those
tests plus `tests/property` pass (79 passed; stream A's D-368 property test now passes). On CI (Ubuntu,
UTF-8) there is nothing to see. **Reported to stream A** (`docs/streams/B.md`); their file, not touched
here. No new dependency.

## 8. For the supervisor

- **"Approved. Merge"** for this PR.
- The quarantine folder `T04l_D-714_20260922T080918Z` to empty when you choose.
- Then T12.
