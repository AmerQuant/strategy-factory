# T04i review — phase-B hourly analysis and the daily-session evidence (D-033)

**Task:** `docs/tasks/T04i_phaseb_hourly_analysis.md` · **Branch:** `b/T04i-phaseb-hourly` from `main` (T04f merged, PR #19)
**Features:** F-0.1.2 (adapter session filter and metadata), F-0.1.6 (quality evidence), F-0.1.9 groundwork (split-adjustment control)
**Decisions used:** D-010, D-021, D-022, D-023, D-025, D-033, D-355, D-358, D-382, D-383, D-386, D-388, D-394
**Supervisor instruction (2026-09-21):** do **not** record D-033 yet; classify every breach day, read the broker's trading hours, and raise a P- question. This review does that.

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/daily_session.py` | the breach detector and its four verdicts; pure, no I/O |
| `scripts/analysis/T04i_daily_session.py` | the sweep: adapter **in memory**, no snapshot, no catalog row (D-382) |
| `docs/reviews/T04i_breach_days.csv` | one row per breach day: symbol, date, class, both breaches in bps, and the prices behind them |
| `docs/reviews/T04i_symbol_coverage.csv` | per symbol: hourly years covered, days compared, counts per class |
| `tests/unit/test_F_0_1_2_daily_session.py` | 11 tests |

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
- **Relisted tickers:** not produced in this run. The breach sweep covers only the 826 symbols that
  have hourly data; the daily exclusion list must cover all 6,711 and is a different query (trading
  gap plus level break). It is the remaining piece of T04i and is listed in §8.

## 7. D-033 — the evidence, not yet the decision

The rule was fixed in the task before the numbers were seen: `RTH` only if the daily range is inside
the RTH hourly range on **every** compared day. It is not — 15,559 days breach, 0.96 % — so the
evidence says the label stays **`exchange`**.

**The conclusion does not depend on the missing years** (D-358): more hourly data can only add
breach days, never remove the ones already observed. For `RTH` to become correct, every one of the
15,559 would have to be wrong, which is refuted by the worked examples in §3.

**Per the supervisor's instruction, D-033 is not recorded here.** `configs/data/alpaca.yaml` still
says `daily_session: exchange`, which is the value the evidence supports; it should be confirmed
together with the answer to **P-71**, because the label alone does not address what the breaches do
to stops.

## 8. Not done yet in T04i

- the relisted-ticker exclusion list for T04g (`configs/universe/us_equity_daily_excluded.csv`),
  including `PX` and `FI` from T04f §9;
- re-running the sweep once the hourly download completes, which will move the 2,178
  `incomplete_hourly_day` rows into a real class.

## 9. Acceptance commands

```
uv run pytest -m "not slow"                  1187 passed
uv run pytest tests/parity tests/leakage     280 passed
uv run pytest -m db                          21 passed, 0 skipped
uv run ruff check . / format --check .       clean
uv run mypy src                              no issues in 99 source files
uv run sfac streams check                    ownership, ids, alembic head: ok
```

No new dependency. Nothing written to `SFAC_DATA_ROOT`; nothing under `configs/costs/` or
`configs/universe.yaml` changed.

## 10. Open questions

- **P-71** — what to do about the breaches (the decision this task is stopping for).
- **P-72** — AVGO's unapplied 10:1 split: it needs a re-download before T04g.
