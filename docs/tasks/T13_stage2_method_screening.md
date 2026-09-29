# T13 — Stage 2: method screening (s02_screen)

**Stream A (D-611).** Plan first (D-403): draft, stop for "Plan approved", then implement. Not
listed as critical in D-402, but it produces the candidates stages 3–7 build on: stop for the
review before merge.
Features: F-2.1 … F-2.7.
Depends on: T12 (EdgeProfiles, baseline, stage framework), T07 (components and indicators), T08
(engine), T09 (metrics), T10b (executor, registry, config hash).

## 1. What stage 2 answers

Stage 1 said **an edge exists** for (symbol, timeframe, edge type, direction). Stage 2 asks
**which methods capture it best**, measured over a coarse grid of each method's parameters, with
the exits still fixed. It hands 3–5 diverse methods per profile to stage 3.

The defence against overfitting at this stage is to **score a method by its whole grid, not by
its best cell** (spec §2.2). A method that is good in one cell and poor around it is luck.

## 2. Decisions to record before implementing

Supervisor range, marked *(supervisor)*, each citing this task. Next free supervisor id: D-622.

| ID | Decision |
|---|---|
| D-622 | **A method is an entry rule with free parameters; exits stay fixed.** The exits are stage 1's (D-101, D-614), including the 3-ATR disaster stop (D-130). Freeing the exits here would multiply the grid and make it impossible to tell whether a method won on its entry or its exit; exits are stage 4's. |
| D-623 | **Ranking is zero-cost; the gate is after costs; both are reported.** The family score (§5) is computed on zero-cost runs, as stage 1 separated "is there an edge" from "does it survive costs" (D-602). The gate (§7) is evaluated on runs with the full Moneta cost profile, so a high-turnover method that ranks first on zero cost but loses after costs is rejected here, not in stage 6. Every cell carries both numbers. |
| D-624 | **The family score is computed over the whole grid** with F-2.4's weights: grid median 40, share of profitable cells 25, excess return over the random baseline 20, yearly consistency 15. The target metric (spec §2.1) is **average annual profit ÷ average annual drawdown, drawdown measured against initial capital**. The excess-return component is computed with stage 1's baseline method (D-102, D-607, D-618) on **one cell only: the median cell of the good region**, where the good region is the top quartile of cells by the target metric. Not the best cell (luck), not every cell (64× the cost). Every constant is config. |
| D-625 | **D-110 stands: 3–5 candidates per profile**, chosen by rank-sum (F-2.5) and the diversity rule (F-2.6, trade overlap ≤ 60 %). A profile with fewer than 3 methods passing the gate sends what passed and says so. |
| D-626 | **Short methods are screened**, as the mirror of the long rule (T07's mirror rule). Stage 1 accepted 7 MR-short profiles on 1D; dropping them now would discard a result without evidence. Whether a short is ever traded is a later stage's decision. |
| D-627 | **The method library is the spec's library plus the user's own MR suite, deduplicated into parameterised families** (§4). Two methods that produce the same signals are one method: T12 found `close_below_bb_lower` ≡ `zscore_below_minus_2`, which double-counted one rule in every statistic. A guard test (§9) fails if any two stage-2 methods produce identical signal vectors. Parts of the user's suite that are not stage-2 entries are routed to their stage (§4.4) and not built here. |
| D-628 | **Input: every stage-1 pass** (D-609), including the four 1H TF-long passes flagged `unconfirmed` (D-621). A profile is screened only with methods of its own edge type and direction. The review reports unconfirmed profiles separately and never lets them stand in for the daily MR finding. |

## 3. Inputs

- The passing EdgeProfiles from the merged T12 run (index + `summary.json`), with their
  candidate ids (D-805) and data caveats (D-610). Today: 14 MR profiles on 1D (7 long, 7 short,
  13 symbols) and 4 TF-long on 1H (unconfirmed).
- **Development data only**; the stage never reaches the holdout (D-306, D-616: no split manager
  in `RunContext`, same static guard as T12).
- Costs: the Moneta profile for the gate leg (D-623).
- The stage-1 battery may change in T15 (the duplicate probe, TF exits, ESS constants). Stage 2
  must not depend on the specific 14 passes: it takes whatever stage 1 produced.

## 4. The method library

Each method is a registered entry component (T07 contract) with `ParamSpec`s whose
`coarse_values` hold exactly 4 values; at most 3 free parameters, at most 64 cells (D-110).
Choice parameters count as parameters. All thresholds below are **starting coarse grids** for the
plan; the plan may adjust them with a stated reason.

### 4.1 MR — from the spec (F-2.1)

The stage-1 MR probes, parameterised, plus: Connors RSI, cumulative RSI, Williams %R, Stochastic
%K, Keltner lower band, distance from a moving average, N-day low. **Keep only one of
`close_below_bb_lower` / `zscore_below_minus_2`** (use the z-score form).

### 4.2 MR — the user's suite, deduplicated

Source: the user's Pine script `Amer-Index-MeanReverses` (commit it unchanged at
`tools/tradingview/user_mr_suite.pine`; it is the specification for these rules). Where a rule
already exists in §4.1, it becomes grid values of that method, not a new method.

| method | rule (long; short is the mirror) | coarse grid (4 values each) | from the script |
|---|---|---|---|
| `mr_ibs` | IBS < t on the last k bars | t {10, 20, 30, 40} %, k {1, 2, 3} | #0 (and stage-1 IBS) |
| `mr_rsi` | RSI(n) < t | n {2, 3, 5, 14}, t {10, 20, 30, 35} | #1, #19 (and stage-1 RSI) |
| `mr_rsi_sum` | sum of RSI(n) over m bars < t | n {2, 3, 4, 5}, m {2, 3}, t per m | #2 (= cumulative RSI, §4.1: one method) |
| `mr_down_closes` | k consecutive lower closes | k {1, 2, 3, 4} | #4 (and stage-1 three_down_closes) |
| `mr_lower_lows` | k consecutive lower lows | k {2, 3, 4, 5} | #3 |
| `mr_n_day_low` | close < lowest close of the previous n | n {3, 5, 7, 10} | #5 (and stage-1, §4.1 N-day low: one method) |
| `mr_daily_drop` | close < close[1]·(1 − d), optionally ATR(5) > ATR(10) | d {0.5, 1, 2, 3} %, atr_expanding {off, on} | #6, #7 |
| `mr_ma_distance` | close below EMA(n) by a level, in % or in ATR(5) units | n {5, 10, 20, 50}, unit {pct, atr}, level index {0..3} mapped per unit (pct {0.5, 1, 2, 3} %, atr {0.25, 0.5, 1, 1.5}) | #8, #9 (§4.1 distance from MA: one method) |
| `mr_ema_slope_drop` | EMA(n) fell by more than p % in one bar | n {3, 5, 10, 20}, p {0.25, 0.5, 1, 1.5} % | #10 |
| `mr_ibs_after_new_high` | high > highest high of previous n, and IBS < t | n {5, 10, 20, 50}, t {10, 15, 20, 25} % | #14 (pullback within strength) |
| `mr_macd_hist_falling` | MACD histogram fell k bars in a row, below 0, and close < close[1] | k {2, 3, 4, 5} (MACD 12/26/9 fixed) | #17 |
| `mr_macd_hist_turn` | histogram rose k bars in a row while below 0 | k {1, 2, 3, 4} | #20 (and stage-1 MACD trough: check equivalence) |
| `mr_candle_score` | the script's candle score summed over n bars ≤ t; variant: also rising | n {2, 3, 5, 8}, t {4 values}, mode {level, rising} | #18 |
| `mr_williams_confirm` | Williams %R(n) < t, then a bar with high > high[1] | n {5, 10, 14, 20}, t {5, 10, 20, 30}, confirm {off, on} | #22 (§4.1 Williams %R: one method, `confirm` is the user's variant) |

Implementation notes from the script: `ta.lowest(n)` / `ta.highest(n)` default to low / high;
IBS is `(close − low)/(high − low)·100`; the candle score is `selfScore + coScore` exactly as the
script defines them. The script's short conditions are not always the exact mirror (e.g. the
candle score's short uses the same threshold): the framework's mirror rule applies, and the plan
lists every place it differs from the script.

### 4.3 TF (F-2.2)

The stage-1 TF probes, parameterised, plus Keltner breakout, ADX/DI, Hull MA, KAMA, Parabolic SAR,
Aroon, dual momentum; and from the user's script, `tf_atr_band` (close > lowest low of n +
k·ATR(m), #11) and `tf_base_candle` (the script's BaseCandle state machine, #23/#24, direction
flip). Today only the four unconfirmed 1H profiles use TF; build the library anyway, since T15 may
change what stage 1 passes.

### 4.4 Routed elsewhere — not built in T13

Record these in the plan as parked items with their destination:
- **Exits** (N consecutive closes above the previous high, TP %, stop %, trailing %, N bars,
  candle-score exit, first profitable close) → stage 4's exit library.
- **Filters** (EMA direction, SPY direction — now possible through the T04m aux join —, the
  normalised-volatility regime with min/max/rising/falling) → stage 5.
- **Calendar rules** (#12 Monday, #16 IBS Monday–Tuesday, #21 hourly seasonality) → stage 1-S and
  stage-5 calendar filters, subject to the edge-type addendum's forbidden families.
- **#13 Narrow range** → the volatility-squeeze (VS) edge type, P1 (addendum).
- **#15 One Day** (a daily IBS read on an intraday session) → not now.
- **MinStrategyNum voting** (entries firing together) → multi-strategy / portfolio, later.

## 5. The family score (F-2.4, D-624)

Per method, over all its cells, on zero-cost runs:

- **grid median (40):** median of the target metric over all cells;
- **profitable share (25):** share of cells with a positive target metric;
- **excess return (20):** mean excess return per trade in ATR units (as stage 1, D-601) of the
  median cell of the good region, against 1000 matched random entries (D-102, D-607, D-618);
- **consistency (15):** share of years with a positive target metric in the good region's cells.

Each component is mapped to its points by a config constant, as ESS was (D-606). The F-2.4
acceptance test is the headline unit test: a synthetic method good in one cell and poor elsewhere
scores below a synthetic method uniformly good.

Cells with fewer trades than the minimum (30 on 1D, 100 on 1H, as stage 1) take part in the grid
statistics as failed cells, not as missing ones, so a method cannot raise its median by being
silent.

## 6. Ranking and diversity (F-2.5, F-2.6)

- **Rank-sum** over the family-score components (F-2.5): invariant to monotone rescaling of any
  metric, tested.
- **Diversity** (F-2.6): overlap = share of bars in position shared by two candidates, computed
  on their good-region median cells. Walk the rank order; drop a method whose overlap with an
  already chosen one exceeds 60 %; take the next. Stop at 5.

## 7. Gate (F-2.7)

`s02_screen`, thresholds in `configs/gates/default.yaml`, on the **after-cost** runs (D-623):
- median of the target metric over the grid > 0;
- share of profitable cells ≥ 60 %;
- trade minimum in the good-region cells, as stage 1;
- overlap ≤ 60 % with already selected candidates.

Register every new metric name in the T10b registry.

## 8. Artifact

`artifacts/<run_id>/s02_screen/<candidate_id>/summary.json` per selected method: identity
(profile's candidate id, method, config hash, stage-config hash, snapshot hash, code version),
the full grid with both zero-cost and after-cost target metrics per cell, the family score with
raw values and points, rank, overlaps with the other selected methods, gate verdict per
criterion, and the parent EdgeProfile's caveats (D-610) and `unconfirmed` flag (D-628). The grid
heatmap is written **as data**; T15 draws it. Every cell is a trial row in the registry
(`cells_run` for D-160). Trades only for the selected methods' good-region median cells.

## 9. Tests

- **F-2.1 / F-2.2:** every method declares its params, respects 4 values and ≤ 64 cells, and has
  a reference test for any new indicator (TradingView golden where one exists; otherwise a naive
  line-by-line implementation from the Pine source).
- **The user's rules:** each is tested against a naive implementation written from
  `user_mr_suite.pine`, on hand cases and random data. If the user provides TradingView exports of
  the custom series (IBS, candle score), add them as golden files.
- **Equivalence guard (D-627):** no two stage-2 methods produce identical signal vectors on the
  reference charts at their default cells. Mutation-check it by registering a duplicate.
- **F-2.4:** the one-good-cell vs uniformly-good synthetic test.
- **F-2.5:** rank-sum invariant to monotone rescaling.
- **F-2.6:** no two selected candidates overlap above 60 %, including a case where the top two
  overlap and the third is chosen.
- **F-2.7:** each criterion failed in turn is named, thresholds from config; the gate reads the
  after-cost leg and the ranking the zero-cost leg (a wiring test that fails if they are swapped).
- **Leakage (rule 3):** truncation invariance for every new method's signals.
- **Holdout:** the stage cannot reach `open_holdout` (the T12 static guard, extended).
- **Reproducibility:** serial and parallel bit-identical.

## 10. Acceptance

- Every constant in config (rule 1).
- A pilot on a few of the passing profiles, reproduced by a second run; measure the cost and
  project the full run before starting it.
- The full run over every stage-1 pass. The review reports, per profile: methods screened, cells
  run, the family-score table, the rank, what the diversity rule removed, what passed the gate,
  and the zero-cost vs after-cost difference for the selected methods.
- **The headline control:** run stage 2 on the same passing profiles with each symbol's returns
  reshuffled (the D-615 control). **No method should pass the gate.** If some do, that is the
  number the review leads with, and it goes to the supervisor before stage 3 is built on it.
- Report which of the user's methods were selected and which were not, and why — this is the
  first time the user's suite is measured by the same yardstick as the library.
- Fast suite, parity/leakage/oracle, db with 0 skipped, slow, ruff, format, mypy (Windows and
  `--platform linux`), stream guards.
- The review states D-802 (D-335/D-336 unverified against TradingView) as T12's does.
- Then stop for "Approved".

## 11. Raise, do not decide

- Any coarse grid above whose values are badly placed on real data (all cells fail, or all pass).
- A profile where no method passes the gate: report it; do not loosen the gate.
- If the control lets methods through.
- Any place the framework's mirror rule gives a materially different short than the user's script.
