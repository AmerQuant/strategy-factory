# T06b — Moneta cost profiles and broker-symbol mapping

**Features:** F-0.2.1 (cost-profile schema, extended), F-0.2.2 (hourly spread profile scaled to the broker spread), F-0.2.3 (swap, Moneta models), F-0.9.1 (universe flag `broker_symbol`) · **Priority:** MVP (F-0.2.2 is P1 in the feature list but D-523 pulls it in) · **Depends on:** T06, T10a (on `main`)

Read first: `CLAUDE.md`, decisions **D-520 … D-526** (section H of the decisions log), D-013 (superseded by D-520 once this task is merged), D-307, D-311, **D-312** (swap on MTM notional), **D-313 + D-315** (volume-step rounding in lots), **D-314**, and **D-317 … D-325, D-340** (resolved batch-2b questions), plus `docs/reviews/T06_review.md` (schema, conventions, Numba commission signature, open questions 1–3) and `docs/reviews/T10a_review.md` (universe).

Input file (read-only, D-028): `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` (sha256 `f71328881a4cdcff573e169e122a78a5274d96c1de8bd968c733643a71eb6199`, manifest next to it, supplied 2026-09-19). It is **not** in git.

## What the file contains (observed while planning; the parser must verify it)
- Six sheets: `Forex&Metals` (70 symbols), `Commodities` (15), `Indices` (33), `Share_CFDs` (873: Stock US 491, ETF 57, Stock EU 132, Stock UK 93, Stock JP 80, Stock AE 20), `Crypto` (59), `Bond_CFDs` (7).
- Columns: `Symbol, Description, Point value, Digits, Contract Size, Profit cal Mode, Leverage, Min volume per click, Max volume per click, Volume Step, …, Spread(For reference only), Commission, 3-day swap, SWAP long, SWAP short, Swap Type, Quote sample, Trading time`. `Share_CFDs` has an extra leading `Region` column.
- `Point value` = money per point per lot in the **quote currency** (e.g. `1.0 CAD` for AUDCAD+, `0.01 USD` for SP500.r). Point = 10^−Digits.
- `Commission`: `6.0 USD per lot` (FX and gold, round turn → 3 USD per side, D-521), `12.0 USD per trade` (51 ETFs), `0.2 percentage per lot` / `0.3 percentage per lot` (EU/UK/AE shares), `-` (none).
- `Swap Type`: `in points` (FX, metals, commodities, some crypto), `in currency` (indices), `in percentage terms` (shares, ETFs, most crypto), `-` (no swap: `ft` futures CFDs, CL-OIL, UKOUSDft, bonds, USDX.r, VIX.r and 16 ETFs).
- `3-day swap`: Wednesday (FX, gold), **Thursday** (USDTRY+), Friday (indices, commodities, shares, XPD/XPT).
- **The `Stock JP` rows are shifted by one column** (their commission cell is missing, so `3-day swap` holds `-3`). The parser must detect shifted rows and report them; they are not in the research universe.

## Scope

### 1. Import the broker file (`costs/moneta.py`, CLI `sfac costs moneta import`)
- Library: **openpyxl, dev-only dependency** (D-317). It is imported lazily inside `import`; without it the command fails with a clear message. Nothing else reads Excel.
- Parse the six sheets into one **normalized, committed** table `configs/costs/moneta/moneta_spec.csv` with typed columns: `sheet, region, broker_symbol, description, digits, point_size, contract_size, contract_unit, quote_ccy, point_value, min_volume_lots, volume_step_lots, spread_points, spread_price, commission_model, commission_amount, commission_ccy, swap_model, swap_long, swap_short, triple_weekday, quote_sample, trading_time_server, row_status (ok | shifted | unparsed)`.
- **Provenance (D-340):** a sidecar `moneta_spec.csv.meta.json` records the source path relative to `SFAC_RAW_ROOT`, the file's **SHA-256** (checked against the manifest; a mismatch is an error), the file date (2026-09-19) and the import time. Re-importing the same file gives a byte-identical CSV.
- Every row is parsed or reported: `row_status != ok` rows are listed in the import report with the reason; they never get a profile.

### 2. Schema extensions (`costs/profile.py`, backwards compatible)
- **Commission model `per_order`** (D-319): a fixed amount per side (per order), `amount`, `currency`. Numba kernel code **4** is appended to the T06 `commission_kernel` signature: `code 4 per_order p0 = amount → p0` (independent of qty). Codes 0–3 are unchanged.
- **Commission currency** on every commission model (`USD` default). The Moneta per-lot FX/metal commission is in USD; the percent commission of non-US shares is in the quote currency (D-328).
- **Swap model `currency_per_lot_day`** (D-321): `long`, `short` in quote currency per lot per day.
- **`points_per_day`** gains an explicit `point_size`, so Moneta points (10^−Digits) are not confused with pips.
- **`annual_rate`** keeps `day_count`: Moneta profiles use **360** (D-320); the T06 default stays 365.
- **`to_verify: list[str]`** on the profile: notes of values not yet confirmed by the broker. Non-USD index swaps get `swap_non_usd_index` (D-321); ETFs with an assumed swap get `swap_assumed` (D-322).
- **Spread mode `broker_scaled`** (D-523, F-0.2.2): the T06 `from_data` hourly shape, scaled so the **bar-weighted mean over the development bars** equals the broker reference spread. The scale is fitted on development bars only, through `DataAccess` (D-340). A `fallback` (the broker spread itself, fixed) is used when the symbol has no spread data.
- **bps spread for share CFDs and ETFs** (D-318): `spread_points × point_size / quote_sample × 10⁴`.
- **Instrument fields:** `quote_ccy`, `point_value`, `contract_size` (instrument units per lot), `volume_step` and `min_volume` (**in lots**, D-315), `volume_step_assumed: bool`. Moneta profiles take them from the file; profiles without a Moneta row follow D-314 (us_equity: contract size 1 share, step 1, minimum 1, `volume_step_assumed: true`). `CostArrays` exposes them as scalars for the engine.
- Every new field has a default that keeps the T06 placeholder YAMLs valid unchanged.

### 3. `round_trip_cost` = the engine's oracle (D-312, D-315)
- The T06 entry-notional swap is **superseded**. At every rollover instant while the position is held, notional = |qty| × contract size × **close of the bar containing the rollover**, converted to USD at that bar (D-307):
  - `annual_rate` → rate / day_count × notional;
  - `points_per_day` → points × point size × |qty| × contract size;
  - `currency_per_lot_day` → amount × lots;
  - triple day → × 3.
- The per-bar swap arrays of `CostArrays` stay "credit per unit of notional at this bar's close", so the engine multiplies them by the MTM notional of the same bar. `round_trip_cost` does the same, bar by bar.
- Quantity (D-315): `lots = floor((notional_usd / (entry_price_usd × contract_size)) / volume_step) × volume_step`, `qty = lots × contract_size`. When lots < `min_volume` the trade is not made and `skipped_min_volume` is returned (D-313).

### 4. Generate the Moneta profiles (`sfac costs moneta build`)
- One profile per **mapped** broker symbol, generated from `moneta_spec.csv` into one generated file `configs/costs/moneta/moneta_profiles.yaml` (header: generated, never hand-edited). `status: verified`. `source_note` = file SHA-256, file date, sheet and row, and for bps spreads the **quote sample price** used (D-318).
- Rules (D-520 … D-523, D-319 … D-322):
  | broker rows | spread | commission | swap | triple |
  |---|---|---|---|---|
  | FX `+` pairs, gold `+` | `broker_scaled` (Dukascopy shape) | per_lot, **3 USD per side** | points_per_day | from file (WED; THU for USDTRY+) |
  | XAG*, XPD, XPT | `broker_scaled` if Dukascopy data, else fixed | none | points_per_day | from file |
  | index cash CFDs (`.r`) | `broker_scaled` | none | currency_per_lot_day (non-USD: `to_verify`) | FRI |
  | commodity CFDs | `broker_scaled` if Dukascopy data, else fixed | none | points_per_day, or none for `-` | FRI |
  | US shares | fixed bps (D-318) | none | annual_rate −6.88 % / −3.5 %, day_count 360 | FRI |
  | ETFs | fixed bps (D-318) | per_order 12 USD per side, or none (`-`) | annual_rate from file; `-` → −6.88 % / −3.5 % with `swap_assumed` (D-322) | FRI |
- **Slippage:** the broker file has none. Keep the T06 slippage values per asset class (research assumptions, not broker numbers) and say so in the header. Stress (F-0.2.4) is unchanged.
- **Rollover:** 17:00 America/New_York (D-522), weekdays Mon–Fri; triple day from the file.
- **Non-mapped research symbols:** a generated `us_share_cfd_proxy` profile (D-324): the Moneta US-share model, spread = median bps of the 491 broker US shares, step 1 share with `volume_step_assumed`, `status: placeholder` (report-only, D-524).

### 5. Broker ↔ research symbol mapping (D-524, D-323, D-325)
- `configs/costs/moneta/symbol_map.csv`: `research_symbol, broker_symbol, method (manual | ticker_exact | override), name_score, note`.
- **Dukascopy instruments (29):** the hand table of D-323.
- **US shares (491) and ETFs (57)** vs the research universe, with the Alpaca asset names in `SFAC_RAW_ROOT/reference/quantplatform/assets/us_assets_2026-06-22.csv` (D-325):
  1. identical ticker **and** name similarity ≥ `min_name_score` → `ticker_exact`;
  2. otherwise the best name match ≥ threshold → **candidate only**, written to `docs/reviews/T06b_mapping_review.csv` for the user, never auto-mapped;
  3. `configs/costs/moneta/symbol_overrides.csv` (manual, committed) wins over everything. It starts with the D-524 cases AALG→AAL, ABBVIE→ABBV, AMAZON→AMZN, AT&T→T, ALIBABA→BABA, and it may mark a broker symbol `unmappable` with a reason.
  4. **Coverage:** every one of the 548 broker US shares/ETFs is mapped to exactly one research symbol or listed as unmappable with a reason; no research symbol maps to two broker symbols.
- Thresholds live in `configs/costs/moneta/mapping.yaml`.

### 6. Universe flag (F-0.9.1, D-524)
- `UniverseEntry` gains `broker_symbol: str | None`, filled from `symbol_map.csv` by the universe generator; `configs/universe.yaml` is regenerated.
- `sfac universe list --broker / --no-broker`. `PipelineConfig` gains `universe_filter: broker | all`, **default `broker`**. A run with `all` marks non-broker results `report_only` in the run config.
- `sfac universe validate` checks that each `broker_symbol` exists in `moneta_spec.csv`, is unique, and its symbol uses the Moneta profile.

### 7. Assignments, flags and the swap share
- `configs/costs/assignments.yaml`: mapped symbols → Moneta profiles; others → the proxy profile. `sfac costs validate` still requires every universe symbol to resolve.
- `cost_status` stays `placeholder | verified`: broker symbols are `verified`, everything else `placeholder` (D-013 superseded by D-520 for broker symbols).
- `sfac costs show <symbol>` prints the broker symbol, the source row, `to_verify` notes and, for `broker_scaled`, the hourly table before and after scaling plus the scale factor.
- `cost_breakdown_shares(costs) -> {spread, slippage, commission, swap}` as fractions, for later stage-8 reporting (D-525). No report work here.

## Out of scope
- Engine-side conversion, sizing and futures (T08).
- Crypto, non-US shares, bonds: parsed into `moneta_spec.csv`, **no profiles** (D-020).
- Any network access.

## Tests (tests first; names start with the feature ID)
`tests/unit/test_F_0_2_moneta.py`:
- **Import:** a synthetic xlsx fixture built in the test with openpyxl, covering each sheet layout, the `Region` column, a shifted row, `-` cells, and floats like `4.3099999999999996`. The re-import is byte-identical. The sidecar holds the SHA-256, and a SHA mismatch with the manifest is an error.
- **Hand-computed profiles:**
  - EURUSD+: per_lot 3 USD/side; points swap −9.46/+4.69; triple WED.
  - USDTRY+: triple THU.
  - SP500.r: currency swap per lot.
  - A non-USD index (GER40.r): currency swap, `to_verify`.
  - AAPL: 9.24 points / 211.06 → 4.378 bps; −6.88 % / −3.5 % over 360 days; `source_note` carries the sample price and file date.
  - An ETF with per_order 12 USD.
  - An ETF with `-` swap: assumed rates, `swap_assumed`.
- **Commission kernel:** code 4 equals the Python commission; codes 0–3 are unchanged, and the T06 tests pass unmodified except for the superseded entry-notional swap expectation (listed in the review).
- **D-312 (required):** a hand-computed **multi-day swap with a changing close price across a triple day**, for each swap model:
  - annual_rate on a share CFD;
  - points_per_day on EURUSD+;
  - currency_per_lot_day on SP500.r;
  - plus a non-USD case converted at each rollover bar's close.
  `round_trip_cost` equals the hand numbers (rel 1e-12).
- **D-315 / D-313 / D-314:**
  - volume fields parsed in lots (EURUSD+ step 0.01, min 0.01, contract 100,000; AAPL step 0.1, contract 1);
  - a hand case where flooring changes the lots;
  - a trade below the minimum volume is flagged `skipped_min_volume`;
  - the proxy profile has step 1 with `volume_step_assumed`.
- **Mapping:**
  - identical ticker + name check → mapped;
  - a name-only candidate goes to the review CSV, not mapped;
  - an override wins;
  - `unmappable` with a reason;
  - a duplicate mapping is rejected.
- **Universe:** `broker_symbol` is filled; the default `universe_filter` is `broker`; validation errors (unknown broker symbol, duplicate).
- **Costs are mandatory:** removing a mapped symbol's profile fails `sfac costs validate`.
- The cost-monotonicity property (T06) is extended to the new models.

`tests/leakage/test_F_0_2_2_broker_scaling_dev_only.py` (mandatory gate, D-340): the `broker_scaled` factor and hourly shape are fitted on development bars only. Multiplying the holdout spreads by 1000 changes neither the factor nor the table. After scaling, the bar-weighted mean over the development bars equals the broker spread (rel 1e-12).

## Acceptance
- ruff, format, mypy (strict for `costs`, `core`), fast suite, parity + leakage, `pytest -m db` (0 skipped).
- `sfac costs moneta import` on the real file: counts per sheet, the SHA-256, and the list of non-ok rows, all in the review.
- `sfac costs moneta build` + `sfac costs validate`: all universe symbols resolve; counts of `verified` vs `placeholder` profiles, and the `to_verify` list, in the review.
- Mapping coverage: 548/548 broker US shares + ETFs mapped or listed as unmappable; the review CSV of name-only candidates is handed to the user.
- `sfac costs show EURUSD` on the Dukascopy pilot (the T06 display-only rule applies): hourly table before/after scaling, the scale factor, and a mean of 2.61 points × 1e-5.

## Review summary
`docs/reviews/T06b_review.md` contains:
- the normalized table columns and per-sheet counts;
- the profile rule table as built;
- the Numba commission signature with code 4;
- mapping statistics by method and the unmapped list;
- the hand-computed examples;
- the changed T06 expectation (D-312);
- deviations and open questions.

It also lists the new dev dependency: **openpyxl**, with its reason (D-317).
