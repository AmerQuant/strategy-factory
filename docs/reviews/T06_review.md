# T06 review — Cost model

**Features:** F-0.2.1, F-0.2.3, F-0.2.4 · **Branch:** `feat/T06-costs` (stacked on T05) · **Status:** done, with open questions below

## Decisions taken with the user during the task
1. **`sfac costs show EURUSD` on the 3-month pilot.** The pilot is too short for a split (holdout ≥ 18 months), so it has no development segment. `costs show` then computes the hourly table over the whole snapshot, clearly labelled **"DISPLAY ONLY … never used for backtests"**. This happens **only** when `HistoryTooShortError` is raised, i.e. when no holdout can exist, so no holdout bar is ever read outside `SplitManager`. For backtests, `resolve_from_data()` accepts only bars from `DataAccess` (the development segment).
2. **`annual_rate` swap:** `day_count` is a profile field, set to 365 in every profile.
3. **`per_lot` commission:** lots = quantity in instrument (base-currency) units / `lot_size`.

## What was built
| file | content |
|---|---|
| `costs/profile.py` | frozen Pydantic schema: `CostProfile` (name, status, source_note, pip_size, spread, commission, swap, slippage); spread `fixed` / `hourly_profile` / `from_data`; commission `none` / `percent` / `per_share` (min, max) / `per_lot`; swap `none` / `annual_rate` / `points_per_day` with rollover rules; `Assignments` (groups, symbols + overrides, stress multipliers); loaders, `resolve_profile`, `validate_all` |
| `costs/arrays.py` | `build_cost_arrays(bars, profile, stress, timeframe=…) -> CostArrays`; `resolve_from_data(profile, dev_bars)`; `hourly_spread_table`; `rollover_instants`; `commission_kernel` + `commission_params`; `round_trip_cost` (reference cost breakdown used by the tests and as an oracle for T08) |
| `costs/cli.py` | `sfac costs show <symbol>`, `sfac costs validate` |
| `configs/costs/*.yaml` | 5 placeholder profiles + `assignments.yaml` |
| `data/split.py` | `HistoryTooShortError(DataError)` (so `costs show` can tell "no split possible" from real errors) |
| `pyproject.toml` | `strategy_factory.costs` removed from the relaxed mypy list (now strict) |

Conventions (module docstrings):
- Spread values are **full** spreads; the arrays carry half.
- `bps` and `pip` amounts are converted with the bar's **open**, the base price of fills at the open.
- Swap values are **credits** per unit of notional per day; negative means a charge.
- A bar `[ts, ts + timeframe)` gets the rollover mask when it contains a rollover instant. That is the rollover time in the local zone (DST-aware) on the rollover weekdays, Mon–Fri by default.

## Profile table (all `status: placeholder`)
| profile | spread (full) | commission | swap | slippage | symbols |
|---|---|---|---|---|---|
| `us_equity_default` | fixed 2 bps | 0.005 USD/share, min 1.00 USD | none | 1 bp + 0 × ATR | 6713 |
| `fx_default` | from_data × 1.0, fallback 1.0 pip | per_lot: 3.5 USD per 100,000 units per side | −3 % / −3 % per year (365), 17:00 NY, triple WED | 0.2 pip + 0.02 × ATR | 15 (pip 0.0001; JPY pairs 0.01 by override) |
| `metal_default` | from_data × 1.0 | none | −3 % / −3 %, 17:00 NY, triple WED | 0.02 × ATR | 2 |
| `index_cfd_default` | from_data × 1.0 | none | −3 % / −3 %, 17:00 NY, triple FRI | 0.02 × ATR | 10 |
| `energy_cfd_default` | from_data × 1.0 | none | −3 % / −3 %, 17:00 NY, triple FRI | 0.03 × ATR | 2 |

`sfac costs validate`: **6742 universe symbols assigned, 0 missing, 5 profiles (5 placeholder).** The universe is `us_equity_daily.csv`, `us_equity_hourly.csv` and `dukascopy.csv`. The aux series are excluded because they are not traded. Stress multipliers `[1.5, 2.0, 3.0]` are in `assignments.yaml`.

## EURUSD hourly spread (`sfac costs show EURUSD`, Dukascopy h1 pilot, DISPLAY ONLY)
Median full spread (ask close − bid close) per UTC hour of the bar start, Q1 2024 (1539 bars):

| UTC hour | bars | spread | pips |
|---|---|---|---|
| 00–03 | 64 each | 0.00002 | 0.20 |
| 04–09 | 64 each | 0.00003 | 0.30 |
| 10–12 | 64 each | 0.00002 | 0.20 |
| 13–14 | 64 each | 0.00003 | 0.30 |
| 15–19 | 64 each | 0.00002 | 0.20 |
| 20 | 64 | 0.00003 | 0.30 |
| **21** | 65 | **0.00014** | **1.40** |
| **22** | 65 | **0.00012** | **1.20** |
| 23 | 65 | 0.00003 | 0.30 |

The widening at 21–22 UTC is the New York rollover (17:00 NY). No hour used the fallback.

## Numba-side commission signature (for T08)
```
commission_kernel(code: int, p0: float, p1: float, p2: float, qty: float, price: float) -> float
  code 0 none                                   -> 0
  code 1 percent   p0 = rate                    -> rate * |qty| * price
  code 2 per_share p0 = per share, p1 = min, p2 = max (inf = none) -> clip(p0*|qty|, p1, p2)
  code 3 per_lot   p0 = lot size, p1 = amount per lot and side     -> |qty| / p0 * p1
```
It uses scalars only and no Python objects. T08 copies it into `engine/` under `@njit(cache=True)`, because the engine may not import `costs`. It receives `CostArrays.commission_params` as four scalars. A test pins `commission_kernel(*commission_params(p), …) == CostArrays.commission(…)`.

## How each criterion is tested (`tests/unit/test_F_0_2_costs.py`, 28 tests)
| criterion | test |
|---|---|
| F-0.2.1 profiles read and validated; exact placeholder values | `_shipped_placeholder_profiles_match_the_task` |
| every universe symbol assigned; JPY pip override | `_every_universe_symbol_is_assigned`, `_validate_cli` |
| missing profile → error (costs mandatory) | `_missing_assignment_is_an_error`, `_validate_cli` (metal group removed → exit 1 naming XAGUSD, XAUUSD) |
| placeholder flag readable by the engine | `_placeholder_flag_reaches_the_arrays` |
| each commission model (per-share min **and** max) | `_commission_models` (6 cases) + kernel equality |
| fixed bps spread/slippage | `_fixed_bps_spread_and_slippage_use_the_open` |
| from_data hourly medians, fallback, refuse unresolved | `_from_data_hourly_medians_hand_computed`, `_from_data_must_be_resolved_first` |
| from_data never sees the holdout | `_from_data_uses_development_bars_only` (holdout spreads × 1000 do not reach the table built through `DataAccess`) |
| F-0.2.3 swap hand-computed, triple day | `_annual_rate_swap_hand_computed_with_triple_wednesday` (long Mon→Sat = 7 swap days, short = credit, Thu→Fri = 1 day), `_points_per_day_swap` (triple Friday) |
| DST around the New York rollover | `_rollover_mask_follows_new_york_dst` (22:00 UTC in winter, 21:00 UTC in summer, the DST weekend) |
| F-0.2.4 stress ×1.5/2/3 on spread and slippage only | `_stress_scales_spread_and_slippage_only` |
| cost monotonicity (property) | `_raising_any_cost_component_never_lowers_total_cost` (Hypothesis, 200 examples, 5 components, fixed 4-trade sequence), `_stress_levels_monotone` |
| CLI show | `_show_cli_fixed_profile`, `_show_cli_display_only_for_short_snapshot` (`db`) |

## Acceptance
| command | result |
|---|---|
| `ruff check .` / `ruff format --check .` | ✅ / ✅ 155 files |
| `mypy src` (strict for `costs`) | ✅ 64 files |
| `pytest` | ✅ **306 passed** (28 new) |
| `pytest tests/parity tests/leakage` | ✅ 2 passed |
| `pytest -m db` | ✅ 14 passed, **0 skipped** |
| `sfac costs show EURUSD` | ✅ (table above) |
| `sfac costs validate` | ✅ |

## Deviations
1. **`build_cost_arrays` takes a keyword `timeframe`,** needed for the rollover mask (bar duration). Its `bars` argument is a mapping of NumPy arrays, not a DataFrame (Polars only in `data/`).
2. **`from_data` is a two-step process:** `resolve_from_data()` on development bars first, then `build_cost_arrays()`. `build_cost_arrays` refuses an unresolved `from_data` profile.
3. **The `from_data` fallback must be in price units or pips,** not bps: a per-hour table has no price to convert bps with.
4. **`points_per_day` swap is converted per notional with the bar's close.**
5. **For daily bars the from_data spread uses the UTC hour of the bar start** (00:00 for FX daily bars).
6. **`rollover_weekdays` (default Mon–Fri) is an extra profile field.** Without it there would be Sunday rollovers.
7. **`round_trip_cost()` is a reference calculator.** The engine (T08) owns the real P&L. It charges swap on the **entry** notional.

## Open questions
1. **Non-USD quote currencies** (EURGBP, DEUIDXEUR, JPNIDXJPY, …): commission (USD) and P&L are mixed with quote-currency prices. Currency conversion is not in T06's scope and has to be decided before T08/T09 run on those symbols.
2. **Swap for daily bars:** a daily FX bar stamped Monday 00:00 UTC also covers Sunday evening, when there is no rollover. The mask is correct, but please confirm that Monday–Friday rollover days with a triple Wednesday (FX/metals) and a triple Friday (CFDs) match the broker once it is known.
3. **Real broker numbers:** only YAML changes are needed (`status: verified`).
