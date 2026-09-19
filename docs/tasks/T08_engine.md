# T08 — Backtest engine — **CRITICAL (D-402)**

**Features:** F-0.3.1 (engine core), F-0.3.2 (basic exits), F-0.3.4 (intrabar ambiguity: tradingview / pessimistic), F-0.3.9 (look-ahead tests) · **Priority:** MVP · **Depends on:** T06b (cost arrays, commission kernel), T07 (components, `ExitSpec`), T09 (containers = output contract) · **Critical:** stop after the review and wait for **"Approved"** before T10b.

Read first: `CLAUDE.md` (rules 3, 4, 6, 8 and the engine conventions), `docs/design.md` §4 (engine signature) and §6 (execution contract and Hypothesis invariants), ADR-001, `docs/reviews/T09_review.md` (**the container contract is the output contract**), `docs/reviews/T06_review.md` (cost arrays, commission kernel), `docs/reviews/T06b_review.md`, `docs/reviews/T07_review.md` (Bars, `ExitSpec`, mirror), and decisions **D-001 … D-004, D-012, D-061, D-101, D-130, D-300, D-301, D-307, D-312, D-313, D-314**, plus pending answers **P-14 … P-21**, **P-24 … P-27**.

**Exit scope (P-21):** SL, TP and trailing in ATR multiples are implemented because the `ExitSpec` fields (T07) and the `ExitReason` codes (T09) exist and F-0.3.4 needs SL/TP. Chandelier and break-even stay in F-0.3.3 (P1); F-0.3.3 is **not** claimed.

## Fixed decisions (do not re-decide)
- Signal at the close of bar *i*, fill at the **open of bar i+1** (D-001). No same-bar execution of a close signal.
- Intrabar modes: `0 = tradingview` (parity only), `1 = pessimistic` (research; stop first) (D-002).
- Mark-to-market equity at every bar close (D-003). Capital 100,000 USD, fixed notional 100,000 USD, qty = notional / entry price; one position per strategy, no pyramiding (D-004). **Long and short are separate runs** (F-0.3.1).
- Disaster stop = entry ∓ 3 × ATR(signal bar), fixed, never optimized (D-130); the multiple comes from `StrategySpec.disaster_stop_atr` (config), never a literal in code.
- `exit_idx == entry_idx` only for intrabar exits (D-300). `ExitReason` codes from T09 (`0 SIGNAL, 1 STOP_LOSS, 2 TAKE_PROFIT, 3 DISASTER_STOP, 4 TIME_EXIT, 5 TRAILING_STOP`).
- The grid kernel returns `n_closed_trades` per configuration (D-301).
- Non-USD quote currencies: P&L and costs in the quote currency, converted to USD with the conversion pair's close **of the same bar** (MTM each bar; realized at the exit bar); HKD peg 7.80 with a flag (D-307). The peg value lives in config.
- Futures are sized in **contracts**, P&L = Δpoints × point value (D-061).
- **Swap on the mark-to-market notional (D-312):** at every rollover instant while the position is held, notional = |qty| × contract size × close of the bar containing the rollover, converted to USD at that bar (D-307); annual_rate → rate / day_count × notional; points_per_day → points × point size × |qty| × contract size; currency_per_lot_day → amount × lots; triple day × 3. The engine owns this; T06b's updated `round_trip_cost` is the oracle.
- **Quantity rounding (D-313):** research mode floors the quantity to the broker volume step so the notional never exceeds 100,000 USD; a rounded quantity below the minimum volume is **not traded** and counted in `n_skipped_min_volume` (flagged when > 0). Futures: whole contracts. `tradingview` (parity) mode uses TradingView sizing, not the broker step (P-27).
- **Assumed volume step (D-314):** symbols without a Moneta profile use step 1 share (us_equity) or whole contracts (futures); results carry `volume_step_assumed`.
- The engine is pure: `engine/` imports only NumPy and Numba. `@njit(cache=True)`; grids use `prange`. No files, DB, config or logging inside kernels. `engine/` must not import `metrics`, `costs` or `components` (metrics depends on engine, not the reverse).

## Scope

### 1. Kernel inputs (`engine/`)
Arrays (float64 or bool, length n) and scalars only:
- prices: `open_, high, low, close`, `atr` (ATR of each bar; the engine reads `atr[signal_bar]`).
- signals (evaluated at close): `entry_sig`, `exit_sig` (bool); `direction` (+1 / −1).
- exit params (from `ExitSpec`): `time_exit_bars` (0 = unused), `sl_atr`, `tp_atr`, `trail_atr` (NaN = unused), `disaster_atr`.
- costs (from `CostArrays`, T06/T06b): `half_spread[n]`, `slippage_fixed[n]`, `slippage_atr_frac`, `swap_long[n]`, `swap_short[n]` (credit per unit of notional per day), `rollover_mask[n]`, `triple_mask[n]`, commission `(code, p0, p1, p2)` and `commission_in_quote` (bool; false = USD).
- currency and sizing: `quote_to_usd[n]` (1.0 for USD-quoted symbols), `sizing_mode` (0 notional floored to the broker step, 1 whole contracts, 2 TradingView parity sizing), `notional`, `contracts`, `point_value` (1.0 unless futures), `contract_size`, `volume_step`, `min_volume` (lots, from the profile, D-313/D-314), `initial_capital`.
- `intrabar_mode`.

`engine/commission.py`: the T06 `commission_kernel` copied under `@njit(cache=True)` with code 4 from T06b; a test pins it to `costs.arrays.commission_kernel` for every code.

### 2. Event order per bar *j* (design §6)
1. **Open:** execute orders scheduled at close *j−1* (exit first, then entry — P-25). A stop level already crossed by the open gap fills **at the open** (worse price).
2. **Intrabar:** disaster stop, SL, TP and trailing via high/low. More than one touched → `tradingview`: path O→H→L→C if the high is closer to the open, else O→L→H→C (tie → pessimistic, P-24); `pessimistic`: any stop (disaster/SL/trailing) before TP. Stop checks start on the entry bar itself (an intrabar exit on the entry bar gives `exit_idx == entry_idx`, D-300).
3. **Close:** evaluate exit signal and time exit (schedule for *j+1*), then the entry signal when flat or when an exit is scheduled (P-25); swap for a position held at the close of a rollover bar on the MTM notional of that bar (D-312; ×3 on triple days; P-15); record `equity_mtm`, `in_position`, `realized_pnl`.
- Time exit: `time_exit_bars = N` exits at the open of `entry_idx + N` (`bars_held = N`).
- An entry signal on the last bar is not filled; a position open at the last bar stays open and is marked (`open_pnl_end`, T09).
- No entry while `atr[signal bar]` is NaN or ≤ 0 (warm-up).

### 3. Prices, costs and sizing (design §6, P-14, P-16)
- Stop/target levels are computed from the **base entry price** (the raw open of the entry bar) and `atr[signal bar]`; triggers use raw high/low.
- Fill: long entry = base + half-spread + slippage; long exit = base − half-spread − slippage; short mirrored. Slippage = `slippage_fixed[j] + slippage_atr_frac × atr[signal bar]` (for intrabar exits the reference bar is *j − 1*).
- Commission at entry and exit from the kernel; converted to USD only when `commission_in_quote`.
- qty (D-313, P-26): research mode → lots = floor(notional / (base_entry_price × contract_size × quote_to_usd[signal bar]) / volume_step) × volume_step, units = lots × contract_size (the conversion rate of the signal bar, P-16); lots < `min_volume` → the entry is skipped and `n_skipped_min_volume` += 1, and the strategy stays flat; futures → whole contracts with `point_value` (P-18); parity mode → TradingView sizing, unrounded (P-27).
- Cost components are recorded separately in money (USD): `cost_spread`, `cost_slippage`, `cost_commission`, `cost_swap` (negative = credit); `pnl_gross` and `pnl_net` follow the T09 identity `pnl_net = pnl_gross − Σ costs`.
- `mae`, `mfe` in money from high/low while in the position; `atr_at_entry` = `atr[signal bar]`.

### 4. Outputs
- `simulate(...)` → trade arrays with every `TradeLog` field (design §6 `TradesArray`) and equity arrays (`EquityArray`: `equity_mtm`, `in_position`, `realized_pnl`, plus `open_pnl_end`).
- `simulate_grid(..., entry_sig_matrix, exit_sig_matrix, param arrays)` with `prange` over configurations → `equity_matrix`, `in_position_matrix`, `n_closed_trades` (int64), the exact inputs of T09 `core_metrics_batch`. **No trade lists per cell** (CLAUDE.md "Do not"). Memory bound: the caller passes a column chunk (P-20); the kernel does not allocate beyond the chunk.
- Batch = single: column *k* of `simulate_grid` equals `simulate` with configuration *k*, bit for bit.
- `n_skipped_min_volume` (int) from `simulate`, and one per configuration from `simulate_grid`. **T09 contract extension (additive, defaults keep old results valid):** `RunMeta` gains `n_skipped_min_volume: int = 0` and `volume_step_assumed: bool = False`; `as_gate_dict()` gains `n_skipped_min_volume` and the flags `min_volume_skip_flag` (1.0 when > 0) and `volume_step_assumed`. The T09 tests stay green; the change is listed in the review.

### 5. Python glue outside `engine/` (`pipeline/backtest.py`)
`run_backtest(bars, spec: StrategySpec, costs: CostArrays, *, direction, intrabar_mode, fx: ConversionArrays | None, sizing) -> RunResult`:
components → signals and `ExitSpec`; `CostArrays` → kernel arrays; kernel → `TradeLog`, `EquityCurve`, `RunMeta` (with `cost_status`, `intrabar_mode`, `stress`, `n_skipped_min_volume`, `volume_step_assumed`). `RunResult` validation (T09) must pass for every run. A `ConversionArrays` builder that takes the conversion pair's closes aligned to the traded bars is included, but **wiring it to the data layer waits for P-17**; tests use synthetic arrays.

## Tests (tests first; names start with the feature ID)
- **F-0.3.1 hand fixtures** (`tests/unit/test_F_0_3_1_engine.py`): 3–4 synthetic series of 10–20 bars where every trade price, qty, cost component, swap day and every equity value is computed by hand in the test file: a long and a short with signal exits, one with a swap across a triple day, one with a non-USD quote (`quote_to_usd` ≠ 1, commission in USD), one futures run with `point_value` and contracts. Assert exact equality (or rel 1e-12).
- **F-0.3.2** each exit type closes at the right bar and price: signal, time (N bars), disaster stop intrabar, disaster stop **gapped through at the open**, first-hit combination (time vs signal vs disaster on the same bar), exit + re-entry at the same open.
- **F-0.3.4** a bar where SL and TP are both touched: `tradingview` picks by the open-proximity path (both orders, plus the tie), `pessimistic` always takes the stop. Same for the disaster stop vs TP. Same-bar intrabar exit on the entry bar gives `exit_idx == entry_idx` and a valid `RunResult`.
- **Property tests (Hypothesis, design §6)** in `tests/property/test_F_0_3_engine_properties.py`:
  1. P&L conservation: Σ `pnl_net` + open P&L = final equity − initial capital;
  2. no same-bar execution: every signal exit/entry fill is ≥ 1 bar after its signal;
  3. costs monotonic: raising any cost component (spread, slippage, commission, swap charge) never raises net profit;
  4. truncation invariance (see F-0.3.9);
  5. long/short mirror: short on the reflected series (`Bars.mirrored`) equals long on the original with zero costs;
  6. batch = single (bit-identical).
  Every generated run must also pass `RunResult` validation.
- **F-0.3.9 leakage** in `tests/leakage/test_F_0_3_9_engine_truncation.py`: for random t, running components + engine on bars `[0, t]` gives identical equity for bars `< t` and identical trades that exit before `t`, for every registered T07 entry component and for every exit type. This is a mandatory gate (never skipped).
- **Oracle** (`tests/oracle/`, marker `oracle`): a simple MA-cross long-only strategy with zero costs vs vectorbt on the same signals (next-open fills). vectorbt is a **test-only** dependency (P-19 asks whether to add it now); if not added, the oracle test is written and skipped with an explicit reason — the parity/leakage folders are unaffected.
- Reproducibility: two runs with the same inputs are bit-identical (`==` on every array).
- **Required by D-312 … D-314** (`tests/unit/test_F_0_3_1_engine_sizing_swap.py`):
  1. a hand-computed **multi-day swap with a changing close price, including a triple day**, for a long and a short (and a non-USD case converted at each rollover bar); engine `cost_swap` = hand value = T06b `round_trip_cost` (rel 1e-12);
  2. **qty rounding with floor**: a price where notional / price is not a multiple of the step (share CFD step 0.1, FX step 0.01 lot); the traded qty is the floored value and the entry notional ≤ 100,000 USD;
  3. **a signal skipped below the minimum volume**: no trade, the strategy stays flat, `n_skipped_min_volume` = 1, the flag is set in `RunMeta` and `as_gate_dict()`; the grid kernel returns the same count;
  4. **parity mode unaffected by rounding**: the same signals in `tradingview` mode give the TradingView-sized (unrounded) qty and no skipped count;
  5. a symbol with `volume_step_assumed` carries the flag into `RunMeta`.
  The Hypothesis generators also draw `volume_step`/`min_volume`, and the invariants (P&L conservation, costs monotonic, batch = single, truncation) must hold with rounding on.

## Acceptance
- ruff, format, mypy (engine kernels relaxed; `pipeline/backtest.py` typed), fast suite, `pytest tests/parity tests/leakage` (the new engine leakage test included), `pytest -m db` 0 skipped.
- Benchmark in the review: `simulate` on 60,000 hourly bars and `simulate_grid` on 2,000 configurations × 2,500 daily bars (wall time, cores). No thresholds, only reported.
- Acceptance-reviewer subagent run; findings fixed.

## Review summary
`docs/reviews/T08_review.md`: the kernel signatures, the event order as implemented, the hand fixtures (with the numbers), how each acceptance criterion and each design §6 invariant is tested, benchmark, deviations, open questions. **Stop and wait for "Approved".**
