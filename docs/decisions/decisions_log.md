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
| D-013 | Costs are mandatory. Until the broker is known, **placeholder profiles** (T06 table) are used and every result carries a `cost_placeholder` flag. | accepted |
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
| D-060 | Source: the TradeStation 1H export (`raw/futures/tradestation/1H`, 64 roots, 2006 → 2025-07-09). Additive back-adjustment (negative prices exist). Labels are **bar-end**, exchange-local time (US/Central; ICE softs assumed US/Eastern, `to_verify`). The adapter converts to bar-start UTC. | accepted (roll rule unknown) |
| D-061 | Futures are sized in **contracts**; P&L = Δpoints × point value (`$/Big Point` from the export header). Signals and ATR are in points, never in percent. **This is an engine design change and must be in T08's contract** (qty in contracts when asset_class = futures). | accepted |
| D-062 | Futures daily bars are built from 1H. `1440min` / `Daily` are not imported. | proposed |

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

## E. Engine and metrics contract (from reviews)
| ID | Decision | Status |
|---|---|---|
| D-300 | `exit_idx ≥ entry_idx` always. `exit_idx == entry_idx` is allowed **only** for intrabar exits (disaster_stop, stop_loss, take_profit, trailing). Signal and time exits need `exit_idx ≥ entry_idx + 1`. | accepted |
| D-301 | Gates use `n_trades` = **closed trades**. The engine's grid kernel returns `n_closed_trades` per configuration; the transition count is only `n_entries`. | accepted |
| D-302 | Polars is used only in the `data/` layer. Result Parquet I/O lives in `data/result_io.py`. | accepted |
| D-303 | Indicator oracles: TradingView golden files (primary) plus naive loop implementations. Connors RSI uses the standard `nz` streak, with a bounded-convergence golden test. Ichimoku spans are unshifted (the displacement belongs to the strategy). Supertrend direction follows TradingView (−1 = up). | accepted |
| D-304 | `start_run` requires resolved data snapshots in the run config (enforced in T10a). | accepted |
| D-305 | Local registry: Docker Postgres on port **5433** (a native Windows Postgres uses 5432). | accepted |

## F. Tooling (ADR-001 … ADR-011) and workflow
| ID | Decision | Status |
|---|---|---|
| D-400 | Stack per ADR-001…011: custom Numba engine (vectorbt as test oracle only), Parquet+DuckDB, Polars/pandas/NumPy layering, PostgreSQL+SQLAlchemy Core+psycopg3+Alembic, two-level parallelism, Typer+YAML/Pydantic, Jinja2+Plotly reports, uv + Python 3.12, pytest+Hypothesis+ruff+mypy, GitHub Actions. | accepted |
| D-401 | Claude Code opens PRs with `gh`. It merges **only** after the user writes "Approved. Merge …", and only once CI passes. | accepted |
| D-402 | **Critical tasks need supervisor review before merge:** engine (T08), parity (T11), split/holdout manager and gate engine. | accepted |
| D-403 | Workflow: Claude Code drafts the batch plan and task files from features, spec, design and this log, then **stops for supervisor approval** before coding. One session in the main folder; worktrees only when explicitly planned. | accepted |

## G. Pending decisions
| ID | Topic | Proposal |
|---|---|---|
| P-01 | Edge-type addendum §8 (10 items) | The supervisor proposals given in chat: registry via config (ADR-012); FB as an independent type; conditional and session-anchored baselines; breadth over applicable groups (min 4); cross-type overlap report-only; IM on US only; long-only groups with `mirror: false` and a reason; forbidden filters per §1.5; 4H only for 24h markets; OR entry at the open of bar 2. Types PB/FB/VS are P1, IM/OR are P2, after the MVP. |
| P-02 | Futures | Roll rule; confirm back-adjustment and exchange time; ICE softs timezone; the `- Copy` files (D-060/062). |
| P-03 | Broker cost profile | Real broker, spreads, commission and swap to replace the placeholders (D-013). |
| P-04 | Parity reference exports | TradingView trade lists and OHLC for the SPX500 daily MR and one 1H TF strategy (T11). |
