# T07 — Strategy components and indicator library

**Features:** F-0.4.1 (component interface), F-0.4.2 (indicator library), F-0.4.3 (edge-type tags) · **Priority:** MVP · **Depends on:** T01 (on `main`)
**Branch:** `feat/T07-components` from `main`.

Read first: `CLAUDE.md`, `docs/design.md` §3–§4, F-0.4.1–F-0.4.3 in `docs/features.md`, and the edge-type addendum `docs/spec/spec_addendum_edge_types_v0_1.md` (§1: the edge-type registry is config-driven).

## Decision (fixed): test oracles
1. **Golden files exported from TradingView** are the primary reference. TradingView is the platform we must match.
2. **Independent naive implementations** in the tests are the second reference: plain Python loops written line by line from the formula, used for property tests on random data.

No TA-Lib and no pandas-ta.

## Golden files
- The Pine script is committed at `tools/tradingview/sf_golden_indicators.pine`. Commit the version the user provides, unchanged.
- The exports go to `tests/fixtures/tv_golden/<EXCHANGE>_<SYMBOL>_<TF>.csv`. They contain TradingView's own OHLC plus one column per plot title (`SMA_20`, `RSI_2`, …) and a UNIX `time` column.
- The golden tests feed **TradingView's own OHLC** from the file into our functions and compare the result with the plot columns. They therefore do not depend on our data sources.
- The files are needed only for the golden tests. If they are not in the folder yet, write the golden tests so they are **skipped with a clear reason** when the folder is empty, and finish everything else. Do not fabricate golden data.

## Scope

### 1. Component interface (F-0.4.1, `components/base.py`)
- `ParamSpec`: `name, kind (int|float|choice), default, min, max, coarse_values (exactly 4), fine_step`.
  - Coarse grid rule (decided): 4 values per parameter; at most 64 cells per method, validated.
- `Component` protocol with `name`, `params: list[ParamSpec]` and `role` (`entry | exit | filter | sizing`). Entries also have `edge_type` and `directions`.
  - Entries: `signals(bars, params) -> (long_entry: bool[n], short_entry: bool[n])`
  - Exits: provide a spec that the engine will consume later (T08). For now define the data structure only.
- `ComponentRegistry`: register by decorator, look up by name, list by role or edge type. Adding a method = registering one new class; no stage code changes.

### 2. Edge-type tags (F-0.4.3)
- Edge types come from a config registry: `configs/edges/edge_types.yaml` with MR, TF and SEASONAL now. The addendum types are added later, by config only.
- Entry components declare `edge_type` and allowed `directions`.
- **Mirror rule (decided):** the short entry is the mirror of the long entry, unless the component sets `mirror: false` with a written reason in its docstring.

### 3. Indicator library (F-0.4.2, `components/indicators/`)
- Pure NumPy functions on float64 arrays. Numba `@njit(cache=True)` where a loop is needed; keep kernels free of Python objects.
- **Warm-up convention:** return NaN wherever TradingView returns `na`.
- **Seeding conventions** (RMA, EMA, RSI, ATR, ADX, PSAR, KAMA, Supertrend) must **match the golden files**. Where TradingView's documentation and the golden values disagree, the golden values win. Document every convention in the function's docstring.
- Implement every plot in the Pine script:
  - SMA, EMA, SMA slope, HMA, KAMA(10,2,30);
  - ATR; Bollinger (mid/up/lo, population stdev); Keltner (mid/up/lo);
  - Donchian hi/lo; lowest close;
  - RSI; IBS; Z-score;
  - MACD (line/signal/hist); ROC; Williams %R; Stochastic K/D; Connors RSI(3,2,100);
  - DI+/DI−/ADX; Supertrend (value + direction in TradingView convention); Parabolic SAR; Aroon up/down;
  - Ichimoku tenkan/kijun/span A raw/span B raw (**unshifted**; the displacement belongs to the strategy).
- Also provide `true_range` and `rma` as public helpers.

### 4. Probe entries for stage 1 (minimal)
Register the stage-1 probe entries from the spec (MR: RSI2<10, RSI5<30, IBS<0.2, close<BB lower, new Donchian-20 low, Z<−2, lowest close 7, 3 down closes, MACD hist trough of 5 bars; TF: MA50 slope turns up, SMA 20/100 cross, Donchian 20/55 breakout, close > BB upper, Supertrend flip, Ichimoku close above cloud and tenkan > kijun, ROC20 crosses 0).
- Each probe with its group (MR: oscillator / band_channel / sequence / momentum; TF: ma / channel_breakout / volatility_trailing / ichimoku / momentum) as metadata.
- Signals only; no backtesting here.

## Tests
- **Golden** (`tests/unit/test_F_0_4_2_golden.py`): for each file and each column, compare our output with TradingView over all bars where both are non-NaN.
  - The NaN warm-up positions must match exactly.
  - Tolerance: `abs ≤ 1e-6 × max(1, |value|)`, or looser only where the export's rounding requires it. Detect the export's decimal places and state the tolerance used per column in the review.
- **Naive oracle** (`tests/property/test_F_0_4_2_naive.py`): Hypothesis-generated OHLC series (valid OHLC, positive prices). Each fast implementation must equal a naive loop implementation written independently in the test file.
- **Leakage** (`tests/leakage/test_F_0_4_2_truncation.py`): for every indicator and probe, output[0..t] computed on bars[0..t] equals output[0..t] computed on the full series.
- **F-0.4.1:**
  - registry lookup and listing;
  - `ParamSpec` validation (exactly 4 coarse values, ≤ 64 cells per method);
  - adding a new component requires no other change (test registers a dummy component).
- **F-0.4.3:**
  - edge-type tags come from the YAML;
  - short = mirror of long on a mirrored price series;
  - `mirror: false` requires a reason.

## Acceptance
ruff, format, mypy (strict for `components/base.py`), pytest pass. CI green. Golden tests pass for every provided file, or are skipped with a clear reason if no files exist yet.

## Review summary
Write it to `docs/reviews/T07_review.md`. Include:
- a table of indicators × golden files with pass/fail, max abs error and tolerance;
- every seeding/warm-up convention found and where it differs from common textbook definitions;
- deviations and open questions.
