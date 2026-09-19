# Decisions log — Strategy Factory

This is the single source of truth for all decisions made so far, including those taken only in the supervision chat. Each decision has an ID. Tasks and reviews cite these IDs.

- **Precedence:** where this log is more specific than the spec (v1.2), the design (v1.0) or the feature list (v1.1), **this log wins**. Changing a decision means a new entry that supersedes the old one; entries are never edited silently.
- **Status:** `accepted` · `proposed` (awaiting user) · `superseded by D-xxx`.

---

## A. Conventions (stage 0)
| ID | Decision | Status |
|---|---|---|
| D-001 | Signals are evaluated at the bar close; orders fill at the **open of the next bar** (TradingView default). | accepted |
| D-002 | Intrabar SL/TP ambiguity has two modes: `tradingview` (parity only) and `pessimistic` (research: stop first). Minute-data resolution is added later (F-0.3.5). | accepted |
| D-003 | Equity is **mark-to-market** at every bar close. | accepted |
| D-004 | Initial capital is 100,000 USD; fixed notional is 100,000 USD per trade. qty = notional / entry price (not for futures, see D-061). One position per strategy; no pyramiding. | accepted |
| D-005 | Annual drawdown is reported in two versions: (a) from the start of each year, (b) against the all-time peak. **Gates and the target metric use (a).** Both are % of **initial capital**. | accepted |
| D-006 | Partial years count fractionally: average annual profit = total / years covered; the average annual DD is weighted by each year's covered fraction. | accepted |
| D-007 | Target metric `profit_dd_ratio` = average annual profit / average annual DD (a). A denominator of 0 gives inf plus a flag. | accepted |
| D-008 | Holdout = the last 20 % of the time span, **at least 18 months**. If fewer than 30 trades are expected in it, a longer forward incubation replaces it. Holdout access is one-shot per candidate, enforced in the DB. | accepted |
| D-009 | Embargo = max indicator lookback + max holding period (in bars). | accepted |
| D-010 | Timestamps are UTC, bar-start. Day boundary is **00:00 UTC**. For `fx`, `metal`, `energy_cfd` and `index_cfd`, Sunday hours are merged into Monday. `broker_session` resampling is for parity only. | accepted |
| D-011 | Parity with TradingView: ≥ 98 % of trades matched, net-profit difference ≤ 3 %. | accepted |
| D-012 | A trial is any evaluated configuration that can influence selection. Monte-Carlo and bootstrap simulations are not trials; only their distribution summaries are stored. | accepted |
| D-013 | Costs are mandatory. Until real profiles are built, **placeholder profiles** (T06 table) are used and every result carries a `cost_placeholder` flag. | superseded by D-520 once T06b is merged |
| D-014 | Auxiliary series are joined as-of (last **closed** value only). A series whose close time is `to_verify` gets **one extra day of lag**. Currently only ^VIX is verified (16:15 America/New_York). | accepted |

## B. Data
| ID | Decision | Status |
|---|---|---|
| D-020 | Asset-class scope, in phases: **MVP** = US equities and ETFs; **P1** = FX/metals/index and energy CFDs (Dukascopy) and futures; **P2** = crypto and Iran. | accepted |
| D-021 | Equity price basis: **split-adjusted only** (TradingView-like). The existing all-adjusted data (MS-US-1D, QP) is for cross-checking only. | accepted |
| D-022 | Alpaca, via alpaca-py, feed **SIP**, `adjustment=split`, from 2016-01-01. Daily: 6,711 symbols (delisted included). Hourly: S&P 500 point-in-time members + main ETFs (827). | accepted |
| D-023 | US hourly bars are hour-aligned; only the bars labelled 09:00–15:00 New York are kept (`RTH_hour_aligned`; the 09:00 bar contains pre-market). The OR edge type is **not** run on US equities with this data. | accepted |
| D-024 | Renamed tickers are downloaded under the **current** symbol, via Alpaca corporate actions (`NAME_CHANGE`, `process_date`) plus a manual override file. | accepted |
| D-025 | The NYSE session calendar comes from Alpaca's calendar API (`configs/calendars/nyse_sessions.csv`). | accepted |
| D-026 | Dukascopy via **dukascopy-node** (pinned, outside the Python package). Bid **and** ask, **h1 from 2010** (29 instruments). m1 only for intrabar resolution, run slowly when needed. The hourly spread profile comes from h1 bid/ask. | accepted |
| D-027 | Yahoo via **yfinance** (pinned), always `auto_adjust=False`, daily, 7 aux series. Every download is a new immutable raw version. | accepted |
| D-028 | Storage: `StrategyFactory_data\raw` (= `SFAC_RAW_ROOT`, immutable, byte-identical copies plus downloads) and `\store` (= `SFAC_DATA_ROOT`, canonical snapshots), outside the repo. Source folders are read-only. | accepted |
| D-029 | Snapshot content hash **version 2**, a library-independent serialization (golden hash in the T04e review). `asset_class` is an enum. The snapshot key is `(snapshot_hash, source, symbol, timeframe)` in both catalog and registry. | accepted |
| D-030 | **Data expansion is frozen** until the whole project is built. Parked proposals: the 13 remaining FX pairs, extra CFDs, 9 extra aux series, ex-dividend data, an ETF coverage check, and a futures refresh. | accepted |
| D-031 | The host has **no TLS interception**. Claude Code's sandbox proxy causes the certificate errors. **All network runs are done by the user in PowerShell** (pilot and download scripts); no CA-bundle workaround. | accepted |
| D-032 | Daily Dukascopy/CFD bars are built from h1 (D-010), not downloaded. | accepted |
| D-033 | Daily session for Alpaca 1D (RTH vs exchange) is decided from the T04e pilot evidence. | proposed |

## C. Futures (P1)
| ID | Decision | Status |
|---|---|---|
| D-060 | Source: the TradeStation 1H export (`raw/futures/tradestation/1H`, 64 roots, 2006 → 2025-07-09). The data shows **additive back-adjustment** (negative prices exist). Labels are **bar-end**, in exchange-local time: America/Chicago for CME/CBOT/NYMEX/COMEX, America/New_York for ICE softs (CC, CT, KC, OJ, SB). The adapter converts to bar-start UTC. The roll rule is **unknown and treated as irrelevant**: the adapter never needs it, and roll gaps are already removed by the back-adjustment. The `- Copy` and `.bak` files are **ignored**. Assumptions are marked `to_verify` in the metadata. | accepted |
| D-061 | Futures are sized in **contracts**; P&L = Δpoints × point value (`$/Big Point` from the export header). Signals and ATR are in points, never in percent. **This is an engine design change and must be in T08's contract** (qty in contracts when asset_class = futures). | accepted |
| D-062 | Futures daily bars are built from 1H. `1440min` / `Daily` are not imported. | accepted |

## D. Pipeline stages
| ID | Decision | Status |
|---|---|---|
| D-100 | Stage-1 probes are grouped. MR has 4 groups (oscillator, band_channel, sequence, momentum); TF has 5 (ma, channel_breakout, volatility_trailing, ichimoku, momentum). Breadth counts groups. Short = mirror unless `mirror: false` with a written reason. | accepted |
| D-101 | Fixed probe exits. MR: close above the previous high, or at most 5 bars. TF: reverse signal, at most 50 bars, disaster stop 3 ATR. | accepted |
| D-102 | Random baseline: 1000 simulations matched on direction, count and holding distribution, on allowed bars; no overlap when the probe has none. | accepted |
| D-103 | ESS weights: breadth 30, magnitude 30, significance 20, consistency 20 (to be calibrated). The complementary stats (VR, Hurst, half-life) are **report-only**. | accepted |
| D-104 | Start timeframes: 1D and 1H. | accepted |
| D-105 | Every probe declares `trigger: state \| event`. Threshold probes are `state`; crosses, breakouts and flips are `event`. `tf_bb_upper_cross` is an event. | accepted |
| D-106 | Seasonal candidates go to stage 5 with **regime filters only** (no calendar filters), then to stage 6. | accepted |
| D-110 | Stage-2 coarse grid: 4 values per parameter, at most 64 cells per method. 3–5 candidates, with trade overlap ≤ 60 %. | accepted |
| D-120 | Stage-3 fine grid: at most 2000 combinations, at most 3 free entry parameters. Full grid; Sobol sampling above 2000; no Bayesian search. Neighbourhood ±1 step. Plateau ratio ≥ 0.8, plateau area ≥ 10 %, stable across both halves. | accepted |
| D-130 | Disaster stop is fixed at 3 ATR and never optimized; a warning is raised if more than 2 % of trades hit it. A new exit is accepted if it improves the metric by ≥ 10 % in most years. At most 5 free parameters in total. | accepted |
| D-140 | Stage-5 buckets: ≥ 30 trades, BH q ≤ 0.1, empirical-Bayes shrinkage, direction stable in ≥ 70 % of years and in both halves. Filters: 1000 random-removal runs, improvement must be ≥ p95, ≥ 60 % of trades kept, at most 2 filters added greedily. Forbidden filter families per the edge-type addendum §1.5. | accepted |
| D-150 | Walk-forward: 1D uses 4 y in-sample / 1 y out-of-sample; 1H uses 2 y / 6 m. The windows auto-shrink if fewer than 4 OOS windows fit. Monte Carlo: 1000 runs for screening, 5000 for final. Cross-symbol validation is report-only. Crisis periods: 2008, 2020-03, 2022, 2015-01 (CHF), 2024-08. | accepted |
| D-160 | Stage 7: the effective number of trials is estimated by clustering correlated results. DSR ≥ 0.95, PBO ≤ 0.25, Hansen SPA, p < 0.05. | accepted |
| D-170 | Stage 8 uses **no LLM API**. The package is `evidence.json` (single JSON) + `PROMPT.md` + `REPORT_SPEC.md`; the analyst produces the Word report in Claude chat, then `sfac report verify`. Scope: passed candidates plus **borderline** ones. Borderline = exactly one non-critical failure within 10 % of its threshold; never after a failure in WF, cost ×2 or holdout. | accepted |
| D-180 | Stage 9: one analyst. | accepted |
| D-190 | Stage 10: caps of 10 % per strategy, 20 % per symbol, 40 % per class. Quarterly rebalance. Equal weights unless another method beats them out-of-sample. | accepted |
| D-200 | Stage 11: fixed notional is the baseline. Dynamic sizing risks 1 % of capital up to the disaster stop, and is adopted only if it improves out-of-sample. | accepted |
| D-210 | Stage 12: incubation of 3 months or 30 trades, whichever is later. Suspension triggers: DD > MC p95, losing streak > p99, CUSUM, slippage drift. Quarterly revalidation; every parameter change is a new version. | accepted |

## D2. Edge-type addendum (spec_addendum_edge_types_v0_1.md §8)
| ID | Decision | Status |
|---|---|---|
| D-230 | Edge types are defined by config (registry, ADR-012); adding a type needs no code change. | accepted |
| D-231 | False breakout (FB) is an independent edge type. | accepted |
| D-232 | A conditional baseline for PB and a session-anchored baseline for OR. | accepted |
| D-233 | Breadth is counted over the groups applicable to the symbol; at least 4 applicable groups. | accepted |
| D-234 | Cross-type trade overlap on one symbol is report-only; control happens at portfolio level. | accepted |
| D-235 | IM is for US equities and indices only. | accepted |
| D-236 | Long-only groups are allowed with `mirror: false` and a written reason. | accepted |
| D-237 | The forbidden filter families per type follow addendum §1.5. | accepted |
| D-238 | 4H bars are used only for 24h markets. | accepted |
| D-239 | OR entry is at the open of the session's 2nd bar. | accepted |
| D-240 | **All five new edge types (PB, FB, VS, IM, OR) are implemented after the MVP.** | accepted |

## E. Engine and metrics contract (from reviews)
| ID | Decision | Status |
|---|---|---|
| D-300 | `exit_idx ≥ entry_idx` always. `exit_idx == entry_idx` is allowed **only** for intrabar exits (disaster_stop, stop_loss, take_profit, trailing). Signal and time exits need `exit_idx ≥ entry_idx + 1`. | accepted |
| D-301 | Gates use `n_trades` = **closed trades**. The engine's grid kernel returns `n_closed_trades` per configuration; the transition count is only `n_entries`. | accepted |
| D-302 | Polars is used only in the `data/` layer. Result Parquet I/O lives in `data/result_io.py`. | accepted |
| D-303 | Indicator oracles: TradingView golden files (primary) plus naive loop implementations. Connors RSI uses the standard `nz` streak, with a bounded-convergence golden test. Ichimoku spans are unshifted (the displacement belongs to the strategy). Supertrend direction follows TradingView (−1 = up). | accepted |
| D-304 | `start_run` requires resolved data snapshots in the run config (enforced in T10a). | accepted |
| D-305 | Local registry: Docker Postgres on port **5433** (a native Windows Postgres uses 5432). | accepted |

| D-306 | `SplitManager.open_holdout` takes a `stage` argument and rejects any caller other than stage 6 (`s06_robust`). It is enforced in code, not only in the pipeline context. | accepted |
| D-307 | **Non-USD quote currencies:** P&L and costs are computed in the quote currency and converted to USD with the conversion pair's **close at the same bar** (MTM each bar; realized at the exit bar). The pairs are EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD and NZDUSD from Dukascopy. **HKD uses the fixed peg 7.80** with a flag, because there is no USDHKD data. This is an engine requirement (T08). | accepted |
| D-308 | Stage-6 Monte Carlo drawdown gate: the p95 of the max drawdown (% of initial capital) must be ≤ **25 %**. It is configurable and will be calibrated later. | accepted |
| D-309 | **One registry of metric names.** The metrics module defines the names; the gate YAML is validated against that registry when it loads, and an unknown metric is an error. The names in T09's `as_gate_dict()` and in T10a's `default.yaml` must be reconciled (batch 2b). | accepted |
| D-310 | The FX/CFD trading week runs from Sunday 17:00 to Friday 17:00 America/New_York. The daily break is learned in New York local time. | accepted |
| D-311 | Keeping the base exit in stage 4 is stage logic, not a gate. Symbol groups equal the asset class until P1. The embargo default is 200 + 50 bars, and the quality thresholds (2 % missing, 15× MAD spikes, stale ≥ 5 bars, 5 % zero volume) are initial values to calibrate later. Rollover triple days come per symbol from the Moneta file (T06b). | accepted |

## F. Tooling (ADR-001 … ADR-011) and workflow
| ID | Decision | Status |
|---|---|---|
| D-400 | Stack per ADR-001…011: custom Numba engine (vectorbt as test oracle only), Parquet+DuckDB, Polars/pandas/NumPy layering, PostgreSQL+SQLAlchemy Core+psycopg3+Alembic, two-level parallelism, Typer+YAML/Pydantic, Jinja2+Plotly reports, uv + Python 3.12, pytest+Hypothesis+ruff+mypy, GitHub Actions. | accepted |
| D-401 | Claude Code opens PRs with `gh`. It merges **only** after the user writes "Approved. Merge …", and only once CI passes. | accepted |
| D-402 | **Critical tasks need supervisor review before merge:** engine (T08), parity (T11), split/holdout manager and gate engine. | accepted |
| D-403 | Workflow: Claude Code drafts the batch plan and task files from features, spec, design and this log, then **stops for supervisor approval** before coding. One session in the main folder; worktrees only when explicitly planned. | accepted |

## H. Broker: Moneta Markets MT5 ECN
The source file is `MT5Moneta-ECN_specification-1.xlsx`, provided by the user on 2026-09-19. It is to be copied immutably to `raw/reference/broker/moneta/`.

| ID | Decision | Status |
|---|---|---|
| D-520 | The execution broker is **Moneta Markets (MT5, ECN)**. Cost profiles are generated **per symbol from the spec file**: spread (reference, in points × point size), commission model, swap model, triple day, contract size and point value. These replace the placeholders (D-013). | accepted |
| D-521 | **Commission models from the file:** FX and metals pay `6.0 USD per lot`; US shares pay none; ETFs pay `12.0 USD per trade` (a few pay none); some EU and other shares pay `0.2 %` or `0.3 % per lot`; indices, commodities, crypto and bonds pay none. The FX `6 USD per lot` is **round turn**, confirmed by the user, i.e. **3 USD per lot per side**. | accepted |
| D-522 | **Swap models from the file:** `in points` per lot per day (FX, metals, commodities, some crypto); `in currency` per lot per day (indices); `in percentage terms` annual on notional (shares, ETFs, most crypto). US shares and most ETFs pay **−6.88 % long / −3.5 % short**, so a charge applies on **both** sides. The triple day comes per symbol from the file: Wednesday for most FX, Friday for indices, commodities and shares. The rollover instant is server midnight. The server time is New York close aligned (GMT+2 winter / GMT+3 summer), so the rollover is **17:00 America/New_York**. | accepted |
| D-523 | **Spread:** for FX, metals and CFDs that have Dukascopy data, the **hourly shape** comes from the Dukascopy bid/ask, **scaled so its mean equals the Moneta reference spread**. Where no data spread exists (US shares, ETFs, symbols without Dukascopy data), the Moneta reference spread is used as a fixed spread. | accepted |
| D-524 | **US equities are traded as share CFDs.** Only **491 US shares + 57 ETFs** are tradable at the broker. Research may run on the full universe, but **the pipeline's default candidate universe is broker-tradable symbols only** (universe flag `broker_symbol`). Results for non-tradable symbols are report-only. A broker-symbol ↔ research-symbol mapping table is required, because the file uses names like `AALG` for AAL, `ABBVIE` for ABBV, `AMAZON` for AMZN, `AT&T` for T and `ALIBABA` for BABA. Build it from ticker and description matching, with a manual override file. | accepted |
| D-525 | The long swap on share CFDs (about −6.9 %/yr) makes multi-week equity holds expensive. The cost model must apply it daily, and the stage-8 report must show the swap share of the total cost. | accepted |
| D-526 | Futures are **research-only** (no futures account). The tradable equivalents at Moneta are the index, commodity and bond CFDs, and future strategies must be validated on the CFD's data or costs before live use. | accepted |

## G. Pending decisions
| ID | Topic | Proposal |
|---|---|---|
| P-04 | Parity reference exports | TradingView trade lists and OHLC for the SPX500 daily MR and one 1H TF strategy (T11). **Reminder: the supervisor asks the user for these files before T11 is planned.** |
