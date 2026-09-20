# T06b review — Moneta cost profiles and broker-symbol mapping

**Features:** F-0.2.1, F-0.2.2, F-0.2.3, F-0.9.1 · **Branch:** `feat/T06b-moneta-costs` (stacked on `docs/batch2b`) · **Status:** done, except the **mapping-coverage criterion, which stays open** until the user reviews the mapping (P-28).

**Decisions used:** D-013 (superseded by D-520 for broker symbols), D-307, D-311, D-312 … D-315, D-317 … D-325, D-340, D-520 … D-526.

## Dependencies
- **openpyxl 3.1.5** (+ et-xmlfile 2.0.0), **dev group only** (D-317). `sfac costs moneta import` imports it lazily and it reads the broker xlsx; nothing else reads Excel. `uv add --dev openpyxl` left the numba/numpy pins unchanged. mypy: `openpyxl` was added to the ignore-missing-imports override because the package ships no types.

## What was built
| File | Content |
|---|---|
| `costs/profile.py` | Schema extensions, all backwards compatible:<br>• commission `per_order`, plus a `currency` on every commission model;<br>• swap `currency_per_lot_day`, and a `point_size` on `points_per_day`;<br>• spread `broker_scaled`;<br>• instrument fields `broker_symbol`, `quote_ccy`, `point_value`, `contract_size`, `volume_step` / `min_volume` (**lots**, D-315), `volume_step_assumed` (default `true`, D-314) and `to_verify`.<br>Loaders also read the generated `moneta/moneta_profiles.yaml` and merge the generated `moneta/assignments.yaml`; a symbol listed in both assignment files is an error. |
| `costs/arrays.py` | • commission kernel code 4;<br>• swap arrays for the new models;<br>• `broker_scaled_table` and `resolve_from_data` for `broker_scaled` (development bars only);<br>• instrument fields on `CostArrays`, and `commission_in_quote`;<br>• a third-currency commission is refused;<br>• `size_lots` (D-315/D-313);<br>• `round_trip_cost` on the MTM notional (D-312), with `close=` and `fx_close=` keywords;<br>• `cost_breakdown_shares` (D-525). |
| `costs/moneta.py` | • xlsx → normalized table (`SpecRow`) with the row statuses `ok / incomplete / shifted / unparsed`;<br>• sidecar holding the SHA-256, checked against the manifest (D-340; a missing manifest is an error);<br>• mapping (D-323, D-325), profile rules (D-318 … D-324), `build`. |
| `costs/cli.py` | • `sfac costs moneta import` (the file must be under `SFAC_RAW_ROOT`) and `sfac costs moneta build`;<br>• `costs show` prints the broker symbol, volume fields and `to_verify`, and for `broker_scaled` the hourly table before and after scaling, the scale factor and the weighted mean. |
| `core/universe.py`, `core/cli.py` | `UniverseEntry.broker_symbol`, filled from `symbol_map.csv`. Validation checks that the broker symbol is an ok row, is unique, and matches the Moneta profile. `sfac universe list --broker/--no-broker`. |
| `core/config.py` | `PipelineConfig.universe_filter: broker \| all` (default `broker`, D-524) and `report_only`, which is filled by `resolve_config` and stored in the run config. |
| `configs/costs/moneta/` | Hand-written: `moneta.yaml` (rules; every number cites a decision), `mapping.yaml`, `dukascopy_map.csv`, `symbol_overrides.csv`.<br>Generated: `moneta_spec.csv` (+ `.meta.json`), `moneta_profiles.yaml`, `assignments.yaml`, `symbol_map.csv`. |
| `configs/costs/assignments.yaml` | `us_equity` group → `us_share_cfd_proxy`. The JPY `pip_size` overrides were removed: they belonged to the `fx_default` fallback, which no symbol uses now. |
| `configs/universe.yaml` | Regenerated with `broker_symbol`. |
| `configs/pipeline/mvp_daily.yaml` | `universe_filter: all` until SPY/QQQ are confirmed (P-29). |
| `docs/reviews/T06b_mapping_review.csv` | Generated review list for the user (127 rows). |

## Import of the real file (`sfac costs moneta import`)
- Source: `reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx`, sha256 `f71328881a4cdcff573e169e122a78a5274d96c1de8bd968c733643a71eb6199`, which equals the manifest. File date 2026-09-19.
- Rows per sheet: Forex&Metals 70, Commodities 15, Indices 33, Share_CFDs 873, Crypto 59, Bond_CFDs 7 → **1057 rows: 977 ok, 80 incomplete**.
- The 80 incomplete rows are **all 80 Stock JP rows** (no spread, no quote sample). **Correction to the task file:** the planning note "Stock JP rows are shifted" was wrong. It was an artefact of my planning parser, which skipped empty cells. openpyxl reads the columns correctly. Shifted-row detection is still implemented and tested with a synthetic row.
- `1e-05 XAU` point values (BTCXAU, ETHXAU) are parsed.
- Re-importing gives a byte-identical `moneta_spec.csv`, and rebuilding gives byte-identical generated files.

## Normalized table columns
`sheet, row, region, broker_symbol, description, digits, point_size, contract_size, contract_unit, quote_ccy, point_value, min_volume_lots, volume_step_lots, spread_points, spread_price, commission_model, commission_amount, commission_ccy, swap_model, swap_long, swap_short, triple_weekday, quote_sample, trading_time_server, row_status, status_reason`

The task lists these columns without `row` and `status_reason`, which were added (P-30).

## Profile rules as built (`moneta_profiles.yaml`: 450 broker profiles + 1 proxy)
| Broker rows | Spread | Commission | Swap | Triple |
|---|---|---|---|---|
| FX `+`, XAU* `+` | `broker_scaled` (reference points × point) | per_lot, lot = contract size, **3 USD per side** (6 round turn, D-521) | points_per_day, point_size 10^−digits | from file (WED; USDTRY+ THU) |
| XAG*, XPD, XPT | `broker_scaled` if research class has data | none | points_per_day | from file |
| index `.r` | `broker_scaled` | none | currency_per_lot_day; non-USD → `to_verify: swap_non_usd_index` (D-321) | FRI |
| commodity CFDs | `broker_scaled` | none | points_per_day, or none for `-` | FRI |
| US shares | fixed **bps** = points × point / quote sample; `source_note` has the sample price and file date (D-318) | none | annual_rate −6.88 % / −3.5 %, **day_count 360** (D-320) | FRI |
| ETFs | fixed bps (D-318) | **per_order 12 USD per side** (D-319), or none | from file; `-` → −6.88 / −3.5 % with `to_verify: swap_assumed` (D-322) | FRI |
| `us_share_cfd_proxy` (D-324) | fixed **21.2224 bps** = median of the 491 broker US shares | none | −6.88 / −3.5 %, 360 days, FRI | — |

All profiles share these settings:
- rollover at 17:00 America/New_York, Mon–Fri (D-522);
- `status: verified` for broker profiles, `placeholder` for the proxy;
- volume fields from the file (EURUSD+: contract 100,000, step 0.01, min 0.01 lot; AAPL: contract 1, step 0.1). The proxy has step 1 with `volume_step_assumed` (D-314);
- slippage keeps the T06 per-class research assumptions (the broker file has none).

`to_verify`: AUSIDXAUD, DEUIDXEUR, FRAIDXEUR, GBRIDXGBP, HKGIDXHKD and JPNIDXJPY carry `swap_non_usd_index`. No mapped ETF currently carries `swap_assumed`, because the ETFs are still in review.

`sfac costs validate`: **6742 universe symbols assigned, 0 missing; 456 profiles (6 placeholder)**. 450 symbols use a verified Moneta profile, and 6292 non-broker US equities use the proxy.

## Numba commission signature (for T08)
```
commission_kernel(code, p0, p1, p2, qty, price) -> float
  0 none -> 0 · 1 percent p0=rate -> rate*|qty|*price · 2 per_share p0,p1=min,p2=max -> clip
  3 per_lot p0=lot size, p1=amount per lot and side -> |qty|/p0*p1
  4 per_order p0=amount per order (side) -> p0          (appended, D-319)
```
The result is in `CostArrays.commission_ccy`. The engine converts it only when `commission_in_quote` is true (D-328). Any other currency is refused when the arrays are built.

## Hand-computed examples (tests)
- **D-312, annual rate, share CFD.** Wed–Tue daily bars with closes 100, 104, 99, 101, 103; triple Friday; qty 10.
  - Swap long = 0.0688/360 × 10 × (100 + 104 + 3×99 + 101) = **1.15049 USD**.
  - Short = 0.035/360 × 6020. Both sides pay.
  - The superseded entry-notional rule would give a different value, and a test asserts it.
- **D-312, points, EURUSD-like.** Tue + Wed(×3), 0.9 lot: 9.46 × 1e-5 × 90,000 × 4 = **34.056 USD**, whatever the close. Short 4.69 points = a credit.
- **D-312, currency per lot, non-USD (GER40-like).** 6 lots, Thu at EURUSD 1.10 + Fri ×3 at 1.09: 3.4908 × 6 × (1.10 + 3.27) = **91.529 USD**.
- **D-315 floor.** EURUSD at 1.0837: 0.92276 lot → **0.92 lot**. A share at 211.07 with step 0.1: 473.7765 → **473.7**, and notional ≤ 100,000. A price of 2,000,000 with step 0.1 is skipped below the minimum (D-313). The proxy with step 1 at price 150,000 is skipped.
- **Profiles.** AAPL spread = 9.24 × 0.01 / 211.06 × 10⁴ = **4.3779 bps**; EURUSD+ commission **3.0 USD per lot per side**.
- **F-0.2.2.** Medians 1e-5 and 3e-5 with 2 bars each and a broker spread of 4e-5 → **scale 2**, and the bar-weighted mean equals the broker spread (rel 1e-12). EURUSD pilot (display only): scale **0.780111**, and the mean after scaling is **2.61e-05**, the broker's 2.61 points.

## How each criterion is tested
| Criterion | Test |
|---|---|
| F-0.2.1: profiles from config, validated; costs mandatory | `test_F_0_2_moneta.py::test_F_0_2_1_costs_mandatory_after_moneta` (removing `moneta_AAPL` fails `costs validate`), `test_F_0_2_costs.py::test_F_0_2_1_validate_cli` |
| Import: every sheet, `Region`, `-`, float artefacts, shifted, incomplete, `1e-05` | `test_F_0_2_1_import_normalizes_every_sheet` (synthetic xlsx) |
| Byte-identical re-import; SHA in sidecar; SHA mismatch and missing manifest are errors | `test_F_0_2_1_import_is_byte_identical_and_records_sha` |
| Real broker table (counts, SHA) | `test_F_0_2_1_repo_broker_table_is_the_imported_file` |
| Hand-computed profiles: FX, USDTRY THU, SP500, GER40 `to_verify`, AAPL bps/360, ETF per_order, ETF assumed swap, no swap, proxy | `test_F_0_2_1_fx_profile_hand_computed`, `_index_profiles_and_non_usd_to_verify`, `_share_profile_bps_and_360_day_swap`, `_etf_profiles_per_order_and_assumed_swap`, `_no_swap_rows_and_proxy_profile` |
| Kernel code 4 = Python | `test_F_0_2_1_commission_kernel_code_4_matches_python` |
| **D-312** multi-day swap, changing price, triple day, each model, non-USD | `test_F_0_2_3_d312_annual_rate_on_changing_price_with_triple_friday`, `_points_per_day_is_price_independent`, `_currency_per_lot_non_usd_converted_each_rollover_bar` |
| D-307/D-328 spread and quote-currency commission conversion; third currency refused | `test_F_0_2_3_non_usd_spread_and_quote_commission_converted`, `test_F_0_2_1_third_currency_commission_is_refused` |
| **D-315/D-313/D-314** floor, skip, assumed step | `test_F_0_2_1_d315_lots_floor_to_the_step`, `_d313_below_minimum_volume_is_skipped`, `_repo_profiles_volume_fields` |
| F-0.2.2 scaling hand-computed; unresolved profile refused; no spread → broker spread fixed | `test_F_0_2_2_broker_scaled_hand_computed` |
| **F-0.2.2 / D-340 leakage** | `tests/leakage/test_F_0_2_2_broker_scaling_dev_only.py`: holdout spreads ×1000 change neither the table nor the factor (`source_note`), and the development mean equals the broker spread |
| `costs show EURUSD` before/after, factor, mean | `test_F_0_2_costs.py::test_F_0_2_1_show_cli_display_only_for_short_snapshot` (db) |
| Mapping: ticker + name, name-only → review, override wins, `UNMAPPABLE`, duplicates rejected (research and Dukascopy broker) | `test_F_0_9_1_mapping_rules`, `_mapping_overrides_unmappable_and_duplicates`, `_dukascopy_map_broker_symbol_listed_twice`, `_name_score` |
| Build and CLI end-to-end; import refuses files outside `SFAC_RAW_ROOT` | `test_F_0_9_1_build_end_to_end`, `test_F_0_2_1_cli_moneta_import_and_build` |
| Universe `broker_symbol`; default filter `broker`; validation errors; `list --broker`; `report_only` | `test_F_0_9_1_universe_broker_flag_and_default_filter`, `_universe_broker_validation_errors`, `test_F_0_8_2_…::test_F_0_9_1_cli_list_broker_filter`, `_report_only_for_non_broker_symbols` |
| Cost monotonicity with the new models (property) | `test_F_0_2_4_new_models_monotone` (Hypothesis, 100 examples) and the unchanged T06 properties |
| `cost_breakdown_shares` (D-525) | `test_F_0_2_4_cost_breakdown_shares` |
| **Mapping coverage 548/548 mapped or unmappable** | **OPEN.** `test_F_0_9_1_repo_mapping_every_broker_symbol_is_accounted_for` only proves that every broker symbol is either mapped or listed for review. It does **not** prove the criterion (P-28). |

## Mapping statistics (548 broker US shares + ETFs; 29 Dukascopy)
- **Mapped: 450** = 29 manual (D-323) + 4 override (D-524: AALG→AAL, ABBVIE→ABBV, AMAZON→AMZN, AT&T→T) + 417 ticker + name (score ≥ 0.80; the lowest, e.g. VFC "VF Corp" / "V.F. Corporation", were checked by hand and are correct).
  - Broker universe: us_equity 421, fx 15, index_cfd 10, metal 2, energy_cfd 2.
- **In `docs/reviews/T06b_mapping_review.csv`: 127.**

| Reason | Stock US | ETF |
|---|---|---|
| ticker match, no research name available | 17 | 23 |
| ticker match, name differs (e.g. `ESL` = Estée Lauder vs research ESL) | 11 | 0 |
| name match only (never auto-mapped) | 24 | 24 |
| no ticker or name match | 17 | 10 |
| unmappable: ALIBABA → BABA not in the research universe | 1 | 0 |

## T06 tests changed (why)
- `round_trip_cost` now requires `close=`, because the swap is charged on the mark-to-market notional (D-312). The T06 swap expectations did not change numerically: their prices are constant.
- The shipped-profile test checks that the five T06 placeholders are a **subset** of the profiles (Moneta profiles are added), and the expected commission dicts include the new `currency` field.
- `every_universe_symbol_is_assigned`: EURUSD/XAUUSD now resolve to `moneta_EURUSD+` / `moneta_XAUUSD+` (D-520).
- `validate_cli`: 6 placeholders (5 + the proxy). The "broken assignments" case removes the `us_equity` group, because removing `metal` no longer leaves symbols unassigned. The expected count is computed, not hard-coded.
- `show` CLI tests: EURUSD is `verified` and shows the scaled table; AAPL shows `moneta_AAPL`; AABA shows the proxy with `ASSUMED, D-314`.
- T10a universe/config tests: the test universes use Moneta profiles and `broker_symbol` for the FX entries (D-520, D-524).

## Acceptance
| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | ✅ / ✅ |
| `mypy src` (strict for `costs`, `core`) | ✅ 88 files |
| `pytest -m "not slow"` | ✅ **801 passed** |
| `pytest tests/parity tests/leakage` | ✅ 106 passed (1 new: the broker-scaling gate) |
| `pytest -m db` | ✅ 15 passed, **0 skipped** |
| `sfac costs moneta import` / `build` | ✅ (numbers above) |
| `sfac costs validate` / `sfac universe validate` | ✅ 6742 assigned, 0 missing / ✅ 6749 symbols |
| `sfac costs show EURUSD` | ✅ scale 0.780111, mean 2.61e-05 |
| acceptance-reviewer subagent | run; findings fixed. It flagged the open coverage criterion as blocking; that is recorded here as open (P-28) |

## Deviations
1. **Row status `incomplete` and the `status_reason` column** (P-30). They cover rows that parse but lack values.
2. **Hours without spread data use the broker spread** in `broker_scaled` (P-30).
3. **The swap-credit share is 0** in `cost_breakdown_shares` (P-30).
4. **Float guard in the floor** (P-30): relative 1e-9.
5. **`mvp_daily.yaml` runs with `universe_filter: all`** until P-28 (P-29).
6. **The import CLI refuses files outside `SFAC_RAW_ROOT`.** The sidecar records the path relative to it.
7. **Build rules the task did not name are config fields in `moneta.yaml`:** `etf_region`, `pip_classes`, `proxy_asset_class`, `etf_assumed.triple_weekday`.

## Open questions
- **P-28:** closing the 127 mappings. Either the user reviews the CSV into `symbol_overrides.csv`, or the user runs a script that saves Alpaca asset names (including ETFs) as a raw reference file. This decides the coverage criterion.
- **P-29:** `mvp_daily.yaml` filter.
- **P-30:** the T06b assumptions (1)–(5).

---

## Addendum (2026-09-20): D-341 rebuild and D-350

### D-341 — mapping rebuilt on the Alpaca asset names
`scripts/download_alpaca_assets.ps1` (the user runs it, D-031; it picks the trading host from
the key prefix) produced `reference/alpaca/alpaca_assets_2026-09-20.csv`: 14,354 rows, ETFs
included, sha256 `4f9bf354…0a8c`. `mapping.yaml: names_file` points at it.

| | before | after |
|---|---|---|
| mapped | 450 (29 manual, 4 override, 417 ticker+name) | **471** (29, 4, **438**) |
| review CSV rows | 127 | **106** |
| profiles | 456 | **477** |
| broker universe | 450 | **471** (us_equity 442 + 29 Dukascopy) |

SPY and QQQ are broker symbols now. A ticker match whose name is another company is still
never auto-mapped (D-341); `ESL` (Estée Lauder vs our Esterline) is the test case.

**The coverage criterion (548/548) is still open.** The 106 remaining rows are:
17 same-ticker-no-name (delisted, absent from the Alpaca *active* list, `ESL` among them),
13 same-ticker-other-wording (one suspicious: broker `AMCX` describes AMC Entertainment, which
is `AMC` here), 48 name-only candidates (the automatic candidate is often wrong), 27 with no
match, 1 unmappable (`ALIBABA` → BABA, not in the universe). They close with the user's
overrides; a `-IncludeInactive` option on the script would resolve most of the first group.

### D-350 — assumptions, two of them changed
| item | outcome |
|---|---|
| (1) `incomplete` status and `status_reason` | accepted. An incomplete row yields no profile (`profile_dict` raises) and **an override onto one is now an error**, not a silent placeholder. Test: `test_F_0_2_1_d350_incomplete_row_never_yields_a_profile`. |
| (2) UTC hours without spread data | **changed**: they take the **maximum of the scaled hourly profile** (the most conservative hour), not the broker reference, and `source_note` records how many hours were filled. Test: `test_F_0_2_2_broker_scaled_hand_computed` (hour 5 = 6e-5, the profile maximum, and the note names 22 filled hours). The bar-weighted mean over development bars still equals the broker spread, because filled hours carry no bars. |
| (3) cost shares | **changed**: shares are computed on **charges only** and a swap credit is reported as `swap_credit_usd`, never dropped. Test: `test_F_0_2_4_cost_breakdown_shares`. |
| (4) 1e-9 relative float guard on the quantity floor | accepted (research and parity sizing). |
| (5) proxy spread | accepted: the median of the broker US shares' reference spreads, computed at build time and written to `source_note` (21.2224 bps with this file), never a literal in code. |

### Price check in the review CSV (supervisor request, D-341)
Four columns were added to `docs/reviews/T06b_mapping_review.csv` for every candidate row:
`broker_quote_sample`, `research_close`, `research_close_date` and `price_ratio`
(= sample / close). The close is our **own** last daily close at or before the broker file's
date (2026-09-19), read from the raw Alpaca files through the new read-only
`data/raw_prices.py`; `mapping.yaml: prices_dir` points at them.

**Read the ratio with care.** The broker's quote samples are clearly older than our closes: on
the **438 correctly mapped** `ticker_exact` symbols the ratio has median 0.930 but p10 0.545
and p90 1.596, and only 45 % sit inside 0.8–1.25. A ratio near 1 is therefore *not* expected,
and a ratio of 0.5 is not by itself suspicious. What the column does show well is
`research_close_date` (a 2019 date means the ticker is delisted here, e.g. `ESL` at 122.49 from
2019-03-13) and the extremes (the mapped baseline runs from 0.049 to 33.65).

### `-IncludeInactive` (P-28)
`scripts/download_alpaca_assets.ps1` takes `-IncludeInactive`: it fetches `status=inactive` as
well, keeps one row per ticker (an active listing wins) and reports how many inactive rows it
kept. That gives names for the 17 delisted tickers in the review list, so the D-341 ticker+name
rule can decide them instead of leaving them open. The user runs it; the mapping is then
rebuilt and the review list shrinks again.

---

## Addendum 2 (2026-09-21): the `-IncludeInactive` asset list (D-341)

### The new raw reference file
`scripts/download_alpaca_assets.ps1 -IncludeInactive` (the user ran it, D-031) produced
`reference/alpaca/alpaca_assets_2026-09-20.v2.csv`, sha256
`9a0e8dad…1e94c` (verified against the manifest next to it): **33,276 rows = 14,354 active +
18,922 inactive**; 254 inactive duplicates of an active ticker were collapsed to the active row,
so the file has **no duplicate tickers**. `mapping.yaml: names_file` points at it.

### Counts, before (active only) and after (active + inactive)
| | before | after |
|---|---|---|
| mapped | 471 (29 manual, 4 override, 438 ticker+name) | **472** (29, 4, **439** ticker+name) |
| review CSV rows | 106 | **105** |
| profiles | 477 (1 proxy + 476) | **478** (1 proxy + 472 broker + 5 T06 placeholders) |
| broker universe | 471 | **472** (us_equity 443, fx 15, index_cfd 10, metal 2, energy_cfd 2) |
| `sfac costs validate` | 6742 assigned | **6742 assigned, 478 profiles (6 placeholder)** |
| `sfac universe validate` | 6749 symbols | **6749 symbols (6742 tradable)** |

### Review rows per reason
| reason | before | after |
|---|---|---|
| name match only (never auto-mapped, D-325) | 48 | **52** |
| no ticker or name match | 27 | **23** |
| ticker match, no research name available | 17 | **15** |
| ticker match, name differs (never auto-mapped, D-341) | 13 | **14** |
| unmappable: override target not in the research universe (`ALIBABA` → BABA) | 1 | 1 |
| **total** | **106** | **105** |

### Ticker+name matches that came from an **inactive** asset
Exactly **one**, and it is the single new mapping:

| research | broker | name score | Alpaca name (status `inactive`) |
|---|---|---|---|
| `IAC` | `IAC` | 1.0000 | IAC Inc. Common Stock |

Every other one of the 439 ticker+name matches resolves against an **active** asset. The
inactive rows did move four rows from "no ticker or name match" to "name match only" (a name is
now available, but D-325 never auto-maps a name-only match) and gave `ESL` its (empty) inactive
entry, which is why "name differs" went from 13 to 14.

### Why the list shrank by only one row
Two findings, both for the user's override work:

1. **273 of the 6,711 research symbols have no entry in the Alpaca asset file at all**, even with
   the inactive ones (`ABMD`, `ATVI`, `ANTM`, `ADS`, `AET`, `AVB`, `BK`, `EA`, `WBA`, …). All
   **15** remaining "ticker match, no research name available" rows fall in that hole, so no name
   lookup can close them — only `symbol_overrides.csv` can. They are unambiguous by description:
   `AVB` AvalonBay, `BK` Bank of New York Mellon, `BTOG` Bit Origin, `CMA` Comerica, `CTRA`
   Coterra, `DFS` Discover, `EA` Electronic Arts, `EQR` Equity Residential, `FI` Fiserv, `FL`
   Foot Locker, `GPS` Gap, `HES` Hess, `K` Kellanova, `MMC` Marsh & McLennan, `WBA` Walgreens.
2. **The price check (D-341) is the useful evidence here**, and it is filled for 91 of the 105
   rows. It confirms three of those 15 outright — `HES` 150.67 / 148.97 (ratio 1.011), `DFS`
   199.30 / 200.05 (0.996), `GPS` 24.52 / 24.55 (0.999) — and it refutes one: **`FI` is not the
   research `FI`** (broker quote 170.78 vs research close 3.15, ratio 54.2). `AMCX` stays
   suspicious (broker "AMC Entertainment Hlds - Class A" vs Alpaca "AMC Global Media Inc. Class
   A", score 0.42).

**The coverage criterion (548/548) is still open.** It closes with the user's
`configs/costs/moneta/symbol_overrides.csv`; nothing further can be automated (D-341).

### Acceptance after the rebuild
| Command | Result |
|---|---|
| `sfac costs moneta build` | ✅ mapped 472, review 105, profiles 473 (1 proxy + 472 broker) |
| `sfac universe generate` | ✅ 6749 symbols |
| `sfac costs validate` / `sfac universe validate` | ✅ 6742 assigned, 478 profiles / ✅ 6749 symbols |
| `ruff check .` / `ruff format --check .` | ✅ / ✅ 213 files |
| `mypy src` | ✅ 89 files |
| `pytest -m "not slow"` | ✅ **805 passed** |
| `pytest tests/parity tests/leakage` | ✅ 106 passed |
| `pytest -m db -rs` | ✅ 15 passed, **0 skipped** |
