# HANDOFF — Strategy Factory (v10, 2026-09-29)

Read together with `CLAUDE.md`, `docs/decisions/decisions_log.md` (source of truth #0),
`docs/decisions/pending.md`, the spec (`docs/spec/spec_v1.2.md`), the design (`docs/design.md`)
and the feature list (`docs/features.md`).

**The work runs in two streams (D-355, D-357).** Each keeps its own status file; this file is
written **only by stream A, at merges**, from both of them:

- `docs/streams/A.md` — stream A, the main folder: parity (T11 done, **T11b parked**), the
  stream and CI tooling, **T12 (#47)**, **T13 (#51)** and **T14 (#54, #55)**, merged;
  **the next task waits for its task file** (the supervisor and the user settle it first).
- `docs/streams/B.md` — stream B, the worktree `../StrategyFactory_B`: the data layer (complete
  for the MVP). `docs/streams/B_data_state.md` is the data state at the handover into T12 and is
  the authority on data facts; §6 below is folded from it.

> **An open gap, stated first so no one reads it as closed.** T11 merged with the parity
> `to_verify` ledger at **3 of 5**. **D-335** (the stop-first branch and the exact tie of the
> TradingView intrabar path) and **D-336** (exit and re-entry at one open) are **not verified
> against TradingView**. Their targeted reference, **T11b, is parked (D-802)**: the user is not
> exporting for now. Both rules are implemented and unit-tested; the risk is intrabar edge
> cases. D-336 is also the **research default**, so if T11b later shows an engine difference,
> **research results produced in the meantime may need re-running** (identified by their
> `code_version`, D-352). See §8.

## 1. Project in one paragraph

Strategy Factory is an internal framework that runs every trading-strategy idea through one standard, reproducible, auditable funnel: edge discovery → method screening → entry optimization → exit optimization → diagnostics and filters → robustness → statistical validation → report package → analyst review → portfolio → sizing → forward lifecycle. Repository `AmerQuant/strategy-factory`, Python package `strategy_factory`, CLI `sfac`, local path `D:\AmerAndish\Projects\Trade\StrategyFactory\`. Data lives outside the repo in `D:\AmerAndish\Projects\Trade\StrategyFactory_data\` (`raw\` = `SFAC_RAW_ROOT`, immutable; `store\` = `SFAC_DATA_ROOT`, canonical snapshots).

## 2. Roles and workflow

- **User:** product owner and final decision maker. Runs Claude Code, runs every network script in PowerShell (D-031), approves plans and merges.
- **Supervisor (Claude chat, inside the Claude Project connected to this repo):** architect and reviewer. Keeps the decisions log, answers `pending.md`, reviews plans and PRs. After every merge, press **Sync** in the Project so the supervisor sees the current `main`.
- **Claude Code, two streams.** Both follow `docs/STANDING_PROMPT.md`: plan (task files + runbook, assumptions to `pending.md`, stop for "Plan approved"), execute (tests first, acceptance commands, the `acceptance-reviewer` subagent, review file), PR with `gh`; merge only on "Approved. Merge …" with green CI (D-401). Critical tasks (D-402) stop after their review for "Approved".
- **Stream protocol** (`docs/streams/PROTOCOL.md`, `docs/streams/ownership.yaml`, enforced in CI by `sfac streams check`): one folder and one session per stream, each session in its own worktree (D-357 (1)); `a/` and `b/` branch prefixes; streams connect only through `main`; merges one at a time, rebased onto the latest `main`; **no direct messages between streams** — cross-stream notes go in the status files and through the supervisor.
- **ID ranges:** supervisor D-355 … D-359 (used up) and D-600 … D-699 (next free **D-652**); stream A D-360 … D-379 (used up) and **D-800 … D-899** (D-378; next free **D-808**), P-40 … P-59 (used up) and **P-100 … P-149** (D-803; next free **P-124**); stream B D-380 … D-399 (used up) and D-700 … D-799, P-60 … P-99.
- **Path ownership (stream A only):** `HANDOFF.md`, `CLAUDE.md`, `docs/STANDING_PROMPT.md`, `.github/`, `pyproject.toml`, `uv.lock`, the Alembic migrations, `configs/universe.yaml` (D-394), and the T12 paths `components/`, `stages/`, `baseline/`, `metrics/`, `configs/gates/`, `configs/stages/` (D-611, D-612). **Stream B:** `configs/universe/`. Everything else is shared.
- **Only stream B writes `SFAC_DATA_ROOT`**; both read `SFAC_RAW_ROOT` read-only. Each stream has its own test database (`sfac` / `sfac_b`) on the shared Postgres (port 5433, D-305).
- Code, identifiers, commits and repo docs are in English; user-facing reports are Persian (RTL, Vazirmatn).

## 3. Task status

| Task | Content | Status |
|---|---|---|
| T00 … T03, T04a … T04c, T05 … T10b | Data inventory, repo, schema, registry, adapters, quality/split, costs, components, **engine (T08)**, metrics, gates, executor | ✅ merged (batches 1, 2a, 2b) |
| T04d | Futures 1H adapter (TradeStation) | ⏸ not started (P1; blocked on P-02) |
| T04e | Data-layer follow-up | ✅ merged (#4); its open parts were taken over by T04f/T04i |
| T04f | Alpaca reference data: NYSE calendar (D-025), symbol changes (D-024) | ✅ merged (#19) |
| T04i | Phase-B hourly analysis; `daily_session` stays `exchange` (D-395) | ✅ merged (#21) |
| T04g | Alpaca 1D ingest (6,707 of 6,711) | ✅ merged (#24) |
| T04k | Clean daily reference (D-396 … D-706) | ✅ merged (#28, #29) |
| T04h | Alpaca 1H ingest (805 references) | ✅ merged (#30) |
| T04l | Re-used tickers decided by CUSIP (D-705 … D-714) | ✅ merged (#34) |
| T04j | Full Dukascopy h1 ingest | ⏭ deferred (D-387); not needed for stage 1 |
| **T11** | **TradingView parity — critical (D-402)** | ✅ **merged (#26)**: MR 462/462, TF long 519/519, TF short 400/400; ledger **3 of 5** |
| D-368 task | Metrics fixture, pinned examples, weekly randomized Hypothesis job | ✅ merged (#31) |
| **T11b** | Targeted parity reference for D-335 / D-336 | ⏸ **parked (D-802)** — the gap stays open (§8) |
| **T12** | **Stage 1 — edge discovery (s01_edge), critical (D-402)** | ✅ **merged (#47)**: built, run at full scope, reviewed (`docs/reviews/T12_review.md`), approved with two conditions, both met. **14 of 1,944 daily profiles pass against 0 of 1,944 on the calibrated control**, all mean reversion; the **4 hourly passes go forward flagged `unconfirmed` (D-621)** |
| **T14** | **Stage 3 — entry optimisation (s03_entry)** | ✅ **merged (#54 plan, #55 stage)**: planned on 132,408 measured runs, built, piloted, run at full scope, reviewed (`docs/reviews/T14_review.md`), approved. **The control passes 0 of 31**; **6 of 31 pass** — 1D SHW long `mr_connors_rsi` and TXN long `mr_ema_slope_drop` (a boundary pass, plateau 0.100), 1H ARKK, BAC, TSLA ×2 (`unconfirmed`); **no short passes**; the stability threshold decides no verdict (D-651 (1), amended) |
| **T13** | **Stage 2 — method screening (s02_screen)** | ✅ **merged (#51)**: planned on measured grids, built, piloted, run at full scope, reviewed (`docs/reviews/T13_review.md`), approved. **Both controls pass 0 methods** (45 daily and 11 hourly stopped by `method_q_value` alone, D-629); 25 daily and 6 hourly (`unconfirmed`) methods selected; **11 of 14 daily profiles end with fewer than 3** (D-625, D-637) |

## 4. Merged since v6 (PRs #18 … #55)

| PR | Content |
|---|---|
| #18, #22, #23 | D-357 stream protocol, path ownership, the CI guards; every session in its own worktree; D-369 (amendment ≠ duplicate) |
| #25, #27, #40 | second ID ranges: stream B D-700 … D-799 (D-372) and P-80 … P-99 (D-376); **stream A D-800 … D-899 (D-378)** |
| #19, #20, #21, #24, #28, #29, #30, #34, #35, #39 | stream B's data layer (T04f, T04i, T04g, T04k, T04h, T04l) and its handover notes; universe regenerated after T04f (#20) |
| #26 | **T11** — TradingView parity (D-366, D-367, D-370, D-373, D-374, D-375) |
| #31 | **D-368** — metrics fixture; the weekly randomized Hypothesis job |
| #32, #33, #36 | the **T12** task file and D-601 … D-610; **D-611** (stream A implements T12 and owns its paths); **D-612** (`configs/stages/`) |
| #37, #38, #41 | **encodings:** P-52 (`registry/writer.py` could record a dirty checkout as clean on Windows); **D-377** (every text-mode subprocess and file access declares its encoding, enforced by a static guard); **D-379** (`sfac` writes its output as UTF-8, set at the entry point `strategy_factory.cli:run`) |
| #43, #42 | **CI:** **D-801** (`checks` runs once per PR update: push only on `main`); **D-800** (a `windows-fast` job on every PR, fast suite only; 1.5× the old per-PR cost) |
| #45, #46 | stream B: **T04m** Yahoo aux ingest (VIX, index) with the as-of join rules D-717 … D-721; P-93. Stage 1 consumes no aux series, so T12's numbers are unaffected |
| **#47** | **T12 — stage 1, edge discovery** (F-1.1 … F-1.9). Also **D-618** (the matched baseline carries no disaster stop — the original rule manufactured edge from drift), **D-804** (Windows efficiency-mode opt-out: runs were being scheduled onto efficiency cores, 3–4× slower), **D-805** (the stage-config hash is part of the candidate id, so a recalibrated re-run can never overwrite this one), **D-621** (the hourly passes are `unconfirmed`), D-613 … D-620, D-803 |
| **#48** | **D-806** — runner images pinned (`ubuntu-24.04`, `windows-2025`; `ubuntu-latest` would migrate to Ubuntu 26 on 2026-10-19) and the weekly Hypothesis search back to 10× |
| #49, #50 | stream A status and HANDOFF v8; the idle state before T13 |
| #52, #53 | stream A status and HANDOFF v9; four obsolete stream-A branches deleted (each checked merged), two kept |
| **#54** | **T14 plan**: the task file, **D-639 … D-651** (the fine grid, the halves, the after-cost plateau, the control as headline; the plan's answers D-646 … D-651, D-649 amending D-120), the measured plan and runbook |
| **#55** | **T14 — stage 3, entry optimisation** (F-3.1, F-3.3 … F-3.7): `stages/optimize*.py`, `metrics/plateau.py`, `robustness/spp.py`, the `EntryOptimisation` artifact (surfaces as data), `method_run` segments (stage 2 unchanged), `sfac run` for `s03_entry`, `plateau_cells >= 3` in the gates; **D-651 (1) amended** (the plan's stability counts were wrong — polars counts `NaN >= 0.8` as true — and any count behind a decision now uses `gates.engine.count_meeting`, tested); **D-807** (the gate values that shape the surfaces are in the candidate id) |
| **#51** | **T13 — stage 2, method screening** (F-2.1 … F-2.7): 35 stage-2 methods (the spec's library plus the user's MR suite, deduplicated), `metrics/family.py`, `stages/screen.py`, the `MethodScreen` artifact, `PipelineConfig.stage_inputs` (old hashes unchanged), `sfac run` for `s02_screen`; decisions **D-622 … D-638** |

## 5. Decisions to carry forward

- **D-802 — T11b parked; the parity ledger stays at 3 of 5.** See the box at the top and §8.
- **T14 (D-639 … D-651, D-807):** the fine grid is stage 2's good region plus a coarse step,
  choices fixed, coarsened (never Sobol) above 2,000 cells; the plateau is found on half 1
  after costs and must hold in half 2; failed cells count as min(worst, 0); the full trade
  minimum in each half; a plateau needs 3 cells; the reshuffled-returns control heads every stage
  review and a control pass stops the stage (D-644). **Any count behind a decision is computed so
  that NaN cannot pass** (D-651 (1)). Candidate ids hash the stage config (D-805) and the gate
  values that shape the result (D-807).
- **T12 (D-601 … D-612):** the percentile statistic, zero-cost probes with a separate PF, the
  broker universe on 1D and 1H, one profile per (symbol, timeframe, edge type, direction), three
  layers of multiple-testing control, the ESS formula (provisional until T15), baseline seeding,
  no trades stored except for passing profiles, every passing profile to stage 2, data caveats
  in the profile. **D-354** still binds T12's acceptance (engine settings only from
  `PipelineConfig.engine`; stage ids from constants; F-0.7.4 partial until the bit-identical
  rerun through `RunContext`).
- **Platform (D-377, D-379, D-800, D-801):** the work happens on Windows, CI on Ubuntu. Every
  text call declares its encoding; `sfac` output is UTF-8; a Windows job runs the fast suite
  on every PR. After a change to the entry point, **`uv sync`** regenerates the installed `sfac`.
- **Data (stream B):** warnings do not block and do not weight (B_data_state item 1); research
  windows are short-history symbols, never re-joined (D-713); hourly data is raw by decision
  (D-707).
- D-351 (executor budget), D-352 (dirty flag), D-353 (futures parity exemption), D-356
  (broker mapping) are unchanged from v6.

## 6. Data status (folded from `docs/streams/B_data_state.md`, measured 2026-09-22)

| | 1D | 1H |
|---|---|---|
| Alpaca references (one per symbol) | 6,708 | 805 |
| quality `ok` / `warning` / `critical` | 4,217 / 2,491 / 0 | 392 / 413 / 0 |
| **pass D-008 (the candidate universe, before the broker filter of D-603)** | **5,470** | **770** |
| … of which quality `warning` | 1,967 | 400 |
| … of which a T04l research window | 108 | 11 |

- Warnings are mostly `price_spikes` (1D 2,099, 1H 401). **The hourly layer is uncleaned
  (D-707)**: 156 wick flags on 105 symbols and known feed-defect dates.
- Plus 3 Dukascopy 1H pilot references (hash version 1; full h1 is T04j). Yahoo auxiliary series
  are downloaded but not ingested. Neither is needed for stage 1.
- The registry's `data_snapshots` table is empty (P-63); runs pin reference hashes through the
  catalog.
- Quarantine folders `<store>/_quarantine/T04k_D-702_*` and `T04l_D-714_*` hold retired,
  never-referenced snapshots, for the supervisor and the user to empty.
- TradingView parity references: `raw/reference/tradingview/parity/`, byte-identical copies in
  `tests/fixtures/parity/` (D-359).
- Data expansion is frozen until the project is built (D-030).

## 7. Open items

- **T11b / D-335 / D-336** — parked (D-802); the gap is open (§8).
- **P-50** — TradingView fills at the tick-rounded open; deferred with T11b.
- **`configs/universe.yaml`** — stream A regenerates it after any stream-B merge that moves a
  symbol (D-394); done for T04f (#20) and checked again at the #47/#48 merges: **#45/#46 moved no
  traded symbol** (they add `configs/universe/aux_yahoo.csv`, an auxiliary-series list), so no
  regeneration was owed.
- **The repository is public since 2026-09-28.** Turn on **secret scanning and push protection**
  (free for public repositories; it also scans the history retroactively). A full pre-public audit
  of the whole history found **no secret has ever been committed** and no workflow that could
  expose one — the method and the result are in `docs/streams/A.md`. From now on, anything
  committed here is public the moment it is pushed, and making the repository private again would
  not undo that.
- **T15 owes a calibration pass**: the twelve items are listed in `docs/streams/A.md` — from T12
  the magnitude target, TF exits on 1D, the disaster-stop hit rate against D-130's 2 %, one
  duplicated probe, which control is the calibrated null, residual biases, P-104; from T13 the
  11 of 14 daily profiles below three candidates (partly the fixed 5-bar exit, D-637), the
  cleanup of private cross-module helpers (T13 review §8 item 16), and T13's provisional
  family-score constants (D-636); from T14 the stability threshold that decides no verdict
  (D-651 (1)), and the 3-cell grids stage 3 cannot optimise (D-648).
- **`scripts/analysis/T04k_assert_provenance.py`** indexes by hash alone; key it by
  `(source, symbol, timeframe, snapshot_hash)` when next touched (T04l review §6.1.4).
- **D-377 exemptions** — three text calls in stream B's paths lack an encoding (listed in
  `tests/unit/test_F_X_9_explicit_encoding.py`, `ALLOWED`), for stream B to fix.
- **P-68, P-69, P-70** (stream B, T04f) — a handful of symbols; do not affect the pipeline.
- **`a/fix-metrics-fixture-prices`** — an obsolete branch from the D-357 incident; deleting it
  needs the supervisor's word.
- P-01 (edge-type addendum) and P-02 (futures, blocks T04d): decisions log section G.

## 8. Parity status (T11 done, T11b parked)

- **T11 (#26):** three references pass D-011 on committed fixtures, in CI, never skipped. Parity-
  only engine behaviours: D-366 (levels in whole ticks from the fill), D-367 (entry gated on
  flat at the signal close), D-374 (sizing on the tick-rounded signal close). Review:
  `docs/reviews/T11_review.md`.
- **The `to_verify` ledger: 3 of 5.** D-327, D-349 (a) and D-349 (h) are confirmed by
  construction (D-371). **D-335** (only its target-first case occurred) and **D-336** (never
  exercised: both scripts gate on flat) are **unverified against TradingView**. The kernel
  docstring and `test_F_0_3_8_d371_the_to_verify_ledger_does_not_drift` hold this state.
- **T11b is parked (D-802)**, plan in `docs/tasks/T11b_parity_tie_reentry.md` (script, export
  instructions, two predicted SPY tie dates 1994-08-29 and 2004-10-05). **Risk scope:** D-335
  acts only in `tradingview` mode; **D-336 is the research default**. If T11b later shows an
  engine difference, research results produced in the meantime may need re-running. **Any
  stage review until then states that D-335 and D-336 are unverified against TradingView.**
- **P-50** (fill rounding, MR's −26.66 USD) stays open and deferred with T11b.

## 9. Review rules

- A task is judged only against the acceptance criteria of the feature list (and the decisions log); "done" without a proving test is not accepted.
- Parity and leakage tests are never weakened or deleted.
- Every new dependency is listed with its reason in the review; non-trivial library choices are the user's.
- Guard tests are mutation-checked: break the guarded thing on its real shape and watch the test fail.
