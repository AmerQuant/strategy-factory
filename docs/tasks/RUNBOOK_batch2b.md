# RUNBOOK — Batch 2b (T06b → T08 → T10b)

Execute in **one session, in the main folder**, in order, after the user writes **"Plan approved"**. Read `CLAUDE.md` and `docs/decisions/decisions_log.md` first; the batch-2b questions are resolved as **D-315 … D-340** in the decisions log (P-18 rejected, see D-329); `pending.md` is empty at the start.

No network access is needed. The Moneta file is read from `SFAC_RAW_ROOT` (read-only).

## Preconditions (stop if one fails)
1. `main` contains T05, T06, T07, T09 and T10a (`costs/arrays.py`, `metrics/containers.py`, `gates/engine.py`, `components/base.py` exist).
2. The Moneta file exists at `SFAC_RAW_ROOT/reference/broker/moneta/MT5Moneta-ECN_specification-1.xlsx` and its sha256 equals the manifest.
3. Docker Postgres is reachable at `SFAC_DB_URL` (port 5433, D-305); DB tests must run with 0 skipped.
4. The working tree is clean.

## Branching (stacked)
| Task | Branch | Based on | Critical (D-402) |
|---|---|---|---|
| — | `docs/batch2b` (this plan) | `main` | |
| T06b | `feat/T06b-moneta-costs` | `docs/batch2b` | no |
| T08 | `feat/T08-engine` | T06b | **yes — stop after the review, wait for "Approved"** |
| T10b | `feat/T10b-executor-metric-names` | T08 | partly: the `open_holdout` and gate-YAML changes are **CRITICAL** (D-339), marked in its review and PR |

## Per-task loop
1. Read the task file and every document it references, including the decisions it cites.
2. Anything ambiguous or conflicting with `CLAUDE.md`, the decisions log or an ADR: stop, ask, and add it to `pending.md`.
3. Tests from the acceptance criteria first, then the implementation.
4. Acceptance commands, all green:
   ```
   uv run pytest -m "not slow"
   uv run pytest tests/parity tests/leakage tests/oracle
   uv run pytest -m db            # 0 skipped
   uv run ruff check . && uv run ruff format --check .
   uv run mypy src
   ```
5. Run the `acceptance-reviewer` subagent on the task; fix its findings.
6. Commit with feature IDs in the messages; write `docs/reviews/<task>_review.md`.
7. T08: **stop** and wait for "Approved".

**Never switch the main folder to another branch** except as the table requires, and never to `main` mid-batch.

## Dependencies
- T06b adds **openpyxl** to the dev group (D-317).
- T08 adds **vectorbt** to the dev group only if the numba/numpy pins stay unchanged (D-330); otherwise it reports this. The naive oracle is mandatory either way.

## User actions during the batch
- T06b: review `docs/reviews/T06b_mapping_review.csv` (name-only match candidates) and add accepted pairs to `configs/costs/moneta/symbol_overrides.csv`, or tell Claude Code which to accept.
- T10b: the scalability benchmark runs locally (no network); nothing to do.

## Stop conditions
- Acceptance commands fail and the fix is outside the task's scope.
- A decision is needed that the task or the decisions log does not give.
- Any change would touch raw data, holdout data, parity fixtures or tolerances.

## End of batch
1. Open the PR(s) with `gh`, body = the reviews (one PR per task, stacked, or one PR for the batch if the supervisor prefers).
2. Update `HANDOFF.md` (task status, open items).
3. Print one combined report: status table per task, links to the reviews, merged open questions, the merge order `docs/batch2b` → T06b → T08 → T10b.
4. Merge only after **"Approved. Merge …"** and green CI (D-401). Remind the user of **P-04** (TradingView parity exports) before T11 is planned.
