# T08 review — Backtest engine — CRITICAL (D-402)

**Features:** F-0.3.1, F-0.3.2, F-0.3.4, F-0.3.9 · **Branch:** `feat/T08-engine` (stacked on `feat/T06b-moneta-costs`) · **Status:** done. **Waiting for "Approved"** before T10b.

**Decisions used:** D-001 … D-004, D-012, D-060, D-061, D-130, D-300, D-301, D-307, D-312 … D-316, D-326 … D-338.

## Dependencies
None added.
- **vectorbt (D-330):** `uv add --dev vectorbt` installs version 1.1.0 and leaves the numba 0.67.0 / numpy 2.5.3 pins unchanged.
- But vectorbt **fails at import** with the resolved plotly: it uses the removed `scattermapbox` trace. Fixing that needs `plotly<6`, while ADR-008 plans Plotly for the reports.
- It was **reverted and not added** (P-35). The mandatory oracle is the naive engine below; it runs and is never skipped.

## What was built
| File | Content |
|---|---|
| `engine/kernel.py` | `_core` (one strategy × one series), `simulate_one`, `simulate_grid_kernel` (`prange`), `research_lots`. `@njit(cache=True)`; scalars and arrays only. |
| `engine/commission.py` | Commission kernel, codes 0–4 (T06/T06b signature). |
| `engine/api.py` | Typed NumPy front end (`MarketArrays`, `CostInputs`, `SizingInputs`, `ExitParams` → `SimResult` / `GridResult`), with shape checks. |
| `pipeline/backtest.py` | `EngineConfig` (`configs/engine/default.yaml`), `BacktestSpec`, `run_backtest` → validated `RunResult`, `FuturesSizing`. Strict mypy. |
| `data/conversion.py` | `FxConversionConfig` (`configs/data/fx_conversion.yaml`), `align_pair`, `conversion_for` (USD / pair / HKD peg), with a window check. |
| `data/split.py` | `DataAccess.conversion_bars` (traded development window) and `SplitManager.open_holdout_with_conversion` (traded holdout window, one-shot). Both go through the private `_conversion_arrays`, which accepts only configured conversion pairs and never the traded symbol (D-316). |
| `metrics/containers.py`, `metrics/standard.py` | Additive T09 extension (see below). |
| `scripts/bench_engine.py` | Benchmark. |

`engine/` imports only `numpy`, `numba`, `math`, `dataclasses` and `typing`. It has no I/O, config or logging, and does not import `metrics`, `costs`, `components` or `data`.

## Kernel signatures
```
simulate_one(open_, high, low, close, atr, entry_sig, exit_sig, direction,
             time_exit_bars, sl_atr, tp_atr, trail_atr, disaster_atr,          # NaN = unused
             half_spread, slip_fixed, slip_atr_frac, swap_long, swap_short, rollover, triple,
             c_code, c_p0, c_p1, c_p2, comm_in_quote,
             fx_open, fx_close, sizing_mode, notional, contracts, point_value,
             contract_size, volume_step, min_volume, step_tol, initial_capital, intrabar_mode)
  -> 15 trade arrays (TradeLog fields), equity, in_position, realized, n_trades,
     open_pnl_end, n_skipped_min_volume
simulate_grid_kernel(... entry_mat (n x k), exit_mat (n x k), ...,
                     time_exit_bars[k], sl_atr[k], tp_atr[k], trail_atr[k], ...)
  -> equity (k x n), in_position (k x n), n_closed_trades[k] (D-301), n_skipped_min_volume[k]
```
Modes: intrabar 0 = tradingview, 1 = pessimistic. Sizing 0 = research lots, 1 = contracts, 2 = parity.

## Event order as implemented (bar *j*)
1. **Open.**
   - A scheduled exit fills first; otherwise a gap through a stop fills at the open (a worse price), or a gap through the target fills at the open.
   - Then a scheduled entry fills (D-336). Sizing:
     - research: `floor(notional / (open[j] × fx_open[j] × contract_size) / step) × step` lots (D-315, D-328); below the minimum volume the entry is skipped and counted (D-313);
     - futures: fixed contracts (D-329);
     - parity: `notional / (close[j−1] × fx_close[j−1])` (D-337).
   - Levels come from the raw open of the entry bar and `atr[j−1]` (D-326).
2. **Intrabar.**
   - Stops (disaster, SL, trailing) and TP are checked via high/low, from the entry bar on.
   - Several stops touched: the one nearest the open wins; ties go SL > trailing > disaster.
   - Stop and target both touched: pessimistic takes the stop. Tradingview goes O→H→L→C when the high is nearer the open, else O→L→H→C; a tie takes the stop (D-335).
   - A stop inside a rollover bar pays that bar's swap only in pessimistic mode, and only if it is a charge (D-327).
3. **Close.**
   - Swap for a held position on `|qty| × close × point_value × fx_close`, ×3 on the triple day (D-312).
   - The trailing level moves.
   - A signal exit (priority) or time exit is scheduled.
   - An entry is scheduled when flat or when an exit is scheduled, if `j < n−1` and `atr[j] > 0`.
   - Equity is marked to market (D-003).

## `to_verify` list (parity mode, D-338; also in the kernel docstring)
- O→H→L→C path and its tie (D-335).
- Exit + re-entry at one open (D-336).
- No swap on intrabar exits in rollover bars (D-327).
- Parity sizing (D-337).

Applied in both modes (P-34):
- the trailing level moves at the close only;
- a gap through the target fills at the open;
- stop tie order;
- stops are checked on the entry bar;
- a signal exit beats a time exit on the same close;
- the MAE/MFE definition;
- exit slippage uses `atr[j−1]`;
- parity sizing converts with `fx_close` of the signal bar.

## Hand-computed fixtures (`tests/unit/test_F_0_3_1_engine.py`)
| Fixture | Numbers |
|---|---|
| **Long, signal exit, costs** | Entry at open 2 (100), exit at open 5 (105), qty 10 = floor(1000/100).<br>Fills 100.17 / 104.83 (0.05 spread + 0.02 fixed + 0.1 × ATR 1).<br>Gross 50; spread 1.0; slippage 2.4; commission 0.001 × 10 × (100.17 + 104.83) = 2.05; **net 44.55**.<br>Equity 100000, 100000, 100007.2983, 100027.2983, 100037.2983, 100044.55 ×3.<br>MFE 50, MAE 5. |
| **Short, time exit, swap** | Time exit N = 3: entry at 2 (50), exit at 5 (47), qty 20.<br>Swap = 0.0001 × 20 × (49 + 3 × 48 + 47) = **0.48** (D-312, MTM notional, triple day).<br>Gross 60, **net 59.52**; equity at bars 2, 3, 4: 19.902, 39.614, 59.52. |
| **Non-USD quote** | Sizing at the fill-bar open 1.0 × fx 1.2: 100000 / 120000 = 0.8333 → **0.83 lot** = 83,000 units.<br>Gross 83000 × 0.03 × fx_close[exit] 1.25 = 3112.5; spread converted at the fill bars (1.15, 1.25); USD commission 2 × 0.83 × 3 = 4.98 (not converted); **net 3103.536**. |
| **Futures** | 2 contracts × 10 points × 50 = **1000 USD**. |

## How each criterion is tested
| Criterion | Test |
|---|---|
| **F-0.3.1** trades and equity equal the hand computation | the four hand fixtures above (rel 1e-12); each also builds a valid `RunResult` |
| **D-312** multi-day swap, changing price, triple day, long and short, non-USD; engine = hand = T06b `round_trip_cost` | `test_F_0_3_1_engine_sizing_swap.py::test_F_0_3_1_d312_*` |
| **D-313/D-315** floor to the step (share CFD 473.7; FX 0.92 lot), notional ≤ 100k | `test_F_0_3_1_d315_qty_floored_to_the_volume_step` |
| **D-313** skip below the minimum: no trade, flat, counted; RunMeta; gate dict; grid | `test_F_0_3_1_d313_signal_below_minimum_volume_is_skipped` |
| **Parity unaffected by rounding** (D-337) | `test_F_0_3_1_parity_mode_is_not_rounded_nor_skipped` |
| **D-314/D-329** flags reach RunMeta (futures carry both flags) | `test_F_0_3_1_run_backtest_flags_and_validation` |
| **D-327** stop inside a rollover bar: charge / no credit / parity none | `test_F_0_3_1_d327_stop_inside_a_rollover_bar` |
| **D-328** qty depends only on the fill-bar open rate | `test_F_0_3_1_d328_sizing_uses_the_fill_bar_open_rate_only` |
| **F-0.3.2** each exit at the right bar and price: signal, time, disaster (intrabar and gapped), SL, TP (intrabar and gap), trailing, first hit, re-entry at the same open, end of data, warm-up, short mirror | `test_F_0_3_2_exits.py` (12 tests) |
| **F-0.3.4** SL + TP in one bar: tradingview (both orders + tie) vs pessimistic; disaster vs TP; short; same-bar exit on the entry bar | `test_F_0_3_2_exits.py::test_F_0_3_4_*` |
| **Oracle (D-330)** | `tests/oracle/test_F_0_3_1_oracle.py`:<br>• Hypothesis, 400 examples, engine == naive engine on every trade field, equity, position, realized, open P&L and skips (rel 1e-12);<br>• the hand fixtures;<br>• a 600-seed sweep asserting that all six exit reasons, same-bar exits, re-entries, skips and swaps occur. |
| **Design §6 invariants** (Hypothesis, 150 examples each, rounding and conversion on) | `tests/property/test_F_0_3_engine_properties.py`: conservation, no same-bar execution, costs monotonic (5 components), truncation, long/short mirror, batch = single (`==`) |
| **F-0.3.9 leakage** | `tests/leakage/test_F_0_3_9_engine_truncation.py`: 17 registered components × 5 exit types × 2 modes = 170 cases. 400 bars, so every component fires in every allowed direction; each case asserts it took a position. |
| **D-316** conversion never beyond the traded window; the pair's holdout is not consumed | `tests/leakage/test_F_0_3_9_conversion_window.py`:<br>• development window; refusal of a longer window (development and holdout);<br>• the traded symbol or a non-conversion symbol is refused;<br>• DB: EURGBP holdout + GBPUSD, after which GBPUSD's own holdout opens exactly once;<br>• HKD peg from config. |
| Reproducibility | `test_F_0_3_1_reproducible_bit_identical` |
| Pins | commission kernel = `costs` kernel (6 parameter sets); `research_lots` = `costs.size_lots`; `ExitReason` codes |

## The naive oracle
`tests/oracle/naive_engine.py` is plain Python and processes one bar at a time. It holds explicit `Position` and `Trade` objects and allocates no buffers.
- It imports neither `engine` nor `costs`.
- It was written from the task text and the decisions.
- It encodes the choices listed in P-34 as well. It therefore proves that the code does what the rules say, but it does **not** independently validate those choices. The TradingView exports (P-04, T11) will test the parity ones.

## T09 contract changes (additive; P-33)
- `RunMeta` gains `n_skipped_min_volume`, `volume_step_assumed`, `contracts_fixed` and `fx_peg`. The last one, D-307's HKD flag, is beyond the task list.
- `MetricsReport` / `as_gate_dict()` gain `n_skipped_min_volume`, `min_volume_skip_flag`, `volume_step_assumed`, `contracts_fixed` and `fx_peg`. The T09 name-set test was extended.
- **Validator fix:** `RunResult._validate_positions` rejected a valid D-336 run: a position re-entered at the open where the last trade exited and still open at the end. It now accepts it. New T09-level tests cover both the accepted case and a bad pattern that is still rejected (`test_F_0_5_1_open_position_reentered_at_the_last_exit_open`).

## Benchmark (`scripts/bench_engine.py`, development machine, 20 cores)
| Run | Wall time |
|---|---|
| `simulate`: 60,000 hourly bars, 2,204 trades | **3.2 ms** |
| `simulate_grid`: 2,000 configurations × 2,500 bars (192,884 trades), 20 threads | **16.1 ms** |

These numbers are only reported; there are no thresholds.

## Acceptance
| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | ✅ / ✅ |
| `mypy src` (strict for `pipeline.backtest`, `data`) | ✅ 93 files |
| `pytest -m "not slow"` | ✅ **1035 passed** |
| `pytest tests/parity tests/leakage tests/oracle` | ✅ **283 passed**, 0 skipped |
| `pytest -m db` | ✅ 16 passed, **0 skipped** |
| acceptance-reviewer subagent | run; findings fixed (below) |

Reviewer findings and fixes:
1. **Blocking:** a public `window_bars` could read any holdout unlogged. It is now private, derives its window from the traded symbol's split, accepts only configured conversion pairs and never the traded symbol, and is tested.
2. The truncation gate was vacuous for two components. It now uses 400 bars and asserts that every case takes a position.
3. Reproducibility test added.
4. The holdout conversion path now carries its window, and the refusal is tested.
5. The `to_verify` list is complete.
6. Assumptions recorded as P-31 … P-35.
7. T09 validator unit tests added.
8. Conversion is drawn in the property tests; tradingview mode added to the leakage gate.
9. HKD peg test added.
10. Strict mypy for the glue.
11. The commission kernel moved to `engine/commission.py`, as the task says.
12. Futures now carry `volume_step_assumed` (D-314).

## Deviations
1. **`BacktestSpec` instead of `StrategySpec`** (P-32): no exit components exist yet.
2. **`configs/data/fx_conversion.yaml`** instead of `configs/costs/` (P-32).
3. **`fx_peg` field and gate name** (P-33).
4. **The ×3 triple-day multiplier is a literal** in the kernel. It is the definition in D-312, not a tunable number.

## Supervisor decisions after this review (2026-09-20)
- **D-343 (P-31):** ATR length 14 is a configurable default; a **parity run passes the length
  of the Pine script** it reproduces (noted in `configs/engine/default.yaml` and the glue).
- **D-344 (P-32):** `BacktestSpec` is accepted as interim and is replaced by `StrategySpec`
  when exit components exist; `configs/data/fx_conversion.yaml` is accepted.
- **D-345 (P-33):** accepted; the validator change is documented in the container-contract
  section of `docs/reviews/T09_review.md`.
- **D-346 (P-35):** **vectorbt is skipped.** The naive reference engine is the T08 oracle and
  the T11 parity test is the external check. This supersedes the vectorbt-oracle part of
  D-400; ADR-001 and CLAUDE.md carry the note.
- **P-34 is still open** (engine choices not stated by the decisions).

## Open questions
- **P-31:** ATR length 14.
- **P-32:** the structural deviations above.
- **P-33:** the T09 changes.
- **P-34:** engine choices not in the decisions.
- **P-35:** vectorbt.
- For T10b: `spec_hash` covers only the spec. The run-level config hash must also include the engine config and the intrabar mode. The T08 gate names must be registered (D-309/D-333).
- Reminder: **P-04**, the TradingView exports, is needed before T11.
