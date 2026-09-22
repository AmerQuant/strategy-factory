# HANDOFF — Strategy Factory (v7, 2026-09-22)

Read together with `CLAUDE.md`, `docs/decisions/decisions_log.md` (source of truth #0),
`docs/decisions/pending.md`, the spec (`docs/spec/spec_v1.2.md`), the design (`docs/design.md`)
and the feature list (`docs/features.md`).

**The work runs in two streams (D-355, D-357).** Each keeps its own status file; this file is
written **only by stream A, at merges**, from both of them:

- `docs/streams/A.md` — stream A, the main folder: parity (T11 done, **T11b parked**), the
  stream and CI tooling, and now **T12** (D-611).
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
- **ID ranges:** supervisor D-355 … D-359 (used up) and D-600 … D-699; stream A D-360 … D-379 (used up) and **D-800 … D-899** (D-378), P-40 … P-59; stream B D-380 … D-399 (used up) and D-700 … D-799, P-60 … P-99.
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
| **T12** | **Stage 1 — edge discovery (s01_edge), critical (D-402)** | ⏭ **stream A, planning next** (D-611); task file `docs/tasks/T12_stage1_edge_discovery.md`, decisions D-601 … D-610 |
| T13 … T15 | Stages 2–3, orchestrator/CLI/reports/self-tests | later |

## 4. Merged since v6 (PRs #18 … #43)

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

## 5. Decisions to carry forward

- **D-802 — T11b parked; the parity ledger stays at 3 of 5.** See the box at the top and §8.
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
  symbol (D-394); checked as T12's first step (B_data_state item 4).
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
