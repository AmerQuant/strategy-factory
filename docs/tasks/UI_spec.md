# Strategy Factory UI — page specification and settings inventory

Companion to `docs/tasks/T17_admin_ui.md`. The visual direction is the approved mockup canvas
(four key screens: Overview, Live monitor, Candidate detail, Profile editor). This document fixes
**what every page shows and does**; T17a/b/c implement it phase by phase.

Conventions used below
- **Data** names where each number comes from: `registry` (PostgreSQL tables), `artifacts`
  (`summary.json` and friends under the artifacts root), `catalog` (the data store's catalog),
  `configs` (the repository defaults), `profiles` (T17c). The UI never recomputes a result; it reads it.
- **Chart** says which library draws it: **E** = ECharts (dashboards, metrics), **P** = Plotly.js
  (scientific: surfaces, heatmaps, distributions).
- **Phase** 1 = T17a, 2 = T17b, 3 = T17c.
- Every list page has search, filters, sortable columns, column chooser and CSV export. Every page
  has a stable URL, so a view can be bookmarked. Dark and light themes.

## 0. Global

- **Sidebar:** Overview · Runs · Results · Strategies · Data · Settings · System; the active profile
  and the server status (127.0.0.1) at the bottom.
- **Top bar:** page title and breadcrumb, global search (symbols, runs, candidates, strategies), the
  "New funnel run" button, a notifications bell (run finished, run failed, stage finished).
- **Banners that follow the data, never dismissable while true:** calibration pending (T15b), the
  D-802 parity gap, synthetic data, `--no-control`.

## 1. Overview (phase 1 skeleton, phase 2 complete)

| block | content | data | chart |
|---|---|---|---|
| KPI row | stage-3 candidates (1D, 1H unconfirmed); control passes; calibrated-null false-positive rate against the 1 % target (D-656); open calibration items | registry, artifacts, A.md-derived list in config | — |
| Funnel | per stage: real, calibrated null, reshuffled control; per timeframe toggle | artifacts | E bars |
| Running now | the live funnel's current stage, progress, elapsed, remaining; the queue | progress events | E progress |
| Data quality | ok / warning / critical per timeframe | catalog | E donut |
| Universe | symbols in scope per market and timeframe | configs, catalog | E bars |
| Recent runs | last 10 funnel runs with source, stage-3 count, wall time, status | registry | — |

## 2. Runs

### 2.1 Launch (phase 1)
A four-step wizard: **Profile** (default or a saved one, with its hash) → **Source** (real, calibrated
null with seed, planted with ladder and seed) → **Scope** (timeframes; broker universe or a symbol
list; stages to run, 1–3 today) → **Control** (on by default; turning it off shows the D-653 warning).
A final review screen shows the resolved config and its hash before "Start". Refuses to start what the
CLI would refuse, with the same message.

### 2.2 Live monitor (phase 1)
As in the mockup: header with source, profile, control; summary (started, elapsed, remaining, stage
runs done); the timeline of every stage run (stage × timeframe × arm) with status, progress bar, units
done / total, elapsed and final duration; the live log; the queue with estimates. Actions: stop,
resume a failed run, open the report when finished. **Chart:** E Gantt of stage runs over wall time.

### 2.3 History (phase 1)
Every funnel run: id, name, source, profile and hash, code version (dirty flagged), start, finish,
wall time, per-stage counts real / control, status. Filters: source, profile, status, date. Row
actions: open, open report, reproduce (shows `sfac funnel reproduce` result), compare with another.

## 3. Results

### 3.1 Funnel explorer (phase 2)
One run: a **Sankey** of symbols → profiles → methods → candidates (E), real against control side by
side; per stage the failing gate criteria by frequency (E bars); for synthetic runs, found against
planted truth (precision, recall per ladder cell).

### 3.2 Candidates (phase 2)
Table of every candidate that reached stage 3 (passed and failed): symbol, timeframe, direction, edge
type, method, parameters, gate verdict and failing criterion, plateau area, stability, SPP median,
half-2 check, cost retention, flags (boundary, unconfirmed, splice, quality warning). Row → candidate
detail.

### 3.3 Candidate detail (phase 2)
As in the mockup, plus tabs:
- **Summary:** lineage cards, stage-3 KPIs, caveats.
- **Stage 1:** the probe table (percentile, p, BH q, PF after cost, positive-year share), the ESS
  breakdown (four components, raw and points) — E radar for ESS, E bars for probes.
- **Stage 2:** the coarse-grid heatmap (P), family score components, rank, overlaps with the other
  selected methods (E matrix).
- **Stage 3:** half-1 and half-2 surfaces with plateau outline and selected cell (P heatmap, and P 3-D
  surface for two-parameter methods), zero-cost surface and the shift, SPP histogram with p5/median/p95
  (P).
- **Performance:** equity curve with and without costs, drawdown against initial capital (the user's
  convention), underwater time, monthly returns heatmap, trade distribution, MAE/MFE scatter, yearly
  table (E except the heatmap). Metrics panel: spec §metrics set.
- **Trades:** the trade list with entry/exit, reason, P&L, costs; click a trade → symbol explorer at
  that date.

### 3.4 Stage views (phase 2)
- **Stage 1:** universe heatmap symbol × edge type × direction coloured by ESS (P); pass rate by
  quality status and timeframe (T12's requirement); probe pass frequencies.
- **Stage 2:** methods leaderboard across profiles (how often each method is selected, family-score
  distribution), the user's suite against the library.
- **Stage 3:** pass/fail by criterion, plateau-area and stability distributions, cost-retention
  distribution.

### 3.5 Compare runs (phase 2)
Two runs side by side: counts per stage, candidates in one and not the other, metric deltas for
candidates in both, the profile diff that separates them. The main use: before and after calibration.

### 3.6 Calibration (phase 2)
False-positive rate on the calibrated null per stage and timeframe against the target; power curves on
the planted ladder per edge type and strength (E lines); seed-to-seed spread; the calibration list with
status.

## 4. Strategies (phase 2 read-only, phase 3 editable)

### 4.1 Library
Every probe (stage 1) and method (stage 2, 3): name, stage, edge type, directions, parameters with
their grids and fine steps, warm-up, source (library / the user's suite with rule number), enabled in
the active profile, how often selected historically. Filters by stage, edge type, source.

### 4.2 Strategy detail
Definition text (and, for the user's rules, the Pine source line it came from), parameters and grids,
exits in force per stage; **signal preview**: pick a symbol and a cell, see entries and exits on the
price chart (E candlestick) — computed by the backend with the same component code, read-only; its
historical results across runs.

## 5. Data

| page | content | chart | phase |
|---|---|---|---|
| Universe | every symbol: market, timeframes, broker mapping (Moneta symbol), cost profile, reference kind (raw, clean, trimmed, window), quality, D-008 eligibility | — | 2 |
| Symbol explorer | price chart per timeframe with markers for repaired bars, splice boundaries, verified events (e.g. SNB 2015), trimmed spans, the holdout boundary; quality events list; snapshot lineage | E candlestick | 2 |
| Data store | snapshots and references per source and timeframe, versions, hashes, quality summary, quarantine folders | E bars | 2 |
| Costs | per symbol: hourly spread table (with the week-open key), commission, swap, conversion | E heatmap, bars | 2 |
| Downloads | coverage per instrument and month (bid/ask), missing months, D-661 windows, last write time — the Dukascopy view the user needed | E calendar heatmap | 1 |

## 6. Settings (phase 3)

- **Profiles:** list, create from defaults, duplicate, rename, version history, diff two versions or two
  profiles (field-level), which runs used each version.
- **Editors:** one per settings domain (§8). Each field shows its type, allowed range, the default and
  whether it differs; invalid values are refused as you type, using the same pydantic models as the
  pipeline. "Validate" resolves the whole profile exactly as a run would. Saving creates a new version;
  nothing is ever overwritten.

## 7. System (phase 2)

Registry and database status and size; disk usage of raw, store and artifacts; executor settings and
the P-104 core budget; CPU and memory while a run is going; the log viewer with filters; version of the
code (commit, dirty flag) and of every dependency.

## 8. Settings inventory — what a profile may change

| domain | repository source | in a profile |
|---|---|---|
| Stage 1 | `configs/stages/s01_edge.yaml` — probes on/off, baseline simulations, ESS constants, significance scale | editable |
| Stage 2 | `configs/stages/s02_screen.yaml` — methods on/off, coarse grids, family-score constants | editable |
| Stage 3 | `configs/stages/s03_entry.yaml` — fine-grid margin, cell cap, smoothing, plateau rules | editable |
| Gates | `configs/gates/default.yaml` — every threshold of every stage | editable |
| Engine | `configs/engine/default.yaml` — capital, notional, disaster stop, ATR length, intrabar mode | editable |
| Executor | `configs/executor` — workers, threads, efficiency-mode opt-out, batch sizes | editable (operational, not hashed) |
| Universe scope | pipeline `symbols` / `universe_filter`, symbol lists | editable |
| Synthetic data | `configs/synthetic/` — null model, seeds, planted ladder | editable |
| Funnel | `configs/funnel/` — timeframes, stages, control | editable |
| Report | report settings (sections, language fixed Persian for the HTML report) | editable |
| Costs | `configs/costs/` — Moneta profiles, mapping, overrides | **read-only view** |
| Data derivation | `configs/data/` — quality thresholds, cleaning, relisting, Dukascopy, aux series, calendars, verified events | **read-only view** |
| Parity | `configs/parity/` | **read-only view** |

Why three domains are read-only: they decide how the **stored data** is built. Changing one does not
change a run; it requires re-deriving snapshots (a data task with its own review), so an edit in a run
profile would silently not apply, or would apply to some runs and not others. They are shown in full so
the user can see what is in force.

## 9. Mockups still to draw

Launch wizard, History, Funnel explorer, Candidates list, Stage-1 universe heatmap, Compare runs,
Calibration, Strategies library, Strategy detail with signal preview, Symbol explorer, Costs, Downloads,
Profiles list and diff, System. Light-theme variant of the four drawn screens.
