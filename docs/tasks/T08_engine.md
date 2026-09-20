# T08 — Backtest engine — **CRITICAL (D-402)**

**Features:** F-0.3.1 (engine core), F-0.3.2 (basic exits), F-0.3.4 (intrabar ambiguity: tradingview / pessimistic), F-0.3.9 (look-ahead tests) · **Priority:** MVP · **Depends on:** T06b (cost arrays, commission kernel, instrument fields, `round_trip_cost` oracle), T07 (components, `ExitSpec`), T09 (containers = output contract) · **Critical:** stop after the review and wait for **"Approved"** before T10b.

Read first:
- `CLAUDE.md` (rules 2, 3, 4, 6, 8 and the engine conventions).
- `docs/design.md` §4 (engine signature) and §6 (execution contract and Hypothesis invariants), and ADR-001.
- `docs/reviews/T09_review.md`: **the container contract is the output contract**.
- `docs/reviews/T06_review.md` and `docs/reviews/T06b_review.md`.
- `docs/reviews/T07_review.md` (`Bars`, `ExitSpec`, mirror).
- Decisions **D-001 … D-004, D-012, D-060, D-061, D-130, D-300, D-301, D-307, D-312 … D-316, D-326 … D-332, D-335 … D-338**.

## Fixed decisions (do not re-decide)
- Signal at the close of bar *i*, fill at the **open of bar i+1** (D-001). No same-bar execution of a close signal.
- Intrabar modes: `0 = tradingview` (parity only), `1 = pessimistic` (research) (D-002).
- **Ambiguity rules (D-338):**
  1. Parity mode mirrors TradingView, and every such choice is marked **`to_verify` until T11**: listed in the module docstring and the review.
  2. Research mode takes the **pessimistic** choice whenever the bar data is ambiguous.
  3. **No look-ahead** anywhere.
- Mark-to-market equity at every bar close (D-003). Capital 100,000 USD, fixed notional 100,000 USD; one position per strategy, no pyramiding (D-004). **Long and short are separate runs** (F-0.3.1).
- Exits (D-332): time, signal, **fixed disaster stop = entry ∓ 3 × ATR(signal bar)** (D-130; the multiple comes from `StrategySpec.disaster_stop_atr`, never a literal), SL/TP in ATR, trailing ATR, first hit wins. Chandelier and break-even are F-0.3.3 (P1, not claimed).
- `exit_idx == entry_idx` only for intrabar exits (D-300). `ExitReason` codes come from T09.
- The grid kernel returns `n_closed_trades` per configuration (D-301).
- **Sizing (D-313, D-315, D-314, D-328, D-329, D-337):**
  - Research mode:
    - `entry_price_usd = raw open of the fill bar × conversion open of the fill bar` (D-328; 1.0 for USD quotes);
    - `lots = floor((notional_usd / (entry_price_usd × contract_size)) / volume_step) × volume_step`;
    - `qty = lots × contract_size`;
    - if lots < `min_volume`, the entry is **skipped** and counted in `n_skipped_min_volume`, and the strategy stays flat.
  - Symbols without a Moneta profile carry `volume_step_assumed` (D-314).
  - Futures: **fixed contract count, default 1** (config), P&L = Δpoints × point value, flag `contracts_fixed` (D-329, D-061). No notional sizing for futures.
  - Parity mode: qty = notional / close of the signal bar, unrounded, no minimum-volume skip (D-337, `to_verify`).
- **Swap (D-312, D-327):**
  - At a rollover bar where the position is held at the close: notional = |qty| × contract size × close of that bar, converted at that bar (D-307). annual_rate → rate / day_count × notional; points_per_day → points × point size × |qty| × contract size; currency_per_lot_day → amount × lots. Triple day × 3.
  - Stop/target exit inside a rollover bar, research mode: the swap is applied if it is a charge and not if it is a credit.
  - Stop/target exit inside a rollover bar, parity mode: no swap (`to_verify`).
- Non-USD quote currencies (D-307, D-328):
  - Spread, slippage, swap and P&L are in the quote currency, converted with the conversion pair's **close of the same bar** (MTM each bar; realized at the exit bar).
  - Commission is converted only when its currency is the quote currency.
  - HKD uses the peg 7.80 from config, with a flag.
- The engine is pure: `engine/` imports only NumPy and Numba, with `@njit(cache=True)` and `prange` for grids. No files, DB, config or logging inside kernels. `engine/` does not import `metrics`, `costs`, `components` or `data`.

## Scope

### 1. Kernel inputs (`engine/`)
Arrays (float64 or bool, length n) and scalars only:
- **Prices:** `open_, high, low, close`, `atr` (the engine reads `atr[signal bar]`).
- **Signals** (evaluated at close): `entry_sig`, `exit_sig`; `direction` (+1 / −1).
- **Exit parameters:** `time_exit_bars` (0 = unused), `sl_atr`, `tp_atr`, `trail_atr` (NaN = unused), `disaster_atr`.
- **Costs:**
  - `half_spread[n]`, `slippage_fixed[n]`, `slippage_atr_frac`;
  - `swap_long[n]`, `swap_short[n]` (credit per unit of notional at the bar's close), `rollover_mask[n]`, `triple_mask[n]`;
  - commission `(code, p0, p1, p2)` and `commission_in_quote`.
- **Currency:** `fx_open[n]` (sizing, D-328) and `fx_close[n]` (P&L/MTM, D-307). Both are 1.0 for USD quotes.
- **Sizing:**
  - `sizing_mode`: 0 = research lots, 1 = fixed contracts, 2 = parity;
  - `notional`, `contracts`, `point_value`, `contract_size`, `volume_step`, `min_volume` (lots);
  - `initial_capital`.
- **Mode:** `intrabar_mode`.

`engine/commission.py`: the T06/T06b `commission_kernel` (codes 0–4) under `@njit(cache=True)`; a test pins it to `costs.arrays.commission_kernel` for every code.

### 2. Event order per bar *j* (design §6)
1. **Open:** execute the orders scheduled at close *j−1*: the exit first, then the entry (D-336, `to_verify`). A stop level already crossed by the open gap fills **at the open**.
2. **Intrabar:** disaster, SL, TP and trailing via high/low.
   - `tradingview`: high closer to the open → O→H→L→C, else O→L→H→C; a tie takes the pessimistic order (D-335, `to_verify`).
   - `pessimistic`: every stop before TP.
   - Stop checks start on the entry bar itself; an intrabar exit there gives `exit_idx == entry_idx` (D-300).
3. **Close:**
   - schedule the signal and time exits for *j+1*;
   - evaluate the entry signal when flat or when an exit is scheduled;
   - apply the swap (D-312, D-327);
   - record `equity_mtm`, `in_position`, `realized_pnl`.
- **Time exit:** `N` bars → exit at the open of `entry_idx + N` (`bars_held = N`).
- **End of data:** an entry signal on the last bar is not filled. A position still open at the last bar is marked (`open_pnl_end`).
- **Warm-up:** no entry while `atr[signal bar]` is NaN or ≤ 0.

### 3. Prices and costs (D-326)
- **Levels:** stop and target levels come from the raw open of the entry bar and `atr[signal bar]`; triggers use raw high/low.
- **Fills:** long entry = base + half-spread + slippage; long exit = base − half-spread − slippage; short is mirrored.
- **Slippage:** `slippage_fixed[j] + slippage_atr_frac × atr[ref]`, where ref = the signal bar for entries and signal/time exits, and *j−1* for intrabar exits.
- **Cost fields:** `cost_spread`, `cost_slippage`, `cost_commission` and `cost_swap` (negative = credit), all in USD. `pnl_net = pnl_gross − Σ costs` (the T09 identity).
- **Trade stats:** `mae` and `mfe` in money; `atr_at_entry = atr[signal bar]`.

### 4. Outputs
- `simulate(...)` returns:
  - trade arrays with every `TradeLog` field;
  - equity arrays (`equity_mtm`, `in_position`, `realized_pnl`, `open_pnl_end`);
  - `n_skipped_min_volume`.
- `simulate_grid(..., entry_sig_matrix, exit_sig_matrix, param arrays)` runs `prange` over a **column chunk** (D-331). It returns `equity_matrix`, `in_position_matrix`, `n_closed_trades` and `n_skipped_min_volume` (int64), i.e. the T09 `core_metrics_batch` inputs. **No trade lists per cell.**
- Batch = single: column *k* equals `simulate` with configuration *k*, bit for bit.
- **T09 contract extension** (additive; the defaults keep old results valid, the T09 tests stay green, and the change is listed in the review):
  - `RunMeta` gains `n_skipped_min_volume: int = 0`, `volume_step_assumed: bool = False` and `contracts_fixed: bool = False`;
  - `as_gate_dict()` gains `n_skipped_min_volume`, `min_volume_skip_flag` (1.0 when > 0), `volume_step_assumed` and `contracts_fixed`.

### 5. Python glue outside `engine/`
- `pipeline/backtest.py`: `run_backtest(bars, spec: StrategySpec, costs: CostArrays, *, direction, intrabar_mode, fx: ConversionArrays | None, sizing) -> RunResult`. It chains components → signals and `ExitSpec`, then cost arrays → the kernel, then the `TradeLog`, `EquityCurve` and `RunMeta` containers. `RunResult` validation must pass for every run.
- **Conversion series (D-316)**, in `data/`:
  - `DataAccess.conversion_series(pair, window)` returns the conversion pair's open and close aligned to the traded bars' timestamps (as-of, closed values only). The window is exactly the traded symbol's segment, and a window that ends after that segment's end is refused.
  - For a holdout run, the same window comes from the traded candidate's holdout access. Reading the pair **does not record or consume a holdout access for the pair**.
  - The pairs and the HKD peg come from `configs/costs/fx_conversion.yaml`.
  - This touches the holdout path, so it is part of this critical review.

## Tests (tests first; names start with the feature ID)
- **F-0.3.1 hand fixtures** (`tests/unit/test_F_0_3_1_engine.py`): synthetic series of 10–20 bars in which every trade price, qty, cost component, swap day and equity value is computed by hand. Cases:
  - a long and a short with signal exits;
  - a non-USD quote (commission in USD);
  - a futures run with fixed contracts and a point value.
  Every value must be exactly equal, or within rel 1e-12.
- **Required by D-312 … D-315** (`tests/unit/test_F_0_3_1_engine_sizing_swap.py`):
  1. a hand-computed **multi-day swap with a changing close price, including a triple day**, for a long and a short, plus a non-USD case converted at each rollover bar. Engine `cost_swap` = hand value = T06b `round_trip_cost`;
  2. **qty rounding with floor** (a share CFD with step 0.1, FX with step 0.01 lot × 100,000): the lots are floored and the entry notional is ≤ 100,000 USD;
  3. **a signal skipped below the minimum volume**: no trade, the strategy stays flat, `n_skipped_min_volume = 1`, and the flag is set in `RunMeta` and `as_gate_dict()`; the grid kernel gives the same count;
  4. **parity mode is unaffected by rounding**: the same signals in `tradingview` mode give the unrounded qty (notional / signal-bar close) and no skip;
  5. the `volume_step_assumed` and `contracts_fixed` flags reach `RunMeta`.
- **D-327:** a stop exit inside a rollover bar. Research mode charges a negative swap and ignores a positive one; parity mode charges none.
- **D-328, no look-ahead in sizing:** changing the conversion close (or any later value) of the fill bar does not change the qty; only the fill bar's open counts.
- **F-0.3.2:** each exit type closes at the right bar and price:
  - signal exit and time exit (N bars);
  - disaster stop intrabar, and disaster stop **gapped through at the open**;
  - SL, TP and trailing;
  - a first-hit combination on the same bar;
  - an exit and a re-entry at the same open.
- **F-0.3.4:** a bar where SL and TP are both touched:
  - `tradingview` follows the open-proximity path (both orders, plus the tie);
  - `pessimistic` always takes the stop; the same holds for disaster vs TP;
  - a same-bar exit on the entry bar gives a valid `RunResult`.
- **Oracle (D-330, never skipped):** `tests/oracle/naive_engine.py` is a plain-Python, bar-by-bar reference engine written from this task's rules, sharing no code with `engine/`. `tests/oracle/test_F_0_3_1_oracle.py` checks that `simulate` equals the naive engine (rel 1e-12, identical trade indices and reasons) on the hand fixtures and on Hypothesis-generated inputs. The generated inputs cover:
  - costs, swap, triple days and conversion;
  - rounding and skips;
  - every exit type;
  - both intrabar modes;
  - all three sizing modes.
  vectorbt is added to the dev group **only if** `uv add --dev vectorbt` leaves the numba/numpy pins unchanged, in which case a zero-cost MA-cross cross-check is added. Otherwise the review reports that it was not added, and the naive oracle still runs.
- **Property tests** (`tests/property/test_F_0_3_engine_properties.py`, Hypothesis, design §6), with rounding enabled:
  1. P&L conservation;
  2. no same-bar execution of close signals;
  3. costs monotonic;
  4. truncation invariance;
  5. long/short mirror (zero costs, step → 0);
  6. batch = single.
  Every generated run must pass `RunResult` validation.
- **F-0.3.9 leakage** (`tests/leakage/test_F_0_3_9_engine_truncation.py`, mandatory): for a random t, running components + engine on bars `[0, t]` gives identical equity for bars `< t` and identical trades that exit before `t`. This must hold for every registered T07 entry component and every exit type.
- **D-316** (`tests/leakage/test_F_0_3_9_conversion_window.py`, mandatory):
  - `conversion_series` never returns a bar after the traded segment's end, and it refuses a longer window;
  - a holdout run of EURGBP reads GBPUSD over the same window and leaves GBPUSD's holdout **unconsumed** (a DB test: GBPUSD's own later `open_holdout` still succeeds once).
- **Reproducibility:** two runs with the same inputs are bit-identical.

## Acceptance
- ruff, format, mypy (engine kernels relaxed; `pipeline/backtest.py` and `data/` strict), the fast suite, `pytest tests/parity tests/leakage tests/oracle`, `pytest -m db` with 0 skipped.
- A benchmark in the review: `simulate` on 60,000 hourly bars, and `simulate_grid` on 2,000 configurations × 2,500 daily bars (wall time, cores). The numbers are reported only; there are no thresholds.
- The acceptance-reviewer subagent has run and its findings are fixed.

## Review summary
`docs/reviews/T08_review.md` contains:
- the kernel signatures and the event order as implemented;
- the hand fixtures with their numbers;
- the **`to_verify` list** (every parity-mode choice, D-338);
- how each acceptance criterion and each design §6 invariant is tested;
- the oracle design;
- the vectorbt outcome;
- the T09 contract extension;
- the D-316 conversion path;
- the benchmark;
- deviations and open questions.

**Then stop and wait for "Approved".**
