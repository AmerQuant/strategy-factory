# T13 — plan: measurements, the method library, the mirror list

Stream A's plan for `docs/tasks/T13_stage2_method_screening.md` (D-403). The task file is the
supervisor's and is not edited; where this plan adjusts it (grids, the gate), the reason is
measured here and the change waits for "Plan approved" and the answers to **P-107 … P-114**.
Decisions: D-622 … D-628 (recorded from T13 §2), D-101, D-102, D-110, D-236, D-605 … D-607,
D-613, D-614, D-618, D-621, D-802.

**Measure before proposing.** Every number below comes from
`scripts/analysis/T13_grid_check.py` (reproducible, read-only: an in-memory split ledger, no
holdout, no registry or store write), written to `docs/reviews/T13_plan_*.csv`:

| file | content |
|---|---|
| `T13_plan_grid_cells.csv` | 16,224 cells: every cell of every grid (task's and proposed), on the 18 stage-1 passes, real **and** the D-615 reshuffled-returns control, zero-cost and full-cost legs |
| `T13_plan_grid_summary.csv` | per (data, profile, method, grid): cells at the trade minimum, profitable share per leg, median target after costs, a §11 flag |
| `T13_plan_baseline.csv` | per (data, profile, method, grid): the good-region median cell (D-624) against 1,000 matched random entries — percentile and empirical p |
| `T13_plan_mirror.csv` | every rule of the user's script at its own parameters: script long/short against the framework long and mirror short, bar by bar |
| `T13_plan_duplicates.csv` | D-627, measured: identical signal vectors across methods or within a grid |

The whole measurement (16,224 cells × 2 legs + 652 baselines) takes **6.7 minutes in one
process** on this machine.

> **Read with two caveats.** (1) The "real" numbers are **in-sample for stage 1**: these 18
> profiles were selected on the same development bars, so methods resembling the stage-1 probes
> are expected to look good on them. The control is the fair null. (2) **D-335 / D-336 are
> unverified against TradingView (D-802)**; D-336 is the research default and shapes every MR
> run here (an exit at a close may be followed by a re-entry at the same open).

## 1. The headline: the draft gate passes drift (P-107)

T13 §7's gate (median target > 0, ≥ 60 % profitable cells, trade minimum; after costs) has **no
term against the random baseline**. Run on the reshuffled-returns control of the same profiles,
with the plan's final grids:

| gate | 1D real | 1D **control** | 1H real | 1H **control** |
|---|---|---|---|---|
| draft (T13 §7) | 134 / 266 | **43 / 266** (7 of 14 profiles) | 46 / 60 | **11 / 60** (2 of 4) |
| + good-region cell's baseline percentile ≥ 90 | 120 / 266 | 16 / 266 | 46 / 60 | 0 / 60 |
| + percentile ≥ 95 | 104 / 266 | 4 / 266 | 41 / 60 | 0 / 60 |
| **+ BH q ≤ 0.1 over the profile's methods** (D-605's pattern) | **102 / 266** (13 of 14 profiles) | **1 / 266** | **44 / 60** | **0 / 60** |
| + BH q ≤ 0.05 | 81 / 266 | 0 / 266 | 28 / 60 | 0 / 60 |

(method × profile pairs; the diversity rule and the 3–5 cap come after the gate.)

- **The control's passes are drift, not rules**: AAPL long 16 of 19 methods, MSFT 11, ETN 10;
  TSLA 1H 8 of 15 — the highest-drift names; 1 of 7 short profiles is touched. A long MR entry
  held a few bars on a stock that rose earns the drift whatever the entry.
- **A per-method percentile cannot reach zero**: the tested cell is chosen from the top quartile
  of its own grid, so on the control its percentile averages **62–65**, not 50 (1D long 61.9, 1D
  short 64.9; 1H 32.2), and there are 19 methods per profile. Multiple-testing control is what
  closes it — exactly stage 1's D-605.
- **ETN long** (a stage-1 pass) passes the draft gate with 17 methods and **none** under BH: on
  this evidence its daily MR edge is drift.
- One control survivor at q ≤ 0.1: MSFT long `mr_daily_drop`. So the §10 control will likely
  be "1 in 266", not literally zero; P-107 asks how the headline is judged.

## 2. The method library (final, pending P-108 … P-113)

`task` = T13 §4's starting grid kept; `proposed` = replaced, reason measured (§3). Every rule is
the **long** rule; the short is the mirror (D-626) unless §4 says otherwise. Exits are stage 1's
(D-622). Cells per profile: **MR 288** (19 methods), **TF 252** (15 methods + dual momentum,
P-113).

### MR (1D today: 14 profiles)

| method | long rule | grid | cells | source |
|---|---|---|---|---|
| `mr_ibs` | IBS·100 < t on the last k bars | t {15, 20, 30, 40}, k {1, 2, 3} | 12 | #0, stage-1 IBS — **proposed** |
| `mr_rsi` | RSI(n) ≤ t (the script's `<=`) | n {2, 3, 5, 7}, t {15, 20, 30, 35} | 16 | #1, #19, stage-1 RSI probes — **proposed** |
| `mr_rsi_sum` | Σ RSI(n) over m bars < m · level | n {2, 3, 4, 5}, m {2, 3}, level {15, 20, 25, 30} | 32 | #2 = cumulative RSI — **proposed** |
| `mr_connors_rsi` | CRSI(rsi_len, 2, 100) < t | rsi_len {2, 3, 4, 5}, t {15, 20, 25, 30} | 16 | F-2.1 — **proposed** |
| `mr_down_closes` | k consecutive lower closes | k {1, 2, 3, 4} | 4 | #4, stage-1 — task |
| `mr_lower_lows` | k consecutive lower lows | k {1, 2, 3, 4} | 4 | #3 — **proposed** |
| `mr_n_day_low` | close < lowest(basis, n)[1] | n {3, 5, 10, 20}, basis {low, close} | 8 | #5, stage-1 Donchian new low and lowest close, F-2.1 N-day low (P-112) — **proposed** |
| `mr_daily_drop` | close < close[1] − d·\|close[1]\|; optionally ATR(5) > ATR(10) | d {0.5, 1, 2, 3} %, atr_expanding {off, on} | 8 | #6, #7 — task |
| `mr_ma_distance_pct` | close < EMA(n) − p·\|EMA\| | n {5, 10, 20, 50}, p {0.5, 1, 2, 3} % | 16 | #9, F-2.1 — task, split (P-108) |
| `mr_ma_distance_atr` | close + a·ATR(5) < EMA(n) | n {5, 10, 20, 50}, a {0.25, 0.5, 1, 1.5} | 16 | #8, F-2.1 — task, split (P-108) |
| `mr_ema_slope_drop` | EMA(n) < EMA(n)[1] − p·\|EMA[1]\| | n {3, 5, 8, 10}, p {0.25, 0.5, 0.75, 1.0} % | 16 | #10 — **proposed** |
| `mr_ibs_after_new_high` | high > highest(high, n)[1] and IBS·100 < t | n {3, 5, 10, 20}, t {15, 20, 25, 30} | 16 | #14 — **proposed** |
| `mr_macd_hist_falling` | hist fell k bars in a row, hist < 0, close < close[1] | k {2, 3, 4, 5} | 4 | #17 — task |
| `mr_macd_hist_turn` | hist rose k bars in a row, hist < 0 | k {1, 2, 3, 4} | 4 | #20 — task |
| `mr_macd_hist_trough` | hist ≤ lowest(hist, w) | w {3, 5, 7, 10} | 4 | stage-1 probe (**not** equivalent to #20: measured, §5) — task |
| `mr_candle_score` | Σ totalScore over n ≤ n · level; `rising`: and above its previous value | n {2, 3, 4, 5}, level {−2.5, −2, −1.5, −1} per bar, mode {level, rising} | 32 | #18 (script: n 3, T −7 = −2.33 per bar) — **proposed** |
| `mr_williams_confirm` | %R(n) (0..100) < t; `confirm`: P-111 (proposed {off, same_bar}; the plan measured `on` as the task's latch) | n {5, 10, 14, 20}, t {5, 10, 20, 30}, confirm {off, same_bar} | 32 | #22, F-2.1 — task |
| `mr_zscore` | z(close, n) < −t | n {10, 20, 30, 40}, t {1.0, 1.25, 1.5, 2.0} | 16 | stage-1 (replaces `close_below_bb_lower`, D-627) — **proposed** |
| `mr_stochastic_k` | Stoch %K(n, 3) < t | n {5, 9, 14, 21}, t {10, 15, 20, 30} | 16 | F-2.1 (smoothed K, so it is not raw %R) — **proposed** |
| `mr_keltner_lower` | close < Keltner lower (n, mult) | n {10, 20, 30, 40}, mult {0.5, 1.0, 1.5, 2.0} | 16 | F-2.1 — **proposed** |

(`mr_ma_distance` as one method with a unit choice and a level index is 32 cells and is what was
measured; split, the cells are the same.)

### TF (1H today: 4 `unconfirmed` profiles, D-621, D-628)

| method | long rule | grid | cells | source |
|---|---|---|---|---|
| `tf_ma_slope` | SMA(n) slope turns up | n {20, 50, 100, 200} | 4 | stage-1 — task |
| `tf_sma_cross` | SMA(fast) crosses above SMA(slow) | fast {5, 10, 15, 20}, slow {30, 50, 75, 100} | 16 | stage-1 — **proposed** |
| `tf_donchian_breakout` | close > highest(high, n)[1] | n {10, 20, 55, 100} | 4 | stage-1 (20 and 55 merged) — task |
| `tf_bb_upper_cross` | close crosses above BB upper (n, mult) | n {10, 20, 30, 40}, mult {1.0, 1.5, 2.0, 2.5} | 16 | stage-1 — **proposed** |
| `tf_supertrend_flip` | Supertrend turns up | atr {7, 10, 14, 20}, factor {2, 2.5, 3, 3.5} | 16 | stage-1 — task |
| `tf_ichimoku_cloud` | above the cloud and tenkan > kijun | conversion {7, 9, 12, 15}, base {22, 26, 30, 40}, span_b {44, 52, 60, 80} | 64 | stage-1 — task |
| `tf_momentum_cross` | close − close[n] crosses above 0 | n {10, 20, 40, 60} | 4 | stage-1 ROC (difference form, mirror-exact) — task |
| `tf_keltner_breakout` | close crosses above Keltner upper | n {10, 20, 30, 40}, mult {0.75, 1.0, 1.5, 2.0} | 16 | F-2.2 — **proposed** |
| `tf_adx_di` | DI+ crosses above DI− with ADX > t | n {5, 7, 10, 14}, t {10, 15, 20, 25} | 16 | F-2.2 — **proposed** |
| `tf_hma_turn` | HMA(n) turns up | n {9, 16, 25, 49} | 4 | F-2.2 — task |
| `tf_kama_cross` | close crosses above KAMA(n, 2, 30) | n {5, 10, 20, 30} | 4 | F-2.2 — task |
| `tf_psar_flip` | SAR flips below price | step {0.01 … 0.04}, maximum {0.1 … 0.4} | 16 | F-2.2 — task (1 wasted cell, §5) |
| `tf_aroon_cross` | Aroon up crosses above Aroon down | n {10, 14, 25, 50} | 4 | F-2.2 — **proposed** |
| `tf_atr_band` | close > lowest(low, n) + k·ATR(m) | n {5, 10, 20, 40}, k {1.5, 2, 2.5, 3}, m {10, 14, 25, 50} | 64 | #11 — task |
| `tf_base_candle` | the BaseCandle direction flips to long | frac {0.25, 1/3, 0.4, 0.5} (the script has none; 1/3 is its rule) | 4 | #23 — **proposed parameter** |
| `tf_dual_momentum` | P-113 | — | — | F-2.2 |

`#24 BaseCandleSignal` is not a separate method: it fires inside the same state machine as #23,
and a stage-2 method needs one entry rule; it is recorded with the parked items (§6).

## 3. The grids, measured (T13 §11: "all cells fail, or all pass")

Per method, over the profiles of its type, real data / **control** (full table:
`T13_plan_grid_summary.csv`). "min-trades" = share of cells reaching 30 (1D) / 100 (1H) closed
trades; "profitable" = mean share of cells with a positive target after costs.

| method | grid | cells | min-trades | profitable | profitable, **control** | why changed |
|---|---|---|---|---|---|---|
| `mr_zscore` | task | 16 | 50 % | 36 % | 12 % | t 2.5 and 3.0: **98 % / 100 % of cells below 30 trades** |
| | proposed | 16 | 99 % | 63 % | 21 % | |
| `mr_connors_rsi` | task | 16 | **29 %** | 29 % | 16 % | **7 of 14 profiles: every cell below the minimum**; t 5 always below |
| | proposed | 16 | 62 % | 56 % | 33 % | still the sparsest MR method |
| `mr_rsi_sum` | task | 32 | 46 % | 43 % | 13 % | level 5 / 10: 88 % / 71 % below; the script's own cell (n 2, m 2, t 20) at the edge |
| | proposed | 32 | 86 % | 72 % | 20 % | |
| `mr_rsi` | task | 16 | 75 % | 56 % | 20 % | RSI(14) < t: 66 % of cells below |
| | proposed | 16 | 83 % | 62 % | 21 % | |
| `mr_ibs` | task | 12 | 74 % | 47 % | 26 % | t 10: 62 % below |
| | proposed | 12 | 81 % | 52 % | 30 % | |
| `mr_ibs_after_new_high` | task | 16 | 64 % | 29 % | 41 % | n 50: 77 % below; t 10: 66 % below |
| | proposed | 16 | 94 % | 33 % | 35 % | **placement fixed, the rule is weak here: 7 of 14 profiles with no profitable cell** |
| `mr_ema_slope_drop` | task | 16 | 73 % | 47 % | 20 % | p 1.5 %: 64 % below; n 20: 52 % below |
| | proposed | 16 | 93 % | 61 % | 21 % | |
| `mr_candle_score` | task | 32 | 78 % | 54 % | 19 % | n 8: 53 % below; level −3: 48 % below |
| | proposed | 32 | 95 % | 61 % | 27 % | |
| `mr_stochastic_k` | task | 16 | 73 % | 44 % | 17 % | t 5: 84 % below |
| | proposed | 16 | 94 % | 57 % | 22 % | |
| `mr_keltner_lower` | task | 16 | 79 % | 51 % | 19 % | mult 2.5: 54 % below |
| | proposed | 16 | 92 % | 54 % | 20 % | |
| `mr_lower_lows` | task | 4 | 88 % | 61 % | 25 % | k 5: 50 % below |
| | proposed | 4 | 100 % | 61 % | 32 % | |
| `mr_n_day_low` | task | 8 | 100 % | 70 % | 26 % | reaches n 20 = stage-1 Donchian (P-112) |
| | proposed | 8 | 100 % | 70 % | 25 % | |
| `tf_sma_cross` | task | 16 | **27 %** | 27 % | 12 % | slow 150 / 200: 94 % / 100 % below on 1H |
| | proposed | 16 | 83 % | 81 % | 42 % | |
| `tf_aroon_cross` | task | 4 | 75 % | 75 % | 19 % | n 100: 100 % below |
| | proposed | 4 | 100 % | 88 % | 19 % | |
| `tf_bb_upper_cross` | task | 16 | 64 % | 64 % | 16 % | mult 3.0: 100 % below |
| | proposed | 16 | 89 % | 86 % | 23 % | |
| `tf_adx_di` | task | 16 | 61 % | 50 % | 17 % | n 28 / t 30: 75 % below |
| | proposed | 16 | 98 % | 72 % | 19 % | |
| `tf_keltner_breakout` | task | 16 | 88 % | 88 % | 36 % | mult 2.5: 44 % below |
| | proposed | 16 | 98 % | 98 % | 34 % | |

Kept as the task set them (all cells reach the minimum on ≥ 88 % of cells): `mr_down_closes`,
`mr_daily_drop`, `mr_ma_distance`, `mr_macd_hist_*`, `mr_williams_confirm`, and the rest of TF.

**"All pass" (raised, not a grid problem).** On the 4 hourly TF-long profiles every TF grid is
profitable almost everywhere: `tf_ichimoku_cloud` **100 % of 64 cells on all 4**,
`tf_supertrend_flip` 98 %, `tf_keltner_breakout` 98 %. On the control the same grids are 50 %,
16 % and 34 % profitable, and **0 of 60 TF method × profile pairs pass** the proposed gate there.
So on these four trending names every trend entry works on the real series and not on the
permuted one. Whether that is edge or the D-621 caveats (uncleaned hourly layer, residual TF
bias) stage 2 cannot tell; the profiles stay `unconfirmed` and reported apart (D-628).

`mr_macd_hist_turn` (#20) and `mr_ibs_after_new_high` (#14) are placed well and still weak: 7 of
14 profiles have no profitable cell. That is a result, not a placement.

## 4. The mirror rule against the user's script (every difference)

The framework's short is the long rule on `Bars.mirrored()` (`p → −p`, D-626). Counted on the
development bars of the 14 daily and 4 hourly profile symbols (24,613 1D bars, 53,542 1H bars),
at the script's own parameters:

| rule | script short (1D / 1H) | mirror short | bars that differ | verdict |
|---|---|---|---|---|
| #0 IBS (k 1, 2, 3), #3, #4 (k 1 … 4), #5, #8, #14, #17, #19, #20 | — | — | **0** | exact mirror |
| #1 RSI2 | 6,739 / 13,702 | same | 0 short; **1 long bar** (script `<=`, framework `<`) | exact once the stage uses `<=` (§2) |
| **#2 RSI2 sum** | **7,817 / 15,818** | 2,495 / 5,684 | **5,322 / 10,134** | **material**: the script's short is `sum > 140`, the mirror of `< 20` is `> 180`; the script fires **3.1×** as often |
| #6 close·1.01 < close[1], ATR up | 3,338 / 4,039 | 3,354 / 4,083 | 16 / 44 | small: the script's own long and short use different constants (`/1.01` vs `·1.01`); 18 / 42 long bars differ as well |
| #7 close < close[1]·0.99 | 5,941 / 5,723 | same | 0 | exact **with the `\|ref\|` form**; a naive mirror of the literal ratio fires on **19,476 of 24,613** bars |
| #9 close·1.01 < EMA5 | 5,661 / 5,682 | 5,725 / 5,760 | 64 / 78 | small (as #6); naive mirror 20,152 bars |
| #10 EMA5·1.005 < EMA5[1] | 5,725 / 5,759 | 5,751 / 5,794 | 26 / 35 | small (as #6); naive mirror 20,189 bars |
| **#11 ATR band** | **none** (commented out) | 4,416 / 13,471 | all | **material**: the script is long-only; no TF-short profile exists today |
| **#18 candle score ≤ −7** | **21,708 / 45,282** (**88 % / 85 % of all bars**) | 5,487 / 11,756 | **16,221 / 33,526** | **material**: the script's short uses the **same** threshold (`≥ −7`), so it fires almost always; the mirror is `≥ +7` |
| **#18 rising** | **9,023 / 18,518** | 1,271 / 2,769 | 7,760 / 15,831 | **material**, same cause |
| **#22 Williams** | **none** (long only) | 906 / 1,738 | all | **material**; and the long itself is P-111 |
| #23 BaseCandle flip | 1,530 / 2,611 | 1,521 / 2,607 | 9 / 4 | warm-up only: the script starts in the long state, the mirror in the short state |
| #24 BaseCandleSignal | 3,518 / 7,985 | 3,518 / 7,986 | 0 / 1 | as #23 |

**The ratio rules need the `|ref|` form, or the mirror breaks.** `Bars.mirrored` is exact only
for translation-equivariant rules (its docstring says so). `close < close[1]·0.99` mirrored is
`close > close[1]·0.99`, which fires on ~80 % of bars. Written as
`close < close[1] − 0.01·|close[1]|` it is the same rule for positive prices and mirrors exactly
to `close > close[1]·1.01`. Applies to `mr_daily_drop`, `mr_ma_distance_pct`,
`mr_ema_slope_drop`; each gets a test that its mirrored short equals the literal short.

Routed rules (§6), for completeness: #12 and #16 are asymmetric by design (the short fires on
the days the long does not); #13 mirrors exactly; #21 increments long and short on the same
condition (no direction).

## 5. Equivalence (D-627) and other checks

- **No two methods produce the same signals** at any cell of the final grids, on MSFT and K 1D
  and BAC 1H (`T13_plan_duplicates.csv`). `mr_zscore` replaces `close_below_bb_lower` (T12's
  duplicate). `mr_macd_hist_turn` and `mr_macd_hist_trough` are distinct. `mr_stochastic_k`
  uses the smoothed K so it is not `mr_williams_confirm` with `confirm = off` (raw %R).
- **One wasted cell:** `tf_psar_flip` step 0.01 with maximum 0.3 and 0.4 flips identically on
  BAC 1H (the factor never reaches 0.3). Kept; the guard tests across methods, not within.
- **The user's script, read closely** (things the task does not state):
  - `ta.lowest(n)` / `ta.highest(n)` default to **low / high** (#5, #11, #14).
  - **Williams (#22): the trigger is declared without `var`**, so it resets every bar. The
    script's rule is therefore "%R(5) < 20 **and** high > high[1] on the same bar", not "%R < 20,
    then a later bar with a higher high" (P-111).
  - **#7 "Small ATR" has its ATR condition commented out**: it is the plain 1 % drop.
  - The script's exits are not the stage's: its default exit is `close > high[1]` (as D-101)
    **plus an always-on "first close above the entry price" exit** (lines 280-283) and a
    50-bar cap, with no 3-ATR stop. Stage 2 measures its entries under stage 1's exits (D-622);
    the user's own backtests of these rules used different exits, so numbers will not match.

## 6. Parked items (T13 §4.4), with destination

| item | script | destination |
|---|---|---|
| exits: N closes above the previous high, TP %, stop %, trailing %, N bars, candle-score exit, first profitable close (always on in the script) | inputs, lines 280-283, 483-537 | stage 4 exit library |
| filters: EMA direction and its opposite, SPY direction (now possible through T04m's aux join), normalised-volatility regime (min, max, rising, falling), Casey direction value | lines 44-50, 84-101, 430-443, 459-475 | stage 5 |
| calendar: #12 Monday, #16 IBS Mon–Tue, #21 hourly seasonality | | stage 1-S / stage-5 calendar filters (addendum forbidden families) |
| #13 narrow range | | VS edge type (P1) |
| #15 One Day | | not now |
| #24 BaseCandleSignal as its own entry | | with #23, revisited if the TF library grows |
| MinStrategyNum voting | line 55 | multi-strategy / portfolio |

## 7. Cost, projected

Final grids: MR 288 cells × 14 profiles + TF 252 × 4 = **5,040 cells**, two legs each; one
baseline (1,000 draws) per method × profile = 330. Measured single-process rates give about
**20 s for the cells and 3 min for the baselines**, the same again for the control — minutes, not
hours, before registry writes (≈ 5,040 trial rows per run). No executor tuning is needed (P-104
stays with T15).
