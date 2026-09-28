# RUNBOOK — T13: stage 2, method screening (stream A)

One task. Not in D-402's list, but T13 §0 asks for a **stop after the review, before the merge**.
Task file: `docs/tasks/T13_stage2_method_screening.md` (supervisor's, unchanged). Plan and
measurements: `docs/tasks/T13_plan.md`. Decisions: **D-622 … D-628** and the answers to
**P-107 … P-114**. Features: F-2.1 … F-2.7; touches F-0.4.1 (P-108), F-0.7.1 … F-0.7.3, F-0.8.1.

## Branches

| step | branch | base | stop |
|---|---|---|---|
| plan | `a/T13-plan` | `main` | **"Plan approved"** (D-403) |
| 1 … 10 | `a/T13-method-screening` (one task, one review file) | `main` after the plan merges | on a §11 trigger (below); after the review, **"Approved"** |

Paths: `components/`, `stages/`, `baseline/`, `metrics/`, `configs/gates/`, `configs/stages/` are
stream A's (D-611, D-612); `stats/`, `core/`, `pipeline/`, `tests/`, `scripts/` are shared;
`data/` is not touched (the stage reads through `DataAccess`, the aux join included if P-113
says so).

## Preconditions

1. P-107 … P-114 answered, or their proposals accepted with "Plan approved".
2. `main` green; `uv sync`.
3. The T12 1D and 1H run ids (`db666562…`, `6f603a07…`) and their artifacts under
   `SFAC_ARTIFACTS_ROOT` are the stage's input; nothing is re-run (supervisor, 2026-09-28).

## Order of work

1. **Contract** (P-108). `GridRules`: 2–4 coarse values per parameter, ≤ 64 cells; the T07
   registry tests updated; every existing component still validates. A test that a 1-value and a
   5-value parameter are refused.
2. **Components** (F-2.1, F-2.2) in `components/entries/methods_mr.py`, `methods_tf.py`: the
   library of `T13_plan.md` §2, each a registered `EntryComponent` with `edge_type`, `trigger`,
   `ParamSpec`s and a declared `warmup(params)`.
   - Ratio rules in the `|ref|` form (plan §4); a test per ratio rule that the mirrored short
     equals the literal short for positive prices.
   - The user's rules: each tested against a **naive line-by-line port of
     `tools/tradingview/user_mr_suite.pine`** (hand cases and random data); the candle score and
     the BaseCandle machine exactly as the script.
   - Indicator reference tests: every indicator used already has a T07 TradingView golden;
     new derived series (candle score, the script's %R scale, rolling RSI sum) get naive-port
     references.
   - Truncation (leakage) test for every method's signals and warm-up.
   - **D-627 guard**: no two methods identical on the parity charts (`BATS_SPY, 1D`,
     `OANDA_XAUUSD, 60`) at their default cells; mutation-checked by registering a duplicate.
3. **Stage config and metrics.** `configs/stages/s02_screen.yaml` (Pydantic): the methods per
   edge type, good-region share (0.25), baseline simulations, family-score weights and points
   constants (P-114), consistency minimum, BH q. `metrics/names.py`: register
   `grid_median_target`, `profitable_cell_share`, `min_trades_good_cells`,
   `overlap_with_selected` (already in the gate YAML) and **`method_q_value`** (P-107).
   `configs/gates/default.yaml`: `method_q_value <= 0.1` under `s02_screen`.
4. **Family score, rank-sum, diversity** (`metrics/family.py`, `stages/screen_select.py`):
   F-2.4 (the one-good-cell vs uniformly-good synthetic test, the headline unit test), F-2.5
   (weighted rank-sum, invariant to monotone rescaling, tested), F-2.6 (overlap on the good-region
   median cells; the "top two overlap, the third is chosen" case).
5. **The stage** `stages/screen.py` (`s02_screen`): one work unit per (profile, method). Inputs
   from the stage-1 artifacts (index + `summary.json`), passing profiles only, carrying the
   caveats and `unconfirmed` (D-610, D-628). Per cell: zero-cost and full-cost runs (D-623); the
   good region and its median cell; the matched baseline on that cell (D-624, D-607 seeds keyed by
   method and cell); the gate on the after-cost leg; BH across the profile's methods; rank-sum,
   diversity, 3–5 (D-625). Registry: one **trial per cell** (both legs in the row), candidates for
   the selected methods with `parent_id` = the stage-1 candidate (P-114 (h)), gate rows.
   Artifacts: `summary.json` per selected method (T13 §8), the grid heatmap as data, trades only
   for the selected methods' good-region median cells.
   `sfac run` accepts `s02_screen` after `s01_edge`'s run id (stage 2 only, no orchestration).
6. **Tests** (T13 §9): each gate criterion failed in turn; the gate reads the after-cost leg and
   the ranking the zero-cost leg (a wiring test that fails if swapped); no `SplitManager` /
   `open_holdout` in the stage modules (T12's guard extended); serial = parallel bit-identical;
   `cells_run` = trial rows.
7. **Pilot**: MSFT long, K short (1D) and BAC long (1H), run twice, identical; cost measured
   against `T13_plan.md` §7. **Checkpoint only on a §11 trigger**: a grid badly placed on another
   profile, a profile with no method passing (reported, not loosened), or the control letting
   methods through beyond P-107's answer.
8. **Full run and the control.** Every stage-1 pass, then the same profiles on the D-615
   reshuffled-returns control. **The control pass count is the headline**; if it is above what
   P-107 set, stop and take it to the supervisor before stage 3 builds on it.
9. **Review** `docs/reviews/T13_review.md`: per profile the methods, cells, family-score table,
   rank, what diversity removed, what passed, zero-cost vs after-cost for the selected methods;
   the unconfirmed profiles apart; **which of the user's methods were selected and why**; D-802
   stated.
10. **Close.** Fast suite, parity/leakage/oracle, db with 0 skipped, slow, ruff, format, mypy
    (Windows and `--platform linux`), `sfac streams check`; the `acceptance-reviewer`; push, PR,
    **stop for "Approved"**.

## Rules for this task

- No threshold, weight or constant in code (rule 1): the stage YAML or the gate YAML.
- Development data only; the stage never holds a `SplitManager` (rule 2, D-616).
- No look-ahead: every new signal and warm-up has a truncation test (rule 3).
- Ranking at zero cost, gate after costs (D-623, rule 4).
- Every cell is a trial; baseline draws are not (rule 5, D-012).
- The engine is not changed. If a method needs it, stop: an engine change is critical (D-402).
- No new dependency.
