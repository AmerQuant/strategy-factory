# T06 — Cost model

**Features:** F-0.2.1 (cost-profile schema), F-0.2.3 (swap), F-0.2.4 (stress multipliers) · **Priority:** MVP · **Depends on:** T02, T04e (on `main`)

Read first: `CLAUDE.md`, `docs/design.md` §6 (execution price and costs), and the three features.

## Fixed decisions
- **Costs are mandatory.** A symbol without a cost profile cannot be backtested.
- Execution price = base price (trade or mid) ± half-spread ± slippage. Slippage = fixed + fraction × ATR of the signal bar. Commission follows the profile's model. Swap is charged at the profile's rollover time, with a triple day from the profile.
- Stress multipliers 1.5, 2 and 3 apply to spread and slippage.
- **The real broker is not known yet.** Build everything with **placeholder profiles** marked `status: placeholder`. Every backtest result that uses a placeholder profile carries a visible flag. The user supplies real numbers later; only YAML changes then.

## Scope

### 1. Profile schema (`costs/profile.py`, Pydantic, frozen)
- `CostProfile`: `name, status (placeholder|verified), source_note`, plus:
  - **spread:** `fixed` (in price units or bps) **or** `hourly_profile` (24 values, UTC hours) **or** `from_data` (use the snapshot `spread` column; median per UTC hour, times a scale factor);
  - **commission:** `percent` | `per_share` (with min and max per order) | `per_lot` (lot size, amount per side);
  - **swap:** `none` | `annual_rate` (long and short, on notional, can be negative) | `points_per_day` (long, short); plus `rollover_time_local`, `rollover_tz`, `triple_weekday`;
  - **slippage:** `fixed` (price units or bps) + `atr_fraction`.
- `configs/costs/*.yaml`: profiles per asset class and group, with symbol overrides. `configs/costs/assignments.yaml` maps each universe symbol or group to a profile. An unassigned symbol is an error.

### 2. Placeholder profiles (exact values; all `status: placeholder`)
| Profile | Spread | Commission | Swap | Slippage |
|---|---|---|---|---|
| `us_equity_default` | fixed 2 bps (full spread) | per_share 0.005 USD, min 1.00 USD | none | 1 bp + 0 × ATR |
| `fx_default` | from_data × 1.0 (Dukascopy hourly median), fallback fixed 1.0 pip | per_lot 3.5 USD per 100k per side | annual_rate −3 % long and −3 % short; rollover 17:00 America/New_York; triple Wednesday | 0.2 pip + 0.02 × ATR |
| `metal_default` | from_data × 1.0 | none | annual_rate −3 % / −3 %; 17:00 America/New_York; triple Wednesday | 0.02 × ATR |
| `index_cfd_default` | from_data × 1.0 | none | annual_rate −3 % / −3 %; 17:00 America/New_York; triple Friday | 0.02 × ATR |
| `energy_cfd_default` | from_data × 1.0 | none | annual_rate −3 % / −3 %; 17:00 America/New_York; triple Friday | 0.03 × ATR |

The swap rates are deliberately conservative placeholders. Document this in the YAML comments.

### 3. Cost arrays for the engine (`costs/arrays.py`)
`build_cost_arrays(bars, profile, stress=1.0) -> CostArrays` with per-bar NumPy arrays:
- `half_spread[n]`
- `slippage_fixed[n]`, `slippage_atr_frac` (scalar)
- `swap_long_per_notional_day[n]`, `swap_short_per_notional_day[n]`
- `rollover_mask[n]`: a bar contains the rollover instant
- `triple_mask[n]`

and a `commission(qty, price, side) -> float` function built from the profile (plain NumPy/Python; the engine will call a Numba-friendly variant in T08 — design that variant's signature now and document it).
- `from_data` spread:
  - for each UTC hour, the median `spread` over the development period, times the scale factor;
  - never uses future data: the profile is computed on the development segment only, through `DataAccess`.

### 4. Stress
`stress` multiplies `half_spread` and slippage by 1.5, 2 or 3. Commission and swap are unchanged.

### 5. CLI
- `sfac costs show <symbol>`: the resolved profile, the status flag, and the hourly spread table when `from_data` is used.
- `sfac costs validate`: every universe symbol is assigned; all profiles are valid.

## Tests
- Hand-computed fixtures for each commission model (including per-share min and max), each swap model (including triple day and DST around the New York rollover), `from_data` hourly medians, and the stress multiplier.
- Property: raising any cost component never lowers the total cost of a fixed trade sequence (cost monotonicity).
- A missing assignment raises an error; placeholder status propagates to a flag the engine can read.

## Acceptance
ruff, format, mypy (strict for `costs`), pytest pass; CI green. `sfac costs show EURUSD` works on the existing Dukascopy h1 snapshot (spread-by-hour table in the review).

## Review summary
Write it to `docs/reviews/T06_review.md`. Include the profile table, the EURUSD hourly spread table, the Numba-side commission signature designed for T08, deviations and open questions.
