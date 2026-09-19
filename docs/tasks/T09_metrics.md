# T09 — Result containers (contract) and standard metrics

**Features:** F-0.5.1 (team metrics), F-0.5.2 (risk & distribution metrics), F-0.5.4 (yearly/monthly tables) · **Priority:** MVP · **Depends on:** T01 only (branch from `main`)
**Branch:** `feat/T09-metrics`.

**Contract-first:** this task defines the **result containers that the engine (T08, written later) must produce**. Design them carefully; they are the contract between engine, metrics, gates and reports. Read `CLAUDE.md`, `docs/design.md` §6 (engine output), the metric definitions in `docs/features.md` (F-0.5.x) and the team conventions below.

## Team conventions (fixed decisions)
- Initial capital 100,000 USD; fixed notional 100,000 USD per trade (default). All percentages are **of initial capital**.
- Equity is **mark-to-market** at each bar close.
- **Annual drawdown, two versions:**
  - (a) **from the start of each year**, the **gate/target basis**: running peak starts at the equity at the end of the previous year;
  - (b) **against the all-time running peak**: the max drawdown occurring inside that year.

  Both are expressed as % of initial capital.
- **Partial years count fractionally.** Average annual profit = total net profit / years covered, where years = (last ts − first ts) / 365.25 days. The average annual drawdown is the mean of the yearly values **weighted by each year's covered fraction**.
- **Target metric:** `profit_dd_ratio` = average annual profit / average annual drawdown (version a). If the denominator is 0, the result is `inf` and a flag is set.
- **Exposure** = share of bars with an open position. **Return per exposure** = average annual profit (% of capital) / exposure.
- Calendar boundaries follow the bar `ts` date in UTC (daily bars are stamped at the session date 00:00 UTC).

## Scope

### 1. Containers (`metrics/containers.py`)
- **`TradeLog`**: columnar NumPy arrays (or a frozen dataclass of arrays), one row per closed trade:
  - timing and direction: `entry_idx, exit_idx, entry_ts, exit_ts, direction (+1/−1), qty, entry_price, exit_price`;
  - money: `pnl_gross, cost_spread, cost_slippage, cost_commission, cost_swap, pnl_net`;
  - trade diagnostics: `exit_reason (enum code), mae, mfe, atr_at_entry, bars_held`.
- **`EquityCurve`**: `ts, equity_mtm, in_position (bool), realized_pnl`, plus `initial_capital` and `notional`.
- **`RunResult`**: a `TradeLog`, an `EquityCurve` and `meta` (symbol, timeframe, spec_hash, `cost_status` placeholder|verified, `intrabar_mode`, `stress`).
- **Validation, raising on violation:**
  - `pnl_net = pnl_gross − all costs`;
  - `exit_idx ≥ entry_idx + 1`;
  - equity at the end = `initial_capital` + Σ `pnl_net` + open P&L (the open position at the end is marked, and a flag is set);
  - `ts` strictly increasing.
- Parquet round-trip helpers (for the artifacts of passed candidates).

### 2. Metrics (`metrics/standard.py`, `metrics/risk.py`)
- **F-0.5.1:**
  - `avg_annual_profit` ($ and %), `avg_annual_dd_ystart`, `avg_annual_dd_peak`, `profit_dd_ratio`;
  - `exposure`, `return_per_exposure`;
  - `profit_factor`, `win_rate`, `n_trades`, `avg_bars_held`;
  - `expectancy` in $, in % of notional, and in ATR units (`pnl_net / (qty × atr_at_entry)`).
- **F-0.5.2:**
  - Sharpe and Sortino on daily P&L / initial capital. Daily = the last equity per UTC date. Periods per year come from config: 252 for `us_equity`, 260 for 24x5 markets;
  - max drawdown (all-time peak, % of initial capital);
  - Ulcer index;
  - longest time under water (bars and calendar days);
  - skewness and excess kurtosis of per-trade returns (`pnl_net` / notional).
- `MetricsReport` (Pydantic, frozen) with all values plus flags (`inf_ratio`, `open_position_marked`, `cost_placeholder`). `as_gate_dict()` gives the metric names the gate engine uses. Document the names in the module docstring.

### 3. Tables (F-0.5.4, `metrics/tables.py`)
- A yearly table: profit, dd_ystart, dd_peak, trades, win rate, and share of profitable months.
- A monthly table: profit and trades.
- The monthly sums equal the yearly sums, which equal the total. This is tested.

### 4. Batch path for grids (`metrics/batch.py`)
- `core_metrics_batch(equity_matrix[n_bars, n_configs], in_position_matrix, ts, initial_capital) -> dict[str, array[n_configs]]`, a Numba kernel.
- It computes, per configuration, `avg_annual_profit`, `avg_annual_dd_ystart`, `profit_dd_ratio`, `exposure` and `n_trades` (from position transitions).
- Stage 2/3 will call this for up to 2000 configurations.
- **It must equal the single-run functions exactly** (tested).

## Tests
- **Hand-computed fixtures:**
  - a 3-year daily equity with a partial first and last year: fractional years, both DD versions, the weighted average DD, and the ratio;
  - one trade spanning a year boundary;
  - an open position at the end;
  - a zero-drawdown case (inf flag).
- **Property tests (Hypothesis):**
  - the table sums are consistent;
  - drawdowns ≥ 0;
  - `dd_ystart ≤ dd_peak` for each year;
  - scaling all P&L by k scales profits and DDs by k and leaves `profit_dd_ratio` unchanged;
  - batch = single;
  - adding a cost never increases `avg_annual_profit`.
- **Container validation:** each violation raises.

## Acceptance
ruff, format, mypy (strict for `metrics/containers.py` and `standard.py`), pytest pass; CI green. **No new dependencies** except `numba` and `numpy` if they are not yet on `main`. If T07 has not merged yet, add them with the same versions T07 uses: `numba 0.67`.

## Review summary
Write it to `docs/reviews/T09_review.md`. Include:
- the container field tables (this is the contract for T08);
- the metric names returned by `as_gate_dict()`;
- the hand-computed fixture results;
- the batch-vs-single check;
- deviations and open questions.
