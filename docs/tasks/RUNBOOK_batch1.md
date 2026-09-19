# RUNBOOK — Batch 1 (T00b → T02 → T04a → T04b → T04c)

Execute the tasks below **in order, in one session**. Each task is a separate unit of work with its own branch, commits and review summary. Read `CLAUDE.md` first; its rules apply to every task.

## Preconditions (check first; if one fails, stop and tell the user)
1. `main` contains T01 and T00: `CLAUDE.md`, `pyproject.toml`, `docs/data_inventory.md` exist on `main`.
2. The working tree is clean (untracked docs from this batch are allowed).
3. `uv run pytest` passes on `main`.

## Step 0 — Commit the batch documents
Create branch `docs/batch1` from `main`. Commit:
- `HANDOFF.md`
- `docs/tasks/RUNBOOK_batch1.md`
- `docs/tasks/T00b_organize_raw_store.md`
- `docs/tasks/T02_schema_store_catalog.md`
- `docs/tasks/T04a_alpaca_download_adapter.md`
- `docs/tasks/T04b_dukascopy_download_adapter.md`
- `docs/tasks/T04c_yahoo_aux.md`
- `docs/spec/spec_addendum_edge_types_v0_1.md` (status: draft)

Do not change their content.

## Branching
| Task | Branch | Based on |
|---|---|---|
| T00b | `feat/T00b-raw-store` | `docs/batch1` |
| T02 | `feat/T02-schema-store` | `feat/T00b-raw-store` |
| T04a | `feat/T04a-alpaca` | `feat/T02-schema-store` |
| T04b | `feat/T04b-dukascopy` | `feat/T04a-alpaca` |
| T04c | `feat/T04c-yahoo` | `feat/T04b-dukascopy` |

The branches are stacked because each later task needs the store from T02. Do not merge anything into `main`; the user merges after review. Do not push unless the user has added a remote and asks.

## Per-task loop
1. Read the task file and every document it references.
2. If the task is ambiguous or conflicts with `CLAUDE.md`, the design or an ADR: **stop the whole batch** and list the questions.
3. Tests first, then the implementation.
4. Run the full acceptance list: ruff, format check, mypy, pytest, plus the task-specific checks.
5. Commit with feature IDs in the messages.
6. Write the task's review summary to `docs/reviews/<task>_review.md` (commit it on the task branch). Then continue with the next task.

## Stop conditions (stop the batch and report)
- Any source data file changed (T00b integrity check).
- Acceptance commands fail and you cannot fix them within the task's scope.
- TLS/certificate errors on any download. Never disable verification or add trust-store workarounds.
- A decision the task marks as "stop and ask" (e.g. the S&P 500 point-in-time source in T04a).

## Skip conditions (skip only the affected pilot, finish the rest, continue)
- `ALPACA_API_KEY` / `ALPACA_API_SECRET` missing → T04a: build and test with mocks, skip the pilot.
- Node.js missing → T04b: stop T04b after the tests that do not need Node; mark the task incomplete; continue with T04c.

## Never in this batch
- Full downloads (only the pilots defined in each task).
- Touching the old project data folders except for read-only reading in T00b.
- Changing `docs/spec`, `docs/design.*`, `docs/features.*`, ADRs or `CLAUDE.md`.

## Final report
At the end, print one combined summary with:
- a status table per task (done / partial / skipped, branch, commit, tests);
- links to the five review files;
- all open questions, merged and de-duplicated;
- the exact commands for the full downloads (from T04a/b/c) with their estimates;
- the recommended merge order: `docs/batch1` → T00b → T02 → T04a → T04b → T04c.
