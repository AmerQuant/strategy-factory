# T14 — plan: measurements, the §10 questions, the design

Stream A's plan for `docs/tasks/T14_stage3_entry_optimisation.md` (D-403). The task file is the
supervisor's and is not edited. Decisions: **D-639 … D-645** (recorded from T14 §2), D-120,
D-130, D-160, D-305, D-354, D-607, D-610, D-615, D-616, D-621 … D-625, D-628, D-636, D-637, D-802,
D-805. Open questions: **P-116 … P-121** (`docs/decisions/pending.md`).

**Measure before proposing.** Every number below comes from two read-only scripts (an in-memory
split ledger, no holdout, no registry or store write):

| script | what it does |
|---|---|
| `scripts/analysis/T14_plan_measure.py run` | builds each candidate's fine grid (D-639, D-640), runs every cell on the whole development window and on each half (D-641), zero cost and full cost, on the real bars and on the D-615 reshuffled-returns control: **11,034 cells × 3 segments × 2 legs × 2 datasets = 132,408 runs in 1 min 42 s** on 8 worker processes |
| `scripts/analysis/T14_plan_analyse.py` | replays T14 §4's rules on those cells under every failed-cell treatment and both per-half minima |

| file | content |
|---|---|
| `docs/reviews/T14_plan_grids.csv` | per candidate: the fine grid (axes, ranges, sizes under both readings of §6 (b), the step multiplier above 2000) |
| `docs/reviews/T14_plan_variants.csv` | per candidate × dataset × treatment × per-half minimum: failed cells per half, the selected cell, stability ratio, plateau area, half 2 at the selected cell, SPP, the zero-cost shift, the gate |
| `<artifacts>/_analysis/T14_plan/cells.parquet` | the 132,408 runs (not committed) |

> **Read with two caveats.** (1) The real numbers are **in-sample**: these 31 methods were
> selected on the same development bars by stages 1 and 2. The control is the fair null
> (D-644). (2) **D-335 / D-336 are unverified against TradingView (D-802)**; D-336 is the
> research default and shapes every MR run here.

## 1. The headline: the control, and what decides it

Under the plan's proposals (failed cells as min(worst, 0), P-116; the full trade minimum in each
half, P-117):

| | real | **control** |
|---|---|---|
| candidates | 31 (25 1D, 6 1H) | 31 (the same, reshuffled returns) |
| **pass the gate** | **9** | **0** |
| `spp_median_target > 0` | 31 | 7 |
| `stability_ratio ≥ 0.8` | ~~24~~ **21** | ~~22~~ **9** (erratum below) |
| `plateau_area ≥ 0.10` | 14 | 6 |
| `selected_in_both_halves` | 20 | 6 |

- **The control passes nothing, but only because of the per-half minimum.** With half the
  minimum in each half (15 on 1D, 50 on 1H), **one control candidate passes under every
  failed-cell treatment**: MSFT long `mr_ibs_after_new_high`, stability 0.92, plateau area 0.107,
  half 2 positive, SPP median 0.52 — a long MR rule on a drifting stock, exactly D-644's worry.
  Under D-644 that would stop the stage. This is the main evidence for P-117.
- ~~**The stability ratio does not discriminate**: 22 of 31 control candidates meet it (24 of 31
  real).~~ **Erratum (T14 review §3, P-122):** these two counts were wrong. The analysis counted
  with polars, which orders NaN above every number, so a NaN stability ratio (a selected cell at a
  loss, D-650 (e)) counted as meeting 0.8. **The correct counts are 21 of 31 real and 9 of 31
  control**; the stage's full runs give the same. Every pass count in this plan was computed in
  Python and is unaffected. What survives of the reading: **no candidate fails on stability
  alone** in either dataset, so the threshold decides no verdict; plateau area and the half-2 check
  separate real from control (14 and 20 real against 6 and 6).
- **SPP median > 0 holds for 7 control candidates** — the high-drift longs (AAPL, MSFT, ETN, TMUS
  williams, TSLA ichimoku 1H). On its own it would be a drift detector.
- **All 9 real passes are long**: AAPL `mr_down_closes`, RTX `mr_n_day_low`, SHW
  `mr_connors_rsi`, TMUS `mr_down_closes`, TXN `mr_ema_slope_drop` (1D) and ARKK
  `tf_base_candle`, BAC `tf_keltner_breakout`, TSLA `tf_hma_turn`, TSLA `tf_ichimoku` (1H,
  `unconfirmed`). **No short candidate passes under any variant measured.** Three of the nine
  pass with a plateau of one or two cells (AAPL and TMUS `mr_down_closes`, RTX `mr_n_day_low`) —
  P-118's subject; with its proposal the count is **6 real, 0 control**.

## 2. The fine grids (D-639, D-640) and the small ones (P-118)

Per numeric parameter: the good region's range, one coarse step outward on each side, clipped to
the parameter's `[min, max]`, at its `fine_step` (every integer parameter has `fine_step` 1,
D-640). Choice parameters fixed at the median cell's values.

| grid size | candidates |
|---|---|
| **3 cells** (one integer parameter) | AAPL L `mr_down_closes`, TMUS L `mr_down_closes`, MSFT L / TXN L / K S / TJX S `mr_macd_hist_falling`, TXN L `mr_macd_hist_turn` — **7** |
| 9 | EEM S `mr_n_day_low` |
| 11 – 34 (one parameter) | ARKK `tf_base_candle` 11, RTX `mr_n_day_low` 16, TMUS `mr_n_day_low` 21, ETN `mr_n_day_low` 29, TSLA `tf_hma_turn` 34 |
| 54 – 1,476 (two or three parameters) | the other 15 |
| **above 2,000** | MRNA `tf_ichimoku` **27,300**, TSLA `tf_ichimoku` **18,900** (1H) — P-119 |

**Every candidate whose fine grid is too small for plateau area to mean anything (T14 §10):**
the **eight** grids below 10 cells, where a single cell is already ≥ 10 % of the space, and
ARKK at 11 (one cell = 9 %):

| candidate | cells | plateau area | stability | half 2 at the selected cell (raw) | verdict (P-116/P-117 proposals) |
|---|---|---|---|---|---|
| 1D AAPL long `mr_down_closes` | 3 | 0.33 (1 cell) | 1.90 | +1.56 | **pass** |
| 1D TMUS long `mr_down_closes` | 3 | 0.33 (1 cell) | 2.74 | +0.35 | **pass** |
| 1D MSFT long `mr_macd_hist_falling` | 3 | 1.00 | 1.30 | +2.07 | fail: half-2 stability 0.49 |
| 1D TXN long `mr_macd_hist_falling` | 3 | 0.67 | 0.77 | +0.19 | fail: stability |
| 1D TXN long `mr_macd_hist_turn` | 3 | 0.67 | 1.22 | −0.03 | fail: half 2 |
| 1D K short `mr_macd_hist_falling` | 3 | 0.33 | 1.85 | −0.50 | fail: half 2 |
| 1D TJX short `mr_macd_hist_falling` | 3 | 0 | — | +0.57 | fail: the selected half-1 value is −0.06 (2 of 3 cells failed) |
| 1D EEM short `mr_n_day_low` | 9 | 0.44 | 0.84 | +0.06 | fail: half-2 smoothed −0.03 |
| 1H ARKK long `tf_base_candle` | 11 | 1.00 | 0.95 | +1.14 | pass |

On a 3-cell line, "plateau area ≥ 10 %" is met by the selected cell alone, and the stability
ratio rests on one or two neighbours. Among the nine real passes, **three have a plateau of one
or two cells**: AAPL and TMUS `mr_down_closes` (1 of 3) and RTX `mr_n_day_low` (2 of 16); the
others hold 10 to 622 cells. **P-118** proposes a minimum plateau size in cells (config) next to
the 10 % share. Measured: **a minimum of 3 leaves 6 real passes** (removes all three), **a minimum
of 2 leaves 7** (removes the two 3-cell grids); the control stays at 0 either way. Proposed: **3**
— on a line, the selected value with a neighbour on each side is the smallest thing that can be
called a plateau.

Two readings of "the good region" for a method with a choice parameter (§6 (b)): the good cells
**sharing the fixed choice values** (the slice actually searched; used) or all good cells. They
differ on two candidates: TMUS `mr_williams_confirm` 527 vs 1,000 cells, RTX `mr_candle_score`
55 vs 66.

## 3. §10 question 1 — how a failed cell enters the smoothed mean (P-116)

A cell below the trade minimum (30 on 1D, 100 on 1H) must pull the smoothed surface down. Five
treatments, replayed on the same cells (the full per-half minimum):

| treatment of a failed cell | real passes | control passes | notes |
|---|---|---|---|
| `skip` — left out of the mean (**forbidden by T14 §4**, the reference) | 9 | 0 | |
| `worst` — the surface's lowest valid value | **10** | 0 | admits **TMUS L `mr_n_day_low` with 20 of its 21 half-1 cells failed**: the lone valid cell's failed neighbours inherit a *positive* "worst" value, so it scores stability 1.00 and plateau area 1.00 — exactly the lone-survivor case T14 §4 warns of |
| `zero` — 0 (no edge) | 9 | 0 | |
| **`worst0` — min(worst valid value, 0)** (proposed) | **9** | **0** | identical outcome to `zero` here; never credits a failed cell with more than zero, and never less than the worst measured cell |
| `neginf` — −∞ (any failed neighbour sinks the cell) | 7 | 0 | loses SHW `mr_connors_rsi` and TXN `mr_ema_slope_drop`: every cell next to a failed one gets a smoothed −∞, which cuts their plateaus |

- With the full per-half minimum, **7 of 31** real candidates change their selected cell or their
  verdict between `worst`, `zero`, `worst0` and `neginf`; with half the minimum, **1**.
- **The treatment never changes the control's count** (0 under the full minimum, 1 under half,
  for all five).
- **Proposal (P-116): `worst0`.** `worst` is disqualified by the measured lone-survivor pass;
  `neginf` punishes a plateau for touching the grid's thin corner; `zero` and `worst0` agree
  here, and `worst0` stays conservative when the grid's worst cell is negative.

The same treatment applies to the raw neighbours in the stability ratio. A failed cell is
**never selectable** (the maximum is taken over cells at the minimum).

## 4. §10 question 2 — the trade minimum in each half (P-117)

The whole window keeps the full minimum (SPP, trades). For each half:

| per-half minimum | failed cells, half 1 | failed cells, half 2 | real passes | **control passes** |
|---|---|---|---|---|
| **full** (30 on 1D, 100 on 1H) — proposed | 5,025 of 11,034 (46 %) | 4,779 (43 %) | 9 | **0** |
| half (15 / 50) | 759 (7 %) | 567 (5 %) | 8 | **1** (MSFT L `mr_ibs_after_new_high`) |

What each choice leaves, per candidate (`T14_plan_variants.csv`, `failed_h1`, `failed_h2`):

- **Full**: **MRNA 1H `tf_ichimoku` has no valid cell at all** (all 1,820 cells below 100 trades
  in each half — a 50-bar TF exit on 1H trades rarely) and fails as `no_valid_cell`; heavy
  losses on MSFT `mr_ibs_after_new_high` (282 of 319 failed in half 1), BAC `tf_keltner_breakout`
  (869 of 1,476), ARKK `tf_sma_cross` (390 of 770), MSFT `mr_zscore` (398 of 936), TMUS
  `mr_n_day_low` (20 of 21).
- **Half**: every candidate keeps a valid region; the only full-grid loss disappears; the
  composition of the passes changes (MSFT `mr_ibs_after_new_high`, RTX `mr_candle_score`, TMUS
  `mr_n_day_low` in; AAPL `mr_down_closes`, BAC, SHW, TXN `mr_ema_slope_drop` out).
- **Proposal (P-117): the full minimum in each half.** A half's result is judged on its own (the
  half-2 check is the only out-of-sample test before stage 6, D-641), so it needs the same number
  of trades as any other result the gates judge. The half-strength rule lets the control through
  (D-644) and is looser exactly where drift acts. The cost is stated: MRNA ichimoku cannot be
  optimised on 1H at all.

## 5. Above 2,000 cells: Sobol has no neighbours (P-119)

D-120 and D-639 say "Sobol sampling only above 2000". Smoothing, the stability ratio and the
plateau (F-3.3, F-3.4) are defined on **lattice neighbours at ±1 step**; 2,000 Sobol points in an
18,900-cell box have almost none. Two candidates are affected, both 1H ichimoku (unconfirmed).

**Proposal (P-119):** above the cap, **coarsen the lattice** — multiply the step of the axis with
the most values by 2, 3, … until the grid fits — so every rule of §4 keeps its meaning. Measured:
MRNA 27,300 → 1,820 cells (`base` step ×3, `span_b` ×5), TSLA 18,900 → 1,540 (`base` ×3, `span_b`
×4); TSLA ichimoku passes on its coarsened lattice (plateau 0.40, stability 0.94, half 2 +1.81).
Sobol would also need a new dependency (`scipy`) or an in-house generator. The step multipliers
are recorded in the artifact. This amends D-639's last clause, so it is the supervisor's.

## 6. Definitions T14 leaves open, as implemented in the measurement (P-120)

(a) **"One coarse step of margin"** = the neighbouring coarse value; beyond the first or last
coarse value, the adjacent coarse interval; then clipped to `[min, max]`; values on
`min + i · fine_step`. (b) **Good-region bounds** from the good cells that share the fixed choice
values (§2). (c) **Halves** (D-641): `mid = n // 2` of the development bars; each half is
simulated on its own bars, with its signals and ATR computed on the bars **up to the half's end**
— half 2's indicators are warmed up by half 1's history (earlier data, not look-ahead), half 1
never reads half 2, and no trade crosses the boundary. (d) **Selection**: the maximum of the
smoothed half-1 after-cost surface among cells at the minimum; ties by the canonical JSON of the
parameters (D-636 (g)). (e) **Stability ratio**: the mean of the selected cell's existing raw
neighbours (failed ones as P-116) over its raw value; **fails when the raw value is ≤ 0** (a
ratio against a loss has no meaning). (f) **Plateau**: cells whose **smoothed** value is ≥ 0.8 ×
the selected cell's smoothed value, connected through the same ±1-step neighbourhood (diagonals
included), containing the selected cell; its share of all cells; 0 when the selected smoothed
value is ≤ 0. The 0.8 is read from the gate's `stability_ratio` threshold, not restated.
(g) **Half-2 acceptance** at the selected cell: valid in half 2, smoothed half-2 value > 0, half-2
stability ratio ≥ 0.8. (h) **An infinite target** (no drawdown: 76 real runs, 70 of them in half 2, and 50 control runs,
of 132,408) is replaced, for smoothing, by the surface's
largest finite value, and counted in the artifact. (i) **SPP** over the whole window after costs,
every cell counted; failed cells ranked below every valid one (D-636 (a)); nearest-rank
percentiles 5 / 50 / 95; the median of the valid cells alone is also reported. (j) **Edge slope**
(reported, not gated): the mean, over the plateau's boundary cells, of (the cell's smoothed value −
the mean smoothed value of its neighbours outside the plateau), divided by the selected cell's
smoothed value; 0 when the plateau fills the grid. (k) **The zero-cost plateau** (D-642) is
selected by the same rules on the zero-cost half-1 surface; its shift is the largest per-axis
step distance. Measured: 22 of 30 unchanged, 2 by one step, 4 by two, 1 by five, 1 by eleven.

## 7. Plumbing assumptions (P-121)

(a) **Input**: the stage-2 run named in `stage_inputs.s02_screen`; candidates = its `selected`
methods; a stage-2 **control** run is refused as input (T13's pattern). (b) **The control**
(D-644): the same real stage-2 selections and the same fine grids, on bars reshuffled with T12's
key (`unit_seed(seed, "<symbol>|<timeframe>|random_walk")`); stage 2's own control selected
nothing, so "the same candidates" can only mean this. (c) **Candidate id**: sha256 of (stage
`s03_entry`, parent = the stage-2 candidate id, control, stage-config hash), D-805's pattern;
`status` active when the gate passes. (d) **Trials** (D-160): one row per cell per segment (whole,
half 1, half 2), both legs in the row — **33,102** real and 33,102 control rows. (e) **Overlap
after optimisation** (D-643): per profile, D-637's overlap between every pair of its stage-3
candidates' selected cells (whole window, after costs), recorded in each artifact with the
partner's verdict; not gated. (f) **Trades** stored for the selected cell's whole-window after-cost
run of passing candidates only. (g) **Exits** read from `s01_edge.yaml`, as stage 2 (D-622).

## 8. Design

| module | content |
|---|---|
| `configs/stages/s03_entry.yaml`, `stages/optimize_config.py` | margin (coarse steps, 1), the cap (2,000, D-120), the coarsening rule (P-119), the failed-cell treatment (P-116), the per-half minimum rule (P-117), the minimum plateau cells (P-118), SPP percentiles, `unconfirmed_timeframes`, `batch_units` (operational, out of the hash as in T13 N2); the exits read from `s01_edge.yaml` |
| `metrics/plateau.py` | the lattice, smoothing, selection, stability ratio, connected plateau and its extent per parameter, edge slope — pure NumPy on arrays (F-3.3, F-3.4) |
| `robustness/spp.py` | the SPP distribution (F-3.5) |
| `stages/optimize.py` (`s03_entry`) | one executor unit per candidate (pure, like `compute_method`): the fine grid, every cell on the three segments and both legs, the surfaces, the verdict inputs; the parent: gate, overlaps per profile, registry, artifacts, index |
| `stages/optimize_artifact.py` | `EntryOptimisation` schema v1, T14 §6 (surfaces as data) |
| `stages/screen.py` | `method_run` gains an optional segment (signals on bars up to the end, simulation on the segment) — **the same function the leakage test calls**, as in T13 |
| `pipeline/stage_run.py`, `cli.py`, `configs/pipeline/s03_*.yaml` | `sfac run` dispatches `s03_entry`; the full run, the control, the pilot per timeframe |

Gate metrics are already registered (`metrics/names.py`); the stage adds `plateau_cells` only if
P-118 is accepted. **No engine change; no new dependency** (P-119 avoids `scipy`).

## 9. Tests (T14 §7)

| criterion | test |
|---|---|
| F-3.3 | synthetic surface with a sharp peak and a broad plateau: the plateau's centre is chosen, not the peak (2-D and 3-D) |
| F-3.4 | hand-built surfaces: stability ratio (edges, 1-D and 3-D neighbour counts), plateau area with **two disjoint islands** (only the selected one counts), edge slope; the failed-cell treatment (the lone-survivor surface of §3 must fail) |
| F-3.5 | SPP median, p5, p95 against a hand-computed distribution, failed cells included |
| F-3.6 / D-641 | a parameter good on half 1 and bad on half 2 fails `selected_in_both_halves`; good on both passes |
| D-639 / D-640 | bounds from a known good region with margin and clipping (both ends, non-uniform coarse values); choice parameters fixed; integer resolution; the above-cap path (P-119) deterministic |
| D-642 wiring | the plateau is selected on the after-cost surface (fails if it reads the zero-cost one; mutation-checked) |
| F-3.7 | each criterion failed in turn, named, thresholds from the gate YAML |
| rule 3 | the halves never read bars beyond the half's end (truncation: the half-1 result is identical with and without half 2 present); every cell of every candidate's grid through the shared `method_run` |
| rule 2 | T12's guard scans `stages/optimize*.py` (no `SplitManager`, no `open_holdout`) |
| D-607 | serial and parallel runs bit-identical |
| D-160 | trial rows = cells × 3 per candidate |
| D-644 | a control run reads the real stage-2 selections; a control stage-2 run is refused as input |

## 10. Pilot, cost, stops

- **Pilot**: 1D MSFT long (three candidates, one a 3-cell grid) and TXN long (three), 1H BAC long;
  run twice, identical; timings. **Stop with the pilot's numbers** (T14 §8).
- **Projected cost**: the measurement ran the full scope and its control in **1 min 42 s**; the
  stage adds registry and artifact writes (T13's full run and control took about 3 minutes).
- **Full run, then the control.** If **any** control candidate passes, **stop and raise it**
  (D-644).
- **Review**, then **stop for "Approved"**.
