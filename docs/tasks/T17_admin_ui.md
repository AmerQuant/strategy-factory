# T17 — Admin UI and dashboard (English)

**Stream B, after T16.** Three phases, each its own task and PR, each usable on its own. Plan first
for every phase (D-403): draft, stop for "Plan approved", then implement; stop for the review before
merge. Design decisions for phases 2 and 3 are settled with the user in chat before their task files.

## 1. What the user asked for

A complete, polished, colourful, professional web application in English, for one user on his own
machine:
- run the whole funnel and **monitor every stage's progress and timing live**;
- a dashboard of results: every important metric, many professional charts;
- administration: every platform setting, and each stage's strategies and parameters viewable and
  editable.

The CLI (`sfac funnel run`, T15a) stays the engine; the UI drives it and reads what it records.

## 1a. Design references — build exactly this

- **Visual design:** the approved mockup canvas https://claude.ai/artifact/97EREXyXnNucS8rG3XVoxS —
  18 screens in the dark theme and the four key screens in the light theme. It fixes the look:
  a deep-navy ground, rounded cards with fine borders; teal for primary actions and "done", blue for
  real data, amber for the calibrated null and warnings, violet for planted data and the user's own
  rules; Manrope for text and JetBrains Mono for numbers. Colours that must be told apart also differ
  in lightness. Reproduce the layout, hierarchy and colour roles; replace illustrative values with
  real data.
- **Page content:** `docs/tasks/UI_spec.md` — every page's blocks, where each number comes from, which
  library draws each chart, the phase it belongs to, and the settings inventory (which domains a
  profile may edit and which are read-only).
- Where the canvas and the spec disagree, the spec wins for content and the canvas for look; raise
  any disagreement you find instead of choosing.

## 2. Decisions (settled with the user)

Record them in the supervisor range from the next free id (D-674 unless taken; check first), marked
*(supervisor)*, citing this task.

| # | Decision |
|---|---|
| 1 | **Stack:** a FastAPI backend (Python) and a React + TypeScript frontend. |
| 2 | **Components:** Mantine. |
| 3 | **Charts:** ECharts for the dashboard and metrics; Plotly.js for the scientific plots (parameter surfaces, heatmaps, distributions), matching the T15a report. |
| 4 | **Live progress:** Server-Sent Events from the backend. |
| 5 | **Single user, local, no login or accounts.** The server binds to `127.0.0.1` only; it must not be reachable from the network. |
| 6 | **Editing scope:** parameters and settings only — enabling or disabling strategies, their grids, gate thresholds, universes, costs and executor settings. New strategy logic stays code: the user supplies the rule (as with his Pine suite) and it becomes a tested component. Composing strategies from existing parts is a possible later phase, not now. |
| 7 | **Edits live in versioned, named config profiles**, never in the repository's config files. A run is started with a profile; its content hash enters the run's config hash, so every run stays reproducible. The repository's configs remain the defaults a profile starts from. |
| 8 | **Stream B builds it, after T16**, so the calibration work (T15b) is not delayed. |
| 9 | **Three phases:** 1 run and monitor (T17a), 2 results dashboard (T17b), 3 administration and config profiles (T17c). |
| 10 | **Read-only settings domains:** costs, data derivation and parity are shown in full but not editable in a profile; changing them is a data task (UI_spec §8). |
| 11 | **Themes:** dark and light, switchable, both as drawn on the canvas. |

## 3. Ownership

New paths for stream B: `src/strategy_factory/api/` (the FastAPI app) and `ui/` (the React app,
with its own `package.json` and lockfile). `pyproject.toml`, `uv.lock` and `ownership.yaml` are
stream A's (D-357): stream A adds the backend dependencies (FastAPI, uvicorn, and an SSE helper if
one is used — options with pros and cons to the user first, per his standing preference) and assigns
the two paths, in one small PR before T17a starts.

## 4. Prerequisite from stream A: progress reporting

Today a stage reports only when it finishes. Live progress needs the stages to report **during** the
run. Stream A adds, as a short task of its own:
- a progress-event contract: funnel run started / stage started / work units done n of N (with
  elapsed time and an estimate of the remainder) / stage finished (with its timing) / failed (with
  the reason) — for the real arm and the control arm separately;
- where events are written so a separate process can read them while the run is going (a registry
  table or an append-only file under the artifacts root — a plan question for stream A, with options);
- no effect on any result: a test that a run's artifacts and ids are identical with and without
  progress reporting.

## 5. T17a — Run and monitor (phase 1)

Screens (canvas): Overview skeleton, New funnel run, Live monitor, Run history, Downloads; the shared shell (sidebar, top bar, banners, themes). UI_spec §0, §1, §2, §5 (Downloads).


- **Start a funnel run** from the UI: choose the funnel config (and, once T17c exists, the profile),
  the data source (real, null, planted), control on or off (off is flagged, D-653). The backend starts
  the orchestrator as a separate process and returns its funnel run id.
- **Live view of a run:** every stage of both arms, with a progress bar, units done, elapsed time,
  estimated time remaining, and the stage's final timing; the current stage highlighted; failures
  shown with their reason; resume a failed run (the orchestrator's content-addressed resume).
- **Run history:** every funnel run with its source, profile, start and finish, total time, per-stage
  counts (real against control), and status; filter and search.
- **Look and feel:** dark and light themes, a consistent colour system, responsive layout; a design
  that reads as a professional analytics product, not a default template.
- **Tests:** backend endpoints with the registry and progress events faked; the SSE stream delivers
  events in order and resumes after a reconnect; frontend component tests for the progress view; one
  end-to-end check that starts a tiny synthetic funnel and watches it finish.
- **Acceptance:** start, watch, fail, resume, and browse history of a real funnel run from the UI;
  the server refuses non-local connections (tested).

## 6. T17b — Results dashboard (phase 2)

Screens (canvas): Overview complete, Funnel explorer, Candidates, Candidate detail, Stage 1 edge map, Compare runs, Calibration, Strategy library and detail (read-only), Symbol explorer, Costs, System. UI_spec §1, §3, §4, §5, §7.


Per funnel run and across runs: the funnel table (real against control and, for synthetic runs,
against the truth); per-stage pass rates and failing criteria; per-candidate pages with the lineage,
stage 1's probes and ESS, stage 2's grid heatmap and family score, stage 3's surfaces with the
plateau and SPP, zero-cost against after-cost; equity curves, drawdowns and the metric set of spec
§metrics. Every number read from the artifacts and the registry, never recomputed. Designed with the
user before its task file.

## 7. T17c — Administration and config profiles (phase 3)

Screens (canvas): Config profiles, Profile editor; the strategy library becomes editable. UI_spec §6, §8.


Profiles: create from the defaults, edit, compare two profiles, duplicate, version history, and see
which runs used each. Editors for strategies per stage (enable, parameters, grids), gates, universes,
costs and executor settings, each validated by the same pydantic models the pipeline uses, so an
invalid profile can never be saved. The config-resolution change that lets a run use a profile is
stream A's (`core/`), done before T17c. Designed with the user before its task file.

## 8. Raise, do not decide (T17a plan)

- The SSE helper, the process model for starting runs, and the frontend build and dev setup — each
  with options, pros and cons and what it means for the repository, for the user to choose.
- How the UI is started (one command that serves both backend and the built frontend is the goal).
- Anything the progress contract (§4) cannot give that the live view needs.
