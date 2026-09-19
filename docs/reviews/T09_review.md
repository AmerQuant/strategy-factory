# T09 review — Result containers (contract) and standard metrics

**Features:** F-0.5.1, F-0.5.2, F-0.5.4 · **Branch:** `feat/T09-metrics` (worktree `StrategyFactory_T09`, rebased onto `main` at `8031958`) · **Status:** done (ruff, format, mypy, fast suite green locally; CI runs on push)

## Dependencies
**None added.** The branch was rebased onto `main` after T07 merged, and T07 had already added numba 0.67.0 (with llvmlite 0.49.0) and numpy 2.5.3. `uv lock` after the rebase changed nothing. The first T09 code commit is still titled "add numba 0.67.0 and numpy 2.5.3", but after the rebase it only adds the strict-mypy block.

`pyproject.toml`: a strict-mypy override for `metrics.containers` and `metrics.standard`, placed after T07's strict `components` block. Both blocks are kept.

## Files
| file | content |
|---|---|
| `src/strategy_factory/metrics/containers.py` | `TradeLog`, `EquityCurve`, `RunMeta`, `RunResult`, `ExitReason`, `ContainerError` (strict mypy) |
| `src/strategy_factory/data/result_io.py` | `write_run_result` / `read_run_result` (Parquet + `meta.json`, write-once). Moved from `metrics/artifacts.py` in Follow-up 1 |
| `src/strategy_factory/metrics/standard.py` | F-0.5.1 metrics, `CoreMetrics`, `MetricsReport`, `compute_metrics` (strict mypy) |
| `src/strategy_factory/metrics/risk.py` | F-0.5.2: daily returns, Sharpe, Sortino, drawdown series, max DD, Ulcer, under-water, skew/kurtosis |
| `src/strategy_factory/metrics/tables.py` | F-0.5.4: `yearly_table`, `monthly_table` (`YearRow`, `MonthRow`) |
| `src/strategy_factory/metrics/batch.py` | `core_metrics_batch` (grid path) |
| `src/strategy_factory/metrics/_kernels.py` | Numba kernels: `yearly_drawdowns`, `weighted_mean`, `position_entries`, `core_one`, `core_batch` (`prange`) |
| `src/strategy_factory/metrics/_calendar.py` | fractional years, per-year weights, month/day keys (UTC) |
| `src/strategy_factory/metrics/config.py` + `configs/metrics/default.yaml` | `MetricsConfig.periods_per_year` = `{us_equity: 252, "24x5": 260}` |
| `tests/fixtures/metrics_runs.py` | hand fixture, zero-DD fixture, `RunSpec`/`build_run` + `run_specs()` Hypothesis strategy that builds runs satisfying the contract |
| `tests/unit/test_F_0_5_1_containers.py` (34), `test_F_0_5_1_standard_metrics.py` (9), `test_F_0_5_1_batch.py` (4), `test_F_0_5_2_risk_metrics.py` (10), `test_F_0_5_4_tables.py` (4), `tests/property/test_F_0_5_metrics_properties.py` (7 properties × 150 examples) | tests |

## Container contract (for T08)
General: arrays are 1-D NumPy, copied and made **read-only** on construction. `ts` is `datetime64[ns]` holding UTC bar-start. Validation raises `ContainerError`, a subclass of `SfacError`.

### `TradeLog`: one row per **closed** trade, ordered by `entry_idx`
| field | dtype | meaning / rule |
|---|---|---|
| `entry_idx` | int64 | bar at whose **open** the entry fills (signal bar = `entry_idx − 1`); ≥ 0 |
| `exit_idx` | int64 | bar in which the exit fills (at its open or intrabar); **always ≥ `entry_idx`**. `exit_idx == entry_idx` is allowed **only** for intrabar reasons (STOP_LOSS, TAKE_PROFIT, DISASTER_STOP, TRAILING_STOP). SIGNAL and TIME_EXIT need `exit_idx ≥ entry_idx + 1`. ≤ last bar |
| `entry_ts`, `exit_ts` | datetime64[ns] | must equal `ts[entry_idx]`, `ts[exit_idx]`; `exit_ts ≥ entry_ts` |
| `direction` | int64 | +1 long / −1 short |
| `qty` | float64 | > 0 (units; default sizing `notional / entry_price`) |
| `entry_price`, `exit_price` | float64 | fill prices incl. half-spread and slippage; > 0 |
| `pnl_gross` | float64 | before costs |
| `cost_spread`, `cost_slippage`, `cost_commission` | float64 | money, ≥ 0 |
| `cost_swap` | float64 | money; a negative value is a swap credit |
| `pnl_net` | float64 | **= `pnl_gross − (spread + slippage + commission + swap)`** (relative tolerance 1e-9) |
| `exit_reason` | int64 | `ExitReason`: 0 SIGNAL, 1 STOP_LOSS, 2 TAKE_PROFIT, 3 DISASTER_STOP, 4 TIME_EXIT, 5 TRAILING_STOP (new codes are appended only). `INTRABAR_EXIT_REASONS` = {1, 2, 3, 5} |
| `mae`, `mfe` | float64 | max adverse / favourable excursion in **money** (`qty × price distance`), ≥ 0 |
| `atr_at_entry` | float64 | ATR of the signal bar; > 0 |
| `bars_held` | int64 | **= `exit_idx − entry_idx`** (0 for a same-bar intrabar exit) |

Other rules: all floats finite; trades must not overlap (one position, no pyramiding). `entry_idx[k+1] ≥ exit_idx[k]`, so an exit and a re-entry at the same open are allowed. `entry_idx` is strictly increasing, so two trades cannot enter on the same bar.

### `EquityCurve`: one row per bar (at least 2 bars)
| field | dtype | meaning / rule |
|---|---|---|
| `ts` | datetime64[ns] | UTC bar-start, **strictly increasing** |
| `equity_mtm` | float64 | mark-to-market equity at the bar close |
| `in_position` | bool | a position is held at the **close** of the bar. A trade occupies bars `entry_idx … exit_idx − 1`; a same-bar trade occupies none |
| `realized_pnl` | float64 | cumulative `pnl_net` of trades closed up to this bar |
| `initial_capital` | float | > 0 (default 100,000) |
| `notional` | float | > 0 (default 100,000) |
| `open_pnl_end` | float | marked P&L of the position still open at the last bar; must be 0 when flat |

Rules: on flat bars `equity = initial_capital + realized_pnl`; **final equity = `initial_capital + realized_pnl[-1] + open_pnl_end`**. `open_position_marked` is `in_position[-1]`.

### `RunMeta` (frozen Pydantic) and `RunResult`
`RunMeta`: `symbol`, `timeframe`, `spec_hash`, `cost_status ∈ {placeholder, verified}`, `intrabar_mode ∈ {tradingview, pessimistic}`, `stress: str | None`.
`RunResult(trades, equity, meta)` checks the parts against each other:
- trade indices lie within the curve;
- `entry_ts`/`exit_ts` equal the curve's `ts`;
- `realized_pnl[-1] = Σ pnl_net`;
- **final equity = capital + Σ pnl_net + open P&L**;
- `in_position` is True **exactly** on the bars the trades occupy, plus the final run of an open position, which must start at or after the last exit.

### Batch path and trade counts (gates use `n_trades` = closed trades)
`core_metrics_batch(equity_matrix, in_position_matrix, n_closed_trades, ts, initial_capital)`:
- `n_closed_trades` is an int array of length `n_configs`. **The T08 grid kernel must return it**, one closed-trade count per configuration.
- It is reported unchanged as **`n_trades`**. This is the same number as `MetricsReport.n_trades` (`len(TradeLog)`), and it is **the count the gates use**.
- **`n_entries`** (batch and `MetricsReport`) counts flat → in-position transitions of `in_position`. It is a diagnostic only: it counts a position still open at the end, merges an exit and re-entry at the same open, and misses same-bar trades.

### Parquet artifacts (`strategy_factory.data.result_io`)
`write_run_result(result, dir)` writes `trades.parquet`, `equity.parquet` and `meta.json` (with `schema_version = 1`). It refuses a non-empty directory, so artifacts are write-once. `read_run_result` rebuilds the containers and so re-validates them.

## Metric names from `MetricsReport.as_gate_dict()`
Every value is a `float`; flags are 0.0/1.0. `*_pct` fields are in percent units of **initial capital**, except `expectancy_pct`, which is % of notional. `exposure` is a fraction from 0 to 1.

`years, total_net_profit_usd, avg_annual_profit_usd, avg_annual_profit_pct, avg_annual_dd_ystart_usd, avg_annual_dd_ystart_pct, avg_annual_dd_peak_usd, avg_annual_dd_peak_pct, profit_dd_ratio, exposure, return_per_exposure, n_trades, n_entries, profit_factor, win_rate, avg_bars_held, expectancy_usd, expectancy_pct, expectancy_atr, sharpe, sortino, max_dd_pct, ulcer_index, max_underwater_bars, max_underwater_days, trade_return_skew, trade_return_excess_kurtosis, inf_ratio, open_position_marked, cost_placeholder`

`core_metrics_batch` returns `avg_annual_profit_usd, avg_annual_profit_pct, avg_annual_dd_ystart_usd, avg_annual_dd_ystart_pct, profit_dd_ratio, exposure, n_trades` (closed trades, passed in as `n_closed_trades`) and `n_entries` (transitions). Changed in Follow-up 1.

The full definitions are in the docstrings of `standard.py`, `risk.py`, `tables.py` and `_calendar.py`.

## Hand-computed fixture results
**Fixture:** 10 daily bars from 2021-07-02 to 2023-07-02 (730 days), capital 100,000.
- Equity: 100000, 105000, 102000, 99500, 108000, 104000, 110000, 109000, 112000, 111000.
- Trades:
  - T1: long, bars 1→3, net −500. It spans the 2021/22 year end.
  - T2: short, bars 4→7, net +9,500.
  - T3: long from bar 8, still open at the end with +2,000.

| metric | hand value | test |
|---|---|---|
| years | 730/365.25 = 1.998631 | exact (rel 1e-12) |
| year weights 2021/22/23 | 183/365.25, 365/365.25, 182/365.25 (sum = years) | ✓ |
| dd from year start per year | 3,000 / 4,000 / 1,000 | exact |
| dd vs all-time peak per year | 3,000 / 5,500 / 1,000 | exact |
| avg annual profit | 11,000/years = 5,503.77 $ = 5.5038 % | ✓ |
| avg annual dd (a, weighted) | (183·3000+365·4000+182·1000)/730 = 3,001.37 $ = 3.0014 % | ✓ |
| avg annual dd (b, weighted) | (183·3000+365·5500+182·1000)/730 = 3,751.37 $ = 3.7514 % | ✓ |
| profit_dd_ratio | 5,503.77 / 3,001.37 = 1.83375 | ✓ |
| exposure / return per exposure | 7/10 = 0.7 / 7.8625 | ✓ |
| n_trades / n_entries | 2 / 3 | ✓ |
| PF / win rate / avg bars held | 19 / 0.5 / 2.5 | ✓ |
| expectancy $ / % / ATR | 4,500 / 4.5 / (−0.25+1.9)/2 = 0.825 | ✓ |
| max DD / Ulcer | 5.5 % / √(57.25/10) = 2.3927 | ✓ |
| longest under water | 2 bars; 243 days (peak 2021-10-01 → recovery 2022-06-01) | ✓ |
| Sharpe / Sortino (252) | 4.0982 / 9.5763, compared with the stdlib `statistics` reference | rel 1e-12 |
| skew / excess kurtosis | 0 / −2 (two trades) | ✓ |
| open position at end | `open_position_marked`; the +2,000 open P&L is in the profit; T3 is not in `n_trades` | ✓ |
| yearly profit 2021/22/23 | 2,000 / 8,000 / 1,000. The year-end MTM of T1 stays in 2021, and T1 is counted in 2022 (its exit year) | ✓ |
| profitable-month share | 1/3, 1/2, 1/3 | ✓ |
| monthly sum = yearly sum = total | exact on this fixture | ✓ |
| zero-DD fixture (rising equity) | `profit_dd_ratio = inf`, `inf_ratio` set, PF = inf | ✓ |

## Batch vs single
Both paths call the same Numba function `core_one`. The batch path runs it per column under `prange`, on a Fortran-ordered copy. Kernels use no `fastmath`, so the order of floating-point operations is fixed.

Tests:
- `test_F_0_5_1_batch_equals_single_hand_fixtures`: the hand and zero-DD fixtures, compared with `==`, including `inf`.
- `test_F_0_5_1_batch_layout_independent`: C-order and F-order inputs give identical output.
- Property `test_F_0_5_1_batch_equals_single`: 1–8 random valid runs per example over 2–150 bars, with hourly, daily and 3-day steps. Every key is compared with `==`. It also checks that `compute_metrics` gives the same ratio, and that entries equal closed trades when nothing is open at the end.

Because both paths share one kernel, a separate property (`test_F_0_5_1_core_matches_plain_python_reference`) compares the kernel with a plain-Python implementation written from the definitions.

## Property tests (Hypothesis, 150 examples each; the `ci` profile is derandomized)
- Table sums: monthly = yearly = total for profit (`fsum`, abs 1e-6) and trade counts (exact).
- Drawdowns ≥ 0; per year `dd_ystart ≤ dd_peak`; avg (a) ≤ avg (b) ≤ max DD; year weights sum to `years`.
- Scaling all P&L and costs by k ∈ {0.25, 0.5, 2, 3, 10} scales profit and both DD averages by k and leaves `profit_dd_ratio` unchanged (rel 1e-7; checked for dd > 1 $, or both are inf).
- Adding a cost to any closed trade never increases `avg_annual_profit` ($ or %).
- Batch = single (exact), and core = plain-Python reference.

## Deviations and decisions I made (please confirm)
1. *(Superseded by Follow-up 1: moved to `data/result_io.py`.)* **Polars in `metrics/artifacts.py`.** CLAUDE.md says "Polars only in `data/`". PyArrow is not a dependency, and pandas cannot write Parquet without it. So I used Polars only as the Parquet codec, at this I/O boundary; arrays go in and come out as NumPy. The alternative is to move the helpers into `data/`, which would make `data` depend on `metrics`.
2. **Extra fields and checks in the contract** beyond the task text:
   - `EquityCurve.open_pnl_end` (needed to state the final-equity identity);
   - `in_position` must match the trades exactly;
   - `qty`, prices and `atr_at_entry` must be > 0;
   - `mae`, `mfe` and the spread, slippage and commission costs must be ≥ 0;
   - no overlapping trades.
3. *(Superseded by Follow-up 1: batch `n_trades` = closed trades; transitions = `n_entries`.)* **Batch `n_trades` = position entries.** It is counted from `in_position` transitions, as the task says. It therefore counts an open position at the end, and merges an exit plus re-entry at the same open. `MetricsReport` reports both `n_trades` (closed trades) and `n_position_entries`.
4. **Year weight** = the part of the `[first ts, last ts]` span inside the calendar year, in 365.25-day units, so the weights sum to `years`. Only years that contain bars get a row.
5. **Edge-value choices:**
   - `profit_dd_ratio = inf` whenever the DD is 0, even when profit is 0 too (for example no trades), because the task says so;
   - `return_per_exposure = NaN` when exposure is 0;
   - PF and Sortino are `inf` with no downside, and NaN when everything is zero;
   - trade statistics are NaN with no trades;
   - skew and kurtosis are NaN with fewer than 2 trades.
6. **Choices the documents leave open:**
   - The Ulcer index uses drawdown as **% of initial capital**, following the team convention, not % of the running peak.
   - Time under water: bars = the length of the run under water; days = from the peak bar to the recovery bar, or to the last bar if there is no recovery. The longest in bars and the longest in days are maximised separately.
   - Skew and kurtosis are the population (biased) moments.
   - Sortino uses a target of 0 and the downside mean over all days.
7. **`calendar` is an argument of `compute_metrics`** (`us_equity` / `24x5`), not a `RunMeta` field. The task's meta field list has no calendar field.

## Open questions
- *(Resolved in Follow-up 1.)* **`exit_idx ≥ entry_idx + 1` vs. intrabar stops on the entry bar.** Design §6 checks SL/TP and the disaster stop intrabar in bar *j* after fills at the open of *j*. So an entry at the open of *j* could be stopped out inside bar *j*, which would give `exit_idx == entry_idx`. The contract rejects that, as the task requires. T08 has to decide: either such exits are impossible by design (for example stops start on the next bar), or the rule is relaxed and `in_position` gets a matching convention.
- Should an interior calendar year with no bars at all (a data gap longer than a year) still carry weight? Currently it does not.
- *(Resolved in Follow-up 1: closed trades.)* `n_trades` for the Stage 2/3 gates: should the gates use position entries (the batch path) or closed trades (the full report)?

## Commands run
`uv run ruff check .` ✓ · `uv run ruff format --check .` ✓ · `uv run mypy src` ✓ (65 files) · `HYPOTHESIS_PROFILE=ci uv run pytest -m "not slow and not db"` → 272 passed · `uv run pytest tests/parity tests/leakage`: no tests exist on `main` yet. The metrics layer has no look-ahead surface of its own.

## Follow-up 1 (supervisor decisions)
**1. Parquet I/O moved to the data layer.**
- `metrics/artifacts.py` moved with `git mv` to `src/strategy_factory/data/result_io.py`. It is covered by the strict mypy of `data`.
- `metrics/` now imports no Polars; it uses NumPy, Numba and Pydantic only.
- `data.result_io` imports the containers from `metrics.containers`, so `data` now depends on `metrics`.
- The round-trip tests import `strategy_factory.data.result_io`. Resolves deviation 1.

**2. Exit-index rule.**
- `exit_idx ≥ entry_idx` always.
- `exit_idx == entry_idx` is allowed only for `INTRABAR_EXIT_REASONS` = STOP_LOSS, TAKE_PROFIT, DISASTER_STOP and the new **TRAILING_STOP (code 5, appended)**.
- SIGNAL and TIME_EXIT need `exit_idx ≥ entry_idx + 1`.
- Knock-on changes:
  - `bars_held` may be 0;
  - `exit_ts ≥ entry_ts`;
  - a same-bar trade occupies no `in_position` bar (flat at the close, P&L already realized);
  - `entry_idx` must be strictly increasing, so a same-bar trade cannot be followed by a second entry on that bar.
- Tests (`test_F_0_5_1_containers.py`):
  - same-bar exit accepted for each of the 4 intrabar reasons;
  - rejected for SIGNAL and TIME_EXIT;
  - `exit_idx < entry_idx` rejected for all 6 reasons;
  - a same-bar DISASTER_STOP trade is accepted inside a full `RunResult`;
  - two entries on the same bar are rejected.
- The Hypothesis run builder now also produces same-bar STOP_LOSS trades (hold 0).
- Resolves the first open question.

**3. `n_trades` in the batch path = closed trades.**
- `core_metrics_batch` takes `n_closed_trades` and returns it as `n_trades`.
- The transition count is kept only as `n_entries`. `MetricsReport.n_position_entries` is renamed to `n_entries`, and the same rename applies in `as_gate_dict()` and `CoreMetrics`.
- Gates use `n_trades`. See "Batch path and trade counts" in the contract section.
- Tests:
  - hand fixtures: `n_trades` = [2, 1] and `n_entries` = [3, 1], and both equal the single-run report;
  - a random grid: `n_trades` equals the given array exactly (int64), and `n_entries` is independent of it;
  - input validation: wrong length, a float array or a negative value raise `ValueError`;
  - property: batch equals single for every core key, including `n_entries` and `n_trades`, and `n_entries` = multi-bar trades + (1 if a position is open at the end).
- Resolves deviation 3 and the last open question.

**Checks re-run:**
- `ruff check .` ✓
- `ruff format --check .` ✓
- `mypy src` ✓ (65 files)
- `HYPOTHESIS_PROFILE=ci pytest -m "not slow and not db"`: 285 passed
- `pytest` (including db tests against the local Postgres): 297 passed
- `pytest -m slow`: no slow tests exist yet

**Still open:** whether a calendar year with no bars inside the span should carry weight. It currently does not.

**After the rebase onto `main` (`8031958`, includes T06, T07, T10a):** the only conflict was the strict-mypy blocks in `pyproject.toml`; both are kept. `uv.lock` was regenerated with `uv lock` (no change). `ruff check`, `ruff format --check` and `mypy src` (87 files) pass. Full `pytest` with `SFAC_DB_URL` on port 5433: 768 passed, including the 15 db tests with none skipped.
