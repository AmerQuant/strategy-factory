# T04i review — phase-B hourly analysis and the daily-session evidence (D-033)

**Task:** `docs/tasks/T04i_phaseb_hourly_analysis.md` · **Branch:** `b/T04i-phaseb-hourly` from `main` (T04f merged, PR #19)
**Features:** F-0.1.2 (adapter session filter and metadata), F-0.1.6 (quality evidence), F-0.1.9 groundwork (split-adjustment control)
**Decisions used:** D-010, D-021, D-022, D-023, D-025, D-033, D-355, D-358, D-382, D-383, D-386, D-388, D-394
**Supervisor answers folded in (2026-09-21):** **D-395** (D-033 accepted, `exchange`), **D-396** (P-71: quality checks + a derived clean snapshot, planned as **T04k**), **D-397** (P-72: an unadjusted split fails that symbol; `--refresh`).

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/daily_session.py` | the breach detector and its four verdicts; pure, no I/O |
| `scripts/analysis/T04i_daily_session.py` | the sweep: adapter **in memory**, no snapshot, no catalog row (D-382) |
| `docs/reviews/T04i_breach_days.csv` | one row per breach day: symbol, date, class, both breaches in bps, and the prices behind them |
| `docs/reviews/T04i_symbol_coverage.csv` | per symbol: hourly years covered, days compared, counts per class |
| `tests/unit/test_F_0_1_2_daily_session.py` | 11 tests |
| `src/strategy_factory/data/relisting.py` | re-used-ticker detection: `trading_gap` and `stale_run` |
| `scripts/analysis/T04i_relisted_tickers.py` | the sweep over all 6,711 daily symbols |
| `docs/reviews/T04i_relisted_candidates.csv` | 379 candidates over 329 symbols, worst level break first |
| `tests/unit/test_F_0_1_2_relisting.py` | 7 tests |
| `sfac data download alpaca --refresh` | re-fetch named symbol-years into a **new version file** (D-397) |
| `docs/tasks/T04k_clean_daily_snapshot.md` | the task D-396 asks for |

`SFAC_DATA_ROOT` is untouched: the catalog still holds only the three Dukascopy pilot rows.

## 2. Coverage (D-358)

Run on **826 symbols** that have both timeframes: **1,796,508** session days compared, at
**2026-09-20 15:21 UTC**. The hourly raw store is still filling while the user downloads the
missing years, so **these counts move between runs** — regenerate with
`uv run python scripts/analysis/T04i_daily_session.py` and the CSVs and this review stay in step.
At this run:

| year | symbols with an hourly file (of 832) |
|---|---|
| 2016–2019 | 832 |
| 2020 | 829 |
| 2021 | 806 |
| 2022 | 806 |
| 2023 | **237** |
| 2024–2026 | 827 |

2022 filled in while T04i was being written (it was 0 at the first run); **2023 is the year still
largely missing**. Every hourly statistic below is restricted to the days that exist, and a day
whose hourly side is only partly downloaded is its own class rather than evidence (§3).

## 3. Breach classification

For each session date present in both timeframes: `rth_high/low` from the **canonical** hourly bars
(09:00–15:00 New York, D-023), `daily_high/low` from the daily bars, the breach in basis points of
the daily close **and** as a multiple of that bar's ATR(14). Each breach is then classified against
the **raw** hourly file, which still holds the extended-hours bars the adapter drops.

| class | days | % of compared days | median bps | p90 | p95 | p99 | max | median × ATR(14) | > 100 bps | > 1000 bps |
|---|---|---|---|---|---|---|---|---|---|---|
| `extended_hours` | 11,565 | 0.644 | 3.1 | 19.6 | 38.7 | 142.0 | 3,523 | 0.02 | 188 | 3 |
| `unexplained` | 3,187 | 0.177 | 8.5 | 71.4 | 149.8 | 556.9 | 8,921 | 0.04 | 229 | 16 |
| `incomplete_hourly_day` | 2,896 | 0.161 | 44.7 | 236.8 | 329.8 | 551.3 | 1,570 | 0.29 | 868 | 2 |
| **total** | **17,648** | **0.982** | | | | | | | | |

Every cell is recomputed from `docs/reviews/T04i_breach_days.csv` (quantiles: linear interpolation).

**Sides:** high only 9361 low only 8257 both sides 30 — almost every breach is one-sided, which is
what a single bad print or a single out-of-hours trade looks like.

`incomplete_hourly_day` — the session has fewer hourly bars than its calendar close implies — was
added **after** a first pass put those days in `unexplained`. On 2021-04-19 alone, **438** symbols
"breached" with a median of **one** hourly bar: that is the download in progress, not the data.
Without checking the bar count against the calendar those days read as bad prints. Its median
breach (44.7 bps, 0.29 × ATR) is far larger than either real class, which is the signature of a
partial session rather than a price event.

**By symbol class** (from the hourly universe's `reason`; `unknown` = not in it):

| symbol_class | extended_hours | incomplete_hourly_day | unexplained |
|---|---|---|---|
| unknown | 135 | 122 | 52 |
| etf | 4,088 | 216 | 440 |
| sp500_pit | 7,342 | 2,558 | 2,695 |

ETFs are 4,744 of the 17,648 breach days from 82 symbols, so they breach far more per symbol than
the index members — consistent with `SPY`, `QQQ` and `IWM` topping the `unexplained` list.

**By year:**

| y | extended_hours | incomplete_hourly_day | unexplained |
|---|---|---|---|
| 2016 | 1,331 | 35 | 619 |
| 2017 | 1,539 | 17 | 746 |
| 2018 | 1,504 | 435 | 348 |
| 2019 | 1,349 | 60 | 311 |
| 2020 | 1,255 | 35 | 316 |
| 2021 | 1,425 | 886 | 293 |
| 2022 | 548 | 658 | 267 |
| 2023 | 381 | 34 | 39 |
| 2024 | 681 | 115 | 67 |
| 2025 | 966 | 336 | 127 |
| 2026 | 586 | 285 | 54 |

`unexplained` peaks in 2016–2017 (619, 746) and the median size is flat, so this is not a recent
regression; `incomplete_hourly_day` tracks the download, not the calendar.

### Does `unexplained` cluster?

3,187 days over **741 of 826** symbols and **1,143** distinct dates — median 3 per affected symbol,
so it is not concentrated in a few bad symbols. By symbol the top are the big ETFs, `SPY` (83),
`QQQ` (31), `IWM` (29), then `TXT` (22), `CA` (17), `XLY` (15). **By date it does cluster**, and
that is the useful signal: 2019-10-31 (75 symbols), 2019-08-12 (64), 2025-03-06 (55, all one-sided
low). A date-wide cluster points at the feed; a symbol-wide one at that symbol.

### The 20 largest breaches

| symbol | date | class | bps | × ATR | daily high | daily low | close | raw high | raw low |
|---|---|---|---|---|---|---|---|---|---|
| `SPY` | 2026-02-02 | `unexplained` | 8,921 | 12.1 | 696.93 | 69.005 | 695.41 | 697.48 | 681.94 |
| `MRK` | 2021-06-11 | `unexplained` | 7,904 | 10.6 | 76.86 | 15.32 | 76.27 | 76.96 | 75.6 |
| `VZ` | 2026-01-08 | `unexplained` | 7,263 | 11.4 | 40.73 | 10.5999 | 40.57 | 40.73 | 40.0645 |
| `NVDA` | 2024-06-10 | `unexplained` | 5,982 | 6.9 | 195.95 | 117.01 | 121.79 | 123.1 | 117.01 |
| `CHK` | 2020-03-13 | `extended_hours` | 3,523 | 1.5 | 60.0 | 30.0 | 60.0 | 60.0 | 30.0 |
| `EXE` | 2020-03-13 | `extended_hours` | 3,523 | 1.5 | 60.0 | 30.0 | 60.0 | 60.0 | 30.0 |
| `TSLA` | 2021-03-04 | `unexplained` | 3,306 | 2.8 | 291.31 | 200.0 | 207.15 | 222.82 | 200.0 |
| `FTR` | 2020-03-18 | `extended_hours` | 2,778 | 0.6 | 0.27 | 0.18 | 0.18 | 0.27 | 0.18 |
| `TSLA` | 2021-03-01 | `unexplained` | 2,130 | 2.8 | 290.67 | 228.35 | 239.48 | 241.81 | 228.35 |
| `WBA` | 2016-12-22 | `unexplained` | 2,014 | 6.6 | 102.82 | 83.9 | 84.27 | 85.85 | 83.9 |
| `ANSS` | 2022-03-04 | `unexplained` | 1,635 | 3.0 | 316.15 | 258.0 | 311.37 | 316.15 | 308.895 |
| `FTR` | 2018-05-02 | `incomplete_hourly_day` | 1,570 | 3.2 | 10.38 | 8.75 | 10.38 | 10.38 | 8.75 |
| `FB` | 2016-06-02 | `unexplained` | 1,359 | 6.0 | 135.6 | 118.22 | 118.93 | 119.44 | 118.22 |
| `META` | 2016-06-02 | `unexplained` | 1,359 | 6.0 | 135.6 | 118.22 | 118.93 | 119.44 | 118.22 |
| `LNT` | 2018-01-03 | `unexplained` | 1,288 | 5.5 | 47.7347 | 41.49 | 41.74 | 42.36 | 41.49 |
| `GE` | 2019-08-16 | `unexplained` | 1,115 | 1.8 | 78.24 | 66.96 | 70.32 | 70.4 | 64.8 |
| `DINO` | 2022-03-08 | `incomplete_hourly_day` | 1,093 | 1.8 | 34.14 | 30.41 | 34.14 | 34.31 | 30.41 |
| `UAA` | 2016-08-22 | `unexplained` | 1,032 | 3.0 | 42.9435 | 38.37 | 38.8 | 38.94 | 38.36 |
| `DUK` | 2016-09-14 | `unexplained` | 1,017 | 4.5 | 87.75 | 78.38 | 78.67 | 79.91 | 78.01 |
| `XLF` | 2017-03-17 | `unexplained` | 1,006 | 5.2 | 24.76 | 22.0 | 24.45 | 24.8 | 24.33 |

`SPY` at a daily low of 69.005 against a 695.41 close is a misplaced decimal point, **12 × the
day's ATR**. `MRK` 15.32 against 76.27, `VZ` 10.60 against 40.57, and `NVDA` 2024-06-10 a high of
195.95 while the whole week trades 117–132 and the hourly maximum is 123.10. A stop anywhere in
those ranges fires on a price that never traded. The two `CHK`/`EXE` rows are the same instrument
before and after its rename — the T04f exclusion rule keeps only `CHK`.

## 4. A separate defect the breach check cannot see: AVGO is not split-adjusted

The known-split check over the 11 splits in `configs/data/known_splits.csv` gives **10 `adjusted`
and 1 `unadjusted`** — and the failure is the one T04e named explicitly:

```
AVGO 1D 2024-07-15  ratio 0.100796  ratio_crosscheck 1.007967  split_ratio 10.0  unadjusted
```

```
2024-07-12   o 1711.03   h 1725.91   l 1691.31   c 1700.67
2024-07-15   o  170.00   h  173.51   l  169.26   c  171.42
```

The 10:1 split is **not applied** in the Alpaca series although the download used
`adjustment=split`. The raw hourly file has the same discontinuity, and the all-adjusted MS-US-1D
cross-check is continuous (1.0080), which is what makes the diagnosis certain.

**The breach analysis does not flag this day at all**, because both feeds are equally unadjusted and
therefore agree. The two checks are complementary, and AVGO would silently poison every backtest
that crosses 2024-07-15. It needs a re-download (network, so the user's run) before T04g ingests it
— see **P-72**.

## 5. The broker's trading hours (supervisor question 2)

Read read-only from `configs/costs/moneta/moneta_spec.csv` (`trading_time_server`); nothing under
`configs/costs/` was modified (D-388). Server time is New York close aligned (D-522), so
16:30–23:00 server = **09:30–16:00 New York**:

| broker hours (server) | New York | symbols |
|---|---|---|
| 16:30–23:00 | 09:30–16:00 — **RTH only** | **528** |
| 14:05–23:00 | 07:05–16:00 — pre-market, no post-market | 20 |

The 20 are mega-caps: `AAPL AMZN BA BIDU DIS GOOG IBM INTC JPM MCD META MSFT NFLX NVDA ORCL SHOP
TSLA TSM XOM` plus `ALIBABA` (unmapped).

So for **528 of 548** broker-tradable US shares and ETFs, a genuine extended-hours extreme is a
price the strategy could not have traded either. That does not make the bar wrong — the daily bar
honestly reports the exchange session — but it means `extended_hours` and `unexplained` have the
same consequence for a stop: both are levels the strategy cannot reach. They differ in what the
right fix is, which is why P-71 keeps them apart.

## 6. The other phase-B items

- **Bars per session:** the hours kept are exactly `[9, 10, 11, 12, 13, 14, 15]`. Over ten
  large-cap symbols 22,213 of 22,416 session days have the full 7 bars and 186 have 4 on a 13:00
  half-day, so the calendar and the adapter agree. The 17 remaining days are short, and — correcting
  what I wrote in the first draft — **2018-05-02/03 is not feed-wide**: the raw hourly files for
  that date hold 2 and 4 bars for `AAPL`, `MSFT` and `QQQ` but 11–16 for `SPY`, `JPM`, `XOM`, `KO`,
  `JNJ`, `PG` and `WMT`. It is a per-symbol gap in the SIP hourly feed, which is why the
  `incomplete_hourly_day` class is per symbol and per date rather than a date blacklist.
- **META before 2022-06-09:** **1,620** daily bars before the rename; the canonical hourly series
  starts `2016-01-04 14:00 UTC` at a close of **101.11** (the 102.22 in the first draft was the
  first *daily* close). Alpaca does serve Meta's pre-rename history under `META`, which is what
  T04f relied on.
- **Split check:** 10 of 11 known splits `adjusted`; AVGO is §4 and §6b.
- **Re-used tickers:** §6a.

## 6a. Re-used tickers — the candidate list for T04g (D-383)

Swept all **6,711** daily symbols → `docs/reviews/T04i_relisted_candidates.csv`, **379 rows over
329 symbols**. D-383's wording ("a ticker re-used by another company") turned out to need **three**
shapes, not the one the plan assumed; the extension is raised as **P-73**.

| reason | rows | symbols | D-383 candidate? |
|---|---|---|---|
| `stale_run` — frozen stretch **with** a level break | 146 | 143 | **yes** |
| `trading_gap` — gap ≥ 200 days **with** a level break | 83 | 83 | **yes** |
| `padding_only` — frozen, no level break | 118 | 96 | no — a dead listing; already a `stale_prices` quality finding |
| `pre_listing_padding` — frozen from the very first bar | 32 | 32 | no — the feed padding backwards before an IPO |

**347 candidate rows over 297 symbols** (4.4 % of the universe).

**The gap test alone would have found only 83 of them, and would have missed both symbols T04f
flagged.** `PX` and `FI` have no gap at all: the feed pads the dead stretch with the last close.
`PX` is Praxair 2016–2018 at 96–169, then **749 consecutive bars at exactly 164.50**, then RPC Inc.
from late 2021 at 12–15, identical to `RPC` day for day. That is the more dangerous shape — a gap
is visibly missing data, a frozen price is silently tradeable and every indicator over it is
meaningless.

Worst cases, all the same story:

| symbol | reason | frozen bars | close before | close after |
|---|---|---|---|---|
| `LINE` | `stale_run` | **2,056** | 0.155 | 80.78 |
| `BIOA` | `stale_run` | 1,668 | 0.172 | 18.31 |
| `SN` | `stale_run` | 1,119 | 0.375 | 42.31 |
| `RELY` | `stale_run` | 780 | 0.509 | 48.45 |
| `PX` | `stale_run` | 749 | 165.49 | 12.08 |
| `AKTS` | `trading_gap` | — | 0.037 | 22.40 |
| `FB` | `trading_gap` | — | 196.64 | 39.91 |

### D-388: seven candidates are Moneta mapping targets and are **kept**

The candidate CSV carries a `moneta_target` column so the rule cannot be applied blind. Seven
symbols on the list are targets in `configs/costs/moneta/symbol_map.csv`, and **every one is a live,
broker-tradable company** — several are genuine ticker re-uses, which is exactly the case D-388
anticipates:

| symbol | reason | evidence | why it is kept |
|---|---|---|---|
| `MBLY` | `stale_run` | 1,297 frozen bars, 62.94 → 28.97 | old Mobileye N.V. was acquired in 2017; Mobileye Global re-listed under the same ticker in Oct 2022 |
| `SNOW` | `stale_run` + `trading_gap` | 610 frozen bars, 23.71 → 253.93 | the ticker's previous owner delisted; Snowflake IPO'd Sept 2020 |
| `SE` | `stale_run` | 166 frozen bars, 41.00 → 16.26 | Spectra Energy merged in 2017; Sea Limited listed Oct 2017 |
| `CTRA` | `stale_run` | 168 frozen bars, 12.93 → 22.77 | Contura became AMR (the feed's own `CTRA → AMR` row); Coterra took `CTRA` in Oct 2021 |
| `MARA` | `trading_gap` | 304-day gap, 27.52 → 6.40 | same company, a long halt |
| `GRAB` | `pre_listing_padding` | 570 padded bars | not a candidate at all — padding before the 2021 listing |
| `DOW` | `padding_only` | 397 frozen bars, no level break | not a candidate — padding before the 2019 spin-off |

**None of them is dropped, nothing under `configs/costs/` was touched, and all seven are listed for
stream A in `docs/streams/B.md`** (D-388). Their padded or pre-re-use history is still unusable,
which is a **T04k**-shaped problem (the series should start at the first real bar), not a reason to
remove a tradable symbol from the universe.

Per D-383 this stays a **candidate list, not an exclusion list**: the supervisor confirms rows into
`configs/universe/us_equity_daily_excluded.csv`, which T04g reads. Nothing in `configs/universe/`
was changed by this task.

## 6b. Every known split that is unadjusted (D-397)

Re-ran the known-split check over both timeframes, all 11 splits in
`configs/data/known_splits.csv` (9 symbols: AAPL, AMZN, AVGO, CMG, GOOGL, NVDA, SMCI, TSLA, WMT):

| timeframe | adjusted | unadjusted | no data on the split date |
|---|---|---|---|
| 1D | 10 | **1** (`AVGO` 2024-07-15) | 0 |
| 1H | 8 | **1** (`AVGO` 2024-07-15) | 2 (`GOOGL` 2022-07-18, `TSLA` 2022-08-25 — 2022 hourly was missing at the time of the run; it has since filled to 806 symbols, so re-run this check in T04h) |

**AVGO is the only genuinely unadjusted split, and it is unadjusted in both timeframes.** The two
`no_data_on_split_date` rows are the download gap, not a defect; they resolve with T04h.

The unadjusted stretch is **2016 through 2024-07-12** — yearly close ranges run 116 → 1,829 and
then drop to 136–481 from 2024-07-15 on — so the refresh must cover every year up to and including
2024, in both timeframes:

```
uv run sfac data download alpaca --timeframe 1D --symbols AVGO --start 2016-01-01 --end 2024-12-31 --refresh
uv run sfac data download alpaca --timeframe 1H --symbols AVGO --start 2016-01-01 --end 2024-12-31 --refresh
```

`--refresh` (D-397) re-fetches those symbol-years although their chunks are complete and writes a
**new version file** beside each old one (`2024.v2.parquet`, manifest `refresh: true`); nothing is
overwritten (D-028) and the adapter picks the newest version. It **requires** an explicit
`--symbols` list, so a refresh cannot silently redownload the whole universe. If the second
download shows the same break it is an Alpaca defect and AVGO goes on the exclusion list with this
evidence.

## 7. D-033 — accepted as D-395

The rule was fixed in the task before the numbers were seen: `RTH` only if the daily range is inside
the RTH hourly range on **every** compared day. It is not — 15,559 days breach, 0.96 % — so the
evidence says the label stays **`exchange`**.

**The conclusion does not depend on the missing years** (D-358): more hourly data can only add
breach days, never remove the ones already observed. For `RTH` to become correct, every one of the
15,559 would have to be wrong, which is refuted by the worked examples in §3.

Recorded as **D-395**: `daily_session` stays **`exchange`**, and `configs/data/alpaca.yaml` already
carries that value, so no config change was needed. The stale "decided in T04e phase B" comment is
replaced by a reference to D-395.

The label alone does not address what the breaches do to stops — that is **D-396**, implemented in
**T04k** (§8).

## 8. What D-396 turns into: T04k

`docs/tasks/T04k_clean_daily_snapshot.md`, placed in the runbook **after T04g and before T12**:
the two quality checks (`daily_extreme_unsupported` where hourly data exists,
`daily_wick_outlier` for every symbol, both thresholds in config), and the derived **clean** daily
snapshot — `derived_from` set, every changed bar logged with its old and new value, never an
overwrite — which becomes the research reference. T04g ingests the raw as-is.

## 8a. Left for later

- the supervisor's confirmation of the 379 relisting candidates into
  `configs/universe/us_equity_daily_excluded.csv` (T04g reads it);
- the AVGO refresh (the command is in §6b; a network run, so the user's);
- re-running the breach sweep once the hourly download completes, which will move the 2,178
  `incomplete_hourly_day` rows into a real class.

## 9. Acceptance-reviewer findings

The `acceptance-reviewer` subagent ran against `main` and confirmed D-382 (no snapshot, no catalog
row — checked on disk and in the code), D-388/D-394 (nothing under `configs/costs/`,
`configs/universe.yaml` untouched), the AVGO diagnosis, the broker-hours numbers and every
clustering figure. It found nine defects; all are fixed above:

1. **The D-388 check was missing from the relisting output** — the worst finding. Seven mapped
   symbols were on the candidate list and none was reported. The candidate CSV now carries a
   `moneta_target` column, the sweep prints the kept symbols, and §6a and `docs/streams/B.md` list
   all seven with their evidence.
2. **`stale_run` applied no level break**, so 46 % of its rows were not what D-383 describes. It is
   now gated on the same `jump_threshold` as the gap arm, and the rows that fail the gate are kept
   under their own labels (`padding_only`, and the new `pre_listing_padding` for a frozen stretch at
   the very start of a series, which is what `GRAB` and `DOW` are). Without that last case the rule
   would have dropped Moneta targets.
3. **The extension itself was an unrecorded assumption** — now **P-73**, with the thresholds.
4. **The p90 column was not reproducible** from the committed CSV. Every quantile is now computed
   with explicit linear interpolation and regenerated from the CSV, and p95 (which the task asks
   for) is included.
5. **Statistics the task requires were missing:** high-side / low-side / both-sides counts, the
   breach as a multiple of **ATR(14)**, the **20 largest** with symbol and date, a by-year table and
   a by-symbol-class table. `breach_atr_frac`, `high_side`, `low_side` and `symbol_class` are now
   columns of the breach CSV and all five tables are in §3.
6. **2021-04-19 was quoted as 244 symbols**; it is **438** (244 was the pre-fix run).
7. **The bars-per-session paragraph was wrong**: 2018-05-02/03 is **not** feed-wide. Corrected in §6
   with the per-symbol raw bar counts.
8. **META's first hourly close was quoted as 102.22**, which is the first *daily* close; it is
   **101.11**.
9. **mypy's file count** (99 → 100).

Two points it raised that I did **not** change, with the reason: `no_raw_hours` is unreachable in
the sweep (the RTH frame is derived from the same raw files) but it is the correct guard for
callers that pass the two frames separately, and it is tested; and the per-symbol `except Exception`
in the sweep is deliberate — one unreadable symbol must not lose the other 825 — but it records the
error in the coverage CSV, which showed 0 errors in this run.

## 10. Acceptance commands

```
uv run pytest -m "not slow"                  1198 passed
uv run pytest tests/parity tests/leakage     280 passed
uv run pytest -m db                          21 passed, 0 skipped
uv run ruff check . / format --check .       clean
uv run mypy src                              no issues in 100 source files
uv run sfac streams check                    ownership, ids, alembic head: ok
```

Tests added by T04i: **22** (12 breach detection, 8 re-used tickers, 2 for `--refresh`).
No new dependency. Nothing written to `SFAC_DATA_ROOT`; nothing under `configs/costs/` or
`configs/universe.yaml` changed.

## 11. Open questions


- **P-73** — the two extra re-used-ticker fingerprints and their thresholds (§6a). Implemented as
  described; the 347-row candidate list is evidence, not an exclusion list.
- P-71 and P-72 are answered (D-395 … D-397) and are reflected above.
