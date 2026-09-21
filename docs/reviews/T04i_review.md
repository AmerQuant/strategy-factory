# T04i review — phase-B hourly analysis and the daily-session evidence (D-033)

**Task:** `docs/tasks/T04i_phaseb_hourly_analysis.md` · **Branch:** `b/T04i-phaseb-hourly` from `main` (T04f merged, PR #19)
**Features:** F-0.1.2 (adapter session filter and metadata), F-0.1.6 (quality evidence), F-0.1.9 groundwork (split-adjustment control)
**Decisions used:** D-008, D-010, D-021, D-022, D-023, D-025, D-033, D-355, D-358, D-382, D-383, D-386, D-388, D-394
**Supervisor answers folded in (2026-09-21):** **D-395** (D-033 accepted, `exchange`), **D-396** (P-71: quality checks + a derived clean snapshot, planned as **T04k**), **D-397** (P-72: an unadjusted split fails that symbol; `--refresh`), **D-398** (P-73: a frozen stretch is removed whatever caused it, and a re-used ticker with an identifiable boundary is **trimmed to that boundary instead of excluded** — §6a).

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/daily_session.py` | the breach detector and its four verdicts; pure, no I/O |
| `scripts/analysis/T04i_daily_session.py` | the sweep: adapter **in memory**, no snapshot, no catalog row (D-382) |
| `docs/reviews/T04i_breach_days.csv` | one row per breach day: symbol, date, class, both breaches in bps, and the prices behind them |
| `docs/reviews/T04i_symbol_coverage.csv` | per symbol: hourly years covered, days compared, counts per class |
| `tests/unit/test_F_0_1_2_daily_session.py` | 12 tests |
| `src/strategy_factory/data/relisting.py` | frozen stretches, re-used tickers and the **D-398 boundary**; pure, no I/O |
| `configs/data/alpaca.yaml` → `relisting:` | `frozen_min_sessions: 10`, `gap_days: 200`, validated by `RelistingConfig` (rule 1) |
| `scripts/analysis/T04i_relisted_tickers.py` | the sweep over all 6,711 daily symbols, `--write-exclusions` |
| `docs/reviews/T04i_relisting_verdicts.csv` | **one row per symbol**: verdict, boundary, dropped span, what is left, `reverse_split_suspect` (797 rows) |
| `docs/reviews/T04i_relisted_candidates.csv` | one row per frozen stretch or gap with its boundary (3,191 rows), worst level break first |
| `configs/universe/us_equity_daily_excluded.csv` | the D-398 (4) exclusions — **empty**, header only |
| `tests/unit/test_F_0_1_2_relisting.py` | 23 tests |
| `sfac data download alpaca --refresh` | re-fetch named symbol-years into a **new version file** (D-397) |
| `docs/tasks/T04k_clean_daily_snapshot.md` | the task D-396 asks for |

`SFAC_DATA_ROOT` is untouched: the catalog still holds only the three Dukascopy pilot rows.

## 2. Coverage (D-358)

> **Amended 2026-09-21 — the hourly download is complete and this section was re-run.**
> The numbers below and in §3 are the **2026-09-21 07:44 UTC** sweep over the completed raw set.
> The original 2026-09-20 15:21 UTC run is kept in the paragraphs that describe what changed.
> Regenerate with `uv run python scripts/analysis/T04i_daily_session.py`.
>
> **Coverage verdict: complete.** Every one of the **806** hourly universe symbols has a file for
> every year 2016 … 2026 — **0 missing symbol-years of 8,866** — and the user's final pass without
> `--end` covers 2026 (695 of 806 symbols carry bars to 2026-09-18; the other 111 stop earlier and
> **109 of them stop in the daily series on the same day or have no 2026 bars in either timeframe**,
> i.e. they are delistings, not gaps). One symbol, **`CCE`**, has **0 bars in all eleven years** and
> will ingest as `no_data` in T04h, like `BHGE`/`FBHS`/`JEC` in 1D. `VMRK` has hourly bars but still
> no daily ones (the D-388 `EQR` case). **T04h's coverage gate (D-386) is satisfied.**

Run on **826 symbols** that have both timeframes: **1,956,214** session days compared, at
**2026-09-21 07:44 UTC** (the first run, on the incomplete set, compared 1,796,508 days). The hourly raw store is still filling while the user downloads the
missing years, so **these counts move between runs** — regenerate with
`uv run python scripts/analysis/T04i_daily_session.py` and the CSVs and this review stay in step.
At this run:

| year | universe symbols with an hourly file (of 806) |
|---|---|
| **2016 – 2026** | **806 — every year, every symbol** |

At the first run the same table read 832/832 for 2016–2019, 829 for 2020, 806 for 2021–2022,
**237** for 2023 and 827 for 2024–2026. The gap is closed.

A year file with **0 rows** is not a gap: 57–98 symbols per year have one, and they are the years
before a company listed or after it delisted — the same shape the daily series shows. Every hourly
statistic below still restricts itself to the days that exist, and a day whose hourly side is short
is its own class (§3) — which now means something different from what it meant on 2026-09-20.

**What the completed download did to the numbers.** Breach days went from **17,648 (0.982 %)** to
**18,580 (0.950 %)** — more breaches in absolute terms over more compared days, exactly as
predicted: more hourly data can only **add** breach days, never remove one. D-395 (§7) is
reinforced, not threatened.

**One prediction in this review was wrong, and it matters.** The 2026-09-20 draft said the
completed run would "move most of the `incomplete_hourly_day` rows into a real class", on the
reading that they were the download in progress. They did not move: **2,896 → 3,017**, and their
median is still **1 hourly bar against 7 expected**. With every symbol-year present, that reading
is refuted — these are **genuine gaps in Alpaca's SIP hourly feed**, concentrated on particular
dates (2021-04-19: 438 symbols, 2021-10-25: 401, 2022-03-08: 347, 2022-01-24: 279, 2018-05-02:
194) across **665 symbols and 784 dates**. They are a property of the feed, and T04k must keep
treating such a day as "not evidence" rather than as a defect of the daily bar.

## 3. Breach classification

For each session date present in both timeframes: `rth_high/low` from the **canonical** hourly bars
(09:00–15:00 New York, D-023), `daily_high/low` from the daily bars, the breach in basis points of
the daily close **and** as a multiple of that bar's ATR(14). Each breach is then classified against
the **raw** hourly file, which still holds the extended-hours bars the adapter drops.

| class | days | % of compared days | median bps | p90 | p95 | p99 | max | median × ATR(14) | > 100 bps | > 1000 bps |
|---|---|---|---|---|---|---|---|---|---|---|
| `extended_hours` | 12,286 | 0.628 | 3.1 | 19.7 | 39.1 | 142.0 | 3,523 | 0.02 | 198 | 3 |
| `unexplained` | 3,277 | 0.168 | 8.3 | 73.9 | 158.0 | 565.3 | 8,921 | 0.04 | 247 | 16 |
| `incomplete_hourly_day` | 3,017 | 0.154 | 43.5 | 236.7 | 329.7 | 551.0 | 1,570 | 0.28 | 895 | 2 |
| **total** | **18,580** | **0.950** | | | | | | | | |

Every cell is recomputed from `docs/reviews/T04i_breach_days.csv` (quantiles: linear interpolation).

**Sides:** high only 9,875, low only 8,675, both sides 30 — almost every breach is one-sided, which
is what a single bad print or a single out-of-hours trade looks like.

`incomplete_hourly_day` — the session has fewer hourly bars than its calendar close implies — was
added **after** a first pass put those days in `unexplained`. On 2021-04-19 alone, **438** symbols
"breached" with a median of **one** hourly bar. The first draft read that as the download in
progress; **the completed download proves otherwise** (§2): the class barely moved, so these are
gaps in the SIP hourly feed itself. Its median breach (43.5 bps, 0.28 × ATR) is far larger than
either real class, which is the signature of a short session rather than a price event — and the
reason the class exists at all is that, without counting bars against the calendar, those days read
as bad prints.

**By symbol class** (from the hourly universe's `reason`; `unknown` = not in it):

| symbol_class | extended_hours | incomplete_hourly_day | unexplained |
|---|---|---|---|
| unknown | 135 | 122 | 52 |
| etf | 4,494 | 289 | 496 |
| sp500_pit | 7,657 | 2,606 | 2,729 |

ETFs are 5,279 of the 18,580 breach days from 82 symbols, so they breach far more per symbol than
the index members — consistent with `SPY`, `QQQ` and `IWM` topping the `unexplained` list.

**By year:**

| y | extended_hours | incomplete_hourly_day | unexplained |
|---|---|---|---|
| 2016 | 1,331 | 35 | 619 |
| 2017 | 1,539 | 17 | 746 |
| 2018 | 1,504 | 435 | 348 |
| 2019 | 1,349 | 60 | 311 |
| 2020 | 1,255 | 35 | 316 |
| 2021 | 1,425 | 886 | 311 |
| 2022 | 989 | 765 | 331 |
| 2023 | 655 | 48 | 65 |
| 2024 | 682 | 115 | 67 |
| 2025 | 967 | 336 | 127 |
| 2026 | 590 | 285 | 54 |

`unexplained` peaks in 2016–2017 (619, 746) and the median size is flat, so this is not a recent
regression. 2022 and 2023 are the rows the completed download changed (2022: 548 → 989
`extended_hours`, 2023: 381 → 655), because those were the thin years; `incomplete_hourly_day`
stayed put, which is what proves it is the feed and not the download.

### Does `unexplained` cluster?

3,277 days over **742 of 826** symbols and **1,168** distinct dates — median 4 per affected symbol,
so it is not concentrated in a few bad symbols. By symbol the top are the big ETFs, `SPY` (87),
`QQQ` (33), `IWM` (30), then `TXT` (22), `CA` (17), `XLY` (15). **By date it does cluster**, and
that is the useful signal: 2019-10-31 (75 symbols), 2019-08-12 (64), 2025-03-06 (55, all one-sided
low), 2017-12-26 (25). A date-wide cluster points at the feed; a symbol-wide one at that symbol.

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

## 6a. Frozen stretches and re-used tickers — D-383 as amended by D-398

**The supervisor answered P-73 on 2026-09-21 as D-398, and it changes the outcome, not only the
wording.** D-383 said "a ticker re-used by another company is excluded for now". D-398 replaces
that with four rules:

1. **Any frozen stretch is removed from the series, whatever caused it** — consecutive bars with
   an identical close **and zero true range**, the threshold in config, starting at **10 sessions**.
   It is feed padding, not data.
2. Where a ticker was re-used and **the boundary is identifiable**, the series is **kept from that
   boundary onward** instead of the symbol being excluded; the boundary and the dropped span are
   recorded.
3. **Leading** pre-listing padding is trimmed and the symbol **stays**.
4. Only where the boundary is **not** identifiable is the symbol excluded, and then it is listed.

A symbol whose remaining history is then too short for a split (**D-008**) simply fails the split
— `HistoryTooShortError`, already implemented in `data/split.py` — and drops out of the candidate
universe. It is never hand-excluded for being short.

### What changed in the code

- `frozen_stretches()` now requires **zero true range** (`high == low == close`), not only an
  identical close, so a genuinely quiet market is no longer mistaken for padding. There is a test
  for exactly that: the same closes with a real high and low produce **no** stretch.
- The threshold moved out of the script into **config** (`CLAUDE.md` rule 1):
  `configs/data/alpaca.yaml` → `relisting.frozen_min_sessions: 10`, `relisting.gap_days: 200`,
  validated by `RelistingConfig`. The CLI options still override them for an experiment.
- `analyse_series()` returns a **`SeriesVerdict` per symbol**: verdict, `boundary_date`,
  `boundary_reason`, the dropped span, the frozen bars cut out of the kept series, and what is
  left. The boundary is the first **kept** bar after the **last** structural break — the end of a
  leading pad, a padded stretch across which the level breaks, or a trading gap with the same
  level break — and it skips any further padding that starts right at it.

### The sweep, re-run over all 6,711 daily symbols

Run at **2026-09-20 19:30 UTC**, thresholds `frozen ≥ 10 sessions`, `gap ≥ 200 days`,
`jump_threshold = 0.40`. Reproduce with
`uv run python scripts/analysis/T04i_relisted_tickers.py --write-exclusions`. Two artefacts now:

| file | content |
|---|---|
| `docs/reviews/T04i_relisting_verdicts.csv` | **one row per symbol**: verdict, **`boundary_date`**, `boundary_reason`, `dropped_from/to`, `dropped_bars`, `frozen_bars_cut`, `kept_bars/from/to`, `moneta_target`, `reverse_split_suspect` |
| `docs/reviews/T04i_relisted_candidates.csv` | one row per stretch or gap, each carrying its symbol's boundary and verdict |

**797 symbols** are affected (11.9 % of the universe), over **3,191** evidence rows:

| verdict | symbols | what happens |
|---|---|---|
| `trim_to_boundary` | **280** | D-398 (2)/(3): the series starts at the boundary; median **1,131** bars dropped, max 2,680 |
| `frozen_removed` | **517** | D-398 (1) only: interior padding cut, the history stays; median **39** bars, 165 symbols lose ≤ 20 |
| `exclude_boundary_unidentifiable` | **0** | D-398 (4) |

| evidence row | rows | symbols | sets a boundary? |
|---|---|---|---|
| `padding_only` — frozen, no level break | 2,885 | 576 | no — cut in place |
| `stale_run` — frozen **with** a level break | 173 | 167 | yes (162 symbols) |
| `trading_gap` — gap ≥ 200 days **with** a level break | 83 | 83 | yes (69 symbols) |
| `pre_listing_padding` — frozen from the very first bar | 50 | 50 | yes (49 symbols) |

**`configs/universe/us_equity_daily_excluded.csv` is written and is empty** (header only): under
D-398 every affected symbol keeps a shorter, honest history. That is the file T04g reads, so the
1D ingest now runs over the **full 6,711-symbol universe**.

Dropping the threshold from 60 to 10 sessions is what widens the list from 379 rows / 329 symbols
to 3,191 / 797. The zero-true-range requirement pulls the other way, and **not** by nothing — an
earlier draft of this review claimed it changed no row, and that was wrong. Measured over all
**6,705** comparable daily symbols, `frozen_stretches()` against the old close-only rule at the same
10-session threshold:

| | zero true range (D-398) | close only (the old rule) |
|---|---|---|
| padded bars found | **202,729** | 212,530 |
| symbols with an identical stretch set | 5,940 | — |
| symbols where the two disagree | **765** | — |
| symbols where close-only finds a stretch and D-398 finds none | **115** | — |

The 9,801-bar difference (4.6 %) is mostly the **run's first bar**: a real bar whose close the pad
then repeats is counted by a close-only rule and not by this one, so a "10-bar" close run is 9
padded sessions and falls below the threshold (`AKO.A`, `ALN`, `AMJL` each lose exactly one
10-bar run that way). That is the intended reading of D-398 — nine padded sessions are nine padded
sessions — and it is what stops a genuinely quiet market from being cut.

**145 of the 280 trimmed symbols keep fewer than 650 bars** and **61 fewer than 250** — below the
embargo alone (`max_lookback_bars 200 + max_holding_bars 50`). Per D-398 they are **not** excluded
here: they fail `SplitManager` with `HistoryTooShortError` when a stage tries to split them.

Worked examples:

| symbol | verdict | boundary | dropped | kept | what it is |
|---|---|---|---|---|---|
| `PX` | `trim_to_boundary` | 2021-10-21 | 1,461 bars (2016-01-04 … 2021-10-20) | 1,080 | Praxair + 749 frozen bars at 164.50, then RPC Inc. |
| `FB` | `trim_to_boundary` | 2025-06-26 | 1,620 bars | 310 | Meta's history stays with `META`; `FB` keeps only the instrument that trades under it today |
| `LINE` | `trim_to_boundary` | 2024-07-25 | 2,153 bars | 540 | 2,055 frozen bars at 0.18, then 80.78 |
| `DOW` | `frozen_removed` | — | — | 2,297 | 396 padded bars before the spin-off, cut in place |

### D-388: the eleven Moneta targets, all kept

The `moneta_target` column is on both artefacts. **Eleven** affected symbols are targets in
`configs/costs/moneta/symbol_map.csv`; under D-398 **none is excluded** — five are trimmed to an
honest boundary exactly as the supervisor's answer says, one loses leading padding, and five lose
only interior padding:

| symbol | verdict | boundary | dropped | kept | why |
|---|---|---|---|---|---|
| `MBLY` | `trim_to_boundary` | 2022-10-26 | 1,716 | 977 | old Mobileye N.V. acquired 2017; Mobileye Global re-listed Oct 2022 |
| `SNOW` | `trim_to_boundary` | 2020-09-16 | 1,006 | 1,509 | Snowflake IPO Sept 2020 |
| `SE` | `trim_to_boundary` | 2017-10-20 | 454 | 2,239 | Spectra Energy merged 2017; Sea Limited listed Oct 2017 |
| `CTRA` | `trim_to_boundary` | 2021-10-04 | 728 | 1,152 | Contura → AMR; Coterra took `CTRA` Oct 2021 |
| `MARA` | `trim_to_boundary` | 2017-10-30 | 252 | 2,233 | same company, a long halt — the pre-halt history goes with it |
| `GRAB` | `trim_to_boundary` | 2020-12-01 | 570 | 1,456 | leading pre-listing padding (D-398 (3)) |
| `DOW` | `frozen_removed` | — | 0 | 2,297 | 396 interior padded bars |
| `CHPT` `DKNG` `HYLN` `VFS` | `frozen_removed` | — | 0 | 1,254–1,854 | 10–19 interior padded bars each |

**Nothing under `configs/costs/` was touched** (D-388), and all eleven are listed for stream A in
`docs/streams/B.md`.

### One thing the fingerprint cannot tell apart — P-74

A frozen stretch or a gap with a level break is *also* what an **unadjusted reverse split** looks
like, and `configs/data/known_splits.csv` holds only **11** hand-picked splits.

The artefact now says so per symbol. `reverse_split_suspect` in
`T04i_relisting_verdicts.csv` is true when the **boundary-setting** break is **upward** and within
**5 %** of one of the ratios a 1:n reverse split produces (`REVERSE_SPLIT_RATIOS` in
`data/relisting.py`: 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 15, 16, 20, 25, 30, 40, 50, 60, 75, 100,
120, 150, 200, 250, 300, 500, 1000). It is a flag on the evidence and never changes a verdict, and
it has its own tests.

**29 of the 280 trims (10.4 %) are flagged** — `ISRL`, `GRO`, `BIOA`, `LGCY`, `CART`, `SN`, `SHNY`,
`DO` and 21 more; **none of them is a Moneta target**. A reverse split's signature is not a new
company's, AVGO proves such splits exist in this feed (§4), and trimming one of these drops **real**
history rather than a splice.

The decisive test is already on disk and is the one that settled AVGO: the all-adjusted MS-US-1D
cross-check (`us_equity/alpaca_sip_all/1D/us_<symbol>.csv`) runs **continuously** across a split
and **breaks** across a re-use. Raised as **P-74**: run that cross-check over the 280 trims before
**T04k** applies them. Nothing is blocked now — T04i writes evidence only, and T04g ingests the raw
as-is with an empty exclusion file.

### What this artefact does *not* see

Three limits, stated so "797 affected, 0 exclusions" is not read as more than it is:

- **A re-use with neither a gap nor a pad is invisible.** If a ticker is re-assigned and the new
  instrument starts trading immediately, there is no fingerprint and no row. "0 exclusions" means
  *no detected candidate lacked a boundary* — not *no undetected re-use exists*.
- **A long halt is indistinguishable from a re-use.** `MARA` is the named case: the review calls it
  "same company, a long halt", and D-398 still trims 252 bars of real pre-halt history because the
  series cannot say which it was. The supervisor named `MARA` among the symbols to keep with a
  shorter history, so that is the decided outcome; it is listed here because the same shape will
  recur. P-74 covers only the reverse-split confusion.
- **A trim can leave almost nothing.** Three symbols keep fewer than ten bars (`AT` 4, `SIC` 7,
  `BURU` 5). Correct under D-398 and D-008 — they fail the split and drop out that way — but they
  are not usable series.

## 6b. Every known split that is unadjusted (D-397)

Re-ran the known-split check over both timeframes, all 11 splits in
`configs/data/known_splits.csv` (9 symbols: AAPL, AMZN, AVGO, CMG, GOOGL, NVDA, SMCI, TSLA, WMT):

| timeframe | adjusted | unadjusted | no data on the split date |
|---|---|---|---|
| 1D | 10 | **1** (`AVGO` 2024-07-15) | 0 |
| 1H (first run, incomplete raw) | 8 | **1** (`AVGO`) | 2 (`GOOGL` 2022-07-18, `TSLA` 2022-08-25) |
| **1H (re-run 2026-09-21, complete raw)** | **10** | **1** (`AVGO` 2024-07-15) | **0** |

**AVGO is the only genuinely unadjusted split, and it is unadjusted in both timeframes.** The two
`no_data_on_split_date` rows **were** the download gap, not a defect: with the completed hourly set
`GOOGL` 2022-07-18 and `TSLA` 2022-08-25 both come back **`adjusted`**, so the 1H table now matches
the 1D one exactly. That closes the "re-run this check in T04h" note; T04h inherits no open
split question.

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

### Does any other symbol need a `--refresh`?

**No — AVGO is the only symbol a refresh can be justified for today.** That is a statement about
the evidence in hand, not a clean bill of health: it holds for the 11 splits in
`known_splits.csv`, and group 3 below is an open list of suspects. Three groups were checked:

1. **The known splits.** 10 of 11 are `adjusted` in 1D; AVGO is the single `unadjusted`, and it is
   unadjusted in **both** timeframes, which is why both commands are needed.
2. **`GOOGL` 2022-07-18 and `TSLA` 2022-08-25**, the two 1H `no_data_on_split_date` rows: that was
   the **download gap**, not a defect. 2022 hourly has since filled to 806 symbols, so these need
   the check **re-run** (T04h), not a refresh.
3. **The 29 trimmed symbols flagged `reverse_split_suspect`** (§6a, P-74). They are suspects, not
   findings: `known_splits.csv` holds only 11 splits, so the relisting sweep cannot tell a reverse
   split from a re-use. The MS-US-1D cross-check settles each one, and any that comes back
   continuous joins the refresh list **then**, with its own command. Refreshing 29 symbols ×
   11 years on a hunch is not justified — and if several turn out to be unadjusted, the right
   response is a systematic split re-check, not 29 hand-written commands.

## 7. D-033 — accepted as D-395

The rule was fixed in the task before the numbers were seen: `RTH` only if the daily range is inside
the RTH hourly range on **every** compared day. It is not — **18,580 days breach, 0.95 %** over the
**complete** hourly set — so the evidence says the label stays **`exchange`**.

**The conclusion never depended on the missing years** (D-358), and that is now demonstrated rather
than argued: the decision was taken on 15,559 breaches over an incomplete set, and the completed
download raised the count to 18,580. More hourly data can only add breach days, never remove one.
For `RTH` to become correct, every one of them would have to be wrong, which is refuted by the
worked examples in §3.

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

- the **AVGO refresh** — the two commands are in §6b; a network run, so the user's (D-031). No other
  symbol needs one (§6b);
- ~~re-running the breach sweep once the hourly download is complete~~ — **done 2026-09-21**
  (§2, §3). It did **not** move the `incomplete_hourly_day` rows, which is itself the finding;
- **P-74** — cross-checking the 280 D-398 trims (29 of them flagged `reverse_split_suspect`)
  against the all-adjusted MS-US-1D series before **T04k** applies them, so an unadjusted reverse
  split is not mistaken for a re-used ticker;
- the exclusion file `configs/universe/us_equity_daily_excluded.csv` exists and is **empty**: under
  D-398 nothing in this sweep is excluded, so T04g ingests the full 6,711-symbol universe.

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

### Second round, after the D-398 amendment

The subagent ran again on the amendment and found four defects and several limits; all are fixed
above:

1. **"37 round-multiple suspects" was not reproducible** — the count came from an ad-hoc list in a
   scratch session. It is now `REVERSE_SPLIT_RATIOS` + `looks_like_reverse_split()` in
   `data/relisting.py`, with tests, emitted as the `reverse_split_suspect` column, and the number
   is **29**, recomputable from the committed CSV.
2. **"the zero-true-range requirement removes nothing" was false.** Replaced by the measured
   comparison over all 6,705 symbols (§6a): 765 symbols differ, 115 lose every stretch, 9,801 fewer
   padded bars.
3. **The acceptance block printed `tests/parity tests/leakage/oracle`**, which matches no tests.
   Both real commands are now listed with their own counts.
4. **`test_F_0_1_2_daily_session.py` was called 11 tests in §1 and 12 in §10**; it is 12.

It also noted three things that were true but unstated, now in §6a: a re-use with neither a gap nor
a pad is invisible to this artefact, a long halt cannot be told from a re-use (`MARA`), and three
trims leave fewer than ten bars. And three gaps in the tests, now closed: nothing loaded
`configs/data/alpaca.yaml` (so "the threshold is in config" was proved by inspection only), the
`--refresh needs --symbols` CLI guard had no test, and the config-model defaults restated the module
constants with nothing pinning them — `RelistingConfig` now imports them.

**D-398 also superseded the shape of findings 2 and 3 of the first round.** The reviewer's point stood — a frozen
stretch with no level break is not a re-used ticker — but the supervisor's answer removes the need
to decide that before acting: **every** frozen stretch is cut, and the level break only decides
whether the series also starts over at a boundary. The fingerprints and labels are unchanged;
`padding_only` and `pre_listing_padding` are no longer "not a candidate, no action" but "cut the
pad, keep the symbol". Finding 1 (the `moneta_target` column) stands and now covers eleven symbols
instead of seven, because the 10-session threshold catches more of them.

## 10. Acceptance commands

Re-run after the D-398 amendment (2026-09-20):

```
uv run pytest -m "not slow"                          1216 passed (on main after the stream-A universe regeneration)
uv run pytest tests/parity tests/leakage                280 passed
uv run pytest tests/parity tests/leakage tests/oracle   283 passed
uv run pytest -m db                                  21 passed, 0 skipped
uv run ruff check . / format --check .               clean
uv run mypy src                                      no issues in 100 source files
uv run sfac streams check --base origin/main         ownership, ids, alembic head: ok
```

Tests added by T04i: **38** (12 breach detection, **23** frozen stretches / re-used tickers /
boundaries / thresholds-from-config / the P-74 flag, 3 for `--refresh` including the CLI guard).
No new dependency. Nothing written to `SFAC_DATA_ROOT`; nothing under `configs/costs/` or
`configs/universe.yaml` changed. `configs/universe/` gained one file,
`us_equity_daily_excluded.csv`, which is empty (D-398).

## 11. Open questions

- **P-74** (new) — an unadjusted reverse split is indistinguishable from a re-used ticker with the
  evidence D-398 uses, and **29 of the 280 trims** carry that signature (§6a). The MS-US-1D
  cross-check decides it; the question is whether to run it before **T04k** applies the trims.
  It blocks nothing now: T04i writes evidence only and T04g ingests the raw as-is.
- P-71, P-72 and **P-73** are answered (**D-395 … D-398**) and are folded into §2, §6a, §6b and §7.
