# RUNBOOK — T14: stage 3, entry optimisation (stream A)

One task. T14 asks for **three stops**: the plan ("Plan approved"), the **pilot's numbers**, and
the review before the merge ("Approved"); plus D-644's stop if **any** control candidate passes.
Task file: `docs/tasks/T14_stage3_entry_optimisation.md` (supervisor's, unchanged). Plan and
measurements: `docs/tasks/T14_plan.md`. Decisions: **D-639 … D-645** and the answers to
**P-116 … P-121**. Features: F-3.1, F-3.3 … F-3.7 (F-3.2 is P1); touches F-0.7.1 … F-0.7.3.

## Branches

| step | branch | base | stop |
|---|---|---|---|
| plan | `a/T14-plan` | `main` (after #53) | **"Plan approved"** (D-403) — given 2026-09-29, answers D-646 … D-651 |
| 1 … 9 | `a/T14-entry-optimisation` (one task, one review file) | stacked on `a/T14-plan` (plan and decisions), as T13 | the pilot's numbers; D-644; after the review, **"Approved"** |

Paths: `stages/`, `metrics/`, `configs/stages/`, `configs/gates/` are stream A's (D-611, D-612);
`robustness/`, `core/`, `pipeline/`, `tests/`, `scripts/` are shared; `data/` and `engine/` are
not touched.

## Preconditions

1. P-116 … P-121 answered, or their proposals accepted with "Plan approved".
2. `main` green; `uv sync`.
3. The T13 runs `dea1d423…` (1D) and `6025ef15…` (1H) and their artifacts under
   `SFAC_ARTIFACTS_ROOT` are the input; nothing upstream is re-run.

## Order of work

1. **Config.** `configs/stages/s03_entry.yaml` + `stages/optimize_config.py` (Pydantic, frozen):
   margin in coarse steps (1, D-639), the cap (2,000, D-120), the above-cap rule (P-119), the
   failed-cell treatment (P-116), the per-half minimum (P-117), `min_plateau_cells` (P-118), SPP
   percentiles, `unconfirmed_timeframes`, `batch_units` (out of the stage-config hash); exits read
   from `s01_edge.yaml` (D-622). The plateau cut is the gate's `stability_ratio` threshold.
2. **Fine grid** (F-3.1, D-639, D-640): from the `MethodScreen` artifact — good-region bounds per
   numeric parameter (plan §6 (a), (b)), choice parameters fixed, integer resolution, the cap and
   the coarsening; tests first (margin, clipping, non-uniform coarse values, the cap path).
3. **`metrics/plateau.py`** (F-3.3, F-3.4) and **`robustness/spp.py`** (F-3.5): smoothing,
   selection, stability ratio, connected plateau and its extent, edge slope, the failed-cell
   treatment, SPP. Tests first: the peak-vs-plateau surface, two disjoint islands, the
   lone-survivor surface (must fail), hand-computed SPP.
4. **Segments** (D-641, rule 3): `method_run` gains a segment — signals and ATR on bars up to the
   segment's end, simulation on the segment; the truncation test (half 1 identical with and
   without half 2 present) and the leakage test over every cell use this same function.
5. **The stage** `stages/optimize.py` (`s03_entry`) and `stages/optimize_artifact.py`: one unit
   per candidate; half-1 selection on the after-cost surface (D-642), the zero-cost plateau and
   its shift; half-2 acceptance; SPP on the whole window; the gate; per profile the D-643
   overlaps; registry (candidate per stage-2 selection, parent = its stage-2 candidate, trials per
   cell per segment, gate rows); artifacts (summary with the surfaces as data, trades for passing
   candidates' selected cells, index). `sfac run` dispatches `s03_entry`; `configs/pipeline/s03_*`.
6. **Tests** (T14 §7, plan §9): every criterion failed in turn; the D-642 wiring test
   (mutation-checked); the holdout guard covers `optimize*.py`; serial = parallel bit-identical;
   trial rows = cells × 3; a stage-2 control run is refused as input.
7. **Pilot** (plan §10): 1D MSFT long and TXN long (all their candidates), 1H BAC long; run twice,
   identical; timings. **Stop with the pilot's numbers** (T14 §8).
8. **Full run, then the control** (the real stage-2 selections on reshuffled bars). **If any
   control candidate passes, stop and raise it (D-644).**
9. **Review** `docs/reviews/T14_review.md`: the control first; per candidate the effective grid
   size (and the step multipliers), the selected centre and plateau extent, stability ratio,
   plateau area, SPP, half 2 at the selected point, the zero-cost plateau and its shift, the
   overlaps after optimisation, the verdict; every small grid named; the unconfirmed candidates
   apart; D-802 stated. Then fast suite, parity/leakage/oracle, db with 0 skipped, slow, ruff,
   format, mypy (Windows and `--platform linux`), `sfac streams check`; the `acceptance-reviewer`;
   push, PR, **stop for "Approved"**.

## Rules for this task

- No threshold, weight or constant in code (rule 1): the stage YAML or the gate YAML.
- Development data only; the stage never holds a `SplitManager` (rule 2, D-616).
- No look-ahead: a half never reads beyond its end (rule 3).
- The plateau on the after-cost surface (D-642, rule 4).
- Every cell on every segment is a trial (rule 5, D-160).
- The engine is not changed; if the stage needs it, stop (D-402).
- No new dependency (P-119).
