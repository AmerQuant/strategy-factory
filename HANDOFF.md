# HANDOFF — Strategy Factory (v4, 2026-09-20)

Read together with `CLAUDE.md`, `docs/decisions/decisions_log.md` (source of truth #0), `docs/decisions/pending.md`, the spec (`docs/spec/spec_v1.2.md`), the design (`docs/design.md`) and the feature list (`docs/features.md`).

## 1. Project in one paragraph

Strategy Factory is an internal framework that runs every trading-strategy idea through one standard, reproducible, auditable funnel: edge discovery → method screening → entry optimization → exit optimization → diagnostics and filters → robustness → statistical validation → report package → analyst review → portfolio → sizing → forward lifecycle. Repository `AmerQuant/strategy-factory`, Python package `strategy_factory`, CLI `sfac`, local path `D:\AmerAndish\Projects\Trade\StrategyFactory\`. Data lives outside the repo in `D:\AmerAndish\Projects\Trade\StrategyFactory_data\` (`raw\` = `SFAC_RAW_ROOT`, immutable; `store\` = `SFAC_DATA_ROOT`, canonical snapshots).

## 2. Roles and workflow

- **User:** product owner and final decision maker. Runs Claude Code, runs every network script in PowerShell (D-031), approves plans and merges.
- **Supervisor (Claude chat, inside the Claude Project connected to this repo):** architect and reviewer. Keeps the decisions log, answers `docs/decisions/pending.md`, reviews plans and PRs against the acceptance criteria. After every merge, press **Sync** in the Project so the supervisor sees the current `main`.
- **Claude Code:** plans and implements batches with the standing prompt (`docs/STANDING_PROMPT.md`):
  1. **Phase 1 — plan:** task files + runbook on branch `docs/<batch>`; assumptions go to `pending.md`; stop.
  2. **Phase 2 — execute**, after "Plan approved": tests first, implementation, acceptance commands, the `acceptance-reviewer` subagent (`.claude/agents/`), review file, commit. Critical tasks (D-402) stop after their review until "Approved".
  3. **End:** PR(s) with `gh` (body = reviews), update this file, batch report. Merge only on "Approved. Merge …" with green CI (D-401).
- Each task branch is pushed to `origin` as soon as its review file is committed (no PR, no merge before approval).
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
| T06b | Moneta cost profiles, broker mapping, broker universe | 🟡 **done, blocked on P-28** — branch `feat/T06b-moneta-costs` (3096c72), review + addendum written, D-350 applied, D-341 rebuild done (471 mapped, 106 review rows). Waiting for the user's `-IncludeInactive` asset list and `symbol_overrides.csv`. |
| T07 | Components and indicators | ✅ merged (#6) |
| T08 | Engine — **critical (D-402)** | 🟢 **approved by the supervisor**, awaiting merge — branch `feat/T08-engine` (c39da49 + docs), stacked on T06b. Merge **after** T06b, rebased onto `main`, CI green. |
| T09 | Metrics and result containers | ✅ merged (#8) |
| T10a | Gate engine, pipeline config, universe | ✅ merged (batch 2a, #7) |
| T10b | Executor (F-0.3.7) + metric-name registry, run-level config hash, holdout stage guard | 📝 **planned** — task file `docs/tasks/T10b_executor_metric_names.md` (d3aaa69); plan approved with three additions (§5 below). Sections 2 and 4 are **critical (D-339)**. |
| T11 … T15 | Parity, stages 1–3, orchestrator/CLI/reports/self-tests | later |

## 4. Batch 2b status

`main` = `docs/batch2b` merged (PR #11, 6a30bc3). D-312 … D-350 are in the decisions log; **no open batch-2b `P-` questions** (`pending.md`: P-05 … P-35 all answered; P-28's *coverage criterion* still needs the user's overrides).

Branch stack: `main` → `feat/T06b-moneta-costs` → `feat/T08-engine` (→ `feat/T10b-…` next).

| Task | Branch | Review | Next step |
|---|---|---|---|
| T06b | `feat/T06b-moneta-costs` | `docs/reviews/T06b_review.md` (+ 2026-09-20 addendum) | user runs `scripts/download_alpaca_assets.ps1 -IncludeInactive` → rebuild → user fills `configs/costs/moneta/symbol_overrides.csv` → coverage criterion closes |
| T08 | `feat/T08-engine` | `docs/reviews/T08_review.md` (+ addendum) | approved; merge after T06b |
| T10b | `feat/T10b-…` (to create) | — | execute the approved plan |

Merge order: T06b → T08 → T10b, each rebased onto `main`, CI green (ruff, format, mypy, fast suite, parity + leakage + oracle, `-m db` with 0 skipped). Merge only on "Approved. Merge …" (D-401).

## 5. T10b plan additions (approved 2026-09-20)

The task file `docs/tasks/T10b_executor_metric_names.md` was approved with these changes; everything else in it stands.

- **(a) `config_hash` must also cover the cost inputs:** the resolved cost-profile content hash per symbol, the Moneta spec SHA-256, `configs/data/fx_conversion.yaml` (pairs and peg) and the conversion pairs' snapshot hashes. Tests: regenerating a profile with a different spread changes the hash; `sfac reproduce` fails loudly when the stored cost hash no longer matches.
- **(b) The allowed holdout stage (`s06_robust`) is a constant in code, not a config value** (D-306: enforced in code). A test proves that no config can change it.
- **(c) The run row stores the code version** (git commit + dirty flag) if it does not already — **stored, not hashed**.

## 6. Data status

| Source | Status |
|---|---|
| Alpaca 1D (6,711 symbols, SIP, split-adjusted) | downloaded, **not ingested** yet |
| Alpaca 1H (827 symbols) | **downloading** (user) |
| Dukascopy h1 bid/ask (29 instruments, from 2010) | **downloading** (user); only the Q1-2024 pilot snapshots are in the catalog |
| Yahoo aux (7 series) | downloaded |
| NYSE calendar (`configs/calendars/nyse_sessions.csv`) | to be generated from the Alpaca calendar fetch (D-025) |
| Moneta broker spec | `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` (read-only, manifest next to it, not in git) |
| Alpaca asset names (mapping) | `SFAC_RAW_ROOT/reference/alpaca/alpaca_assets_2026-09-20.csv`, 14,354 rows, active only. **A `-IncludeInactive` run is pending** (P-28). |
| TradingView parity references (D-348) | `raw/reference/tradingview/parity/`: BATS:SPY 1D (MR) and OANDA:XAUUSD 1H (TF), trade list + OHLC each, immutable, SHA-256 in a manifest |

Data expansion is frozen until the project is built (D-030).

## 7. Open items

- **P-28 — broker mapping coverage (blocks T06b).** The user runs `scripts/download_alpaca_assets.ps1 -IncludeInactive` and gives Claude Code the file name; then `sfac costs moneta build` + `sfac universe generate` are repeated and the user fills `configs/costs/moneta/symbol_overrides.csv` for what is left (106 review rows today: 17 same ticker/no name, 13 same ticker/other wording — `AMCX` is suspicious —, 48 name-only, 27 no match, 1 unmappable `ALIBABA`). The 548/548 criterion stays open until then (D-341).
- **`universe_filter` must go back to `broker` (D-342, D-524)** in `configs/pipeline/mvp_daily.yaml` before the first real stage-1 run. It runs with `all` only while P-28 is open.
- **P-04 is closed by D-348.** The TradingView exports exist; T11 runs parity mode on the exported OHLC as-is (no D-010 Sunday merge, no resampling, no Alpaca/Dukascopy bars), with the Pine settings recorded in the parity config.
- P-01 (edge-type addendum) and P-02 (futures, blocks T04d) are in the decisions log, section G. P-03 (broker costs) is addressed by T06b.
- `pending.md` has no open batch-2b questions.

## 8. T11 notes (parity only — check before or during T11)

1. **ATR warm-up entries.** The engine only schedules an entry when `atr[j] > 0`; TradingView may enter during the ATR warm-up. Check the first trades of the exported trade lists against the engine's.
2. **Trailing ATR basis.** The engine's trailing distance uses the ATR **at entry** (`atr_e`, fixed for the trade); Pine scripts often recompute the distance from the *current* ATR on every bar. Check the TF script before deciding — this interacts with D-349 (a), which is still `to_verify` in parity mode.
3. Remaining parity `to_verify` items (T08 review): the O→H→L→C path and its tie (D-335), exit + re-entry at one open (D-336), no swap on intrabar exits in rollover bars (D-327), trailing updates only at the close (D-349 a), and the parity conversion rate = the signal bar's `fx_close` (D-349 h).

## 9. Review rules

- A task is judged only against the acceptance criteria of the feature list (and the decisions log); "done" without a proving test is not accepted.
- Parity and leakage tests are never weakened or deleted.
- Every new dependency is listed with its reason in the review; non-trivial library choices are the user's.
