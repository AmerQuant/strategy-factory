# T17a-FE — Admin UI phase 1, frontend on a mock API — review

Branch `b/ui-T17a-frontend` (stream B's UI session, worktree `StrategyFactory_UI`). Task
`docs/tasks/T17a_ui_frontend.md`; plan `docs/tasks/T17a-FE_plan.md` (its §0 records the approval);
decisions **D-760 … D-770** (T17 §2) and **D-771 … D-788** (library choices, the user's; answers
Q1–Q10, the supervisor's). **Stopped for "Approved. Merge".**

Everything is in `ui/`, except these docs, the screenshots and the decisions log rows. No Python
changes, and `ruff check .` and `ruff format --check .` pass with `ui/` present.

## 1. What was built

| screen (UI_spec) | built | contract source |
|---|---|---|
| Shell (§0) | Sidebar with the navigation of all three phases; later entries are disabled and tagged with the phase that brings them (Downloads: T17a-BE, D-779). Top bar with title, breadcrumb and "New funnel run". Global search and the notifications bell are disabled (phase 2, D-787). The `/api/status` banners are shown and cannot be dismissed. Server status and version. Dark/light switch, remembered. | `GET /api/status` |
| Overview skeleton (§1) | **Running now**: the current stage, units, progress, elapsed, remaining, the funnel's stage runs done, and the queue. **Recent runs**: the last 10, with source, stage-3 passes real/control, wall time and status. KPI row, Funnel, Data quality and Universe are labelled phase-2 placeholders. Synthetic-data and `--no-control` banners appear while the running run has them. | list + SSE |
| New funnel run (§2.1) | Profile (defaults; profiles are T17c) → Source (real / null + seed / planted + seed) → Scope (the funnel config; stages, timeframes, universe, ladder and hash shown read-only, D-781) → Control (on by default; off shows the D-653 warning) → Review (the request as sent) → Start. A refusal is shown verbatim as `error_kind: message`. | `GET /api/configs`, `POST /api/funnel-runs` |
| Live monitor (§2.2) | **Header**: name, id, status, source, profile, control, config id and hash, code version (dirty flagged). **Actions**: Stop (with confirmation, D-780), Resume (failed or stopped, D-783), Open report (disabled, phase 2). **Summary**: started, elapsed (wall and compute), remaining, stage runs done. **Timeline** of every stage run in the plan, grouped by timeframe: status, progress bar, units done/total, unit kind, elapsed, ETA or final duration, passes n_passed/n_in, a "reused" badge, the failure reason. The current stage is highlighted. **E Gantt** of stage runs over wall time, including earlier failed or stopped attempts. **Queue**: waiting stage runs, "no estimate" (D-787). **Live log**: every event except `progress`; unknown types are shown and marked. It also shows delivery counters (applied, duplicates dropped, gaps), the connection state and the reconnect count. | summary + SSE + `POST …/stop`, `…/resume` |
| Run history (§2.3) | All runs. Columns: id, name, source (+ seed), profile, config + hash, code (dirty flagged), started, finished, wall time, passes per stage real/control, status. **Server-side filters**: source, status, start-date range. **Client-side**: search (name, id, config, commit) and sortable columns. Also a column chooser, CSV export, and a row menu (Open; Open report, Reproduce and Compare disabled, phase 2). The URL holds every filter, the sort and the hidden columns. | `GET /api/funnel-runs` |
| Downloads (§5) | Disabled nav entry (D-779). | — |

### Core pieces

- **`src/api/contract.ts`**: §3 written once as zod schemas. The client validates every HTTP response and every event with them. The mock builds its responses from the inferred types.
- **`src/run/reducer.ts`**: a pure `(RunState, events) → RunState`.
  - It drops any `seq` already applied, and events of another run.
  - It counts gaps.
  - It keeps unknown types in the log.
  - A reused stage keeps its original wall times and numbers.
  - A failed or stopped attempt is kept for the Gantt, and the stage is re-queued clean on `funnel_resumed`.
  - A terminal funnel event leaves no stage "running".
  - Events are applied in batches (one copy per batch), so replaying a long history stays linear.
- **`src/run/runStream.ts`**: the browser's `EventSource` (D-773).
  - The first connection carries no id. A reopen (after a resume, or on returning to the monitor) carries `?last_event_id=<last applied seq>` (D-782).
  - A drop is left to the browser's reconnect.
  - If the browser gives up on a run that has not ended, the client reopens after 1 s with `?last_event_id=`.
  - The stream is closed after the run's last event.
  - An event that breaks the contract is recorded, not applied.
- **`src/mock/`** (dev and tests only):
  - `sim.ts` simulates one funnel run on a compressed clock (stage runs in plan order, progress at most once per simulated second, failure injection, stop, resume with reuse).
  - `backend.ts` implements §3.3 with the fixtures and illustrative refusals: 422 unknown config / seed required / no planted ladder; 409 a run in progress / not resumable / not running.
  - `stream.ts` implements the SSE logic (§3.2).
  - `handlers.ts` holds the MSW handlers.
  - `browser.ts` starts MSW and exposes `window.__sfacMock`: speed, drop connections, fail the next stage, and the recorded connections.
- **Fixtures** (D-784):
  - **T15a planted pilot**, with the real timings: 1D s01 13/12 min, s02 15/16, s03 7/7; 1H s01 29/27, s02 real 6.
  - Failed-and-resumed (null, seed 7; 1H s01 real crashes, resumed the next morning).
  - Real with the control off.
  - A smoke run carrying an unknown event type (`checkpoint_written`).
  - A stopped run.
  - Everything not measured is marked **ILLUSTRATIVE** in `fixtures.ts`: 1H s02 control, 1H s03, every count, the `funnel_default` config's timings, names, hashes, the ladder and the banner texts. Replace from `docs/streams/A.md` after the next run.
- **Theme** (`src/theme/`): every colour, radius, size and font from `UI_tokens.md` (D-785), exposed as `--sf-*` CSS variables per scheme through Mantine's `cssVariablesResolver`. Mantine's own variables are mapped onto the tokens. Fonts are bundled (D-777).
- **`src/charts/EChart.tsx`**: the thin ECharts wrapper (D-776). It uses `echarts/core` with tree-shaken imports, and handles the theme per scheme, resize on the next frame, and dispose.

## 2. How each acceptance criterion is tested (T17a-FE §5)

| criterion | test | result |
|---|---|---|
| lint | `npm run lint` (ESLint + typescript-eslint strict + react-hooks) | 0 problems |
| format check | `npm run format:check` (Prettier) | clean |
| type check, strict | `npm run typecheck` (`strict`, `noUncheckedIndexedAccess`; src, e2e, scripts, configs) | clean |
| unit + component tests | `npm test` (Vitest, jsdom): **57 tests in 7 files** | all pass |
| e2e: start a run on the mock, watch it finish, reconnect mid-stage, a failure and a resume | `npm run e2e` → `e2e/run.spec.ts`, "T17a-FE start, watch, reconnect mid-stage, stop, resume, fail, resume, finish" (Chromium) | passes (47 s) |
| screenshots of every phase-1 screen, both themes | `npm run screenshots` → 26 PNGs in `docs/reviews/T17a-FE/` (§4) | written |
| Python CI green | nothing outside `ui/` but docs; ruff check and format pass | — |
| CI commands for stream A | §6 | — |

### What proves what

**Reconnect mid-stage, without duplicating or losing progress (§3.2):**
- `reducer.test.ts`:
  - "replaying the whole history after a cut at any point" (for every k, apply k events, then the whole history; the state equals one clean pass, and exactly k duplicates are dropped);
  - "never moves progress backwards when a reconnect replays older progress events";
  - "drops an out-of-order older seq and counts a gap".
- `mock.test.ts` "streams a live run, survives a drop without duplicating or losing events".
- e2e: a drop mid-stage, then the browser reconnects; units never decrease; the replayed events are counted as duplicates dropped; gaps 0; no seq appears twice in the log.

**`?last_event_id=` (D-782):**
- `runStream.test.ts` "a reopen after a resume carries ?last_event_id=" and "reopens with ?last_event_id= when the browser gives up".
- e2e: the connection after Resume carries the query.
- `mock.test.ts`: "the header wins over the query".

**Failure and resume (D-783):**
- `reducer.test.ts` "shows a failure, then a resume with reused stages and the failed attempt kept".
- `reducer.test.ts` "a funnel_failed without stage_failed leaves no stage running, and resume re-queues it clean".
- `mock.test.ts` "stop … resume keeps the id and reuses the finished stages".
- `StageRow.test.tsx` "failed: the reason shown" and "reused: flagged".
- e2e: failure → banner, the row's `error_kind` and message → Resume → finished, with the first stage reused.

**Stop (D-780):**
- `mock.test.ts`; `reducer.test.ts` "marks the interrupted stage when the run is stopped".
- e2e: Stop → confirm → status stopped, one stopped row, Stop hidden, `funnel_stopped` in the log → Resume.

**Unknown types and fields (§3.1):**
- `reducer.test.ts` "keeps an unknown event type in the log and ignores unknown fields".
- `client.test.ts` "ignores unknown fields in a response".
- Screenshot 03d.

**zod on every response (D-774):**
- `client.test.ts` "rejects a response that does not match the contract".
- `runStream.test.ts` "records an event that breaks the contract".
- `reducer.test.ts` "rejects an event of another schema version".
- `mock.test.ts`: every fixture event and response parses with the contract.

**The live view's stage row:** `StageRow.test.tsx` covers queued, running (highlighted, units, elapsed, ETA), running without an estimate, finished (duration, passes), reused, and failed (the reason; "failed" in place of a timing).

**Wizard (`pages.test.tsx`):**
- the D-653 warning on the Control step and the Review;
- the scope read-only from the chosen config;
- a synthetic source needs a seed;
- a refusal shown verbatim (409 `run_in_progress`).

**History (`pages.test.tsx`):**
- every run, newest first;
- source and status filters from the URL;
- the date range;
- search and sort kept in the URL;
- every column's content;
- a run without control shows "off".

**Shell (`pages.test.tsx`):**
- the `/api/status` banners and server status;
- later phases disabled with their phase tag;
- the theme switch changes the scheme and remembers it in `localStorage`.

**The mock is never in a production build:**
- `npm run build` ends with `scripts/check-bundle.mjs`. It fails the build if `dist/` contains MSW, its worker script, the mock backend, the fixtures or the mock's test hooks.
- A planted marker is detected.
- The worker script is served from `node_modules` by a dev-only Vite plugin, so it is neither committed nor copied into `dist`.
- `import.meta.env.DEV` removes the mock's dynamic import from the production build.

**T15a timings (D-784):** `mock.test.ts` "uses T15a's real timings for the planted funnel".

## 3. Decisions used

- D-760 … D-770: stack, Mantine, ECharts, SSE, local single user, three phases, themes.
- D-653: control off is flagged.
- D-771 … D-788: all of them.
- D-671: the calibration banner text in the mock.
- D-031 as clarified by D-788: `npm install` and Playwright's Chromium download were run by this session.

## 4. Screenshots (`docs/reviews/T17a-FE/`, `-dark` and `-light` of each)

| file | screen | checked against UI_spec |
|---|---|---|
| `01-overview-idle` | Overview, nothing running | §1: phase-1 blocks live, phase-2 blocks labelled; §0 banners |
| `01b-overview-running` | Overview with the planted pilot running | §1 Running now: stage, progress, elapsed, remaining, queue |
| `02a-new-run-source` | Wizard, Source (null + seed) | §2.1 Source |
| `02b-new-run-scope` | Wizard, Scope (read-only) | §2.1 Scope (D-781) |
| `02c-new-run-control-off` | Wizard, Control off | §2.1 Control, D-653 warning |
| `02d-new-run-review` | Wizard, Review | §2.1 review; the "resolved config and its hash" is the config's own hash (no resolve endpoint, D-781) |
| `03a-live-monitor-running` | Monitor, live planted pilot | §2.2 header, summary, timeline, Gantt, queue, log |
| `03b-live-monitor-failed` | Monitor, a stage failed | failure with reason, Resume |
| `03c-live-monitor-resumed` | Monitor, the resumed fixture | reused badges; the failed first attempt in red on the Gantt |
| `03d-live-monitor-unknown-event` | Monitor, unknown event type | shown in the log, marked "unknown" |
| `03e-live-monitor-stop-confirm` | Stop confirmation | §2.2 stop |
| `04-history`, `04b-history-filtered` | History, all runs / real sorted by name | §2.3 columns, filters, sort, column chooser, CSV |

Colours are the tokens throughout:
- real is `blue-fg`, control `amber-fg`;
- source badges REAL `blue`, NULL `amber`, PLANTED `violet`;
- done `accent`, running `blue` / `status-running`, queued `waiting`, failed `danger`;
- warnings in amber.

Page title: 26 px, weight 800. Captions: 11 px uppercase. Numbers: JetBrains Mono, tabular. The canvas itself could not be opened here; the look follows `UI_tokens.md`.

## 5. Deviations, choices and open questions (for the supervisor)

**Contract points §3 does not fix.** The mock chose each one. **Ruled (D-789):** they are now the contract, `T17a_ui_frontend.md` §3.4, with a stage run's status gaining `queued` and `planted_ladder`'s fields left to stream A.
1. **Stage-run `status` enum** in the summary: the mock uses `running | finished | failed | stopped`.
2. **The list's "per-stage-id counts real against control"**: the mock uses `stage_counts: [{stage_id, real, control}]`. `real`/`control` are passes summed over the timeframes; null when that arm finished no run of the stage.
3. **List filter parameter names**: `source`, `status`, `started_from`, `started_to` (dates, inclusive). The list is a bare JSON array: no envelope, no pagination. Search and sort are client-side.
4. **The list's order** is not fixed. The UI sorts newest first itself.
5. **Nullable fields**:
   - `started_at`, `finished_at`, `elapsed_s` in summary and list items (null while queued or running);
   - a stage run's `elapsed_s`, `n_in`, `n_passed` (null while running);
   - `funnel_stopped.stage_run_id` (null if stopped between stages).
6. **`planted_ladder`'s shape** is not fixed. The UI shows it as JSON, and the mock's shape is illustrative.
7. **An unknown run id** answers 404 `{error_kind: "not_found", message}` in the mock. §3.3 names only 409/422.
8. **`schema_version` is validated as exactly `1`.** An event of another version becomes a recorded contract error; it is not parsed as v1.
9. **SSE behaviour the client relies on:**
   - the server **closes the stream after a run's terminal event**, and at once when a client connects to a run that has already ended;
   - when both the header and `?last_event_id=` are present, **the header wins**. On the browser's own reconnect the URL still carries the id it was opened with.
   - The mock does both; T17a-BE must too.

**Not proven on the mock:**
10. **The `Last-Event-ID` header path.** Through MSW's service worker, Chrome's automatic reconnect reaches the handler with neither header nor query. The mock therefore replays the whole history, and the seq dedup absorbs it (D-782's second guard; the e2e checks exactly that). The resume from the header is unit-tested in the mock's stream logic, but must be proven end-to-end against T17a-BE's real HTTP. (The plan listed this as MSW's known limit.)
11. **Page reload.** The mock lives in the page, so a reload restarts it: live runs started from the UI disappear, and the fixtures come back.

**Colours and look** (UI_tokens has no value for these; my choices, to confirm):
12. "Stopped" is amber: the badge (`amber-bg`/`amber-fg`) and the Gantt bar (`amber`).
13. "Reused" is a neutral badge (`surface-alt`/`text-secondary`) and a dimmed bar.
14. An `info`-level banner is neutral (`surface-2`/`text-secondary`). Not used by today's data.
15. The primary button's hover is left at the accent. There is no hover token; `accent-fg` in light gave poor contrast.

**Other choices:**
16. **Wizard order.** The steps follow UI_spec §2.1: Profile → Source → Scope → Control → Review. The plan's §0 had written "Config → Source → Control → Review". UI_spec is the authority for layout.
17. **Wall time vs compute time.** History's "Wall time" is `finished_at − started_at`, so a resumed run includes the idle gap (the fixture shows 11 h 59 m). The monitor shows both (wall, and compute from `elapsed_s`).
18. **Queue estimates.** "Remaining" is the running stage's estimate; queued stages show "no estimate" (D-787).
19. **Test naming.** `docs/features.md` has no feature id for the UI, so the tests are named `T17a-FE …`. Should a feature id be added?
20. **Fixture config names and hashes** (`funnel_planted_pilot`, `funnel_default`, `funnel_smoke`) are invented placeholders. `configs/funnel/` does not exist on this branch.
21. **MSW internals.** The mock's stream cleanup uses MSW 2.15's client emitter (`Symbol.for('kClientEmitter')`), because MSW does not abort the request when the page closes its EventSource. It warns if the emitter is missing. This is pinned with MSW, and is mock-only.

**Found while building (fixed):**
- MSW's `client.error()` makes Chrome **give up** on the EventSource instead of retrying. The mock's drop now ends the stream the way a lost connection does.
- The client reopens by itself with `?last_event_id=` if the browser ever gives up on a run that has not ended.
- The embedded browser of the desktop app refuses service workers, so the mock UI must be viewed in a normal browser (or Playwright's Chromium).

## 6. Dependencies (all new, all in `ui/package.json`, exact versions, lockfile committed)

Runtime:

| package | version | why |
|---|---|---|
| react, react-dom | 19.3.0 | D-760 |
| @mantine/core, @mantine/hooks | 9.6.3 | D-761 |
| @tanstack/react-router | 1.170.40 | D-772 |
| @tanstack/react-query | 5.104.0 | D-772 |
| zod | 4.6.5 | D-774 |
| echarts | 6.1.0 | D-762, D-776 |
| @fontsource/manrope, @fontsource/jetbrains-mono | 5.3.0 | D-777 |
| **@tabler/icons-react** | 3.48.0 | **Not covered by a decision.** The icon set (nav, actions, banners). Mantine ships no icons; Tabler is Mantine's own recommendation and is tree-shaken. |

Development:

| package | version | why |
|---|---|---|
| vite, @vitejs/plugin-react | 8.3.1, 6.1.1 | D-771 |
| typescript | 6.0.3 | typescript-eslint 8.71 supports `< 6.1` (D-775) |
| msw | 2.15.0 | D-774. SSE confirmed before use. 3.0.1 was two days old |
| vitest | 5.0.3 | D-775 |
| jsdom | 30.1.1 | D-775 |
| @testing-library/react, @testing-library/user-event, @testing-library/jest-dom | 16.3.3, 14.6.7, 7.0.1 | D-775 |
| @playwright/test | 1.63.0 | D-775. Chromium only |
| eslint, @eslint/js, typescript-eslint, eslint-plugin-react-hooks, globals | 10.11.0, 10.0.1, 8.71.0, 7.1.1, 17.12.0 | D-775 (`globals`: ESLint's environment globals) |
| prettier | 3.9.9 | D-775 |
| postcss, postcss-preset-mantine | 8.5.28, 1.18.0 | Mantine's PostCSS preset (its CSS mixins/breakpoints) |
| @types/react, @types/react-dom, @types/node | 19.3.0, 19.3.0, 26.6.3 | types |

Node 26 is declared in `engines` (`>=26 <27`) and `ui/.nvmrc`; the session ran v26.5.1 with npm 11.17.0. npm 11 warns that MSW's `postinstall` is not in `allowScripts`. The script only copies the worker into a configured public folder, which this setup does not use, so it is left unapproved.

## 7. The `ui` CI job (for stream A, `.github/`)

Ubuntu, Node from `ui/.nvmrc`. Working directory `ui/`.

```bash
npm ci
npx playwright install --with-deps chromium
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm run e2e
```

- `npm run build` includes the bundle check (it fails if the mock reaches `dist/`).
- `npm run e2e` starts its own Vite dev server on 127.0.0.1:5179 with the mock (about 1 min).
- `npm run screenshots` is for reviews only; it does not belong in CI.
- Cache `~/.npm` keyed on `ui/package-lock.json`, and `~/.cache/ms-playwright` keyed on the Playwright version.

## 8. Files

- `ui/`:
  - config: `package.json`, `package-lock.json`, `.nvmrc`, `.gitignore`, `.gitattributes`, `.prettierrc.json`, `.prettierignore`, `eslint.config.js`, `postcss.config.cjs`, `tsconfig*.json`, `vite.config.ts`, `playwright.config.ts`, `index.html`, `public/favicon.svg`
  - `src/api/` (contract, client, queries)
  - `src/run/` (reducer, runStream)
  - `src/mock/` (sim, backend, stream, handlers, browser, fixtures)
  - `src/pages/` (Overview, NewRun, LiveMonitor, LiveRedirect, History)
  - `src/components/` (ui, StageRow, EventLog)
  - `src/charts/` (EChart, gantt)
  - `src/theme/` (tokens, theme, global.css)
  - `src/app/` (Shell, router, search)
  - `src/lib/format.ts`
  - `src/test/`, `e2e/`, `scripts/check-bundle.mjs`
  - tests: `src/**/*.test.ts(x)`, `e2e/*.spec.ts`
- `docs/reviews/T17a-FE_review.md` and `docs/reviews/T17a-FE/*.png` (26).
- `docs/streams/B_ui.md` (status).
- Earlier commits on this branch: the task files (`T17a_ui_frontend.md` as extended, `UI_tokens.md`), the plan's §0, and D-771 … D-788 in the decisions log.

## 9. Acceptance review

`acceptance-reviewer` ran on the finished work. Its findings were fixed as follows:

- **Checks:**
  - the format gate;
  - the bundle check now runs inside `build` and resolves its path with `fileURLToPath`.
- **New tests:**
  - Stop in the e2e;
  - the theme switch, the shell, the HTTP contract error and the history columns.
- **Contract:** `schema_version` fixed at 1, and client-side list order.
- **Reducer:**
  - terminal funnel events end any running stage;
  - a resume re-queues a stage clean.
- **Client:** a failed or stopped run is polled so a resume from elsewhere is picked up.
- **Colours:**
  - a hard-coded colour replaced with its token;
  - colour roles: the resume log line and the info banner no longer use blue (real data);
  - "stopped" is the same colour on the badge and the Gantt.
- **Fixtures:** `funnel_default`'s timings marked illustrative.
- **Mock:** a narrowed `catch`; the emitter check.
- **Tests:** an order-dependent test made independent.

The contract items it raised are in §5 (1–9).
