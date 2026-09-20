# HANDOFF — Strategy Factory (v5, 2026-09-21)

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
| T06b | Moneta cost profiles, broker mapping, broker universe | 🟡 **done, blocked on P-28** — PR [#13](https://github.com/AmerQuant/strategy-factory/pull/13), branch `feat/T06b-moneta-costs` (2e7a730). D-350 applied; rebuilt on the `-IncludeInactive` list (**472 mapped, 105 review rows**). Waiting only for the user's `symbol_overrides.csv`. |
| T07 | Components and indicators | ✅ merged (#6) |
| T08 | Engine — **critical (D-402)** | 🟢 **approved**, awaiting merge — PR [#14](https://github.com/AmerQuant/strategy-factory/pull/14), branch `feat/T08-engine`, stacked on T06b. Merge **after** T06b, rebased onto `main`, CI green. |
| T09 | Metrics and result containers | ✅ merged (#8) |
| T10a | Gate engine, pipeline config, universe | ✅ merged (batch 2a, #7) |
| T10b | Executor (F-0.3.7), metric-name registry, run config hash, holdout stage guard | 🟢 **done and approved** (both CRITICAL parts, D-339) — PR [#15](https://github.com/AmerQuant/strategy-factory/pull/15), branch `feat/T10b-executor-metric-names`, stacked on T08. Review: `docs/reviews/T10b_review.md`. |
| T11 | Parity (TradingView) — **critical (D-402)** | ⏭ next; references exist (D-348), notes in §8 |
| T12 … T15 | Stages 1–3, orchestrator/CLI/reports/self-tests | later; T12 carries D-354 (§5) |

## 4. Batch 2b status — complete, awaiting merges

`main` = `docs/batch2b` (PR #11) + `docs/batch2b-2` (PR #12, D-351 … D-354). **All three batch-2b
tasks are implemented, reviewed and approved.** `pending.md` has no open questions left; P-28's
coverage criterion still needs the user's overrides (D-341).

Branch stack: `main` → `feat/T06b-moneta-costs` → `feat/T08-engine` → `feat/T10b-executor-metric-names`.

| Task | PR | Base | Review | State |
|---|---|---|---|---|
| T06b | [#13](https://github.com/AmerQuant/strategy-factory/pull/13) | `main` | `docs/reviews/T06b_review.md` (+ addendum) | blocked on P-28 |
| T08 | [#14](https://github.com/AmerQuant/strategy-factory/pull/14) | `feat/T06b-moneta-costs` | `docs/reviews/T08_review.md` (+ addendum) | approved |
| T10b | [#15](https://github.com/AmerQuant/strategy-factory/pull/15) | `feat/T08-engine` | `docs/reviews/T10b_review.md` (+ addendum) | approved |

### Merge sequence (D-401: only on "Approved. Merge …", CI green)

1. **P-28 closes first:** the `-IncludeInactive` list is in and the mapping is rebuilt on the
   branch (2e7a730). What remains is the user's `configs/costs/moneta/symbol_overrides.csv` for
   the 105 review rows; then `sfac costs moneta build` + `sfac universe generate` run once more
   and T06b's coverage criterion (548/548) closes.
2. **T06b → `main`**, then **T08 → `main`**, then **T10b → `main`**, each rebased onto `main` with
   CI green.

**Known merge mechanics (checked with a merge probe, 2026-09-21):** only
`docs/decisions/pending.md` conflicts, and only at the end of its table, because `main` already
carries P-36 … P-38 while the branches carry P-28 … P-30 (T06b) and P-31 … P-35 (T08).
**Resolution: keep every row, in ID order.** `decisions_log.md` and all code files auto-merge
cleanly. T10b's `pending.md` was already aligned with `main`, so it does not conflict.

## 5. Decisions from the T10b review (2026-09-21) and the T12 notes

- **D-351** (P-36) — the executor `auto` budget: both `auto` → `workers = floor(sqrt(cpu))`,
  `numba_threads = cpu // workers`; one given → the other is `max(1, cpu // given)`; both given
  and over `cpu_count` → error (D-334). Accepted on the T10b benchmark (20 cores: 4 × 5 fastest);
  **revisit if the stage-2/3 grid shapes differ.**
- **D-352** (P-37, changed) — `code_version` is `<sha>-dirty` for uncommitted tracked changes **or
  untracked files under `src/` or `configs/`**; untracked files elsewhere do not count. Stored,
  never hashed. Implemented on the T10b branch.
- **D-353** (P-38) — until T04d there is no futures flag in a pipeline config, so
  `validate_config` requires `parity_qty_step` for every `tradingview` run while `run_backtest`
  keeps the futures exemption (contracts, D-329). T04d adds the flag and the same exemption.
- **D-354 — T12 notes (carry into the T12 task file and its acceptance):**
  1. Stage code takes the engine settings **only** from the run's `PipelineConfig.engine`;
     `DEFAULT_ENGINE_CONFIG` is forbidden in stage code (**grep test**), so `config_hash`
     describes what the run actually reads.
  2. A stage passes its stage id from its own stage constant; a **grep test** ensures the literal
     `"s06_robust"` appears only in `data/split.py` and the stage-6 module.
  3. F-0.7.4 stays **partial** until the bit-identical rerun through `RunContext` is proven.

## 6. Data status

| Source | Status |
|---|---|
| Alpaca 1D (6,711 symbols, SIP, split-adjusted) | ✅ download **complete**, **not ingested** yet |
| Alpaca 1H (827 symbols) | ✅ download **complete**, **not ingested** yet |
| Dukascopy h1 bid/ask (29 instruments, from 2010) | **still downloading** (user, several more days); only the Q1-2024 pilot snapshots are in the catalog |
| Yahoo aux (7 series) | downloaded |
| NYSE calendar (`configs/calendars/nyse_sessions.csv`) | to be generated from the Alpaca calendar fetch (D-025) |
| Moneta broker spec | `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` (read-only, manifest next to it, not in git) |
| Alpaca asset names (mapping) | `SFAC_RAW_ROOT/reference/alpaca/alpaca_assets_2026-09-20.v2.csv`, sha256 `9a0e8dad…1e94c`: 33,276 rows = 14,354 active + 18,922 inactive, no duplicate tickers (D-341). The mapping is rebuilt on it. |
| TradingView parity references (D-348) | `raw/reference/tradingview/parity/`: BATS:SPY 1D (MR) and OANDA:XAUUSD 1H (TF), trade list + OHLC each, immutable, SHA-256 in a manifest |

Data expansion is frozen until the project is built (D-030).

## 7. Open items

- **P-28 — broker mapping coverage (blocks T06b).** The `-IncludeInactive` list is in and the mapping is rebuilt (472 mapped, **105 review rows**). What is left needs the user's `configs/costs/moneta/symbol_overrides.csv`: 52 name-only candidates, 23 with no match, 15 with a matching ticker but **no name anywhere in the Alpaca file** (273 research symbols are missing from it, so no lookup can close them — `AVB`, `BK`, `EA`, `WBA` …), 14 same ticker/other wording (`AMCX` suspicious; the price check refutes `FI`, ratio 54) and 1 unmappable `ALIBABA`. The price check confirms `HES`, `DFS` and `GPS`. The 548/548 criterion stays open until then (D-341).
- **`universe_filter` must go back to `broker` (D-342, D-524)** in `configs/pipeline/mvp_daily.yaml` before the first real stage-1 run. It runs with `all` only while P-28 is open.
- **P-04 is closed by D-348.** The TradingView exports exist; T11 runs parity mode on the exported OHLC as-is (no D-010 Sunday merge, no resampling, no Alpaca/Dukascopy bars), with the Pine settings recorded in the parity config.
- P-01 (edge-type addendum) and P-02 (futures, blocks T04d) are in the decisions log, section G. P-03 (broker costs) is addressed by T06b.
- `pending.md` has no open questions: P-36 … P-38 were answered by D-351 … D-353.

## 8. T11 notes (parity only — check before or during T11)

1. **ATR warm-up entries.** The engine only schedules an entry when `atr[j] > 0`; TradingView may enter during the ATR warm-up. Check the first trades of the exported trade lists against the engine's.
2. **Trailing ATR basis.** The engine's trailing distance uses the ATR **at entry** (`atr_e`, fixed for the trade); Pine scripts often recompute the distance from the *current* ATR on every bar. Check the TF script before deciding — this interacts with D-349 (a), which is still `to_verify` in parity mode.
3. Remaining parity `to_verify` items (T08 review): the O→H→L→C path and its tie (D-335), exit + re-entry at one open (D-336), no swap on intrabar exits in rollover bars (D-327), trailing updates only at the close (D-349 a), and the parity conversion rate = the signal bar's `fx_close` (D-349 h).

## 9. Review rules

- A task is judged only against the acceptance criteria of the feature list (and the decisions log); "done" without a proving test is not accepted.
- Parity and leakage tests are never weakened or deleted.
- Every new dependency is listed with its reason in the review; non-trivial library choices are the user's.
