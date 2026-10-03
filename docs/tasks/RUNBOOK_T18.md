# RUNBOOK — T18: the stage-6 robustness library (stream B)

One task. **Two stops:** the plan (**"Plan approved"**, D-403), and the review before the merge
(**"Approved. Merge"**). Task file: `docs/tasks/T18_robustness_library.md` (the supervisor's,
unchanged). Plan and measurements: `docs/tasks/T18_plan.md`. Questions: **P-150 … P-159**. Features:
F-6.1 … F-6.4, F-6.7, F-6.9.

## Branches

| step | branch | base | stop |
|---|---|---|---|
| plan | `b/T18-plan` | `main` `2b846ff` | **"Plan approved"** |
| 1 … 9 | `b/T18-robustness-library` (one task, one review file) | stacked on `b/T18-plan` | after the review, **"Approved. Merge"** |

## Preconditions

1. P-150 … P-159 answered (decisions from D-726, stream B's own range, below D-760, marked
   "(supervisor)" where the supervisor settles them).
2. **Stream A's ownership PR on `main`:** `src/strategy_factory/robustness/` and
   `tests/**/test_F_6_*` assigned to stream B (task §6). Until then no code in `robustness/`.
3. T16 merged or at least its seed and bootstrap conventions settled (D-723, D-725); T18 reuses them.

## Order of work (tests first in each step; light by day, heavy runs only at night)

1. **Result types** (`robustness/results.py`) and the purity test (T16's static import check).
2. **Consistency** (F-6.1): yearly / quarterly metrics through `metrics/`, R², K-ratio, KS, the CV
   rule of P-156, the anomaly checks.
3. **Walk-forward** (F-6.2, F-6.3): window generation (anchored, rolling, D-150, auto-shrink and its
   flag, P-159's answer), the re-optimization and evaluation callables, WFE per P-150, the
   OOS-profitable share, the matrix and its passing cells per P-151. The look-ahead test.
4. **Monte Carlo** (F-6.4): shuffle, bootstrap (P-152), removal on a trade list; price noise
   (P-153), parameter noise (P-154), random start (P-155) and cost stress through the re-run
   callable; CRC32-derived seeds; serial equals parallel.
5. **Crisis periods** (F-6.7): the per-period table with "no data".
6. **Score** (F-6.9): block pass / fail and 0–100 (P-157), the weighted total, the critical-block
   rule (WF, 2× cost stress, holdout) and the gate / report split of P-158.
7. **Night measurements** (plan §10), if the answers leave options open: resumable, line-by-line
   logs, behind T16's queue.
8. **Gates:** fast suite, parity / leakage, db (0 skipped), ruff, format, mypy strict for
   `robustness` (Windows and `--platform linux`), `sfac streams check`.
9. **Review** `docs/reviews/T18_review.md`, the acceptance reviewer, the PR, stop for
   **"Approved. Merge"**.
