# T04l review — re-used tickers decided by CUSIP

**Task:** `docs/tasks/T04l_cusip_reuse.md` · **Branch:** `b/T04l-cusip-reuse` from `main` (`d2ebc6a`)
**Features:** F-0.1.2 (re-use boundary, evidence fetch), F-0.1.6 (quality: `known_splice`), F-0.1.8 (derived snapshots, catalog marker)
**Decisions used:** D-008, D-392, D-397, D-398, D-399 (4), D-700, D-702, D-704, **D-705 … D-713**
**Open for the supervisor:** **P-86** (three derived snapshots carry first-run notes — retire and re-derive before they become references?)
**Status:** implemented and run on the store **without `--set-reference`**: every derived snapshot, log, provenance and marker is written; **no reference has moved.** Stopped for the review.

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/download/alpaca_reference.py` | `fetch_corporate_actions` (every type but `name_change`, no row cap), `check_truncation` (D-711), `latest_action_files`, `action_date` |
| `src/strategy_factory/data/cli_alpaca.py` | `sfac data reference alpaca-corporate-actions` (runs the truncation check in-process) and `alpaca-corporate-actions-check` (offline) |
| `src/strategy_factory/data/cusip_evidence.py` | the CUSIP on each side of a break, with **D-712's two re-keying rules**; pure |
| `src/strategy_factory/data/reuse.py` | candidate gaps (D-708), the action per boundary (D-709), the plan per symbol (D-713); pure |
| `src/strategy_factory/data/cli_reuse.py` | `sfac data reuse [--symbols] [--set-reference]`: derives the 1D and 1H snapshots, logs, provenance, markers, quality |
| `src/strategy_factory/data/catalog.py` | catalog column `splices`, `Splice`, `Catalog.splices()` / `mark_splices()` (a `splice` event per change) |
| `src/strategy_factory/data/quality.py`, `configs/data/quality.yaml` | check `known_splice` (severity from config) |
| `src/strategy_factory/data/split.py` | `DataAccess.splices()` — **one read-only method** next to the split manager (D-402 critical): it reads the catalog, touches no bar, split or holdout (test proves no bar is read and the ledger is untouched) |
| `src/strategy_factory/data/config.py`, `configs/data/alpaca.yaml` | `reuse.corporate_actions_dir`; `KnownSpliceConfig` |
| `scripts/pilots/T04l_corporate_actions.ps1` | the user's download (D-031); delegates the truncation verdict to the tested command |
| `scripts/analysis/T04l_feed_scope.py`, `T04l_coverage.py`, `T04l_report.py` | the scope check, the per-type coverage, the review aggregates |
| tests | `test_F_0_1_2_corporate_actions.py` (14), `test_F_0_1_2_cusip_evidence.py` (7), `test_F_0_1_8_reuse.py` (6), `test_F_0_1_8_splices.py` (6), check-set update in `test_F_0_1_6_quality.py` |

## 2. The evidence (D-710, D-711, D-712)

The user's download (v2, 387,840 rows) passes the tested truncation check: rows per year 24,401 …
47,871, none on a page boundary. It is market-wide (28,039 symbols; the AVGO, GOOGL and TSLA splits are
present). Its limits, all in the task file and D-712:

- **Evidence before 2020 is absent by construction.** Mergers start 2019–20, worthless removals 2023;
  dividend CUSIPs are blank for 2016–18. **38 of the 255 unsettled boundaries are before 2020 and can
  never be settled by this feed.** A missing row is never read as evidence, at any date.
- **The feed is not point-in-time:** ≈ 5 % of rows sit under a ticker the security took later. D-712's
  two rules — drop a CUSIP's rows under a ticker dated before that CUSIP renamed into it; count the
  arriving holder's rows within `rename_window_days` on the after side — are what make `CTRA` read a
  different issuer instead of *same CUSIP*. That worked example is a test
  (`test_F_0_1_2_D_712_ctra_reads_a_different_issuer_not_a_clean_series`), and so is the dangerous
  direction without rule 1 (`…_without_rule_1_ctra_would_have_read_same_cusip`).

## 3. The decisions (`docs/reviews/T04l_decisions.csv`)

317 boundaries on 304 symbols — 221 T04k kept, 96 long gaps found only by D-708 (an hourly gap that
overlaps a daily break is that break, dated as the daily series dates it: §6.2).

| action | T04k kept | long gap only | all |
|---|---|---|---|
| **trim** (different issuer) | 24 | 21 | **45** |
| **keep** (same CUSIP 5, same issuer 12; split cross-check: no unadjusted split) | 16 | 1 | **17** |
| **unsettled** | 181 | 74 | **255** — no CUSIP 89, after only 122, before only 44 |

- **D-709 change 1:** all 17 same-CUSIP / same-issuer boundaries went through the known-split
  cross-check (`T04l_same_issuer.csv`); every verdict is `unsettled` — none is an unadjusted split, so
  **the D-397 path is empty**.
- 19 of the 255 unsettled show the old security **ceasing** before the break (a merger or removal); D-709
  does not let that trim alone, and it did not.
- Named: `CTRA` **trim** (Alpha/Contura `020764106` → Coterra `127097103`); `MBLY`, `SE`, `SNOW`, `AYA`,
  `CSRA`, `HAWK` unsettled (no CUSIP); `PCL`, `Q`, `DOW`, `EMC`, `CIVI` unsettled (after only).

## 4. What each symbol gets (`docs/reviews/T04l_references_moved.csv`)

| timeframe | trim | research window | total |
|---|---|---|---|
| 1D | 45 | 242 | 287 |
| 1H | 4 (`BBBY`, `CTRA`, `INFO`, `LB`) | 23 | 27 |

Per derived snapshot: `derived_from` the base (the current reference, or the snapshot a T04l snapshot was
derived from — found by its full key), the notes naming D-705/D-708/D-709/D-712/D-713, the config hash,
the start and every boundary with its decision; a log `_reuse/<tf>/<symbol>/<hash>.csv` (what was cut and
why) and a provenance JSON (evidence file hashes included). Replaying the log — the base's bars from the
start on — reproduces the snapshot (test). **Markers:** 242 + 23 bases carry `full_history`, their
derived snapshots `research_window` (485 1D / 46 1H catalog rows; one extra 1D row is the superseded CA
snapshot of §6.2); every base's quality report now fails `known_splice` at `warning`.

**The cost, and why it is not a loss (D-713).** Of the 287 derived 1D snapshots, **118 can be split and
169 fall below D-008's minimum** once they start at their boundary; they keep 197,997 of 386,072 bars.
**Those 169 were never usable:** their history joined two companies (or may have, and cannot be shown not
to), and we only believed otherwise. A later reader must not try to "recover" them by reading the
full-history snapshot — the marker on it says why.

**References.** None has moved: the pass ran without `--set-reference`. On approval,
`uv run sfac data reuse --set-reference` makes the 314 derived snapshots the references (it re-derives
from the bases, writes nothing new, and moves only references). Moving a reference affects **only future
runs** — a run pins the snapshot hashes it read (D-709); nothing has been run on these (registry `sfac_b`
empty, T12 not started).

## 5. Acceptance criteria (task file)

| criterion | proof | result |
|---|---|---|
| coverage table in the review before any rule applied | task file "Update 2026-09-21 (2)" and the full-download section; `T04l_coverage_by_type.csv` | pass |
| a CUSIP change of issuer trims | `test_F_0_1_2_D_709_the_actions`, end to end `test_F_0_1_8_T04l_decisions_and_derived_snapshots` (REUSE) | pass |
| the same CUSIP across a halt keeps | `test_F_0_1_2_D_709_the_actions`; SAME in the end-to-end test | pass |
| one side only keeps and lists | `test_F_0_1_2_D_712_absence_is_never_evidence`; UNS (marker + research window) | pass |
| CUSIP and names disagreeing keeps and lists | `test_F_0_1_2_D_709_the_actions` (`same_company` + different issuer → unsettled) | pass |
| issuer-prefix reorganisation classified as the rule states | `test_F_0_1_2_D_709_same_issuer_is_a_new_cusip_of_the_same_issuer` + the split cross-check | pass |
| every re-derived snapshot: `derived_from`, config hash, boundary, replayable log; previous reference still in store and catalog | end-to-end test (replay); store: 314 derived, 0 bases removed | pass |
| before/after for `MBLY`, `SE`, `SNOW`, `CTRA` | §3; `T04l_references_moved.csv` | pass |
| 1H follows 1D (D-707/D-708) | end-to-end test (UNS 1H); store: 27 hourly | pass |
| a re-run never derives from its own output | `test_F_0_1_8_T04l_set_reference_moves_and_a_rerun_derives_from_the_base` | pass |
| gates green, `sfac streams check` clean | §7 | pass |

## 6. Deviations and findings

1. **P-86 — three derived snapshots carry first-run notes.** The pass ran twice (§6.2); for `CA` 1H and
   `PCL` 1D/1H the second run's bars were identical, so the store kept the first run's notes (D-392):
   `CA` 1H says "from 2023-12-18" (it starts 2023-12-15 — there is no hourly bar in between), `PCL` lists
   a "2025-09-12 keep" boundary that no longer exists. Detected (`metadata_stale` 3), the provenance JSON
   is current, **none is a reference**. As with D-702, I recommend retiring and quarantining them (and the
   superseded `CA` 1D snapshot) before `--set-reference`, then re-running.
2. **An hourly gap is dated as the daily break it overlaps.** The first run treated `PCL`'s hourly
   resumption (2025-09-12, six weeks after the daily 2025-08-01) as its own break; judged at the later
   date, the new holder's first dividends fell on the before side and it read *same CUSIP, keep*. Fixed
   (`_same_break`, test); it changed one outcome — `CA` now starts 2023-12-15, not 2023-12-18 — and
   left the first run's `CA` 1D snapshot superseded (never a reference).
3. **A T04l snapshot's base is found by its full key.** Found in testing: two symbols with identical bars
   share a content hash, and a hash-only lookup marked the wrong symbol. The real store has no such pair
   today (checked: 0 hashes shared across symbols), but `scripts/analysis/T04k_assert_provenance.py`
   indexes by hash alone too — correct on today's store, latent otherwise.
4. The 1D trim is derived from the **current (T04k clean) reference**, not re-derived from raw: the bars
   after the boundary are the clean bars, so the log is one row (the range cut) and replay is a filter.
   A wick clipped near the boundary used an ATR window that reached across it; the pass does not
   re-clip.
5. The pass re-runs quality on what it touches, so a re-run appends `quality` events (as T04k's does).

## 7. Acceptance commands

```
uv run pytest -m "not slow"                            see PR
uv run pytest tests/parity tests/leakage tests/oracle  327 passed
uv run pytest -m db                                     21 passed, 0 skipped
uv run ruff check . / ruff format --check .            clean
uv run mypy src                                        clean
uv run sfac streams check --base origin/main           ok
```

The fast suite's one failure is stream A's `test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio`
(D-368), untouched and failing on `main` too. No new dependency.

## 8. For the supervisor

- **Approve** the rule as run, and **P-86** (retire the four never-referenced T04l snapshots and re-run
  before the references move).
- Then `sfac data reuse --set-reference`, the PR, and T12.
