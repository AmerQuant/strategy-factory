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

The sweep ran on **826 symbols** that have both timeframes, **1,617,247 session days** compared.
The hourly raw store is still filling while the user downloads the missing years; at the time of
this run:

| year | symbols with an hourly file (of 832) |
|---|---|
| 2016–2019 | 832 |
| 2020 | 829 |
| 2021 | 660 |
| **2022** | **0** |
| 2023 | 207 |
| 2024–2026 | 827 |

Every hourly statistic below is restricted to the days that exist, and a day whose hourly side is
only partly downloaded is reported as its own class rather than as evidence (§3).

## 3. Breach classification

For each session date present in both timeframes: `rth_high/low` from the **canonical** hourly bars
(09:00–15:00 New York, D-023), `daily_high/low` from the daily bars, breaches in basis points of the
daily close. Each breach is then classified against the **raw** hourly file, which still holds the
extended-hours bars the adapter drops.

| class | days | % of compared days | median bps | p90 | p99 | max | > 100 bps | > 1000 bps |
|---|---|---|---|---|---|---|---|---|
| `extended_hours` | 10,521 | 0.651 | 3.1 | 33.0 | 148.6 | 3,523 | 175 | 3 |
| `unexplained` | 2,860 | 0.177 | 9.8 | 70.1 | 558.0 | 8,921 | 220 | 15 |
| `incomplete_hourly_day` | 2,178 | 0.135 | 29.1 | 200.6 | 452.7 | 1,570 | 434 | 1 |
| **total** | **15,559** | **0.962** | | | | | | |

`incomplete_hourly_day` — the session has fewer hourly bars than its calendar close implies — was
added **after** a first pass put 2,178 of these in `unexplained`. The clearest case was
2021-04-19, where 244 symbols "breached" on one day with a **median of 1 hourly bar**:
that is the download in progress, not the data. Without the calendar those days read as bad prints,
which is why the class exists and why the number is reported separately rather than folded in.

### Does `unexplained` cluster?

**By symbol: weakly.** 727 of 826 symbols have at least one, median 3 per affected symbol. The top
are the big ETFs — `SPY` (72), `QQQ` (25), `IWM` (22) — then `TXT` (22), `CA` (17), `EMC` (14).
`CA` and `EMC` are delisted tickers whose hourly history is short.

**By date: yes, and it matters.** 1,039 distinct dates, but 2019-10-31 (75 symbols), 2019-08-12
(64) and 2025-03-06 (55) are feed-wide days, not per-symbol errors. 2025-03-06 is one-sided: all 55
are low-side breaches, median 14.8 bps. A date-wide cluster points at the feed, a symbol-wide one at
that symbol.

**By year:** 2016 (619) and 2017 (746) carry half of them, and the median size is flat (9–17 bps)
across the sample, so this is not a recent regression.

### The worst unexplained breaches are decimal errors

| symbol | date | daily low | daily close | raw hourly low | breach |
|---|---|---|---|---|---|
| `SPY` | 2026-02-02 | **69.005** | 695.41 | 681.94 | 8,921 bps |
| `MRK` | 2021-06-11 | **15.32** | 76.27 | 75.60 | 7,904 bps |
| `VZ` | 2026-01-08 | **10.5999** | 40.57 | 40.0645 | 7,263 bps |

`SPY` at 69.005 against a 695.41 close is a misplaced decimal point. These are exactly the prints
the supervisor is worried about: a stop anywhere between 690 and 69 fires on a price the market
never traded at, in the most liquid instrument there is.

And a high-side one, **`NVDA` 2024-06-10**: daily high **195.95** while the whole week trades
117–132 and the hourly maximum that day is 123.10. A long's take-profit or a short's stop at 150
"fills" on a print that does not exist in the hourly feed.

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

- **Bars per session:** hours kept are exactly `[9, 10, 11, 12, 13, 14, 15]`. Over ten large-cap
  symbols, 22,213 of 22,416 days have the full 7 bars and 186 have 4 on a 13:00 half-day — the
  calendar and the adapter agree. The 17 exceptions are the same 2 days per symbol:
  **2018-05-02 and 2018-05-03 have a single hourly bar** for every symbol checked, so it is a
  feed-wide gap, not an AAPL one as I assumed while planning.
- **META before 2022-06-09:** 1,620 daily bars and hourly history back to 2016-01-04 14:00 UTC,
  first close 102.22. Alpaca does serve Meta's pre-rename history under `META`, which is what T04f
  relied on.
- **Split check:** 10 of 11 known splits `adjusted`; AVGO is §4.
- **Relisted tickers:** see §6a.

## 6a. Re-used tickers — the candidate list for T04g (D-383)

Swept all **6,711** daily symbols. **379 candidates over 329 symbols** (4.9 %), in
`docs/reviews/T04i_relisted_candidates.csv`. The planning assumption — "a trading gap followed by a
level break" — found only part of it:

| fingerprint | rows | symbols |
|---|---|---|
| `stale_run` | 296 | 267 |
| `trading_gap` | 83 | 83 |

**The gap test alone would have missed `PX` and `FI`, the two symbols T04f flagged**, because they
have **no gap at all**: the feed pads the dead stretch with the last price. `PX` is
Praxair 2016–2018 at 96–169, then **749 consecutive bars at exactly 164.50**, then RPC Inc. from
late 2021 at 12–15, identical to `RPC` day for day. `FI` has 315 frozen bars. That is the more
dangerous shape of the two: a gap is visibly missing data, a frozen price is silently tradeable and
every indicator over it is meaningless.

Worst cases, all the same story — a delisted shell frozen at pennies, then the ticker re-used:

| symbol | reason | frozen bars | close before | close after |
|---|---|---|---|---|
| `LINE` | `stale_run` | **2,056** | 0.155 | 80.78 |
| `BIOA` | `stale_run` | 1,668 | 0.172 | 18.31 |
| `SN` | `stale_run` | 1,119 | 0.375 | 42.31 |
| `RELY` | `stale_run` | 780 | 0.509 | 48.45 |
| `PX` | `stale_run` | 749 | 165.49 | 12.08 |
| `AKTS` | `trading_gap` | — | 0.037 | 22.40 |
| `FB` | `trading_gap` | — | 196.64 | 39.91 |

Per D-383 this is a **candidate list, not an exclusion list**: the supervisor confirms rows into
`configs/universe/us_equity_daily_excluded.csv`, which T04g reads. Nothing in `configs/universe/`
was changed by this task.

## 6b. Every known split that is unadjusted (D-397)

Re-ran the known-split check over both timeframes, all 11 splits in
`configs/data/known_splits.csv` (9 symbols: AAPL, AMZN, AVGO, CMG, GOOGL, NVDA, SMCI, TSLA, WMT):

| timeframe | adjusted | unadjusted | no data on the split date |
|---|---|---|---|
| 1D | 10 | **1** (`AVGO` 2024-07-15) | 0 |
| 1H | 8 | **1** (`AVGO` 2024-07-15) | 2 (`GOOGL` 2022-07-18, `TSLA` 2022-08-25 — 2022 hourly is missing) |

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

## 9. Acceptance commands

```
uv run pytest -m "not slow"                  1196 passed
uv run pytest tests/parity tests/leakage     280 passed
uv run pytest -m db                          21 passed, 0 skipped
uv run ruff check . / format --check .       clean
uv run mypy src                              no issues in 99 source files
uv run sfac streams check                    ownership, ids, alembic head: ok
```

Tests added by T04i: **18** (11 breach detection, 7 re-used tickers) plus 2 for `--refresh`.
No new dependency. Nothing written to `SFAC_DATA_ROOT`; nothing under `configs/costs/` or
`configs/universe.yaml` changed.

## 10. Open questions

- **P-71** — what to do about the breaches (the decision this task is stopping for).
- **P-72** — AVGO's unapplied 10:1 split: it needs a re-download before T04g.
