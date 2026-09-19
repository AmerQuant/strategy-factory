# RUNBOOK — Batch 2a (T05 → T06 → T10a)

Execute in **one session, in the main folder**, in order. Read `CLAUDE.md` first. No network access is needed for any of these tasks.

## Preconditions (stop if one fails)
1. `main` contains T04e and T03. Check that `src/strategy_factory/registry/` exists and that `hash_version` exists in `data/schema.py`.
2. The working tree is clean, apart from the untracked batch-2a task files.
3. Docker Postgres is reachable at the `SFAC_DB_URL` in `.env`. If it is not, the DB tests may skip locally; they must still pass in CI.

## Step 0
Create branch `docs/batch2a` from `main`. Commit the four batch-2a task files (`RUNBOOK_batch2a.md`, `T05_quality_resample_split.md`, `T06_costs.md`, `T10a_gates_config_universe.md`) unchanged.

## Branching (stacked)
| Task | Branch | Based on |
|---|---|---|
| T05 | `feat/T05-quality-resample-split` | `docs/batch2a` |
| T06 | `feat/T06-costs` | T05 |
| T10a | `feat/T10a-gates-config-universe` | T06 |

## Per-task loop
Same as batch 1:
1. Read the task and every document it references.
2. If anything is ambiguous or conflicts with `CLAUDE.md`, the design or an ADR: stop and ask.
3. Tests first, then the implementation.
4. Run the full acceptance list.
5. Commit with feature IDs in the messages.
6. Write the review to `docs/reviews/<task>_review.md`, then continue with the next task.

**Never switch the main folder to another branch** except as the table above requires, and never to `main` in the middle of the batch.

## Stop conditions
- Acceptance commands fail and you cannot fix them within the task's scope.
- A decision is needed that the task does not give.
- Any change would touch raw data, holdout data, parity fixtures or tolerances.

## Final report
Print one combined report:
- a status table per task;
- links to the reviews;
- merged open questions;
- the merge order `docs/batch2a` → T05 → T06 → T10a.
