# T14 pilot — stage 3 (s03_entry)

RUNBOOK_T14 step 7. **Stopped here with the pilot's numbers** (T14 §8). Branch
`a/T14-entry-optimisation` (stacked on `a/T14-plan`), code `56d78b9` (committed, clean).
Decisions D-639 … D-651.

> **Open parity gap (D-802).** D-335 and D-336 are unverified against TradingView (T11b is
> parked). D-336 is the research default and shapes every MR run here.

## 1. Runs, and reproduction

| config | run | candidates | cells | trials | seconds |
|---|---|---|---|---|---|
| `s03_pilot_1d` (MSFT, TXN) | `06180946…` | 8 | 1,966 | 5,898 | 7 |
| `s03_pilot_1d` again | `ac0f0218…` | 8 | 1,966 | 5,898 | 7 |
| `s03_pilot_1h` (BAC, `unconfirmed`) | `4cd17d81…` | 1 | 1,476 | 4,428 | 12 |
| `s03_pilot_1h` again | `841fa84e…` | 1 | 1,476 | 4,428 | 12 |

- **Both pairs are identical**: every `summary.json` (with the run id removed) and the index,
  byte for byte (`scripts/analysis/T14_pilot_compare.py`).
- Trials = cells × 3 segments (D-160), checked in the registry.
- **The pilot reproduces the plan's measurement exactly** on all 9 candidates (the failed-cell and
  per-half rules the supervisor accepted, D-646, D-647): the same selected cell, plateau cells,
  stability ratio and half-2 verdict (`docs/reviews/T14_plan_variants.csv`, `worst0` / `full`).
  The stage slices the whole-window cost arrays per half where the plan's script rebuilt them per
  half; measured on TXN, MSFT and BAC, the two are identical.

## 2. Per candidate

After costs, half 1 (D-642). `plateau` = cells in the connected plateau / area; `h2` = the
selected cell's raw half-2 target; `shift` = steps between the after-cost and the zero-cost
plateau (D-642); `overlap` = the largest D-637 overlap with another of the profile's candidates at
their selected cells (D-643, reported only).

| candidate | grid | selected (stage 2's median cell) | stability | plateau | h2 | both halves | SPP median | shift | overlap | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1D MSFT L `mr_ibs_after_new_high` | 319 | n 4, t 18 (n 10, t 15) | 1.36 | 15 / 0.047 | 1.12 | yes | 1.38 | 0 | 0.30 | fail: plateau area |
| 1D MSFT L `mr_zscore` | 936 | n 28, t 0.75 (n 20, t 1.0) | 1.04 | 91 / 0.097 | 0.84 | yes | 1.38 | 0 | 0.61 | fail: plateau area |
| 1D MSFT L `mr_macd_hist_falling` | **3** | k 1 (k 2) | 1.30 | 3 / 1.00 | 2.07 | **no** (half-2 stability 0.49) | 1.19 | 0 | 0.61 | fail: both halves |
| 1D TXN L `mr_ema_slope_drop` | 180 | n 6, p 0.70 (n 8, p 0.5) | 0.99 | 18 / **0.100** | 1.29 | yes | 1.18 | **11** | 0.45 | **pass** |
| 1D TXN L `mr_macd_hist_falling` | **3** | k 4 (k 3) | 0.77 | **2** / 0.67 | 0.19 | yes | 0.32 | 2 | 0.45 | fail: stability, plateau cells |
| 1D TXN L `mr_macd_hist_turn` | **3** | k 3 (k 2) | 1.22 | **2** / 0.67 | −0.03 | no | 0.31 | 2 | 0.10 | fail: plateau cells, both halves |
| 1D TXN S `mr_ema_slope_drop` | 210 | n 6, p 0.70 (n 5, p 0.75) | 0.76 | 7 / 0.033 | 0.91 | yes | 0.56 | 0 | 0.64 | fail: stability, area |
| 1D TXN S `mr_rsi_sum` | 312 | level 18, m 2, n 2 (level 30, m 3, n 4) | — (selected half-1 value ≤ 0) | 1 / 0.003 | 1.03 | yes | 0.11 | 0 | 0.64 | fail: stability, area, cells |
| 1H BAC L `tf_keltner_breakout` | 1,476 | n 41, mult 1.0 (n 30, mult 1.5) | 0.91 | 195 / 0.13 | 1.19 | yes | 1.05 | 2 | — | **pass** (`unconfirmed`) |

Readings, stated plainly:

- **2 of 9 pass**: TXN long `mr_ema_slope_drop` and BAC 1H `tf_keltner_breakout` — the same two
  the plan measured among these nine.
- **TXN long `mr_ema_slope_drop` passes at the edge**: its plateau is exactly 18 of 180 cells,
  0.100 against the threshold of 0.10. Costs moved its plateau **11 steps** from the zero-cost one
  (D-642's reason for selecting after costs).
- **The 3-cell grids (D-648).** Stage 3 moved all three pilot ones by one step from stage 2's
  median cell (k 2 → 1, 3 → 4, 2 → 3). With a 3-cell minimum, a 3-cell grid passes only if all
  three values form the plateau, so stage 3 can only accept or reject the neighbourhood of stage
  2's parameter — none of the three did (MSFT on half 2, both TXN on the plateau's size).
- **Stability does not decide here either**: 6 of 9 meet 0.8, while plateau area and the half-2
  check remove most (T15 calibration item, D-651 (1)).
- Overlaps after optimisation reach 0.61 (MSFT `mr_zscore` / `mr_macd_hist_falling`) and 0.64
  (TXN short) — above stage 2's 0.60, reported, not gated (D-643).

## 3. Cost and the full-run projection

- 1D: 1,966 cells in 7 s (3 s of it start-up); 1H: 1,476 cells in 12 s (about 6× the bars per cell).
- **Full scope** (the plan's grids: 5,383 cells on 1D, 5,651 on 1H): about **15 s (1D) and 45 s
  (1H) per run**, the same again for each control — **about 2 minutes for all four runs**.
  Registry: about 16,000 (1D) and 17,000 (1H) trial rows per run. Artifacts: the largest summary
  is 1.0 MB (1,476 cells, the surfaces as data); about 4 MB per 1H run.

## 4. What was built, and what changed on the way

- `stages/optimize.py` (`s03_entry`), `optimize_grid.py`, `optimize_config.py` +
  `configs/stages/s03_entry.yaml`, `optimize_artifact.py` (`EntryOptimisation` v1);
  `metrics/plateau.py`; `robustness/spp.py`; `sfac run` dispatches `s03_entry`;
  `configs/pipeline/s03_*.yaml` (full run, control, pilot).
- **`stages/screen.py`: `method_run` gains a segment** (signals and ATR on the bars up to the
  segment's end, simulation on the segment). Stage 2's call is unchanged: a T13 grid (MSFT
  `mr_zscore`, 16 cells × 2 legs) recomputes to the stored artifact exactly, and T13's tests pass.
  `CostArrays.segment` cuts the per-bar cost arrays.
- **D-648 as a gate criterion**: `plateau_cells >= 3` in `configs/gates/default.yaml`, registered
  in `metrics/names.py`.
- **The trade minimum is read from the `s02_screen` gate** (`min_trades_good_cells`, 30 / 1H 100:
  "as stages 1 and 2", T14 §4) and the plateau cut from the `s03_entry` gate's `stability_ratio`
  (D-650 (f)), so neither is restated.
- **`unconfirmed` is read from the stage-2 identity** (D-645: "carried forward unchanged"), not
  from a stage-3 setting.
- **A defect found by a test and fixed:** `summary.json` is written with sorted keys, so a dict of
  axes lost its order (`mr_keltner_lower`'s `n, mult` came back as `mult, n`) and the surface
  would have been read transposed. The axes are now an ordered list, and a test checks the layout.
- **Mutation checks** (each break applied, the guard fails, the source restored):
  - D-642 swapped (the plateau chosen on the zero-cost surface): the wiring test fails.
  - D-646 replaced by "the grid's worst value": the half-2 rule test fails.
  - half 1 reading half 2 (signals once on the whole series with a 20-bar look-ahead): 9 leakage
    tests fail.
  - **Not caught, and why:** a one-bar look-ahead that stays inside a half. It is a causality
    defect of the component, which T13's per-method truncation tests cover; the stage-3 test
    guards the half boundary, and a one-bar roll changed no signal at the boundary bar in the
    tested cells. I strengthened that test instead: half 2's bars are **replaced** by another path
    of the same length, and half 1 must not change.
- Tests: F-3.1 grid (8), F-3.3/F-3.4 surfaces (14, the lone survivor included), F-3.5 (3),
  F-3.6/F-3.7 stage (28), leakage (11), db registry (1), the holdout guard now names the
  stage-3 modules. Fast suite **2,530**, parity/leakage/oracle **869**, db **24 / 0 skipped**,
  ruff, format, mypy (Windows and `--platform linux`), stream guards: green.

## 5. Next, on the word

The full run over all 31 selections (`s03_entry_1d`, `s03_entry_1h`), then the control on the
same selections (`s03_entry_1d_control`, `s03_entry_1h_control`). **If any control candidate
passes, stream A stops and raises it (D-644).** Then the review, the acceptance commands, the
acceptance reviewer, and the stop for "Approved".
