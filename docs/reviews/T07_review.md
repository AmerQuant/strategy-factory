# T07 review — Strategy components and indicator library

**Features:** F-0.4.1, F-0.4.2, F-0.4.3 · **Branch:** `feat/T07-components` (from `main` @ `7ddd838`) · **Status:** done — all acceptance tests pass locally; CI not yet run (branch not pushed)

## Golden files (committed first, unchanged in content)
The four exports were gzip-compressed losslessly (level 9, empty file name, **mtime 0**, header `1f8b08000000000002ff`), the decompressed bytes were verified identical to the originals twice (Python `gzip.decompress` and `gzip -dc | cmp`), then the CSVs were deleted. The golden tests read the `.csv.gz` files. `.gitattributes` now marks `*.gz binary`.

| file | original CSV | `.csv.gz` | sha256 of the original CSV |
|---|---|---|---|
| `AMEX_SPY_1D` | 6,812,436 B | **2,768,661 B** | `eae09f32…12170` |
| `CAPITALCOM_SPX500_1D` | 5,504,457 B | **2,272,112 B** | `5dd015b1…a354c` |
| `FX_EURUSD_1H` | 19,542,606 B | **7,295,944 B** | `55804a03…cda91` |
| `OANDA_XAUUSD_1H` | 18,063,329 B | **7,263,868 B** | `97412598…5d9e6` |
| **total** | 49.9 MB | **19.6 MB** | |

Commit 1 (`593a021`) contains exactly the task file, `tools/tradingview/sf_golden_indicators.pine` and the four `.csv.gz` files.

## What was built
| file | content |
|---|---|
| `src/strategy_factory/components/indicators/_core.py` | Numba kernels with Pine `na` semantics (SMA, EMA/RMA recursion, WMA, stdev, highest/lowest, highest/lowest-bars, true range, fixnan, shift) |
| `…/indicators/averages.py` | `sma, ema, rma, wma, hma, kama, sma_slope` |
| `…/indicators/volatility.py` | `true_range, atr, stdev, bollinger, keltner` |
| `…/indicators/channels.py` | `highest, lowest, highest_bars, lowest_bars, donchian` |
| `…/indicators/oscillators.py` | `rsi, ibs, zscore, macd, roc, momentum, williams_r, stochastic, percent_rank, updown_streak, connors_rsi` |
| `…/indicators/trend.py` | `dmi` (DI+/DI−/ADX), `supertrend` (value + TV direction), `psar`, `aroon`, `ichimoku` (unshifted) |
| `src/strategy_factory/components/base.py` | `ParamSpec`, `GridRules` (4 values/param, ≤ 64 cells), `Bars` (+ `mirrored()`), `Component` protocol, `EntryComponent` (mirror rule), `ExitSpec` + `ExitComponent` (data structure only), `resolve_params`, `ComponentError` — mypy strict |
| `src/strategy_factory/components/registry.py` | `ComponentRegistry` (`register` decorator, `get`, `names`, `list_by_role`, `list_by_edge_type`, `check_edge_tags`), `default_registry()` auto-imports every module of `components/{entries,exits,filters,sizing}` — mypy strict |
| `src/strategy_factory/components/edges.py` + `configs/edges/edge_types.yaml` | edge-type registry (MR, TF, SEASONAL with probe groups), Pydantic-validated — mypy strict |
| `src/strategy_factory/components/entries/probes.py` | the 17 stage-1 probes (9 MR, 8 TF) |
| `tests/fixtures/tv_golden_io.py`, `tests/fixtures/indicator_cases.py` | golden loader (gz, decimals detection, Pine plot-title parser); all indicator cases + OHLC generator for leakage tests |
| tests | `tests/unit/test_F_0_4_2_golden.py` (201), `tests/property/test_F_0_4_2_naive.py` (12 Hypothesis tests), `tests/leakage/test_F_0_4_2_truncation.py` (103), `tests/unit/test_F_0_4_1_components.py` (24), `tests/unit/test_F_0_4_3_edges.py` (15) |

**Dependencies added** (direct): `numpy>=2.5.3` (was already installed as a transitive dependency; now used directly by `components`) and `numba>=0.67.0` (+ `llvmlite 0.49.0`) for the `@njit(cache=True)` kernels, as required by the design (§2, CLAUDE.md engine conventions). mypy: one `ignore_missing_imports` override for `numba` (no type information). No TA-Lib, no pandas-ta.

## Golden results — indicators × files
Every file is a **full-precision export** (up to 20–31 printed decimals, shortest round-trip floats), so no rounding allowance was needed: the tolerance for **every column** is `|ours − tv| ≤ 1e-6 · max(1, |tv|)`. NaN positions match exactly for every column in every file. Cells show pass/fail and the max absolute error.

| column | SPY 1D (8,467 bars) | SPX500 1D (7,013) | EURUSD 1H (23,079) | XAUUSD 1H (21,986) | first value at bar |
|---|---|---|---|---|---|
| SMA_20 | pass 1.5e-12 | pass 1.1e-11 | pass 1.0e-14 | pass 1.8e-11 | 19 |
| SMA_50 | pass 9.7e-13 | pass 1.2e-11 | pass 1.1e-14 | pass 1.1e-11 | 49 |
| SMA_100 | pass 1.3e-12 | pass 1.0e-11 | pass 7.3e-15 | pass 2.4e-11 | 99 |
| SMA_200 | pass 8.5e-13 | pass 1.6e-11 | pass 1.0e-14 | pass 2.3e-11 | 199 |
| EMA_20 | pass 3.4e-13 | pass 3.6e-12 | pass 8.9e-16 | pass 3.6e-12 | 19 |
| EMA_50 | pass 8.0e-13 | pass 8.2e-12 | pass 2.7e-15 | pass 8.2e-12 | 49 |
| EMA_100 | pass 1.1e-12 | pass 1.1e-11 | pass 2.9e-15 | pass 1.1e-11 | 99 |
| SMA_50_SLOPE | pass 8.5e-13 | pass 3.2e-12 | pass 6.7e-16 | pass 6.4e-12 | 50 |
| HMA_20 | pass 4.5e-13 | pass 3.6e-12 | pass 1.1e-15 | pass 3.6e-12 | 22 |
| KAMA_10_2_30 | pass 0 | pass 0 | pass 0 | pass 0 | 0 |
| ATR_14 | pass 1.4e-14 | pass 1.1e-13 | pass 3.5e-18 | pass 7.1e-14 | 13 |
| BB_20_2_MID | pass 1.5e-12 | pass 1.1e-11 | pass 1.0e-14 | pass 1.8e-11 | 19 |
| BB_20_2_UP | pass 6.1e-10 | pass 3.5e-09 | pass 5.0e-11 | pass 3.7e-08 | 19 |
| BB_20_2_LO | pass 6.1e-10 | pass 3.5e-09 | pass 5.1e-11 | pass 3.7e-08 | 19 |
| KC_20_2_MID | pass 3.4e-13 | pass 3.6e-12 | pass 8.9e-16 | pass 3.6e-12 | 19 |
| KC_20_2_UP | pass 3.4e-13 | pass 3.6e-12 | pass 8.9e-16 | pass 3.6e-12 | 20 |
| KC_20_2_LO | pass 3.4e-13 | pass 3.6e-12 | pass 8.9e-16 | pass 3.6e-12 | 20 |
| DC_10_HI / DC_10_LO | pass 0 | pass 0 | pass 0 | pass 0 | 9 |
| DC_20_HI / DC_20_LO | pass 0 | pass 0 | pass 0 | pass 0 | 19 |
| DC_55_HI / DC_55_LO | pass 0 | pass 0 | pass 0 | pass 0 | 54 |
| LOWEST_CLOSE_7 | pass 0 | pass 0 | pass 0 | pass 0 | 6 |
| RSI_2 | pass 0 | pass 0 | pass 0 | pass 0 | 2 |
| RSI_5 | pass 2.8e-14 | pass 2.8e-14 | pass 3.6e-14 | pass 2.8e-14 | 5 |
| RSI_14 | pass 4.3e-14 | pass 4.3e-14 | pass 4.3e-14 | pass 5.0e-14 | 14 |
| IBS | pass 0 | pass 0 | pass 0 | pass 0 | 0 |
| ZSCORE_20 | pass 2.5e-10 | pass 1.4e-10 | pass **2.7e-07** | pass 5.3e-08 | 19 |
| MACD_12_26_9_LINE | pass 4.5e-13 | pass 3.6e-12 | pass 1.3e-15 | pass 5.5e-12 | 25 |
| MACD_12_26_9_SIGNAL | pass 3.2e-13 | pass 2.8e-12 | pass 1.0e-15 | pass 4.2e-12 | 33 |
| MACD_12_26_9_HIST | pass 2.8e-13 | pass 2.7e-12 | pass 6.9e-16 | pass 2.4e-12 | 33 |
| ROC_20 | pass 0 | pass 0 | pass 0 | pass 0 | 20 |
| WPR_14 | pass 0 | pass 0 | pass 0 | pass 0 | 13 |
| STOCH_14_3_K | pass 8.5e-14 | pass 8.5e-14 | pass 5.7e-14 | pass 8.5e-14 | 15 |
| STOCH_14_3_3_D | pass 8.5e-14 | pass 8.5e-14 | pass 9.9e-14 | pass 1.1e-13 | 17 |
| CONNORS_RSI_3_2_100 | pass 2.8e-14 | pass 2.8e-14 | pass 2.8e-14 | pass 2.8e-14 | 100 / 681 / 209 / 2040 |
| DI_PLUS_14 | pass 4.3e-14 | pass 4.3e-14 | pass 4.3e-14 | pass 4.3e-14 | 14 |
| DI_MINUS_14 | pass 4.3e-14 | pass 3.6e-14 | pass 4.3e-14 | pass 5.0e-14 | 14 |
| ADX_14 | pass 5.0e-14 | pass 5.0e-14 | pass 7.1e-14 | pass 7.8e-14 | 27 |
| SUPERTREND_10_3 | pass 1.1e-13 | pass 9.1e-13 | pass 2.2e-16 | pass 9.1e-13 | 0 (value 0.0), then 9 |
| SUPERTREND_10_3_DIR | pass 0 | pass 0 | pass 0 | pass 0 | 0 |
| PSAR_002_02 | pass 0 | pass 0 | pass 0 | pass 0 | 1 |
| AROON_25_UP / AROON_25_DOWN | pass 0 | pass 0 | pass 0 | pass 0 | 25 |
| ICHI_TENKAN_9 | pass 0 | pass 0 | pass 0 | pass 0 | 8 |
| ICHI_KIJUN_26 / ICHI_SPAN_A_RAW | pass 0 | pass 0 | pass 0 | pass 0 | 25 |
| ICHI_SPAN_B_52_RAW | pass 0 | pass 0 | pass 0 | pass 0 | 51 |

All 49 plot titles of the Pine script are mapped (a test parses the Pine file and fails if a plot is added without a mapping). The largest relative error is ZSCORE_20 on EURUSD 1H (2.7e-7 on values ≈ 1, i.e. 27 % of the tolerance) — the population stdev of 20 hourly EURUSD closes is tiny, so TradingView's own stdev algorithm and our two-pass version differ in the last digits; BB bands on XAUUSD (3.7e-8 on values ≈ 2000) have the same cause.

## Seeding / warm-up conventions (all verified by the golden files)
| indicator | convention implemented | differs from the common textbook definition |
|---|---|---|
| EMA, RMA (and everything built on them: ATR, RSI, MACD, KC, DMI, Supertrend) | first value = SMA of the first `length` values at bar `length−1`; NaN before; re-seeded by SMA if the previous value is NaN | textbook EMA often seeds with the first price at bar 0 |
| ATR | `rma(tr)` with `tr[0] = high−low` (`ta.tr(true)`) → first ATR at bar `length−1` | many libraries drop bar 0 (first ATR at bar `length`) |
| Keltner | bands use the **bare** `ta.tr` (NaN on bar 0) → bands start one bar after the midline (bar 20 vs 19) | textbook: same start for all three lines |
| DMI | `rma(ta.tr)` with the bare true range; `fixnan` on DI; ADX from bar `di+adx−1` = 27; **+DM/−DM moves that differ by ≤ 1e-10 are a tie (both 0)** | Wilder uses sums, not RMA, for the seed; the tie rule is TradingView-specific: a strict float `>` gives DI errors up to 10 points (EURUSD 1H) because equal price moves differ in the last bits (e.g. 0.09000000000000341 vs 0.08999999999997499 on SPY bar 5333) |
| RSI | Wilder RMA of gains/losses, first at bar `length`; `down == 0 → 100`, else `up == 0 → 0` | a flat window is 100 here (textbooks: undefined or 50) |
| Stdev / Bollinger / Z-score | population stdev (biased), two-pass; deviations with `|d| ≤ 1e-10` count as 0 (TradingView reference); Z-score NaN when stdev = 0 | sample stdev (n−1) is common in textbooks and pandas |
| KAMA | `kama = src` for bars `0..length−1` (no NaN), then the recursion; `er = 0` if the volatility sum is 0 | textbook seeds once (first close or SMA) and has a warm-up |
| HMA | half length `length // 2`, sqrt length `floor(sqrt(length))` → first value at bar 22 for length 20 | for odd lengths Pine's `length/2` is ambiguous; integer division chosen (open question 6) |
| Supertrend | line-by-line port of TradingView's reference: `nz()` on the previous bands → **value 0.0 on bar 0**, NaN on bars 1…8, values from bar 9; direction **+1 during warm-up**, TradingView convention −1 = up-trend | textbook Supertrend is NaN during warm-up and uses +1 = up-trend |
| Parabolic SAR | TradingView's reference: NaN on bar 0; bar 1 decides the trend by `close[1] > close[0]` (start SAR = `low[0]`, EP = `high[1]`), reversal SAR = `max(high, EP)` / `min(low, EP)`, clamp to the previous 2 bars | Wilder starts from a chosen trend's first extreme |
| Aroon | `100·(highestbars(high, 26) + 25)/25` (window 26 = length + 1, current bar included); **ties resolve to the oldest bar** | many libraries use a window of `length` or break ties toward the most recent bar |
| Percent rank (Connors RSI) | share of the previous `length` values (current excluded) that are `≤` current; starts at bar `length`; a NaN in the history counts as "not ≤" (divisor stays `length`) | — |
| Connors RSI streak | the Pine helper `updown` has `ud[1] = na` on bar 0 and `na ± 1 = na`, so the streak is **NaN until the first unchanged close** (bar 6 on SPY, ~679 on SPX500, ~2038 on XAUUSD) | textbook streak starts at 0 on bar 0 (open question 1) |
| Ichimoku | lines unshifted; the displacement belongs to the strategy | — |
| Donchian / highest / lowest | window includes the current bar | — |

## Probes (stage 1, signals only)
Short = long rule on the mirrored series for every probe (no `mirror: false` probe exists). Breakouts compare the close with the **previous** bar's channel (addendum §1.6). NaN never signals.

| probe | edge / group | long rule (defaults) |
|---|---|---|
| `mr_rsi2_below_10` | MR / oscillator | `rsi(close, 2) < 10` |
| `mr_rsi5_below_30` | MR / oscillator | `rsi(close, 5) < 30` |
| `mr_ibs_below_0_2` | MR / oscillator | `ibs < 0.2` |
| `mr_close_below_bb_lower` | MR / band_channel | `close < bb(20, 2).lower` |
| `mr_donchian20_new_low` | MR / band_channel | `close < lowest(low, 20)[1]` |
| `mr_zscore_below_minus_2` | MR / band_channel | `zscore(close, 20) < −2` |
| `mr_lowest_close_7` | MR / band_channel | `close <= lowest(close, 7)` (current bar included) |
| `mr_three_down_closes` | MR / sequence | `close < close[1]` on each of the last 3 bars |
| `mr_macd_hist_trough_5` | MR / momentum | `macd(12,26,9).hist <= lowest(hist, 5)` |
| `tf_ma50_slope_up` | TF / ma | `slope > 0 and slope[1] <= 0`, `slope = sma50 − sma50[1]` |
| `tf_sma_cross_20_100` | TF / ma | `crossover(sma20, sma100)` |
| `tf_donchian20_breakout`, `tf_donchian55_breakout` | TF / channel_breakout | `close > highest(high, N)[1]` |
| `tf_close_above_bb_upper` | TF / channel_breakout | `close > bb(20, 2).upper` |
| `tf_supertrend_flip` | TF / volatility_trailing | direction goes `+1 → −1` (TV convention) |
| `tf_ichimoku_cloud` | TF / ichimoku | `close > max(spanA, spanB)[25] and tenkan > kijun` |
| `tf_roc20_cross_zero` | TF / momentum | momentum `close − close[20]` crosses above 0 (same sign as ROC for positive prices; keeps the mirror exact) |

## Acceptance criteria → tests
| criterion | test(s) | result |
|---|---|---|
| F-0.4.2 golden: every file × every column, NaN warm-up exact, tolerance | `test_F_0_4_2_golden_values[<file>-<column>]` (196), `test_F_0_4_2_golden_file_has_every_plot`, `test_F_0_4_2_every_pine_plot_is_mapped` | ✅ 201 passed |
| golden tests skip with a clear reason when the folder is empty | `skipif(not FILES, reason=…)`; checked manually by emptying the folder: "1 passed, 50 skipped" with the reason text | ✅ (manual check, not a permanent test) |
| F-0.4.2 naive oracle (Hypothesis OHLC, ties, zero-range bars) | 12 tests in `tests/property/test_F_0_4_2_naive.py` covering every public indicator; a mutation check (RSI off-by-one, EMA first-value seed, most-recent Aroon tie) was detected | ✅ |
| leakage: every indicator and probe, output[0..t] on bars[0..t] = full output[0..t] | `test_F_0_4_2_indicator_truncation_invariant` (35 cases × 2 series, every t = 1…180, exact equality), `test_F_0_4_2_probe_truncation_invariant` (17 probes × 2), `…_cover_every_public_indicator` | ✅ 103 passed |
| F-0.4.1 registry lookup and listing | `test_F_0_4_1_registry_lookup_and_listing`, `…_duplicate_and_invalid_registrations_raise` | ✅ |
| F-0.4.1 ParamSpec validation: exactly 4 coarse values, ≤ 64 cells | `test_F_0_4_1_param_spec_requires_exactly_four_coarse_values`, `…_param_spec_validation` (9 cases), `…_at_most_64_cells_per_method`, `…_every_registered_component_respects_the_grid_rule` | ✅ |
| F-0.4.1 new component needs no other change | `test_F_0_4_1_adding_a_component_needs_only_registration` (dummy class registered; a stage-like scan picks it up unchanged) | ✅ |
| F-0.4.3 tags come from the YAML | `test_F_0_4_3_edge_types_come_from_yaml`, `…_tags_not_in_yaml_are_rejected`, `…_new_edge_type_is_config_only`, `…_invalid_edge_registry`, `…_every_probe_group_is_populated` | ✅ |
| F-0.4.3 short = mirror of long on a mirrored price series | `test_F_0_4_3_short_is_long_on_mirrored_prices` (Hypothesis, positive reflection `K − p`, all 17 probes, both directions), `…_mirror_is_exact_under_negation`, `…_mirror_example_rsi` | ✅ |
| F-0.4.3 `mirror: false` requires a reason | `test_F_0_4_3_mirror_false_requires_a_reason` (3 cases), `…_requires_own_short_rule` | ✅ |
| ruff, format, mypy (strict for `components/base.py`) | `ruff check .`, `ruff format --check .`, `mypy src` (base, edges, registry strict via overrides) | ✅ |
| full fast suite / mandatory gates | `pytest -m "not slow"`: **572 passed**; `pytest tests/parity tests/leakage`: 103 passed | ✅ |
| CI green | — | ⏳ not pushed yet |

## Deviations and open questions
1. **Connors RSI streak (Pine script quirk).** Matching the golden files requires the streak to be NaN until the first unchanged close (`updown` in the Pine script reads `ud[1]`, which is `na` on bar 0, and `na ± 1` stays `na`). On XAUUSD 1H Connors RSI therefore only starts at bar 2040, and on a series without an unchanged close it never starts. I implemented the golden behaviour (task rule "golden values win"). **Recommendation:** decide whether this is intended; if not, change the helper to `nz(ud[1])`, re-export, and I switch `updown_streak` to start at 0.
2. **Extra export column.** All four exports contain `Upper Line (Lowest + ATR)`, which is not in `sf_golden_indicators.pine` (another indicator was on the chart). The tests ignore it; the files were committed unchanged.
3. **DMI tie tolerance (1e-10, absolute).** Inferred from the golden data (any epsilon from 1e-12 to 1e-8 gives errors ≤ 5e-14 on all files; 0 fails). TradingView does not document it. For instruments with very large prices (≥ ~1e6) an absolute 1e-10 is below float resolution of the differences; a relative rule may be needed then. The same constant is used for TradingView's stdev zero rule.
4. **Supertrend bar-0 value 0.0.** Replicated because the warm-up must match exactly. Only bar 0 is affected; the probe uses the direction, not the value.
5. **Probe interpretations** where the spec is short (please confirm): MACD "trough of 5 bars" = histogram at its 5-bar low (current included, no sign condition, no turn-up confirmation); "new Donchian-20 low" = **close** below the prior 20 bars' lowest low (spec wording "close below the Donchian floor"); "lowest close 7" includes the current bar; "MA50 slope turns up" = slope crosses from ≤ 0 to > 0; Ichimoku cloud displacement = `base − 1` = 25 bars (TradingView's plotted cloud), tied to the `base` parameter; RSI/IBS/BB/Z/Ichimoku probes are **state** signals (true on every qualifying bar), MA slope, SMA cross, Supertrend flip and ROC cross are **events**.
6. **HMA odd lengths:** `length // 2` (Pine's `length/2` is a float for odd lengths); only length 20 is golden-tested.
7. **Probe coarse grids are placeholders.** `ParamSpec` must declare exactly 4 coarse values, but the spec gives only the fixed stage-1 values. The defaults are the spec values (tested); the other coarse values/ranges are my choice and are not used by stage 1. MACD 12/26/9 in `mr_macd_hist_trough_5` is a class constant (standard definition), not a parameter, to stay within the 64-cell rule. Please confirm or supply grids when stage 2 needs them.
8. **Grid rule numbers** (4 values/param, 64 cells) are defaults of the `GridRules` config model (spec phase-1 decision); there is no YAML file for them yet. `ParamSpec` checks the count against the model default; the registry checks count and cells against its `GridRules` instance.
9. `params` is declared as a **tuple** of `ParamSpec` (immutable class attribute) instead of the task's `list`.
10. Hypothesis tests that call Numba kernels use `deadline=None`: with a cold Numba cache the first example includes JIT compilation (~0.4–0.6 s) and the default 200 ms deadline produced a spurious "unreliable timings" failure (reproduced and fixed). CI already runs with `deadline=None`.
11. Golden tests carry the existing `parity` marker (TradingView parity gate) although they live in `tests/unit/` as the task specifies.
12. The naive property tests take ~30 s locally (they are in the fast suite).
13. Numba's `cache=True` writes `.nbi/.nbc` files into `src/**/__pycache__/` (git-ignored).

## Commits
1. `593a021` F-0.4.2: task file, Pine script, golden exports (.csv.gz)
2. `a41c19c` F-0.4.2: indicator library with golden and naive-oracle tests (+ numpy, numba)
3. `e64fc3f` F-0.4.1, F-0.4.3: component interface, registry, edge-type config, stage-1 probes, leakage tests
4. F-0.4.1: registry auto-discovery, Hypothesis deadline fix, this review
