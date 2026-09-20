# HANDOFF — Strategy Factory (v6, 2026-09-21)

Read together with `CLAUDE.md`, `docs/decisions/decisions_log.md` (source of truth #0),
`docs/decisions/pending.md`, the spec (`docs/spec/spec_v1.2.md`), the design (`docs/design.md`)
and the feature list (`docs/features.md`).

**Since D-355 the work runs in two streams.** Each keeps its own status file; this file is
written **only by stream A, at merges**, from both of them:

- `docs/streams/A.md` — stream A, the main folder: the batch-2b merges (done), then **T11 parity**.
- `docs/streams/B.md` — stream B, the worktree `../StrategyFactory_B`: **data** (batch 3-data),
  then T12. Stream B's file is the authority on data facts; §6 below is folded from it.

## 1. Project in one paragraph

Strategy Factory is an internal framework that runs every trading-strategy idea through one standard, reproducible, auditable funnel: edge discovery → method screening → entry optimization → exit optimization → diagnostics and filters → robustness → statistical validation → report package → analyst review → portfolio → sizing → forward lifecycle. Repository `AmerQuant/strategy-factory`, Python package `strategy_factory`, CLI `sfac`, local path `D:\AmerAndish\Projects\Trade\StrategyFactory\`. Data lives outside the repo in `D:\AmerAndish\Projects\Trade\StrategyFactory_data\` (`raw\` = `SFAC_RAW_ROOT`, immutable; `store\` = `SFAC_DATA_ROOT`, canonical snapshots).

## 2. Roles and workflow

- **User:** product owner and final decision maker. Runs Claude Code, runs every network script in PowerShell (D-031), approves plans and merges.
- **Supervisor (Claude chat, inside the Claude Project connected to this repo):** architect and reviewer. Keeps the decisions log, answers `docs/decisions/pending.md`, reviews plans and PRs against the acceptance criteria. After every merge, press **Sync** in the Project so the supervisor sees the current `main`.
- **Claude Code, two streams (D-355).** Both follow the standing prompt (`docs/STANDING_PROMPT.md`):
  1. **Phase 1 — plan:** task files + runbook on a docs branch; assumptions go to `pending.md`; stop.
  2. **Phase 2 — execute**, after "Plan approved": tests first, implementation, acceptance commands, the `acceptance-reviewer` subagent, review file, commit. Critical tasks (D-402) stop after their review until "Approved".
  3. **End:** PR(s) with `gh` (body = reviews), the stream's status file updated, batch report. Merge only on "Approved. Merge …" with green CI (D-401).
- **Stream rules that matter across the boundary (D-355):** ID ranges — supervisor D-355…D-359, stream A D-360…D-379 / P-40…P-59, stream B D-380…D-399 / P-60…P-79; each worktree has its own test database (`sfac` / `sfac_b`) on the shared Postgres; **only stream B writes `SFAC_DATA_ROOT`**; both read `SFAC_RAW_ROOT` read-only; docs edits go on the stream's own branch and conflicts are resolved by **keeping every row in ID order**; benchmarks only when the other stream is idle; every branch rebases onto `main` before its merge.
- Each task branch is pushed to `origin` as soon as its review file is committed. Stream B's task branches use the `b/` prefix.
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
| T04e | Data-layer follow-up (hash v2, calendar, renames, pilots) | ✅ merged (#4) — its calendar fetch and v1→v2 re-hash were never run; picked up by T04f/T04i (stream B) |
| T05 | Data quality, resampling, split manager | ✅ merged (batch 2a, #7) |
| T06 | Cost model (placeholder profiles) | ✅ merged (batch 2a, #7) |
| **T06b** | Moneta cost profiles, broker mapping, broker universe | ✅ **merged (#13)** — P-28 closed by D-356, **548/548** mapped or unmappable |
| T07 | Components and indicators | ✅ merged (#6) |
| **T08** | Engine — critical (D-402) | ✅ **merged (#14)** |
| T09 | Metrics and result containers | ✅ merged (#8) |
| T10a | Gate engine, pipeline config, universe | ✅ merged (batch 2a, #7) |
| **T10b** | Executor, metric-name registry, run config hash, holdout stage guard | ✅ **merged (#15)** |
| **T11** | TradingView parity — **critical (D-402)** | ⏭ **stream A, next**; references exist (D-348), notes in §8 |
| T04f | Alpaca reference fetch + NYSE calendar (D-025) | 🔄 stream B, in progress (`b/T04f-alpaca-reference`) |
| T04g / T04h / T04i | Alpaca 1D ingest / 1H ingest / phase-B hourly analysis | ⏭ stream B, planned (batch 3-data) |
| T12 … T15 | Stages 1–3, orchestrator/CLI/reports/self-tests | later; T12 carries D-354 and is stream B's |

## 4. Batch 2b — closed 2026-09-21

Everything is on `main`:

| PR | Content |
|---|---|
| [#11](https://github.com/AmerQuant/strategy-factory/pull/11) | batch-2b plan and decisions D-312 … D-350 |
| [#12](https://github.com/AmerQuant/strategy-factory/pull/12) | D-351 … D-354 (executor budget, dirty flag, futures parity, T12 notes) |
| [#16](https://github.com/AmerQuant/strategy-factory/pull/16) | D-355 (two streams), D-356 (P-28 closed) |
| [#13](https://github.com/AmerQuant/strategy-factory/pull/13) | **T06b** — Moneta cost model, broker mapping, broker universe |
| [#14](https://github.com/AmerQuant/strategy-factory/pull/14) | **T08** — the Numba backtest engine (critical, approved) |
| [#15](https://github.com/AmerQuant/strategy-factory/pull/15) | **T10b** — executor, metric-name registry, run config hash, holdout stage guard (critical parts approved) |

State of `main` after the merges: `ruff` ✅, `ruff format` ✅, `mypy src` ✅ 96 files,
`pytest -m "not slow"` ✅ **1153 passed**, parity + leakage + oracle ✅ **283**, `pytest -m db -rs`
✅ **21, 0 skipped**.

`pending.md` carries P-28 … P-38, all answered. Stream B's P-60 … P-67 are answered on its own
branch and arrive with its merge.

## 5. Decisions to carry forward

- **D-354 — T12 acceptance (stream B).** (1) Stage code takes the engine settings **only** from
  the run's `PipelineConfig.engine`; `DEFAULT_ENGINE_CONFIG` is forbidden in stage code (grep
  test). (2) A stage passes its stage id from its own constant; a grep test ensures the literal
  `"s06_robust"` appears only in `data/split.py` and the stage-6 module. (3) F-0.7.4 stays
  **partial** until the bit-identical rerun through `RunContext` is proven.
- **D-351** the executor `auto` budget (revisit if the stage-2/3 grid shapes differ); **D-352**
  the dirty flag (tracked changes, or untracked files under `src/` or `configs/`); **D-353** a
  futures parity run gets its exemption when T04d adds the futures flag.
- **D-355** the two streams; **D-356** the closed broker mapping (62 broker-tradable instruments
  have no research data — a data expansion after D-030 is lifted).

## 6. Data status (folded from `docs/streams/B.md`, which is the authority)

| Source | Status |
|---|---|
| Alpaca **1D** raw (6,711 symbols, SIP, split-adjusted) | ✅ **complete**, 11 years (2016–2026); 3 symbols returned no bars (`BHGE`, `FBHS`, `JEC`). **Not ingested** (T04g, gated on D-033). |
| Alpaca **1H** raw (827 symbols) | ⚠️ **incomplete** as of 2026-09-20: 2021 and 2022 missing for **all** symbols, 2020 for 137, 2023 for 620 — **no symbol has all eleven years**. The user is refilling 2020–2023. T04h stays blocked until it is complete (D-386; no `--allow-gaps`). *This corrects the "1H download complete" line in v5.* |
| Dukascopy h1 bid/ask (29 instruments, from 2010) | still downloading (user, several more days); only the Q1-2024 pilot snapshots are in the catalog |
| Yahoo aux (7 series) | downloaded |
| NYSE calendar (`configs/calendars/nyse_sessions.csv`) | ❌ **missing** — the T04e fetch was never run, so the calendar, `configs/universe/symbol_changes.csv` and the raw calendar/corporate-action files do not exist. T04f §1 is the user's PowerShell run (D-025). |
| Snapshot store (`SFAC_DATA_ROOT`) | untouched: 3 Dukascopy Q1-2024 pilot snapshots, all still `hash_version = 1` (the T04e v1→v2 re-hash never ran) |
| Moneta broker spec | `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` (read-only, manifest next to it, not in git) |
| Alpaca asset names (mapping) | `SFAC_RAW_ROOT/reference/alpaca/alpaca_assets_2026-09-20.v2.csv`, sha256 `9a0e8dad…1e94c`: 33,276 rows = 14,354 active + 18,922 inactive, no duplicate tickers (D-341) |
| TradingView parity references (D-348) | `raw/reference/tradingview/parity/`: BATS:SPY 1D (MR) and OANDA:XAUUSD 1H (TF), trade list + OHLC each, immutable, SHA-256 in a manifest |

Data expansion is frozen until the project is built (D-030).

## 7. Open items

- **Stream A owes `sfac universe generate` after every stream-B merge (D-394).**
  `configs/universe/` is stream B's; **`configs/universe.yaml` is stream A's** and is not
  regenerated in the worktree. Stream B lists each added or removed symbol in
  `docs/streams/B.md` ("Symbols for stream A"); until stream A regenerates,
  `configs/universe.yaml` is knowingly stale. Nothing is listed yet — T04f fills it in when the
  `NAME_CHANGE` feed arrives.
- **D-357 is cited but has no row in the decisions log.** `docs/streams/B.md` and
  `docs/tasks/RUNBOOK_batch3-data.md` cite it for the `b/` branch prefix; the log has no D-357
  entry. The supervisor should add it (it is in the supervisor range D-355…D-359).
- **D-388 (stream B → stream A):** the renamed/re-used-ticker exclusion rule was checked against
  the merged T06b. The affected Moneta research targets (`COR`, `LUMN`, `META`, `RTX`, `MRSH`
  from broker `MMC`, `BNY` from broker `BK`) are all current names and survive it, so **no change
  is needed under `configs/costs/`**. If the Alpaca `NAME_CHANGE` feed contradicts the `EQR`
  finding, stream B stops and reports.
- **D-356 follow-ups:** `AMCX` and the broker symbol `FI` are checked in **MT5** before any
  forward activation; 62 broker-tradable instruments have no research data.
- P-01 (edge-type addendum) and P-02 (futures, blocks T04d) are in the decisions log, section G.
- `pending.md` has no open questions in batch 2b.

## 8. T11 notes (parity only — check before or during T11)

1. **ATR warm-up entries.** The engine only schedules an entry when `atr[j] > 0`; TradingView may enter during the ATR warm-up. Check the first trades of the exported trade lists against the engine's.
2. **Trailing ATR basis.** The engine's trailing distance uses the ATR **at entry** (`atr_e`, fixed for the trade); Pine scripts often recompute the distance from the *current* ATR on every bar. Check the TF script before deciding — this interacts with D-349 (a), which is still `to_verify` in parity mode.
3. Remaining parity `to_verify` items (T08 review): the O→H→L→C path and its tie (D-335), exit + re-entry at one open (D-336), no swap on intrabar exits in rollover bars (D-327), trailing updates only at the close (D-349 a), and the parity conversion rate = the signal bar's `fx_close` (D-349 h).
4. **Parity inputs are per run and required:** `parity_qty_step` (D-347) and the Pine `atr_length` (D-343) — a `tradingview` pipeline config that omits either is refused (T10b).

## 9. Review rules

- A task is judged only against the acceptance criteria of the feature list (and the decisions log); "done" without a proving test is not accepted.
- Parity and leakage tests are never weakened or deleted.
- Every new dependency is listed with its reason in the review; non-trivial library choices are the user's.
