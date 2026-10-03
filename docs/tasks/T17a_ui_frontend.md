# T17a-FE — Admin UI, phase 1, frontend first

**Stream B, second worktree `StrategyFactory_UI` (the UI session).** Plan first (D-403): draft, stop
for "Plan approved", then implement; stop for the review before merge.
Read with: `docs/tasks/T17_admin_ui.md` (the decisions, §2), `docs/tasks/UI_spec.md` (the screens,
their content) and `docs/tasks/UI_tokens.md` (the colours, type and spacing of both themes, extracted
from the canvas). **`UI_spec.md` and `UI_tokens.md` are the authority for layout and look.** The design
canvas lives on claude.ai and cannot be opened from Claude Code; where `UI_spec.md` is silent, raise it,
do not invent.

## 1. Why this split

T17a needs two things from stream A — the backend dependencies in `pyproject.toml` and the
progress-event contract in the orchestrator — and stream A is busy with T15a's acceptance runs. So
phase 1 is built **frontend first**: the React app, complete, against a **mock API** that implements
the contract in §3 exactly. When stream A has landed its prerequisites, **T17a-BE** builds the FastAPI
backend to the same contract and the mock is switched off. Nothing in this task touches Python.

## 2. Scope

In `ui/` only (its own `package.json` and lockfile):

- **The app shell:** navigation for all three phases as `UI_spec.md` defines it; phase-2 and phase-3
  screens appear as disabled entries or placeholders, not as half-built pages.
- **Dark and light themes** from `UI_spec.md`'s tokens (Mantine theme), switchable, remembered.
- **Start a funnel run:** funnel config, data source (real, null with seed, planted), control on or
  off — off is visibly flagged (D-653). Profile selection is shown disabled until T17c.
- **Live run view:** every stage of both arms and both timeframes as the plan of §3 lists them; per
  stage a progress bar, units done of total, elapsed, estimated remaining, final timing; the current
  stage highlighted; failures with their reason; a resume action on a failed run.
- **Run history:** every funnel run with source, start, finish, total time, per-stage counts real
  against control, status; filter and search.
- **The mock API** (in `ui/`, dev and tests only, never in a production build): serves the endpoints
  of §3.3 and replays event streams. Its fixtures include **one built from the real timings of T15a's
  planted funnel** (1D s01 13/12 min, s02 15/16, s03 7/7; 1H s01 29/27, s02 6, …, real/control), one
  failed-and-resumed run, and one run with the control off.

Out of scope: the backend, phases 2 and 3, any change outside `ui/` except this stream's status file.

## 3. The contract (the supervisor's; stream A implements it as written)

### 3.1 Progress events

One JSON object per event. Every event has:

| field | type | meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `funnel_run_id` | uuid | the funnel run |
| `seq` | int | strictly increasing within a funnel run, from 1 — the SSE event id |
| `ts` | string | UTC, ISO 8601 with `Z` |
| `type` | enum | below |

| `type` | extra fields |
|---|---|
| `funnel_started` | `name` (the user's, or generated), `config_id`, `config_hash`, `profile_hash` (null until T17c), `code_version` `{git_sha, dirty}`, `source` (`real` \| `null` \| `planted`), `seed` (int or null), `control` (bool), `plan`: ordered list of `{stage_id, timeframe, arm}` |
| `funnel_resumed` | `code_version`; `seq` continues, the `funnel_run_id` is the same |
| `stage_started` | `stage_id`, `timeframe` (`1D` \| `1H`), `arm` (`real` \| `control`), `stage_run_id`, `units_total`, `unit_kind` (`profile` \| `method` \| `candidate` \| …), `reused` (bool — true when a resume takes the stage's completed result instead of running it; then `stage_finished` follows at once) |
| `progress` | `stage_run_id`, `units_done`, `units_total`, `elapsed_s`, `eta_s` (null until estimable) |
| `stage_finished` | `stage_run_id`, `elapsed_s`, `n_in`, `n_passed` |
| `stage_failed` | `stage_run_id`, `elapsed_s`, `error_kind`, `message` |
| `funnel_finished` | `elapsed_s` |
| `funnel_failed` | `elapsed_s`, `error_kind`, `message` |
| `funnel_stopped` | `elapsed_s`, `stage_run_id` of the interrupted stage (its partial output is discarded, never reused) |

Rules: `progress` events are throttled by the producer (at most one per second per stage run); a
resume keeps the `funnel_run_id`, continues `seq`, and marks each completed stage with `reused: true`;
unknown fields are ignored by the UI and unknown `type`s are shown, not dropped (forward compatibility).
A stopped or failed run can be resumed.

### 3.2 Live delivery

Server-Sent Events. The SSE `id` is `seq`; a reconnect with the `Last-Event-ID` header **or the query
parameter `?last_event_id=`** (for a page reload, where the browser's `EventSource` cannot send the
header) resumes after it, and a client with neither receives the whole history of the run first. The
UI also drops any `seq` it has already applied. The UI must handle a reconnect in
the middle of a stage without duplicating or losing progress.

### 3.3 Endpoints (the mock implements them; T17a-BE implements the same)

- `GET  /api/funnel-runs` — list, with filters (source, status, date range)
- `GET  /api/funnel-runs/{id}` — summary: the `funnel_started` fields, status, per-stage results
- `GET  /api/funnel-runs/{id}/events` — SSE, §3.2
- `POST /api/funnel-runs` — start: `{config, source, seed, control}` → `{funnel_run_id}`
- `POST /api/funnel-runs/{id}/resume` → `{funnel_run_id}`
- `POST /api/funnel-runs/{id}/stop` → `{funnel_run_id}`; the run ends with `funnel_stopped`
- `GET  /api/configs` — the funnel configs a run can start from; each item
  `{id, name, config_hash, stages, timeframes, universe: {name, n_symbols}, planted_ladder}`
  (`planted_ladder` null when the config has none). In phase 1 the wizard shows the scope read-only
  from the chosen config.
- `GET  /api/status` — server status and the open-item banners: `{server: {host, version},
  banners: [{id, level, title, text}]}` (today: calibration pending, D-802 parity gap)

**Shapes.** A run summary is the `funnel_started` fields plus `status` (`queued`, `running`,
`finished`, `failed`, `stopped`), `started_at`, `finished_at`, `elapsed_s`, and per stage run
`{stage_id, timeframe, arm, stage_run_id, status, reused, elapsed_s, n_in, n_passed}`. A list item is
the summary without the per-stage list, plus per-stage-id counts real against control. A refused
request answers 409 or 422 with `{error_kind, message}`.

**Deferred, shown disabled with the phase that brings it:** the Downloads page (T17a-BE, with its own
endpoint), time estimates for queued stages, open report, reproduce and compare (phase 2), profiles
(T17c).

### 3.4 Ruled after the frontend review (2026-10-03; the mock's choices become the contract)

T17a-FE's review §5 (1–9) listed what §3.1–3.3 left open; the user accepted the mock's choice for
each. Stream A and T17a-BE build exactly this:

1. **A stage run's `status`** in the summary: `queued`, `running`, `finished`, `failed`, `stopped`
   (`queued` for a stage run in the plan that has not started).
2. **The list's per-stage counts**: `stage_counts: [{stage_id, real, control}]` — passes summed over
   the timeframes; `null` when that arm finished no run of the stage.
3. **List filters**: `source`, `status`, `started_from`, `started_to` (dates, inclusive). The list is
   a bare JSON array, no envelope, no pagination; search and sort are the client's.
4. **The list's order**: newest `started_at` first (the UI sorts too).
5. **Nullable**: `started_at`, `finished_at`, `elapsed_s` of a run (null until known); a stage run's
   `elapsed_s`, `n_in`, `n_passed` (null while running); `funnel_stopped.stage_run_id` (null when
   stopped between stages); a **queued** stage run's `stage_run_id` (null until it starts — it is
   identified by `(stage_id, timeframe, arm)`, unique within a run, as in `plan`; D-794).
6. **`planted_ladder`**: an object or null; **stream A defines its fields** from T15a's planted
   config when it implements the contract, and the mock's fixture is updated to match. The UI shows
   it as given, so no UI change follows.
7. **An unknown run id** answers **404** `{error_kind: "not_found", message}`.
8. **`schema_version`** is exactly `1`; an event of another version is a contract error, not parsed.
9. **SSE**: the server **closes the stream after a run's terminal event**, and at once when a client
   connects to a run that has already ended; when both `Last-Event-ID` and `?last_event_id=` are
   present, **the header wins**.

Proven only against the real server (T17a-BE's acceptance, not the mock's): the resume from the
`Last-Event-ID` header end to end, and a page reload during a live run.

If building the screens shows the contract lacks something, **raise it in the plan**; do not extend it
unilaterally — stream A builds to this text.

## 4. Raise, do not decide (the plan)

The user chooses among libraries personally. For each, give the options with pros and cons, their
effect on the repository and on T17a-BE, and what implementation looks like:
- the build tool and dev server; the package manager;
- routing; server-state and SSE handling on the client;
- the mock layer; the test runner, component tests and the end-to-end tool;
- how the built frontend will be served in T17a-BE (goal: one command starts everything).

Also state the Node version in use and whether it matches what the Dukascopy tooling needs.

## 5. Acceptance

- `ui/`: lint, format check, type check (strict), unit and component tests, one end-to-end test that
  starts a run on the mock, watches it finish, forces a reconnect mid-stage and a failure plus resume.
- Screenshots of every phase-1 screen in both themes in the review, checked against `UI_spec.md`.
- The Python CI stays green (nothing outside `ui/` changes). A CI job for `ui/` is stream A's
  (`.github/`): state the exact commands it should run in the review, for stream A to add.
- Review in `docs/reviews/T17a-FE_review.md`; stop for "Approved. Merge".

## 6. Working rules for this session

- Own worktree, own branches `b/ui-…`; never switch another folder's checkout; `uv run sfac streams
  session` **without** `--stream` (a helper session).
- Status in **`docs/streams/B_ui.md`** (this session's own file; `docs/streams/B.md` is stream B's
  main session's). No messages to other sessions; notes for them go in `B_ui.md` and through the
  supervisor.
- Decision ids **D-760 … D-799** (carved from stream B's range for this session). No pending ids until
  stream A lands P-150 … P-199; put questions in the stop report.
- Heavy commands (full test runs, builds) are light next to the funnel, but do not run benchmarks.
