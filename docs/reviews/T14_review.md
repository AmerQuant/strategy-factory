# T14 — Stage 3: entry optimisation (s03_entry) — review

Branch `a/T14-entry-optimisation`, stacked on `a/T14-plan` (task file, plan, decisions). Features
F-3.1, F-3.3 … F-3.7 (F-3.2 is P1); decisions **D-639 … D-651**. Plan `docs/tasks/T14_plan.md`;
pilot `docs/reviews/T14_pilot.md`. **Stopped for "Approved".**

> **Open parity gap (D-802).** D-335 and D-336 are unverified against TradingView (T11b is
> parked). **D-336 is the research default and shaped every MR run here**: an exit scheduled at
> a close may be followed by a re-entry at the same open. If T11b later shows an engine
> difference, these results may need re-running; every run records its `code_version`.

## 1. The headline: the control (D-644)

Stage 3 on **the same 31 stage-2 selections and the same fine grids**, on each symbol's returns
reshuffled (D-615, T12's seeds; D-651 (b)):

| | 1D control | 1H control |
|---|---|---|
| run id | `66c31bde…` | `d9de3267…` |
| candidates | 25 | 6 |
| **pass the gate** | **0** | **0** |
| `spp_median_target > 0` | 6 | 1 |
| `stability_ratio ≥ 0.8` | 8 | 1 |
| `plateau_area ≥ 0.10` | 5 | 1 |
| `plateau_cells ≥ 3` | 6 | 2 |
| `selected_in_both_halves` | 4 | 2 |

**No control candidate passes; D-644's stop is not triggered.** The two nearest misses are both
drift longs, and each is stopped by **plateau area alone**: 1D MSFT long `mr_ibs_after_new_high`
(21 cells, 0.066; stability 0.93, half 2 positive, SPP median 0.52) and 1D TMUS long
`mr_williams_confirm` (15 cells, 0.028). The plan predicted the MSFT one: with half the trade
minimum in each half it passes (D-647).

## 2. The full run

| | 1D | 1H (all `unconfirmed`, D-645) |
|---|---|---|
| run id | `e1c1d243…` | `c28bfb47…` |
| candidates (stage-2 selections) | 25 | 6 |
| fine-grid cells | 5,383 | 5,651 (2 grids coarsened, D-649) |
| trials (cells × 3 segments, D-160) | 16,149 | 16,953 |
| **pass the gate** | **2** | **4** |
| small grids (< 10 cells, D-648) | 8 | 0 |
| wall time | 15 s | 34 s |

- The runs were made on the **committed tree** (`code_version` `0f9cd10…`, clean), after the
  acceptance review's fixes (§12). The first full runs on `75eefa0…` (`768685ea…`, `b1021722…`,
  controls `86f27fb0…`, `9c98bad1…`) gave **identical artifacts** apart from the one intended
  change: three control overlaps against a candidate without a selection are now `null`, not
  0.0. The pilot showed that a run reproduces byte for byte (pilot §1). Every artifact records
  its config hash, stage-config hash and code version; the registry run records the seed (42).
- **6 of 31 pass — the count the plan predicted** under D-646 … D-648.
- Gate rows: 5 per candidate. Candidate ids carry no run id (D-651 (c)), so a candidate row keeps
  the run that first wrote it: the pilot's 9 and the first full runs' 22 (real) and 31 (control),
  as T13 §8 item 11 described. Trial and gate rows always carry the run that made them. Whether
  gate values that shape the surfaces belong in the id is **P-123** (§9).
- The four run indexes are copied to `docs/reviews/T14_index_{1D,1H,1D_control,1H_control}.csv`;
  the tables below come from `scripts/analysis/T14_review_tables.py`.

## 3. D-651's two findings — and a correction to the first

**(1) The stability ratio decides no verdict — but the plan's number for it was wrong.**

The plan said, and D-651 (1) records, that "22 of 31 control candidates meet" the stability
ratio. **That number was my error.** The plan's analysis counted with polars, which orders NaN
above every number, so `NaN >= 0.8` was true and every NaN stability ratio — a selected cell at a
loss (D-650 (e)) — counted as meeting the threshold. The correct counts:

| `stability_ratio ≥ 0.8` | real | control |
|---|---|---|
| the plan, as printed | 24 of 31 | 22 of 31 |
| **the plan, corrected** | **21 of 31** | **9 of 31** |
| **the full runs** | **21 of 31** | **9 of 31** |

Every pass count of the plan was computed in Python and is unaffected; the script is fixed
(`T14_plan_analyse.py`), and the plan carries an erratum. **P-122** asks the supervisor to amend
D-651 (1).

What holds after the correction:

- **The stability threshold decides no verdict.** In the full runs **no candidate, real or control,
  fails on stability alone** (0 of 31 and 0 of 31): whenever it fails, plateau area, plateau cells
  or the half-2 check fail too. Removing the criterion would change no pass.
- **The half-2 check separates real from control the most** (20 real against 6 control, 3.3×).
  Stability (21 against 9) and plateau area (14 against 6) separate about equally (both 2.3×);
  but only plateau area, plateau cells and the half-2 check ever decide a verdict, so stability
  adds nothing at the margin. **On T15's calibration list: the stability threshold may be
  redundant** — for the corrected reason, not for the one first given.

**(2) No short candidate passes, and four of the six passes are the unconfirmed 1H TF
candidates.**

- **All 10 short candidates fail** (ADI, EEM, GNRC, K ×2, LEN, TJX ×2, TXN ×2 — every 1D short
  profile): 9 on the plateau (area or cells), 4 on half 2 (a candidate can fail both); none has
  a plateau that passes and holds in half 2.
- **The six passes:** 1D **SHW** long `mr_connors_rsi` and **TXN** long `mr_ema_slope_drop`; 1H
  **ARKK** `tf_base_candle`, **BAC** `tf_keltner_breakout`, **TSLA** `tf_hma_turn` and **TSLA**
  `tf_ichimoku` — the last four `unconfirmed` (D-621, D-628, D-645): stage 3 cannot separate a
  trend edge on 1H from the uncleaned hourly layer and the residual TF bias, and they never stand
  in for the daily MR finding.
- So the daily mean-reversion finding of stages 1 and 2 reaches stage 4 as **two long
  candidates** (SHW, TXN): `mr_connors_rsi` from the spec's library and `mr_ema_slope_drop`, the
  user's rule #10 — one of the 25 daily selections, 22 of which were the user's rules in T13.

## 4. A boundary pass, and why D-642 selects after costs

**1D TXN long `mr_ema_slope_drop` passes at exactly the threshold**: its plateau is **18 of 180
cells = 0.100**, against `plateau_area >= 0.10`. One cell fewer and it would fail. It is reported
as a **boundary pass**.

It is also the clearest case for D-642. On half 1:

| cell | trades (whole / h1 / h2) | target zero cost → after costs (h1) | smoothed h1, after costs |
|---|---|---|---|
| **after-cost plateau** n 6, p 0.70 (selected) | 100 / 38 / 62 | 1.87 → 1.28 | **1.27** |
| **zero-cost plateau** n 2, p 0.15 | 333 / 153 / 180 | 2.64 → 1.45 | 1.25 |
| stage 2's median cell n 8, p 0.5 | 116 / 44 / 72 | 2.01 → 1.46 | 1.07 |

On the zero-cost surface the best plateau is **n 2, p 0.15, 11 steps away**: a shallow trigger
that trades **3.3 times as often** and looks best before costs (smoothed zero-cost 2.30 on half
1). After costs it keeps **55 %** of its whole-window target (2.29 → 1.25), while the selected
cell keeps **68 %** (1.86 → 1.27). Selecting on the zero-cost surface would have chosen a
parameter that pays 3.3 times the costs for its apparent advantage. On the after-cost surface
that advantage is gone: its smoothed half-1 value (1.25) is below the selected cell's (1.27) — a
small margin, and the choice is the best **smoothed** cell, not the best raw one (the zero-cost
cell's raw half-1 value after costs is 1.45, stage 2's median cell's 1.46, the selected cell's
1.28; the selected cell's neighbourhood is what holds). That is D-642's point: the plateau is
chosen where it survives costs, and costs move it. Costs moved 7 other plateaus (TSLA `tf_ichimoku` 5 steps; BAC,
ARKK `tf_sma_cross`, TXN `mr_macd_hist_falling` and `_turn` 2 each; ADI and TJX `mr_rsi_sum` 1
each) and left 22 in place (MRNA has no plateau).

## 5. Per candidate

`plateau` = cells / area; `h2` = the selected cell's raw half-2 target and whether it is in half
2's acceptance region; SPP = median [p5, p95] after costs over every cell, failed cells ranked
lowest (`—` = a failed cell); `shift` = steps to the zero-cost plateau. Control: which criteria
it fails.

**1D, long**

| candidate | grid | selected (stage 2) | plateau | stability | h2 | SPP | shift | verdict | control fails |
|---|---|---|---|---|---|---|---|---|---|
| AAPL `mr_down_closes` | 3 | k 2 (3) | 1 / 0.33 | 1.90 | 1.56 ✓ | 1.24 [0.38, 1.50] | 0 | fail: cells | stab, cells |
| AAPL `mr_ibs_after_new_high` | 676 | n 14, t 32 (20, 25) | 31 / 0.046 | 0.97 | 4.97 ✓ | 2.54 [1.24, 3.42] | 0 | fail: area | area, h2 |
| ETN `mr_n_day_low` | 29 | n 2 (20) | 2 / 0.069 | 0.56 | 2.14 ✗ | 0.80 [0.44, 1.05] | 0 | fail: stab, area, cells, h2 | area, cells, h2 |
| MSFT `mr_ibs_after_new_high` | 319 | n 4, t 18 (10, 15) | 15 / 0.047 | 1.36 | 1.12 ✓ | 1.38 [—, 2.35] | 0 | fail: area | **area only** |
| MSFT `mr_macd_hist_falling` | 3 | k 1 (2) | 3 / 1.00 | 1.30 | 2.07 ✗ | 1.19 [0.57, 1.63] | 0 | fail: h2 (stability 0.49) | stab, cells, h2 |
| MSFT `mr_zscore` | 936 | n 28, t 0.75 (20, 1.0) | 91 / 0.097 | 1.04 | 0.84 ✓ | 1.38 [0.22, 2.01] | 0 | fail: area (0.097) | spp, area, h2 |
| RTX `mr_candle_score` | 55 | −2.25, n 1 (−1.5, 2) | 4 / 0.073 | 1.85 | 0.17 ✗ | 0.24 [—, 1.51] | 0 | fail: area, h2 | spp, area, cells, h2 |
| RTX `mr_n_day_low` | 16 | n 17 (10) | 2 / 0.125 | 0.93 | 0.25 ✓ | 0.47 [0.39, 0.51] | 0 | fail: cells (D-648) | all five |
| **SHW `mr_connors_rsi`** | 78 | rsi_len 2, t 17 (2, 30) | 10 / 0.128 | 1.87 | 0.43 ✓ | 0.79 [0.36, 1.34] | 0 | **pass** | spp, h2 |
| TMUS `mr_down_closes` | 3 | k 2 (3) | 1 / 0.33 | 2.74 | 0.35 ✓ | 0.25 [0.22, 0.62] | 0 | fail: cells | all five |
| TMUS `mr_n_day_low` | 21 | n 10 (20) | 1 / 0.048 | 0.00 | 0.95 ✓ | 0.62 [0.34, 0.98] | 0 | fail: stab, area, cells (20 of 21 half-1 cells failed) | no valid cell |
| TMUS `mr_williams_confirm` | 527 | same_bar, n 26, t 40 (20, 20) | 23 / 0.044 | 1.04 | −0.15 ✗ | 0.63 [—, 1.37] | 0 | fail: area, h2 | **area only** |
| **TXN `mr_ema_slope_drop`** | 180 | n 6, p 0.70 (8, 0.5) | 18 / **0.100** | 0.99 | 1.29 ✓ | 1.18 [0.80, 1.63] | **11** | **pass (boundary)** | all five |
| TXN `mr_macd_hist_falling` | 3 | k 4 (3) | 2 / 0.67 | 0.77 | 0.19 ✓ | 0.32 [0.16, 0.46] | 2 | fail: stab, cells | all five |
| TXN `mr_macd_hist_turn` | 3 | k 3 (2) | 2 / 0.67 | 1.22 | −0.03 ✗ | 0.31 [0.03, 0.67] | 2 | fail: cells, h2 | spp, stab, cells, h2 |

**1D, short**

| candidate | grid | selected (stage 2) | plateau | stability | h2 | SPP | shift | verdict | control fails |
|---|---|---|---|---|---|---|---|---|---|
| ADI `mr_rsi_sum` | 240 | 23, m 2, n 6 (20, 3, 3) | 6 / 0.025 | 1.03 | 0.65 ✗ | 0.41 [—, 1.03] | 1 | fail: area, h2 | all five |
| EEM `mr_n_day_low` | 9 | n 10 (5) | 4 / 0.44 | 0.84 | 0.06 ✗ | 0.65 [0.39, 0.94] | 0 | fail: h2 | spp, stab, cells, h2 |
| GNRC `mr_candle_score` | 54 | −1.75, n 6 (−2.5, 4) | 1 / 0.019 | −0.10 | 0.95 ✗ | 0.34 [—, 1.01] | 0 | fail: stab, area, cells, h2 | spp, stab, area, cells |
| K `mr_macd_hist_falling` | 3 | k 4 (5) | 1 / 0.33 | 1.85 | −0.50 ✗ | 0.01 [−0.07, 0.39] | 0 | fail: cells, h2 | all five |
| K `mr_stochastic_k` | 972 | n 5, t 18 (21, 30) | 15 / 0.015 | 0.92 | 0.31 ✓ | 0.35 [—, 0.88] | 0 | fail: area | all five |
| LEN `mr_stochastic_k` | 338 | n 5, t 13 (5, 15) | 5 / 0.015 | 0.65 | 0.85 ✓ | 0.31 [—, 1.17] | 0 | fail: stab, area | spp, area, h2 |
| TJX `mr_macd_hist_falling` | 3 | k 4 (5) | 0 / 0 | — | 0.57 ✓ | 0.46 [0.27, 0.97] | 0 | fail: stab, area, cells | all five |
| TJX `mr_rsi_sum` | 390 | 19, m 2, n 2 (20, 2, 5) | 0 / 0 | −2.13 | 0.90 ✓ | 0.18 [—, 0.98] | 1 | fail: stab, area, cells | all five |
| TXN `mr_ema_slope_drop` | 210 | n 6, p 0.70 (5, 0.75) | 7 / 0.033 | 0.76 | 0.91 ✓ | 0.56 [—, 1.32] | 0 | fail: stab, area | all five |
| TXN `mr_rsi_sum` | 312 | 18, m 2, n 2 (30, 3, 4) | 1 / 0.003 | — | 1.03 ✓ | 0.11 [—, 0.51] | 0 | fail: stab, area, cells | all five |

**1H, long — `unconfirmed`, reported apart (D-645)**

| candidate | grid | selected (stage 2) | plateau | stability | h2 | SPP | shift | verdict | control fails |
|---|---|---|---|---|---|---|---|---|---|
| **ARKK `tf_base_candle`** | 11 | frac 0.47 (0.5) | 11 / 1.00 | 0.95 | 1.14 ✓ | 1.25 [1.11, 1.46] | 0 | **pass** | spp, cells, h2 |
| ARKK `tf_sma_cross` | 770 | fast 2, slow 30 (10, 50) | 39 / 0.051 | 1.29 | 0.24 ✗ | 0.67 [0.37, 1.12] | 2 | fail: area, h2 | spp, stab, area |
| **BAC `tf_keltner_breakout`** | 1,476 | mult 1.0, n 41 (1.5, 30) | 195 / 0.132 | 0.91 | 1.19 ✓ | 1.05 [0.62, 1.51] | 2 | **pass** | spp, stab, area, cells |
| MRNA `tf_ichimoku` | 1,820 of 27,300 | — (no valid cell) | 0 | — | — | 0.61 [0.31, 0.93] | — | fail: no cell reaches 100 trades per half | all five |
| **TSLA `tf_hma_turn`** | 34 | n 32 (25) | 12 / 0.353 | 0.99 | 1.74 ✓ | 1.50 [1.22, 1.91] | 0 | **pass** | all five |
| **TSLA `tf_ichimoku`** | 1,540 of 18,900 | base 39, conv 5, span_b 49 (40, 9, 44) | 622 / 0.404 | 0.94 | 1.81 ✓ | 1.35 [1.09, 1.60] | 5 | **pass** | stab, area, h2 |

Plateau extents (per parameter, lowest–highest value inside the plateau) for the passes: SHW
rsi_len 2–4, t 17–20; TXN n 5–10, p 0.50–0.85; ARKK frac 0.40–0.50; BAC mult 0.75–1.25, n 23–50;
TSLA `tf_hma_turn` n 25–36; TSLA `tf_ichimoku` base 21–48, conversion 5–18, span_b 37–77. Every
pass moved off stage 2's median cell. **What stage 4 receives is the selected cell — the
maximum of the smoothed half-1 surface (D-650 (d)) — not the geometric centre of its plateau**:
on real surfaces it can sit at the plateau's edge (SHW at the lowest corner, rsi_len 2 and t 17;
TSLA `tf_ichimoku` at conversion 5, the edge of 5–18). F-3.3 and T14 §6 say "centre"; the
spec (§3.2) and D-650 (d) say the smoothed maximum, which is what F-3.3's test checks (an
interior plateau cell, not the peak). Every candidate's plateau extent, zero-cost plateau, step
multipliers and overlaps are in `docs/reviews/T14_candidates.csv`.

## 6. The small grids (D-648) and the cost of D-647

- **The eight small grids** — seven of 3 cells (AAPL and TMUS `mr_down_closes`; MSFT, TXN, K and
  TJX `mr_macd_hist_falling`; TXN `mr_macd_hist_turn`) and EEM's 9-cell grid (D-648 says "eight
  grids of 3 cells"; it is seven plus EEM): **stage 3 cannot optimise them, only accept or reject
  their stage-2 parameter.** With a 3-cell minimum a 3-cell grid passes only if all three values
  form the plateau, i.e. if the parameter's neighbourhood holds. **None did**: of the seven, 5
  fail on the plateau's size (1 or 2 cells, D-648), 3 on half 2 (MSFT, K, TXN `_turn`; two fail
  both), and TJX because its selected half-1 cell loses (no plateau); EEM fails on half 2. Without
  D-648, AAPL and TMUS `mr_down_closes` (and RTX `mr_n_day_low`, 2 of 16 cells) would have passed
  on one- or two-cell plateaus.
- **D-649's coarsening:** MRNA 1H `tf_ichimoku` 27,300 → 1,820 cells (conversion ×1, base ×3,
  span_b ×5), TSLA 1H `tf_ichimoku` 18,900 → 1,540 (×1, ×3, ×4).
- **D-647's accepted cost:** MRNA 1H `tf_ichimoku` has **no cell with 100 trades in each half**
  (all 1,820), so it cannot be optimised on 1H and fails. With the full minimum, 46 % of half-1
  cells fail across the scope (plan §4); every failed cell entered the surfaces as min(worst, 0)
  (D-646). TMUS `mr_n_day_low` — the plan's lone-survivor case, 20 of 21 half-1 cells failed —
  fails as D-646 intended (stability 0.00).

## 7. Overlaps after optimisation (D-643 — reported, not gated)

- **TSLA 1H `tf_hma_turn` and `tf_ichimoku` both pass and overlap 0.64** (D-637's definition, at
  their selected cells) — above stage 2's 0.60, reached by optimising each on its own. Choosing
  between them is stage 4's or the portfolio's (D-643).
- ARKK `tf_base_candle` (pass) overlaps `tf_sma_cross` (fail) 0.71; TXN long `mr_ema_slope_drop`'s
  largest overlap is 0.45; SHW and BAC are their profiles' only candidates.
- Among the failures: TJX short's two methods overlap 0.78, TMUS long's `mr_down_closes` /
  `mr_n_day_low` 0.76, K short's 0.72, TXN short's 0.65, MSFT long's `mr_zscore` /
  `mr_macd_hist_falling` 0.62. Per candidate: `docs/reviews/T14_candidates.csv`.

## 8. What was built

| module | content |
|---|---|
| `stages/optimize_grid.py` | the fine grid (D-639, D-640), coarsening above the cap (D-649) |
| `metrics/plateau.py` | failed cells (D-646), smoothing, selection, stability ratio, connected plateau, extent, edge slope, half-2 acceptance (D-641, D-650) |
| `robustness/spp.py` | SPP (F-3.5), failed cells ranked lowest |
| `stages/optimize.py`, `optimize_artifact.py`, `optimize_config.py`, `configs/stages/s03_entry.yaml` | the stage, the `EntryOptimisation` v1 artifact (surfaces as data, axes as an ordered list), the config |
| `stages/screen.py` | `cell_signals` / `segment_run`: `method_run` gains a segment; stage 2's call unchanged |
| `costs/arrays.py` | `CostArrays.segment` (per-bar arrays cut to a half; the whole-window cost model) |
| `configs/gates/default.yaml`, `metrics/names.py` | `plateau_cells >= 3` (D-648), registered |
| `pipeline/stage_run.py`, `cli.py`, `configs/pipeline/s03_*.yaml` | `run_stage3`, `sfac run` dispatches `s03_entry`; full run, control, pilot |
| `scripts/analysis/T14_*` | the plan's measurement and analysis, the pilot comparison, the review tables |

**Nothing in the engine changed. No new dependency** (D-649 avoided `scipy`).

## 9. Deviations and judgement calls

1. **D-648 is a gate criterion** (`plateau_cells >= 3` in the gate YAML), so its verdict is named
   and stored like the others, rather than a stage-config constant.
2. **The trade minimum is read from the `s02_screen` gate** (`min_trades_good_cells`: 30, 1H 100 —
   "as stages 1 and 2", T14 §4), and the plateau cut and half-2 test from the `s03_entry` gate's
   `stability_ratio` (D-650 (f), (g)). Neither is restated in the stage config.
3. **`unconfirmed` is read from the stage-2 artifact** (D-645: carried unchanged), not set by a
   stage-3 timeframe list.
4. **Halves use the whole-window cost arrays, sliced** (`CostArrays.segment`); the plan's script
   rebuilt them per half. Measured identical on TXN, MSFT and BAC (pilot §1). **So the cost model
   is estimated over the whole development window**: for a profile with data-derived spreads
   (`from_data`, `broker_scaled`: hourly medians over the window), half 1's costs use half 2's
   spread data. It is a cost-model estimation window, as in stages 1 and 2, not price data, and it
   has no effect on this evidence (every T14 symbol is a US equity or ETF with the same result
   either way); the leakage tests use flat costs and would not see it.
5. **The plateau is measured on the smoothed surface** with failed cells filled (D-650 (f)), so a
   failed cell can lie inside a plateau; the plateau's cells are flagged in the surface.
6. **A +inf target** (no drawdown) is replaced by the surface's largest finite value before
   smoothing and counted per half in the artifact (D-650 (h)); SPP ranks a +inf target as the best.
7. **Stage-3 candidate ids carry no run id** (D-651 (c), D-805's pattern): the pilot's 9 rows
   keep the pilot's run id (§2).
8. **The half-2 acceptance rule is a pure function** (`metrics.plateau.accepted`) so that F-3.6's
   "good on both / bad on half 2" cases are tested on hand-built surfaces; a stage-level test
   shows a half-2 failure on a series that is mean-reverting in half 1 and trending in half 2, and
   another recomputes every artifact's verdict from its own surface.
9. **The review corrects the plan** (§3, P-122): the stability counts.
10. **`selected_in_both_halves` checks half 2 only** (D-650 (g)): half-1 acceptance is enforced by
    the `stability_ratio` and `plateau_*` criteria. So the index can show
    `selected_in_both_halves = True` for a candidate whose half-1 stability fails (TJX short
    `mr_rsi_sum`, −2.13); read it as "half 2 accepts the selected cell".
11. **An overlap with a candidate that has no selection is `null`** (D-643), not 0.0 — fixed
    after the acceptance review (§12); it changed three control overlaps (TMUS).
12. **Gate values that shape the surfaces are recorded, not hashed** (P-123): the trade minimum
    and the plateau cut change which cells fail and the plateau, but are not in the candidate id
    (D-651 (c)); each artifact records them (`segments.*.min_trades`, the gate lines).
13. **Stage 2 unchanged:** besides T13's tests and the recomputed T13 grid, the acceptance
    reviewer loaded `origin/main`'s `screen.py` beside the branch's: 88 `method_run` cases (5
    methods, both directions, zero and flat costs) identical. No committed test pins the
    pre-refactor code itself.

## 10. How each acceptance criterion is tested

| criterion | proving test(s) |
|---|---|
| F-3.1: caps, fine grid in the good region, every cell in the registry | `test_F_3_1_*` (margin, ends, clipping, float lattice, integer resolution, choices fixed, cap → coarsened deterministically, > 3 free parameters refused); db `test_F_0_7_1_stage3_registry_rows` (trials = cells × 3 per candidate, one row per cell and segment) |
| F-3.3: plateau centre, not the peak | `test_F_3_3_the_plateau_centre_is_chosen_not_the_peak` (2-D), `…_in_3d`; `…the_selection_is_the_smoothed_half1_after_cost_maximum` (every artifact recomputed) |
| F-3.4: stability ratio, plateau area (two islands), edge slope | `test_F_3_4_*` on hand-built surfaces; D-646's lone survivor `…d646_the_lone_survivor_does_not_pass` |
| F-3.5: SPP median, p5, p95 | `test_F_3_5_spp_on_a_hand_computed_distribution`, failed cells ranked lowest |
| F-3.6 / D-641: good on half 1, bad on half 2 fails; good on both passes | `test_F_3_6_half2_acceptance_on_hand_built_surfaces`, `…a_parameter_good_on_half_1_and_bad_on_half_2_fails` (stage level), `…the_stage_applies_the_half2_rule` |
| F-3.7: gate by name, thresholds from config; artifact content | `test_F_3_7_each_criterion_fails_by_name_from_the_config` (5, incl. `plateau_cells`), `…the_artifact_reports_centre_extent_and_spp`, `…gate_values_are_the_artifacts_numbers`, `…the_surface_is_laid_out_in_the_declared_axis_order` |
| D-642 wiring | `test_F_3_7_d642_the_plateau_is_selected_after_costs` (mutation: selecting on the zero-cost surface fails it) |
| D-647: the full minimum in each half; config values reach the stage | `test_F_3_7_d647_the_full_trade_minimum_applies_in_each_half`, `…config_values_reach_the_stage` (half rule, margin, SPP percentiles changed in the YAML change the artifacts) |
| rule 3: halves never read beyond their end | `tests/leakage/test_F_3_6_half_truncation.py`: half 1 unchanged when half 2 is **replaced**, truncation of half 2 / whole, signals up to `end` = the full prefix (mutation: half 1 reading half 2 fails 9 tests) |
| rule 2: holdout | T12's guard scans `stages/*.py`; `test_F_1_8_d616_the_guard_scans_every_stage_module` names the stage-3 modules |
| D-607: serial = parallel | `test_F_3_7_d607_serial_and_parallel_runs_are_bit_identical`; the pilot's reruns |
| D-644 / D-651 (b): the control | `…d651_the_control_reruns_the_real_selections_on_reshuffled_bars`, `…a_control_stage2_run_is_refused_as_input` |
| D-622, D-645, D-651 (c), rule 8 | `…d622_the_exits_are_stage_1s…`, `…d645_unconfirmed_is_carried_from_stage_2`, `…d651_candidate_id_carries_…`, `…operational_settings_change_no_id` |
| inputs, `sfac run` | `…stage_inputs_expand_to_the_stage2_selections`, `…sfac_run_dispatches_s03`, `…run_stage3_refusals` |
| stage 2 unchanged | T13's stage tests pass; a T13 grid recomputes to its artifact exactly; `test_F_3_6_method_run_whole_equals_the_unsegmented_run` |

## 11. Decisions used or made

- **Used:** D-004, D-120 (as amended), D-130, D-160, D-306, D-334, D-354, D-607, D-610, D-615,
  D-616, D-621 … D-625, D-628, D-636, D-637, D-802, D-805.
- **Made, supervisor range:** D-639 … D-645 (T14 §2), **D-646 … D-651** (the plan's answers;
  D-649 amends D-120).
- **Stream A:** **P-122 open** — the correction of D-651 (1) (§3); **P-123 open** — the gate
  values that shape the surfaces are not in the candidate id (§9 item 12).

## 12. The acceptance review, and what changed

The `acceptance-reviewer` subagent checked the task claim by claim. **Nothing blocking.** It
recomputed every candidate of the four full runs from the stored surfaces with its own
implementation (fill, smooth, select, stability, plateau, half-2 rule, SPP, shift, gate): **0
mismatches in 62 artifacts**; every table and count in §1–§7 matched the artifacts and the
registry; all 54 fine-grid axes matched D-639 / D-650 (a), (b) recomputed from the T13 artifacts.
Its findings and what changed:

| # | finding | what changed |
|---|---|---|
| 1 | §3 ranked plateau area above stability; by difference stability separates more, by ratio equally | §3 reworded (both 2.3×; only the half-2 check separates more); P-122 reworded |
| 2 | §4 "chooses the one that is actually traded best" overclaims: the selection is the best **smoothed** cell; raw, other cells score higher | §4 reworded with the raw numbers |
| 3 | D-647's per-half minimum had no test | `test_F_3_7_d647_…`, `…config_values_reach_the_stage` |
| 4 | the trade minimum and the plateau cut shape the surfaces but are not in the id or the stage-config hash | raised as **P-123** (recorded in every artifact; the id follows D-651 (c)) |
| 5 | "the plateau centre is what stage 4 receives": it is the smoothed maximum, which can sit at the plateau's edge | §5 reworded; F-3.3's "centre" vs D-650 (d) stated |
| 6 | extents, zero-cost cells, multipliers and overlaps not given per candidate | `docs/reviews/T14_candidates.csv`; multipliers in §6; §7 completed |
| 7 | numeric defaults restating config values (`margin`, `max_cells`, `max_free_params`, SPP percentiles, `failed_cell`) | removed; the tests pass the values or read the shipped config |
| 8 | halves slice the whole-window cost model (data-derived spreads use half 2's data) | declared (§9 item 4) |
| 9 | the db test proved the count, not one row per cell and segment | asserted |
| 10 | "stage 2 unchanged" rests on a one-off script | the reviewer's old-vs-new check recorded (§9 item 13) |
| 11 | `selected_in_both_halves` measures half 2 only | declared (§9 item 10) |
| 12 | an overlap against a candidate with no selection was 0.0 | now `null`; the full scope re-run on the fixed code (§2) |
| 13 | pilot report: overlaps truncated, not rounded; the control runs' notes said "T14 full" | pilot corrected; the re-runs carry their own notes |

## 13. Acceptance

Run on Windows after the reviewer's fixes, on the code of the full runs (`0f9cd10`; the final
commit adds only a `ruff format` line wrap in `metrics/plateau.py`, no behaviour):

| suite | result |
| --- | --- |
| fast (`-m "not slow"`) | **2,532 passed** |
| `tests/parity tests/leakage tests/oracle` | **869 passed** |
| `-m db -rs` | **24 passed, 0 skipped** |
| `-m slow` | **20 passed** |
| ruff, `ruff format --check` (402 files), mypy `src` and `--platform linux`, `sfac streams check` | clean |

Mutation checks (each break applied, its guard fails, the source restored): the plateau selected
on the zero-cost surface (the D-642 wiring test); failed cells as "the grid's worst value" (the
half-2 rule test); half 1 reading half 2 (9 leakage tests). Not caught, and why: a one-bar
look-ahead inside a half (pilot §4) — a component causality defect that T13's per-method
truncation tests cover. The full run and its control take about 1.6 minutes.

## 14. A note on commit `caf74be`

The subject line of `caf74be` (`D-646 ... D-651: the T14 plan's answers`) begins with an invisible
UTF-8 byte-order mark: its message file was written by PowerShell 5.1's `Out-File -Encoding utf8`,
which adds one. Some log views show it as a stray character before "D-646". It is left as it is on
the supervisor's instruction: removing it would rewrite the branch and orphan `56d78b9`, the
`code_version` the pilot runs recorded. Later message files are written as ASCII.
