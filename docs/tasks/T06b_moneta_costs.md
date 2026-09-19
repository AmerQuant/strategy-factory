# T06b — Moneta cost profiles and broker-symbol mapping

**Features:** F-0.2.1 (cost-profile schema, extended), F-0.2.2 (hourly spread profile scaled to the broker spread), F-0.2.3 (swap, Moneta models), F-0.9.1 (universe flag `broker_symbol`) · **Priority:** MVP (F-0.2.2 is P1 in the feature list but D-523 pulls it in) · **Depends on:** T06, T10a (on `main`)

Read first: `CLAUDE.md`, decisions **D-520 … D-526** (section H of the decisions log), D-013 (superseded by D-520 once this task is merged), D-307, D-311, **D-312 (swap on MTM notional), D-313 (volume-step rounding), D-314 (assumed volume step)**, `docs/reviews/T06_review.md` (schema, conventions, Numba commission signature, open questions 1–3), `docs/reviews/T10a_review.md` (universe), and the pending answers **P-05 … P-13** in `docs/decisions/pending.md`.

Input file (read-only, D-028): `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` (sha256 `f7132888…6199`, manifest next to it). It is **not** in git.

## What the file contains (observed while planning; the parser must verify it)
- Six sheets: `Forex&Metals` (70 symbols), `Commodities` (15), `Indices` (33), `Share_CFDs` (873: Stock US 491, ETF 57, Stock EU 132, Stock UK 93, Stock JP 80, Stock AE 20), `Crypto` (59), `Bond_CFDs` (7).
- Columns: `Symbol, Description, Point value, Digits, Contract Size, Profit cal Mode, …, Spread(For reference only), Commission, 3-day swap, SWAP long, SWAP short, Swap Type, Quote sample, Trading time`. `Share_CFDs` has an extra leading `Region` column.
- `Point value` = money per point per lot in the **quote currency** (e.g. `1.0 CAD` for AUDCAD+, `0.01 USD` for SP500.r). Point = 10^−Digits.
- `Commission`: `6.0 USD per lot` (FX and gold, round turn → 3 USD per side, D-521), `12.0 USD per trade` (51 ETFs), `0.2 percentage per lot` / `0.3 percentage per lot` (EU/UK/AE shares), `-` (none).
- `Swap Type`: `in points` (FX, metals, commodities, some crypto), `in currency` (indices), `in percentage terms` (shares, ETFs, most crypto), `-` (no swap: `ft` futures CFDs, CL-OIL, UKOUSDft, bonds, USDX.r, VIX.r and 16 ETFs).
- `3-day swap`: Wednesday (FX, gold), **Thursday** (USDTRY+), Friday (indices, commodities, shares, XPD/XPT).
- **The `Stock JP` rows are shifted by one column** (their commission cell is missing, so `3-day swap` holds `-3`). The parser must detect shifted rows and report them; they are not in the research universe.

## Scope

### 1. Import the broker file (`costs/moneta.py`, CLI `sfac costs moneta import`)
- Parse the six sheets into one **normalized, committed** table `configs/costs/moneta/moneta_spec.csv` with typed columns: `sheet, region, broker_symbol, description, digits, point_size, contract_size, contract_unit, quote_ccy, point_value, spread_points, spread_price, commission_model, commission_amount, commission_ccy, swap_model, swap_long, swap_short, triple_weekday, quote_sample, trading_time_server, row_status (ok | shifted | unparsed)`.
- A header comment line (or sidecar `moneta_spec.csv.meta.json`) records the source path, its sha256 and the import time. Re-importing the same file gives a byte-identical CSV.
- The runtime never reads the xlsx; only `import` does. **Library: P-05.**
- Every row is parsed or reported: `row_status != ok` rows are listed in the import report with the reason; they never get a profile.

### 2. Schema extensions (`costs/profile.py`, backwards compatible)
- **Commission model `per_order`** (P-07): a fixed amount per side (per order), `amount`, `currency`. Numba kernel code **4** is appended to the T06 `commission_kernel` signature: `code 4 per_order p0 = amount → p0` (independent of qty). Existing codes 0–3 are unchanged.
- **Commission currency** field on every commission model (`USD` default). The Moneta per-lot FX/metal commission is in USD; the percent commission of non-US shares is in the quote currency. The engine converts only non-USD amounts (D-307, T08).
- **Swap model `currency_per_lot_day`** (P-09): `long`, `short` in quote currency per lot per day, `contract_size`; converted per unit of notional with the bar close (like `points_per_day`).
- **`points_per_day`** gains an explicit `point_size` so Moneta points (10^−Digits) are not confused with pips.
- **`annual_rate`** keeps `day_count`; the Moneta percentage swap uses `day_count: 360` (P-08).
- **Spread for broker-mapped symbols:** new mode `broker_scaled` = the T06 `from_data` hourly shape, scaled so the bar-weighted mean over the development segment equals the broker reference spread (D-523, F-0.2.2). A `fallback` (the broker spread itself, fixed) is used when the symbol has no spread data.
- `bps` spread for share CFDs and ETFs, derived from the broker points and the file's `Quote sample` (P-06).
- `quote_ccy` and `point_value` become profile fields (needed by T08 for D-307 and D-061).
- **Volume fields (D-313, D-314):** `contract_size` (instrument units per lot), `volume_step` and `min_volume` (both in **lots**, from the file's `Volume Step` and `Min volume per click`), and `volume_step_assumed: bool`. Moneta profiles take them from the file (`volume_step_assumed: false`). Profiles without a Moneta row: us_equity → contract size 1 share, step 1, minimum 1; futures → whole contracts (step 1, minimum 1); both with `volume_step_assumed: true` (D-314). The engine reads them through `CostArrays` (scalars) (P-26).
- Every new field has a default that keeps the T06 placeholder YAMLs valid unchanged.

### 2b. Swap on the mark-to-market notional (D-312) — `round_trip_cost` is the test oracle
- `round_trip_cost()` (T06, entry notional) is **superseded**: at every rollover instant while the position is held, notional = |qty| × contract size × **close of the bar containing the rollover**, converted to USD at that bar (D-307):
  - `annual_rate` → rate / day_count × notional;
  - `points_per_day` → points × point size × |qty| × contract size;
  - `currency_per_lot_day` → amount × lots;
  - triple day → × 3.
- The per-bar swap arrays of `CostArrays` stay "credit per unit of notional at this bar's close", so the engine multiplies by the MTM notional of the same bar; `round_trip_cost` does the same, bar by bar, so T08 can use it as the oracle.
- `round_trip_cost` also applies the D-313 quantity rule (floor to the volume step, skip below the minimum) and returns the rounded qty and a `skipped_min_volume` flag.

### 3. Generate the Moneta profiles (`sfac costs moneta build`)
- One profile per **mapped** broker symbol, generated from `moneta_spec.csv` into `configs/costs/moneta/profiles/*.yaml` (or one generated `moneta_profiles.yaml`; either way generated, never hand-edited, with a header saying so). `status: verified`, `source_note` = file sha256 + row.
- Rules (D-520 … D-523):
  | broker rows | spread | commission | swap | triple |
  |---|---|---|---|---|
  | FX `+` pairs, gold `+` | `broker_scaled` (Dukascopy shape) | per_lot 100,000 / 100 oz, **3 USD per side** | points_per_day | from file (WED; THU for USDTRY+) |
  | XAG*, XPD, XPT | `broker_scaled` if Dukascopy data, else fixed | none | points_per_day | from file |
  | index cash CFDs (`.r`) | `broker_scaled` | none | currency_per_lot_day | FRI |
  | commodity CFDs | `broker_scaled` if Dukascopy data, else fixed | none | points_per_day or none (`-`) | FRI |
  | US shares | fixed bps (P-06) | none | annual_rate −6.88 % / −3.5 %, day_count 360 (P-08) | FRI |
  | ETFs | fixed bps (P-06) | per_order 12 USD per side (P-07), or none | annual_rate as file; `-` per P-10 | FRI |
- **Slippage:** the broker file has none. Keep the T06 slippage values per asset class (they are research assumptions, not broker numbers) and state it in the YAML header. Stress (F-0.2.4) is unchanged.
- **Rollover:** 17:00 America/New_York (D-522), weekdays Mon–Fri; triple day from the file.
- Non-mapped symbols keep a profile (costs are mandatory): **P-12**.

### 4. Broker ↔ research symbol mapping (D-524)
- `configs/costs/moneta/symbol_map.csv`: `research_symbol, broker_symbol, method (manual | ticker_exact | ticker_name | override), name_score, note`.
- **Dukascopy instruments (29):** a hand-written table (P-11). All 29 have a Moneta equivalent.
- **US shares (491) and ETFs (57):** matched against the research universe with the Alpaca asset names in `SFAC_RAW_ROOT/reference/quantplatform/assets/us_assets_2026-06-22.csv` (P-13):
  1. exact ticker match **and** name similarity ≥ `min_name_score` (config) → `ticker_exact`;
  2. otherwise the best name match with score ≥ threshold → **candidate only**, written to `docs/reviews/T06b_mapping_review.csv` for the user;
  3. `configs/costs/moneta/symbol_overrides.csv` (manual, committed) wins over everything; known cases from D-524: AALG→AAL, ABBVIE→ABBV, AMAZON→AMZN, AT&T→T, ALIBABA→BABA; entries may also mark a broker symbol `unmappable` with a reason.
  4. **Acceptance of the mapping:** every one of the 548 broker US shares/ETFs is either mapped to exactly one research symbol or listed as unmappable with a reason; no research symbol maps to two broker symbols.
- The thresholds live in `configs/costs/moneta/mapping.yaml`.

### 5. Universe flag (F-0.9.1, D-524)
- `UniverseEntry` gains `broker_symbol: str | None` and the universe generator fills it from `symbol_map.csv`; `configs/universe.yaml` is regenerated.
- `sfac universe list --broker` / `--no-broker`; `PipelineConfig` gains `universe_filter: broker | all` with **default `broker`** (D-524). A run with `all` marks non-broker results `report_only` (stored in the run config; the reporting itself is later work).
- `sfac universe validate` checks: a `broker_symbol` exists in `moneta_spec.csv`, is unique, and its profile is the Moneta profile.

### 6. Assignments and the placeholder flag
- `configs/costs/assignments.yaml`: mapped symbols → Moneta profiles; non-mapped symbols → P-12 profiles. `sfac costs validate` still requires every universe symbol to resolve.
- `CostArrays` / `RunMeta.cost_status` stays `placeholder | verified`. After this task, broker symbols are `verified`, everything else `placeholder` (D-013 superseded by D-520 for broker symbols).
- `sfac costs show <symbol>` prints the broker symbol, the source row and, for `broker_scaled`, the hourly table before and after scaling plus the scale factor.

### 7. Swap share (D-525)
- `round_trip_cost()` (the T06 reference calculator) reports the swap component separately (already does); add a helper `cost_breakdown_shares(costs) -> {spread, slippage, commission, swap}` as fractions, to be used by T09/stage-8 reporting. No report work here.

## Out of scope
- The engine side of currency conversion and futures sizing (T08).
- Crypto, non-US shares, bonds: parsed and stored in `moneta_spec.csv`, **no profiles** (D-020: P2 / not in the universe).
- Any network access.

## Tests (`tests/unit/test_F_0_2_moneta.py`; names start with the feature ID)
- Import: a small **synthetic xlsx fixture** (built in the test with the chosen library, P-05) covering each sheet layout, the `Region` column, a shifted row, `-` cells, numbers stored as floats like `4.3099999999999996`. Byte-identical re-import.
- Hand-computed profile per model: EURUSD+ (per_lot 3 USD/side, points swap −9.46/+4.69 → per notional at a given close, triple WED), USDTRY+ (triple THU), SP500.r (currency swap −1.5024/+0.27989 per lot → per notional), AAPL (bps spread from 9.24 points / 211.06, annual −6.88 % / −3.5 % over 360 days, triple FRI), an ETF with per_order 12 USD, an ETF with `-` swap (P-10).
- `commission_kernel` code 4 equals the Python commission; codes 0–3 unchanged (the T06 tests still pass unmodified).
- F-0.2.2: after `broker_scaled`, the bar-weighted mean of the hourly spread over the **development** bars equals the broker spread (rel 1e-12); holdout bars never reach the scaling (same technique as the T06 `from_data` test).
- Mapping: exact ticker + name check, a name-only candidate goes to review (not auto-mapped), an override wins, `unmappable` with reason, duplicate mapping rejected.
- Universe: `broker_symbol` filled; default `universe_filter` is `broker`; validation errors (unknown broker symbol, duplicate).
- Costs remain mandatory: removing a mapped symbol's profile fails `sfac costs validate`.
- Cost monotonicity property (T06) extended to the new models.
- **D-312 (required):** a hand-computed **multi-day swap with a changing close price across a triple day**, for each swap model (annual_rate on a share CFD, points_per_day on EURUSD+, currency_per_lot_day on SP500.r), with a non-USD case converted at each rollover bar's close; `round_trip_cost` equals the hand numbers (rel 1e-12). The old entry-notional expectation in the T06 tests is updated, and the change is listed in the review.
- **D-313 / D-314:** profile volume fields parsed from the file (EURUSD+ step 0.01 lot, contract 100,000; AAPL step 0.1, contract 1 share); the proxy us_equity profile has step 1 share and `volume_step_assumed: true`; `round_trip_cost` floors the qty to the step (a hand case where flooring changes the qty) and flags a trade below the minimum volume.

## Acceptance
- ruff, format, mypy (strict for `costs`, `core`), fast suite, parity + leakage, `pytest -m db` (0 skipped).
- `sfac costs moneta import` on the real file: counts per sheet and the list of non-ok rows in the review.
- `sfac costs moneta build` + `sfac costs validate`: all universe symbols resolve; counts of `verified` vs `placeholder` profiles in the review.
- Mapping coverage: 548/548 broker US shares + ETFs mapped or listed as unmappable; the review CSV of name-only candidates is attached for the user.
- `sfac costs show EURUSD` on the Dukascopy pilot (display-only rule of T06 applies): hourly table before/after scaling, scale factor, mean = 2.61 points × 1e-5.

## Review summary
`docs/reviews/T06b_review.md`: the normalized table columns, per-sheet counts, the profile rule table as built, the Numba commission signature with code 4, mapping statistics (by method) and the unmapped list, hand-computed examples, deviations, open questions. New dependency (if P-05 = openpyxl) listed with its reason.
