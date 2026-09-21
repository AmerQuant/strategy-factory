# T04l review — re-used tickers decided by CUSIP

**Task:** `docs/tasks/T04l_cusip_reuse.md` · **Branch:** `b/T04l-cusip-reuse` from `main` (`d2ebc6a`)
**Features:** F-0.1.2 (re-use boundary, evidence fetch), F-0.1.6 (quality: `known_splice`), F-0.1.8 (derived snapshots, catalog marker)
**Decisions used:** D-008, D-392, D-397, D-398, D-399 (4), D-700, D-702, D-704, **D-705 … D-713**
**Open for the supervisor:** **P-86** (retire and re-derive the 366 never-referenced T04l snapshots before the references move)
**Status:** implemented; acceptance review run and every finding fixed; the pass has run on the store **without `--set-reference`** — **no reference has moved**. Stopped for the review.

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

**The cost, and why it is not a loss (D-713).** Of the 302 derived 1D snapshots, **120 can be split and
182 fall below D-008's minimum** once they start at their boundary (202,726 of 407,621 bars kept). **Those
182 were never usable:** their history joined two companies — or may have, and cannot be shown not to —
and we only believed otherwise. A later reader must not try to "recover" them from the full-history
snapshot; its marker says why.

**References: none has moved.** On approval (and P-86), `sfac data reuse --set-reference` makes the
derived snapshots the references. Moving a reference affects only future runs — a run pins the snapshot
hashes it read (D-709); nothing has been run on these (registry `sfac_b` empty, T12 not started). New
evidence that settles a break later puts the base back as the reference and clears its marker (test).

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

1. **P-86 — 280 current derived snapshots carry an earlier run's notes, 37 more are superseded.** The pass
   ran four times as the fixes landed; identical bars return the first writer's notes (D-392). The pass now
   refuses to make such a snapshot a reference. None of the 366 T04l snapshots has ever been a reference.
   Recommendation: retire and quarantine all 366 with the D-702 tools, re-run, assert 0 stale, then
   `--set-reference`.
2. **An hourly gap is dated as the daily break it overlaps** (`PCL`: 1D 2025-08-01, 1H 2025-09-12 — judged
   at the later date the new holder's first rows fell on the before side). Test.
3. **A base is found by its full key** (identical bars share a hash across symbols; found in testing).
   `scripts/analysis/T04k_assert_provenance.py` indexes by hash alone — correct on today's store (0 hashes
   shared across symbols), latent otherwise.
4. The pass re-runs quality on what it touches, so a re-run appends `quality` events (as T04k's does).
5. `PAGE_SIZE` (1,000) and `ISSUER_LEN` (6) are constants: properties of the endpoint and of the CUSIP
   format, not thresholds (rule 1).

## 7. Acceptance commands

```
uv run pytest -m "not slow"                            1500 passed, 1 failed (below)
uv run pytest tests/parity tests/leakage tests/oracle  327 passed
uv run pytest -m db                                     21 passed, 0 skipped
uv run ruff check . / ruff format --check .            clean
uv run mypy src                                        clean
uv run sfac streams check --base origin/main           ok
```

The fast suite's one failure is stream A's `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio`
(D-368), untouched. No new dependency.

## 8. For the supervisor

- **Approve** T04l as run, and **P-86** (retire the 366 never-referenced T04l snapshots, re-run, assert 0
  stale).
- Then `sfac data reuse --set-reference`, the PR, and T12.
