# Stream B — UI session (worktree `StrategyFactory_UI`)

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory_UI`, a git worktree of its own (no stream
owns the folder; `uv run sfac streams session` passes without `--stream`). A helper session of
stream B for **T17** (the admin UI): branches `b/ui-…`, decision ids **D-780 … D-799**, no pending
ids (questions go in the stop report). This file is this session's status only; `docs/streams/B.md`
is stream B's main session's. No messages to other sessions — notes here, relayed by the supervisor.

## Resume here (2026-09-30)

| branch | state | waiting on |
|---|---|---|
| `b/ui-T17a-frontend` | T17a-FE implemented; review `docs/reviews/T17a-FE_review.md` with 26 screenshots (`docs/reviews/T17a-FE/`); plan approved, D-780 … D-797 recorded | **"Approved. Merge"**, and the supervisor's word on review §5 (contract points 1–9 for stream A before T17a-BE; colour choices 12–15; a UI feature id, 19) |

Task: **T17a-FE** — phase 1 of the admin UI, frontend only, in `ui/`, against a mock of the
supervisor's contract (`docs/tasks/T17a_ui_frontend.md` §3). Nothing outside `ui/` changes except
this file, the task/plan/review docs and the decisions log rows above. Next: T17a-BE (after stream
A's prerequisites).

## Notes for the supervisor (to relay)

- **D-675 is left free on purpose.** Stream A renumbers its duplicate D-673 (P-134's answer) to "the
  next free supervisor id after D-674" (`docs/streams/B.md`), which is D-675; T17's decisions start
  at D-676 so the two cannot collide. If stream A used a different id, D-675 simply stays unused.
- **The three T17 task files were found in stream A's folder** (`StrategyFactory/docs/tasks/`,
  untracked), not in this worktree. They were **copied** here (identical to the user's Downloads
  copies) and committed on this branch; stream A's folder was not touched. The untracked copies there
  should be removed by the user or stream A, so they are not committed twice.
- **For stream A (T17a-BE and the `ui` CI job):** the CI commands are in `docs/reviews/T17a-FE_review.md`
  §7; the contract points the mock had to choose (stage-run status enum, `stage_counts`, list filter
  names, nullable fields, 404, SSE close and header-over-query) are in §5 — T17a-BE should match
  whatever the supervisor rules. The `Last-Event-ID` header path could not be exercised end to end on
  MSW (§5.10): T17a-BE's test must prove it over real HTTP.
- **The updated task files were again found untracked in stream A's folder** (`StrategyFactory/docs/tasks/`:
  `T17a_ui_frontend.md`, `UI_tokens.md`, and the earlier `T17_admin_ui.md`, `UI_spec.md`); they were
  copied here (identical to the Downloads copies) and committed. The copies there should be removed.
