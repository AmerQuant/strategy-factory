# T14 — Stage 3: entry optimisation (s03_entry)

**Stream A (D-611).** Plan first (D-403): draft, stop for "Plan approved", then implement. Stop
before the full run with the pilot's numbers, and stop for the review before merge.
Features: F-3.1 … F-3.7.
Depends on: T13 (the `MethodScreen` artifacts), T12 (stage framework, baseline, control), T08
(engine), T09 (metrics), T10b (executor, registry).

## 1. What stage 3 answers

Stage 2 said **which methods** capture an edge. Stage 3 chooses **the parameters a method is
traded with**, on a fine grid, by the centre of a stable plateau and never by the peak (D-120,
F-3.3). Exits stay fixed (D-622); stage 4 frees them.

## 2. Decisions to record before implementing

Supervisor range, marked *(supervisor)*, each citing this task. Next free supervisor id: D-639.

| ID | Decision |
|---|---|
| D-639 | **The fine grid covers stage 2's good region plus one coarse step of margin on each side**, per numeric parameter, clipped to the parameter's valid range. Re-searching the whole space would repeat the overfitting stage 2 avoided; the margin lets a true plateau that sits just outside the good region be seen. D-120 stands: at most 2000 combinations and 3 free parameters; the full grid, and Sobol sampling only above 2000; no Bayesian search. |
| D-640 | **Choice parameters are fixed at the value of stage 2's good-region median cell**; only numeric parameters enter the fine grid. Smoothing and plateaus have no meaning across categorical values. Integer parameters are gridded at integer resolution, so a method with a small integer range gets a small fine grid; the artifact records the effective grid size and the review reports it. |
| D-641 | **Halves:** the development window is split chronologically into two halves of equal bar count. The plateau is found on **half 1** only. The selected point must also lie in **half 2's acceptance region** (`selected_in_both_halves`), and the selected parameters' half-2 result is reported as the only out-of-sample test before stage 6. A half's acceptance region is the set of cells whose smoothed after-cost target is positive and whose stability ratio meets the gate's threshold. |
| D-642 | **The plateau is selected on the after-cost surface.** Stage 3 chooses the parameters actually traded, and a parameter with more trades pays more cost, which moves the choice. This differs from stage 2's zero-cost ranking (D-623) because the question differs. The zero-cost surface is computed alongside and the review reports how far costs moved the plateau. The target metric is stage 2's: average annual profit ÷ average annual drawdown against initial capital (D-624). |
| D-643 | **Trade overlap between a profile's candidates is re-measured after optimisation (D-637's definition) and reported, not gated.** Optimising two methods separately can drive them onto the same bars; choosing between overlapping candidates belongs to stage 4 or the portfolio stage. |
| D-644 | **The reshuffled-returns control is the headline of the review**, as in stages 1 and 2 (D-615). The stage-3 gate has no comparison with chance, and a smooth, stable plateau can appear on pure drift (a long rule on a rising stock is good at almost any parameter). Run stage 3 on the same candidates with each symbol's returns reshuffled. **If any candidate passes the gate on the control, stop and raise it before stage 4 is built on stage 3.** |
| D-645 | **Every candidate passing the gate continues** (F-3.7). The `unconfirmed` flag (D-621, D-628) is carried forward unchanged. |

## 3. Inputs

- The `MethodScreen` artifacts of the merged T13 runs: 25 selected methods on 1D, 6 on 1H
  (unconfirmed). Read each method's good region, median cell and choice-parameter values from them.
- Development data only (D-306, D-616): no split manager in `RunContext`; the T12 static guard
  covers `stages/*.py`.
- The Moneta cost profile for the after-cost leg; the zero-cost leg alongside (D-642).

## 4. The surface and its metrics

Per candidate, on each half and on the whole development window:

- **Raw surface:** the target metric at every fine-grid cell, after costs (and zero-cost alongside).
- **Smoothing (F-3.3):** the mean over the cell and its neighbours at ±1 step in every numeric
  dimension (up to 26 neighbours in 3-D); at the grid's edge, only the neighbours that exist.
- **Selection (F-3.3):** the maximum of the smoothed surface on half 1 (D-641).
- **Stability ratio (F-3.4):** mean of the selected cell's neighbours ÷ the selected cell's value,
  on the raw surface. Gate ≥ 0.8.
- **Plateau area (F-3.4):** the connected set of cells, containing the selected cell, whose value is
  at least the stability threshold × the selected cell's smoothed value, as a share of all cells.
  Connected, not merely above the threshold: disjoint islands are not one plateau. Gate ≥ 10 %.
- **Edge slope (F-3.4):** the drop across the plateau's boundary; reported.
- **SPP (F-3.5):** the distribution of the after-cost target over all fine-grid cells on the whole
  development window: median, p5, p95. Gate: median > 0.

**Cells below the trade minimum** (30 on 1D, 100 on 1H, as stages 1 and 2) are failed cells, as in
stage 2: they must pull the smoothed surface down, never be skipped, or a lone surviving cell among
failed neighbours would look stable. How a failed cell enters the mean is a plan question (§10).
Whether the minimum applies per half at full or half strength is also a plan question.

## 5. Gate (F-3.7)

`s03_entry`, thresholds already in `configs/gates/default.yaml`: `spp_median_target > 0` (after
costs), `stability_ratio ≥ 0.8`, `plateau_area ≥ 0.10`, `selected_in_both_halves == 1`. Register
any new metric name the stage emits.

## 6. Artifact

`artifacts/<run_id>/s03_entry/<candidate_id>/summary.json` per candidate: identity and parent (the
stage-2 candidate id, D-805's hash scheme), the fixed choice parameters, the fine-grid definition and
effective size, the selected centre, the plateau's extent per parameter, stability ratio, plateau area,
edge slope, SPP (median, p5, p95), both halves' results at the selected point, the zero-cost plateau
and its shift (D-642), the post-optimisation overlaps (D-643), the `unconfirmed` flag, the data
caveats (D-610), and the gate verdict per criterion. The surfaces are written **as data**; T15 draws
them. Every evaluated cell, on every half, is a trial row (D-160). Trades only for the selected point.

## 7. Tests

- **F-3.3:** on a synthetic surface with a sharp peak and a broad plateau, the plateau's centre is
  chosen, not the peak.
- **F-3.4:** stability ratio, plateau area (including a surface with two disjoint islands, where only
  the selected one counts) and edge slope on hand-built surfaces.
- **F-3.5:** SPP median, p5, p95 against a hand-computed distribution.
- **F-3.6 / D-641:** a synthetic parameter good on half 1 and bad on half 2 fails
  `selected_in_both_halves`; one good on both passes.
- **D-639 / D-640:** the fine grid's bounds from a known good region with margin and clipping; choice
  parameters fixed; the Sobol path above 2000 is deterministic by seed.
- **D-642 wiring:** the plateau is selected on the after-cost surface (a test that fails if it reads the
  zero-cost surface).
- **F-3.7:** each criterion failed in turn is named, thresholds from config.
- **Leakage (rule 3):** the halves are computed without reading bars beyond each half's end.
- **Holdout:** the stage cannot reach `open_holdout`.
- **Reproducibility:** serial and parallel bit-identical.

## 8. Acceptance

- Every constant in config (rule 1).
- A pilot on a few candidates, reproduced by a second run; measure the cost and project the full run.
  **Stop there with the pilot's numbers**, as T12 and T13 did.
- The full run over every stage-2 selection. The review reports, per candidate: the effective grid
  size, the selected centre and plateau extent, stability ratio, plateau area, SPP, half-2's result at
  the selected point, the zero-cost plateau and how far costs moved it, the overlaps after optimisation,
  and the gate verdict.
- **The headline control (D-644):** the same candidates on reshuffled returns. It leads the review.
- D-802 stated, as in every stage review.
- Fast suite, parity/leakage/oracle, db with 0 skipped, slow, ruff, format, mypy (Windows and
  `--platform linux`), stream guards. Then stop for "Approved".

## 9. Out of scope

Exits (stage 4); choosing between overlapping candidates (stage 4 or 10); any Bayesian search (D-120).

## 10. Raise, do not decide

- How a failed cell enters the smoothed mean (for example as the grid's worst observed value, or as a
  fixed floor), measured on real candidates before choosing.
- Whether the trade minimum applies to each half at full or half strength, with the counts that each
  choice leaves.
- Any candidate whose fine grid is so small that plateau area is not meaningful (a handful of cells).
- Any candidate passing on the control (D-644).
