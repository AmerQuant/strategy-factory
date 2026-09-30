# T17a-FE plan — admin UI phase 1, frontend first

Plan for `docs/tasks/T17a_ui_frontend.md` (D-403), with `docs/tasks/T17_admin_ui.md` (decisions
D-676 … D-686, recorded from its §2) and `docs/tasks/UI_spec.md` (the authority for layout and look).
Stream B's UI session, worktree `StrategyFactory_UI`, branch `b/ui-T17a-frontend`, decision ids
D-780 … D-799. **Nothing is built until "Plan approved" and the library choices of §3.**

## 1. What gets built

Everything under `ui/` (its own `package.json` and lockfile); outside `ui/` only
`docs/streams/B_ui.md`, the review and the screenshots.

| screen | UI_spec | phase-1 content | contract source (T17a-FE §3) |
|---|---|---|---|
| Shell | §0 | sidebar (Overview · Runs · Results · Strategies · Data · Settings · System; phase-2/3 entries disabled with their phase), top bar with title and breadcrumb, "New funnel run", banners that follow the data (synthetic data, `--no-control`; the other two see Q9), server status, dark/light switch remembered | `GET /api/funnel-runs` |
| Overview (skeleton) | §1 | **Running now** (current stage, progress, elapsed, remaining, queue) and **Recent runs** (last 10); the KPI, funnel, data-quality and universe blocks as labelled phase-2 placeholders | list + summary + SSE |
| New funnel run | §2.1 | wizard: Profile (disabled until T17c, shows "defaults") → Source (real / null + seed / planted + seed) → Scope (from the chosen funnel config, read-only; Q3) → Control (on by default; off shows the D-653 warning) → Review → Start; the server's refusal shown verbatim | `GET /api/configs`, `POST /api/funnel-runs` |
| Live monitor | §2.2 | header (source, profile, control), summary (started, elapsed, remaining, stage runs done), timeline of every stage run (stage × timeframe × arm from `plan`) with status, progress bar, units done / total, elapsed, ETA, final duration, "reused" badge; current stage highlighted; failures with `error_kind` and message; the event log (unknown `type`s shown, not dropped); resume on a failed run; **E Gantt** of stage runs over wall time | summary + SSE + `POST …/resume` |
| Run history | §2.3 | table: id, source, profile, start, finish, wall time, per-stage counts real / control, status; filters (source, status, date range), search, sortable columns, column chooser, CSV export; URL holds the filters | `GET /api/funnel-runs` |
| Downloads | §5 | **see Q1** — no endpoint in the contract | — |

Core pieces, independent of the library choices:

- **`api/contract.ts`** — the §3 types, written once; the mock and the client both import them, so
  the mock cannot drift from the contract without a type error.
- **The run reducer** — a pure function `(RunState, Event) → RunState`. It ignores any `seq` it has
  already applied, so replaying the whole history after a reconnect (§3.2: "a client with no id
  receives the whole history") cannot duplicate or lose progress. Everything the live view shows is
  derived from it. Unit-tested event by event, including a replay from every cut point.
- **The mock API** — serves the six endpoints of §3.3 and replays event streams on a compressed
  clock (a speed factor, e.g. one real minute = one mock second), honours `Last-Event-ID`, and can be
  told to drop a connection mid-stage and to fail a stage. Fixtures: the planted funnel with T15a's
  real timings (Q6), a failed-and-resumed run, a run with the control off, plus one run with an
  unknown event type. Dev and tests only; the production build never contains it (checked by a test
  that greps the built bundle).
- **Theme** — Mantine theme from the tokens (Q7): both schemes, the colour roles of T17 §1a (teal
  actions/done, blue real, amber null/warnings, violet planted/user rules), Manrope and JetBrains
  Mono (numbers in tabular mono everywhere).

## 2. Tests and acceptance (T17a-FE §5)

- Lint, format check, type check (`tsc --noEmit`, `strict` plus `noUncheckedIndexedAccess`).
- Unit: reducer (order, duplicates, gaps, unknown types, unknown fields, reused stage runs, resume),
  ETA / duration formatting, the mock's replay and `Last-Event-ID` handling.
- Component: the live monitor's stage row and timeline for each state (pending, running, finished,
  reused, failed), the D-653 warning, the history filters.
- End-to-end, one test on the mock: start a run → watch it → force a reconnect mid-stage (progress
  neither jumps back nor repeats) → a stage fails → resume → the run finishes.
- Screenshots of every phase-1 screen in both themes, in `docs/reviews/T17a-FE/`, checked against
  `UI_spec.md` in the review.
- Python CI untouched. The review states the exact commands stream A's `ui` CI job should run.

## 3. Library choices — the user's (T17a-FE §4)

No option is picked here. "Repo" = what lands in the repository; "BE" = the effect on T17a-BE.

### 3.1 Build tool and dev server

| option | pros | cons | repo / BE | implementation |
|---|---|---|---|---|
| **Vite** (+ `@vitejs/plugin-react`) | the de-facto standard for a React SPA; instant dev server, HMR; a dev proxy for `/api` built in; output is plain static files | none significant for an SPA | `ui/vite.config.ts`, `ui/index.html`; BE serves `ui/dist` | `npm run dev` / `npm run build`; later `server.proxy['/api'] → 127.0.0.1:<be port>` |
| **Rsbuild** (Rspack) | very fast builds, webpack-compatible plugins | smaller ecosystem; fewer examples with Mantine/Vitest | same shape as Vite | `rsbuild.config.ts`; same proxy idea |
| **Next.js** (static export) | routing and conventions included | server-oriented; static export drops much of it; a second server concept next to FastAPI | `next.config`, `app/` tree; BE serves `out/` | fights the "FastAPI is the server" decision (D-676) |

### 3.2 Package manager

Node **v26.5.1** (a "Current" release, not LTS) and npm **11.17.0** are installed. The Dukascopy tool
(`tools/dukascopy`, dukascopy-node 1.50.0) declares no Node engine range and runs on v26.5.1 today
(T04b, T04j), and it uses **npm** (`npm ci --ignore-scripts`). pnpm is not installed, and Node 25+ no
longer bundles corepack.

| option | pros | cons | repo / BE |
|---|---|---|---|
| **npm** | already here; the same tool as `tools/dukascopy`; nothing to install | slower installs; flat `node_modules` | `ui/package-lock.json` |
| **pnpm** | fast; strict dependency graph (no phantom imports); disk-efficient | a second tool to install and pin (no corepack on Node 26) | `ui/pnpm-lock.yaml`; the CI job installs pnpm |
| **Bun** | fastest install; can also run tests | another runtime; its Windows support and Vitest/Playwright interplay less proven | `ui/bun.lock` |

Also a choice: pin Node with `engines` in `ui/package.json` (+ `.nvmrc`), and whether to target the
current v26 or move to an LTS line.

### 3.3 Routing (every page needs a stable URL, UI_spec conventions)

| option | pros | cons | implementation |
|---|---|---|---|
| **React Router v7** (library mode) | the most used; simple; stable | search params are untyped strings — filters in the URL need hand-written parsing | `createBrowserRouter([...])`, `useSearchParams` |
| **TanStack Router** | fully typed routes and **typed, validated search params** (the history filters live in the URL); pairs with TanStack Query | younger; more concepts; a code generator for file routes (or code routes) | `createRoute({ validateSearch })` per page |
| **Wouter** | tiny | no nested layouts or search-param tooling; more hand work | `<Route path>` |

BE effect for all: the server must answer any non-`/api` path with `index.html` (SPA fallback).

### 3.4 Server state, and SSE on the client

Server state:

| option | pros | cons |
|---|---|---|
| **TanStack Query** | caching, refetch, loading/error states, mutations (start, resume) with invalidation; widely used | one more concept; SSE lives beside it (the reducer), not in it |
| **SWR** | smaller, simple | weaker mutation story |
| **RTK Query** (Redux Toolkit) | one store for everything | Redux weight for a small app |
| **plain `fetch` + hooks** | no dependency | caching, retries and states by hand |

SSE transport (the reducer of §1 is the same under all three):

| option | pros | cons |
|---|---|---|
| **native `EventSource`** | no dependency; the browser reconnects by itself and sends `Last-Event-ID` automatically — exactly §3.2 | GET only, no custom headers (none needed: local, no auth); a *new* `EventSource` (page reload, manual reconnect) cannot set `Last-Event-ID` — it then replays the whole history, which the seq-dedup reducer absorbs (see Q4) |
| **`@microsoft/fetch-event-source`** | fetch-based: headers, custom retry, can set `Last-Event-ID` on any reconnect | a dependency; its reconnect logic is ours to configure; last release is old |
| **`eventsource-parser` over `fetch`** | full control, small | we write the reconnect loop |

BE effect: none — the server speaks the same SSE either way (`sse-starlette` or a hand-written
`StreamingResponse` is T17a-BE's choice).

### 3.5 The mock layer

| option | pros | cons | repo / BE |
|---|---|---|---|
| **MSW 2** (Mock Service Worker) | one set of handlers for browser, component tests and Node; has an `sse()` API; switched off by one flag; production-excluded via a dynamic import | runs in a service worker, so the "network" is simulated — a real TCP drop / real `Last-Event-ID` reconnect is emulated, not real; `ui/public/mockServiceWorker.js` is committed | BE switch = do not start the worker |
| **A mock HTTP server as a Vite dev-server plugin** (Node middleware, the same process as `npm run dev`) | real HTTP and real SSE: the browser's own reconnect and `Last-Event-ID` are exercised; the switch to T17a-BE is just the proxy target | tied to the dev server; component tests need a separate stub (or fetch it over HTTP) | BE switch = proxy `/api` to FastAPI instead |
| **A standalone mock server** (e.g. Hono or Express, `npm run mock`) | real HTTP; independent of the build tool; the e2e test starts it like the real backend | one more process; two commands in dev | BE switch = start FastAPI instead |

Contract types are shared with the mock under every option (§1). Optional, also a choice: runtime
validation of responses with **zod** (catches a BE mismatch at the boundary; a dependency) or
TypeScript types only.

### 3.6 Test runner, component tests, end-to-end

| layer | options (pros / cons) |
|---|---|
| unit + component runner | **Vitest** — shares the Vite config, fast, Jest-compatible API (natural with Vite, workable with others) / **Jest** — the old default; needs Babel/ts-jest and ESM configuration |
| component rendering | **React Testing Library on jsdom or happy-dom** — fast, standard; no real layout (canvas charts not rendered) / **Vitest browser mode** (real Chromium via Playwright) — real layout and charts; slower, needs browsers |
| end-to-end | **Playwright** — multi-browser, auto-wait, screenshots (the review's screenshots come from it, both themes), traces; downloads ~300 MB of browsers once (`npx playwright install chromium` is enough) / **Cypress** — good runner UI; Chromium-family focus, heavier, screenshots too |
| lint / format | **ESLint + Prettier** (typescript-eslint, react-hooks) — the standard pair; two tools / **Biome** — one fast tool for both; fewer rules (no react-hooks equivalents of every rule) |

Repo: config files in `ui/` only. BE: the e2e test later runs against FastAPI with the same spec by
switching its base URL.

### 3.7 Charts in phase 1 (the Gantt and the progress bars; ECharts per D-678)

**`echarts-for-react`** (a thin wrapper, popular, lags ECharts releases) or **a small own wrapper**
around `echarts/core` with tree-shaken imports (~40 lines, full control). Plotly is not needed in
phase 1.

### 3.8 Fonts (Manrope, JetBrains Mono)

**Bundled with `@fontsource`** (works offline, as a local app should; adds ~100–300 KB to `dist`) or
**Google Fonts** at runtime (smaller build; the app then needs the internet to look right).

### 3.9 How the built frontend is served in T17a-BE (goal: one command)

| option | pros | cons | implementation |
|---|---|---|---|
| **FastAPI serves `ui/dist`** (`StaticFiles` + SPA fallback) | one process, one port on 127.0.0.1; `sfac ui` starts everything | Node is needed to build `dist` after a UI change; `sfac ui` must detect a missing or stale `dist` | `sfac ui` → uvicorn on `127.0.0.1`; `npm run build` first (or `sfac ui --build` runs it) |
| **Build into the Python package** (`dist` copied to `src/strategy_factory/api/static/` at build) | installs as one package; no Node at run time | build output in `src/` (git-ignored, but a build step before `uv sync`); `pyproject.toml` (stream A's) must include it | a build hook or script |
| **Dev mode: two processes, one launcher** (Vite dev server proxying `/api` to uvicorn) | hot reload while developing | two ports; not the production shape | `sfac ui --dev` starts both |

Options 1 and 3 combine naturally (production = 1, development = 3).

## 4. Contract gaps found while mapping the screens (raise, not extend)

Stream A builds to the §3 text, so none of these is added by me; each needs the supervisor's word.
Numbered Q-items are also in the stop report.

- **Q1 — Downloads.** T17 §5 puts the Downloads page (UI_spec §5, the Dukascopy coverage calendar) in
  T17a; T17a-FE §2 does not list it and §3.3 has no endpoint for it. In or out of T17a-FE? If in, it
  needs an endpoint shape.
- **Q2 — Stop.** UI_spec §2.2 lists a "stop" action; §3.3 has no stop endpoint. Show it disabled?
- **Q3 — Wizard vs `POST`.** UI_spec §2.1's wizard has a planted **ladder**, **timeframes**, universe
  or symbol list, stages 1–3, and a review with the **resolved config and its hash**; the `POST` takes
  only `{config, source, seed, control}` and there is no resolve endpoint. Proposal: in phase 1 the
  scope comes read-only from the chosen funnel config, the ladder from the config, and the review
  shows what `GET /api/configs` returns. Also needed: the shape of `GET /api/configs` items, and the
  shape of a refusal ("with the same message as the CLI" — e.g. HTTP 422 `{error_kind, message}`).
- **Q4 — Reconnect semantics.** A browser reconnect sends `Last-Event-ID` itself; a *fresh*
  connection (reload, second tab) cannot set that header with the native `EventSource`, so it gets the
  whole history (the reducer deduplicates). Enough, or should the server also accept
  `?last_event_id=`?
- **Q5 — Resume.** Does `POST …/resume` return the **same** `funnel_run_id` (events continue its
  `seq`, a second `funnel_started`?) or a new one linked to the old? And how does the UI know a stage
  run was *reused* — only by seeing a `stage_run_id` it already knows, or a `reused: true` field?
- **Q8 — List and summary shapes.** §3.3 names the endpoints but not their bodies. History needs a
  status enum (running, finished, failed, …), finish time, wall time, per-stage `n_in`/`n_passed` per
  arm, and UI_spec §2.3 also wants a run **name**, **profile hash** and **code version (git SHA, dirty
  flag)** that no event carries. Also the filter/sort/search/page parameter names.
- **Q9 — Shell data without a source.** Server status (a `GET /api/health`?), the notifications bell
  (can be derived from SSE of running runs only), global search (phase 2?), the "calibration pending"
  and "D-802 parity gap" banners (no endpoint), the monitor's **queue estimates** for stages not yet
  started (no source — show "pending" without an estimate?), "open the report" (no report URL), and
  History's reproduce / compare / open report (phase 2 — disabled?).

Other questions (not contract):

- **Q6 — T15a timings.** T17a-FE §2 gives 1D s01 13/12 min, s02 15/16, s03 7/7; 1H s01 29/27, s02 6,
  then "…". The rest (1H s02 control, 1H s03 real/control, and the funnel's total) is not recorded in
  the repository. Please supply them, or I mark those fixture values as illustrative.
- **Q7 — Theme tokens.** T17a-FE §2 says "from `UI_spec.md`'s tokens", but `UI_spec.md` has none;
  T17 §1a gives only colour *roles* and fonts, and the canvas cannot be opened from here. Exact values
  (hex per role and scheme, radius, border, spacing) are needed — an export from the canvas, or
  permission to derive values from the §1a description (inventing, which the task forbids).
- **Q10 — Installs.** `npm install` (and Playwright's browser download) reach the npm registry and a
  CDN. May this session run them, or should I write a PowerShell script for the user (D-031)?

## 5. Runbook

1. (done) `B_ui.md`, task files and D-676 … D-686 committed on `b/ui-T17a-frontend`.
2. On "Plan approved" + the §3 choices: scaffold `ui/` with the chosen tools; `contract.ts`; theme.
3. Tests first: reducer, mock replay, then the components, then the e2e spec.
4. Mock and fixtures; shell; history; launch; live monitor with the Gantt; overview skeleton.
5. Acceptance commands, screenshots in both themes, `acceptance-reviewer`, fixes.
6. `docs/reviews/T17a-FE_review.md` (with the CI commands for stream A), push the branch, PR; stop
   for "Approved. Merge".
