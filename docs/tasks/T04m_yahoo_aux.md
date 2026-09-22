# T04m — Yahoo auxiliary series: ingest, and the as-of join a filter reads

**Features:** F-0.1.4 (Yahoo adapter: dates and adjustment metadata recorded; the series usable
by F-0.1.11), **F-0.1.11** (as-of alignment with lag; the leakage test), F-0.1.6 (quality per
snapshot), F-0.1.8 (immutable snapshots, catalog, references)
**Priority:** P1: the inputs to the stage-5 filters (spec §5.2: "VIX for the US market",
"the reference market's regime: the main index or the dollar against its MA") and, after the MVP,
the IM edge type (addendum §5, D-235, D-240). **Depends on:** T04c (downloader, adapter),
T04f (NYSE calendar). **Branch:** `b/T04m-yahoo-aux` from `main`. **Independent of T04j**, which
is paused on its download.

Read first: `CLAUDE.md` rules 2, 3, 7, 8, 10, 11; D-014, D-020, D-027, D-235, D-240, D-306, D-316,
D-392; spec §5.2 (filter families); addendum §5.1–5.3 (the aux series and the timing rule, "critical
for leakage"); `docs/tasks/T04c_yahoo_aux.md`, `docs/reviews/T04c_review.md`.

## What exists today (measured 2026-09-22)

**Raw store:** `SFAC_RAW_ROOT/aux/yahoo/1D/<ticker>/2026-09-19.parquet`, one version per ticker,
downloaded 2026-09-19 with `yfinance 1.7.0`, `Ticker.history(period=max, interval=1d,
auto_adjust=False, actions=False)`. Each has a manifest (sha256, row count, call). Columns:
`Date` (midnight in the exchange zone), OHLC, `Adj Close`, `Volume`.

| series (symbol) | rows | first | last | Yahoo zone | OHLC flat (all / since 2016) | notes |
|---|---|---|---|---|---|---|
| `^VIX` (VIX) | 9,248 | 1990-01-02 | 2026-09-18 | America/Chicago | 508 (to 1997) / 0 | volume always 0; **2 rows on NYSE holidays in 2026** (2026-05-25, 2026-09-07) with real ranges |
| `^GSPC` (SPX) | 24,796 | 1927-12-30 | 2026-09-18 | America/New_York | 8,547 (to 1983) / 0 | close-only before 1983 |
| `^NDX` (NDX) | 10,321 | 1985-10-01 | 2026-09-18 | America/New_York | 1 / 0 | |
| `^RUT` (RUT) | 9,830 | 1987-09-10 | 2026-09-18 | America/New_York | 0 / 0 | |
| `^DJI` (DJI) | 8,740 | 1992-01-02 | 2026-09-18 | America/New_York | 0 / 0 | |
| `^TNX` (TNX) | 16,166 | 1962-01-02 | 2026-09-18 | America/Chicago | 7,954 / **17** | quoted in **percent** (median 3.79 since 2020), not ×10, which answers T04e's scale question. The 17 flat bars since 2016 fall on **bond-market holidays** (Columbus Day, Veterans Day); 15 of them carry a value different from the day before |
| `DX-Y.NYB` (DXY) | 14,146 | 1971-01-04 | 2026-09-18 | America/New_York | 3,726 (to 2013) / 0 | ICE trades some US holidays: 3 rows on NYSE holidays; missing 2 bond holidays |

- **Against the NYSE calendar, 2016-01-04 … 2026-09-18 (2,693 sessions):** SPX, NDX, RUT and DJI
  match it exactly. VIX has 2 extra days, TNX is missing 1, DXY has 3 extra and 2 missing.
- **Integrity:** 0 null closes, 0 non-positive values, 0 high < low or close outside the range,
  0 weekend dates, `Adj Close` = `Close` everywhere. The longest gap is 7 days: 9/11 for the US
  indices, 12 days for SPX in 1933.
- **Catalog:** **0** Yahoo snapshots; the series have never been ingested (runbook "Deferred").
- **Code:**
  - `data/download/yahoo.py`: `sfac data download yahoo`, the user's network run; each run writes a
    new immutable version and a revision check.
  - `data/adapters/yahoo.py`: raw → canonical daily bars. `ts` = the session date at 00:00 UTC; raw
    `Close`, never `Adj Close`; `asset_class="aux"`, `adjustment="raw"`; `value_final_*` taken from
    `configs/universe/aux_yahoo.csv`.
  - `data/cli_yahoo.py`: `sfac data ingest yahoo`.
  - `configs/data/aux_series.yaml`: `unverified_extra_lag_days: 1` (D-014).
  - `universe.yaml` already lists the seven as `asset_class: aux`, `tradable: false`,
    `cost_profile: null`.
- **Not built: the as-of join (F-0.1.11).** Nothing in the code reads an aux series next to a
  traded symbol yet, and no leakage test covers it.
- **No download is needed for this task.** The 2026-09-19 versions are ingested as they are. A
  later refresh is the user's run (D-031) and writes a new version.

## How an aux series differs from a tradeable symbol

| | tradeable symbol | aux series |
|---|---|---|
| candidate in any stage | yes | **never**: an input to a filter or probe only |
| cost profile | required (rule 4) | none |
| split / embargo / holdout of its own | yes (F-0.6.1) | **none registered, ever** |
| read through | `DataAccess.bars/arrays` (development segment) | **only the as-of join**, over a **traded symbol's** window (the D-316 pattern for conversion pairs) |
| stage-6 holdout | one-shot, logged, per candidate | read **together with** the traded candidate's one-shot access, over its holdout window; the aux series' own holdout is never consumed |
| time of a value | the bar's close (rule 3) | the **instant its daily value becomes final** (D-014: `value_final_time_local` + zone; `to_verify` → one extra day) |
| D-008 | counted | not counted |

**Guard (new):** a reference whose `asset_class` is `aux` is **refused as a traded symbol** by
`DataAccess.bars / arrays / split` and `SplitManager.registered / compute / open_holdout`. So an
aux series can never get a split or a holdout record, whatever a stage asks for. The ingest
refuses an aux symbol that is also a tradeable universe symbol (none of the seven is today:
checked against the 6,711 daily, 806 hourly and 29 Dukascopy symbols).

## Keying

- Source `yahoo`, the symbol from `aux_yahoo.csv` (VIX, SPX, NDX, RUT, DJI, TNX, DXY), timeframe
  `1D`, `asset_class aux`. One reference per `(symbol, 1D)` (D-392 rules as everywhere).
- `ts` = the **session date at 00:00 UTC** (the day boundary of CLAUDE.md rule 7). The date is
  taken in Yahoo's exchange zone (Chicago for VIX and TNX), so the session date is correct.
- **The final instant** of each bar is computed at read time from the snapshot metadata, never
  stored as a column:
  - verified: the session date at `value_final_time_local` in `value_final_tz` (DST-aware; VIX
    16:15 New York);
  - `to_verify`: that instant **+ `unverified_extra_lag_days`** (D-014). Where no close time is
    recorded (DXY, TNX, SPX, NDX, RUT, DJI today), the base instant is **24:00 of the session date
    in the series' own zone** — **P-89**.
- On early-close days the regular close time is used, which is later than the true one. That is
  conservative: a value is never usable earlier than it really was.

## The as-of join (F-0.1.11): what a consumer reads

**Decision instant of a traded bar i** (rule 3: signals use data up to the close of bar i):

| traded bars | decision instant |
|---|---|
| 1H (any market) | `ts + 1h` |
| 1D, 24x5 (Dukascopy; D-032, D-010) | `ts + 24h` (Monday's bar, which holds the Sunday hours, also ends Tuesday 00:00) |
| 1D, NYSE (Alpaca) | the session's **close** from `configs/calendars/nyse_sessions.csv`, including its early closes |

**Rule:** bar i sees the **latest aux bar whose final instant is strictly before bar i's decision
instant**, and nothing newer. Addendum §5.3's examples follow from it:

- A US equity at the close of day d (16:00 New York) sees **VIX of d−1**: VIX d is final at 16:15.
- An FX daily bar of day d (decision at 24:00 UTC) sees **VIX of d**.

**Holidays:** the latest final value carries forward, up to `max_staleness_days` (config, **5**,
addendum §5.3). Beyond that, bar i gets no value, which the consumer must treat as an invalid
signal (**P-90**).

**API, in `data/aux.py` (pure alignment) and `data/split.py` (access):**

```python
DataAccess.aux(aux_symbol, traded_symbol, timeframe) -> AuxView       # development window
SplitManager.open_holdout_with_conversion(candidate_id, symbol, timeframe, pairs,
                                          *, aux=(), stage)           # stage 6: one one-shot access

@dataclass(frozen=True)
class AuxView:
    key: SnapshotKey          # the aux snapshot read -- the run records it (rule 8)
    ts: int64[m]              # aux bar starts (session date 00:00 UTC), ascending
    open/high/low/close: float64[m]
    final_us: int64[m]        # final instant of each aux bar (lag applied)
    idx: int64[n]             # per traded bar: index into the aux arrays, -1 = none / stale
    decision_us: int64[n]     # the traded bars' decision instants
```

- **The aux arrays end at the window's last decision instant.** Only aux bars that are final
  before the last traded bar's decision are returned. During development that bar is the traded
  symbol's `dev_end`, so nothing after it is ever visible.
- **No lower bound:** earlier aux history is the past, and indicators such as a 252-day VIX
  percentile or SMA(DXY, 50) need it for warm-up.
- **How a filter uses it:** compute the indicator **on the aux bars** (causal), then read it at
  `idx`: `vix_sma10[idx]`, never an indicator over values repeated onto the traded bars. That is
  how "VIX > 1.1 × SMA(VIX, 10)" stays a daily VIX statistic on hourly bars.
- **Holdout:** an aux series is read over the traded candidate's holdout window only inside that
  candidate's one-shot access (stage guard D-306 first, as for conversion pairs). `aux=` joins the
  existing `pairs=` so a run that needs both spends one access, not two.
- **Rule 8:** the run records `AuxView.key`. Wiring that into the run row is the consumer's (stream
  A, stage 5); the data layer always returns it.

## Scope

1. **Ingest** the seven with `sfac data ingest yahoo --set-reference`.
   - The reference moves only with `--set-reference`. Today's "reference on first ingest" goes, as
     in every later ingest task.
   - Refuse an aux symbol that is a tradeable universe symbol.
   - Record the TNX unit (percent) in the snapshot notes.
   - Idempotent: a re-run writes nothing (test and store evidence).
2. **Quality reports** for the seven: the generic checks (OHLC consistency, duplicates,
   non-positive values, gaps). Schedule checks are **skipped for `aux` with that reason written**.
   Different holiday calendars are normal for these series, and the join's staleness cap handles
   them. The table above goes into the review (**P-91**).
3. **`data/aux.py`:** decision instants, final instants, the as-of index, the staleness cap;
   `max_staleness_days` in `configs/data/aux_series.yaml` (rule 1).
4. **Access:** `DataAccess.aux`, `aux=` on the stage-6 holdout method, and the guard that refuses
   `aux` as a traded symbol.
5. **Tests (written first):**
   - **leakage / truncation (F-0.1.11 acceptance):** cutting the aux series after any instant T
     changes nothing for traded bars whose decision instant is ≤ T, and no traded bar ever sees an
     aux value final at or after its decision instant (Hypothesis over random calendars);
   - VIX / equity → d−1; FX → d; an early close; a `to_verify` series one day later; a blank
     close time; DST on both sides;
   - holidays carried forward up to the cap, then `-1`;
   - aux refused by `bars / arrays / split / registered / open_holdout`; no split row is ever
     written for an aux key;
   - the holdout read happens only inside the one-shot access and never records the aux series;
   - the development read ends at `dev_end`'s decision instant;
   - the collision guard; ingest idempotence.
6. **Report:** the seven references, their quality, the join tested end to end on a real equity
   (1D and 1H) and a Dukascopy pilot symbol; `B_data_state.md` updated.

## Out of scope

- **The filters and probes themselves:** stage 5 and `components/` are stream A's (D-611). IM is
  after the MVP (D-240).
- **Hourly VIX or DXY:** Yahoo has no long hourly history (addendum §5.8).
- **Verifying the close times** of the six `to_verify` series. That needs the index providers'
  documents and a supervisor decision (**P-89**).
- **The reference index per symbol** (addendum §5.1: "defined in the universe metadata"). It is
  metadata stage 5 will need, but it is a universe-schema change stream A regenerates from:
  **P-92**, proposed and not built unless approved.
- New downloads.

## Acceptance

- Seven aux references (`asset_class aux`, hash version 2), each with a quality report; no split
  or holdout row for any of them.
- The F-0.1.11 leakage test (truncation) passes and sits in `tests/leakage/`, never skipped.
- The addendum §5.3 examples hold as tests: equity at the close of d → VIX d−1; FX daily of d →
  VIX d.
- An aux series is unreachable as a traded symbol (tests), and a holdout read of it happens only
  inside a candidate's one-shot access.
- The gates pass: the fast suite, parity, leakage, db (0 skipped), ruff, format, mypy;
  `sfac streams check` is clean.

## Open questions (in `docs/decisions/pending.md`)

- **P-89:** the six `to_verify` series have no recorded close time. Keep D-014 as it is, with the
  final instant at 24:00 of the session date plus one day? The cost is that a US equity at the
  close of d sees SPX/NDX/RUT/DJI of **d−2**, not d−1. Or should the supervisor verify their close
  times?
- **P-90:** what "forward-fill capped at 5 days" (addendum §5.3) measures: calendar days from the
  value's final instant to the traded bar's decision instant (proposed); and whether a stale bar is
  `-1` (proposed) rather than an error.
- **P-91:** schedule checks for `aux`: skipped with a written reason (proposed), or checked against
  the NYSE calendar and reported as warnings?
- **P-92:** the reference index per symbol (addendum §5.1). Proposed: US equity → SPX; FX and
  metals → DXY; the US index CFDs → their own index (USA500 → SPX, USATECH → NDX, USA30 → DJI,
  USSC2000 → RUT); others none. Stored as a column in `configs/universe/` (stream B) and a
  `reference_index` field on the universe entry, which stream A regenerates (D-394). Build it here,
  or in stage 5's task?
