# HANDOFF — Strategy Factory (v3)

Read together with `CLAUDE.md`, `docs/decisions/decisions_log.md` (source of truth #0), the spec (`docs/spec/spec_v1.2.md`), the design (`docs/design.md`) and the feature list (`docs/features.md`).

## 1. Project in one paragraph

Strategy Factory is an internal framework that runs every trading-strategy idea through one standard, reproducible, auditable funnel: edge discovery → method screening → entry optimization → exit optimization → diagnostics and filters → robustness → statistical validation → report package → analyst review → portfolio → sizing → forward lifecycle. Repository `AmerQuant/strategy-factory`, Python package `strategy_factory`, CLI `sfac`, local path `D:\AmerAndish\Projects\Trade\StrategyFactory\`. Data lives outside the repo in `D:\AmerAndish\Projects\Trade\StrategyFactory_data\` (`raw\` = `SFAC_RAW_ROOT`, immutable; `store\` = `SFAC_DATA_ROOT`, canonical snapshots).

## 2. Roles and workflow

- **User:** product owner and final decision maker. Runs Claude Code, runs every network script in PowerShell (D-031), approves plans and merges.
- **Supervisor (Claude chat, inside the Claude Project connected to this repo):** architect and reviewer. Keeps the decisions log, answers `docs/decisions/pending.md`, reviews plans and PRs against the acceptance criteria. After every merge, press **Sync** in the Project so the supervisor sees the current `main`.
- **Claude Code:** plans and implements batches with the standing prompt (`docs/STANDING_PROMPT.md`):
  1. **Phase 1 — plan:** task files + runbook on branch `docs/<batch>`; assumptions go to `pending.md`; stop.
  2. **Phase 2 — execute**, after "Plan approved": tests first, implementation, acceptance commands, the `acceptance-reviewer` subagent (`.claude/agents/`), review file, commit. Critical tasks (D-402) stop after their review until "Approved".
  3. **End:** PR(s) with `gh` (body = reviews), update this file, batch report. Merge only on "Approved. Merge …" with green CI (D-401).
- Code, identifiers, commits and repo docs are in English; user-facing reports are Persian (RTL, Vazirmatn).

## 3. Task status

| Task | Content | Status |
|---|---|---|
| T00 | Data inventory | ✅ merged (#2) |
| T00b | Raw store organization (byte copies) | ✅ merged (batch 1, #3) |
| T01 | Repo setup, CI | ✅ merged (#1) |
| T02 | Schema, snapshot store, catalog | ✅ merged (batch 1, #3) |
| T03 | Registry (PostgreSQL, Alembic) | ✅ merged (#5) |
| T04a | Alpaca download + adapter | ✅ merged (batch 1, #3) |
| T04b | Dukascopy download + adapter | ✅ merged (batch 1, #3) |
| T04c | Yahoo aux series | ✅ merged (#3) |
| T04d | Futures 1H adapter (TradeStation) | ⏸ not started (P1; blocked on P-02) |
| T04e | Data-layer follow-up (hash v2, calendar, renames, pilots) | ✅ merged (#4) — **phase-B pilot analysis pending the Alpaca hourly download** |
| T05 | Data quality, resampling, split manager | ✅ merged (batch 2a, #7) |
| T06 | Cost model (placeholder profiles) | ✅ merged (batch 2a, #7) |
| T07 | Components and indicators | ✅ merged (#6) |
| T08 | Engine | ⏭ next batch (2b), **critical** |
| T09 | Metrics and result containers | ✅ merged (#8) |
| T10a | Gate engine, pipeline config, universe | ✅ merged (batch 2a, #7) |
| T06b, T10b | Moneta costs; executor + metric-name registry | ⏭ next batch (2b) |
| T11 … T15 | Parity, stages 1–3, orchestrator/CLI/reports/self-tests | later |

## 4. Data status

| Source | Status |
|---|---|
| Alpaca 1D (6,711 symbols, SIP, split-adjusted) | downloaded, **not ingested** yet |
| Alpaca 1H (827 symbols) | **downloading** (user) |
| Dukascopy h1 bid/ask (29 instruments, from 2010) | **downloading** (user); only the Q1-2024 pilot snapshots are in the catalog |
| Yahoo aux (7 series) | downloaded |
| NYSE calendar (`configs/calendars/nyse_sessions.csv`) | to be generated from the Alpaca calendar fetch (D-025) |
| Moneta broker spec | `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` (read-only, manifest next to it, not in git) |

Data expansion is frozen until the project is built (D-030).

## 5. Open items

- **P-04 — parity reference exports:** TradingView trade lists and OHLC for the SPX500 daily MR strategy and one 1H TF strategy. **Remind the user before T11.**
- P-01 (edge-type addendum), P-02 (futures) and P-03 (broker costs; addressed by T06b) are in the decisions log, section G.
- Open questions from the batch-2a reviews (`docs/reviews/T05|T06|T10a_review.md`) not yet answered in the log.

## 6. Next batch: 2b

- **T06b — Moneta cost profiles** from the broker spec (D-520 … D-526; D-521: commission 3 USD per side). Broker ↔ research symbol mapping with manual overrides. Universe flag `broker_symbol`; the default candidate universe = broker-tradable symbols (D-524).
- **T08 — Engine — CRITICAL (D-402).** The T09 containers (`TradeLog`, `EquityCurve`, `RunResult`) are its output contract. Conventions D-001 … D-004; D-300 intrabar exits (`exit_idx == entry_idx` only for intrabar exits); D-301 `n_closed_trades` returned by the grid kernel; D-307 non-USD quote conversion; D-061 futures sized in contracts × point value. Costs come from the T06 cost arrays, with the Numba commission signature designed in T06.
- **T10b — Executor (F-0.3.7) and metric-name registry** reconciling T09 `as_gate_dict()` with the T10a gate YAML (D-309). `SplitManager.open_holdout` gets a stage argument (D-306).

## 7. Review rules

- A task is judged only against the acceptance criteria of the feature list (and the decisions log); "done" without a proving test is not accepted.
- Parity and leakage tests are never weakened or deleted.
- Every new dependency is listed with its reason in the review; non-trivial library choices are the user's.
