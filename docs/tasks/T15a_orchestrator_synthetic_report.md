# T15a — Funnel orchestrator, synthetic universes and the Persian report

**Stream A (D-611).** Plan first (D-403): draft, stop for "Plan approved", then implement. Stop
for the review before merge.
Features: the orchestrator, CLI and stage 1–3 report features assigned to T15 in
`docs/features.md`, plus the synthetic-data self-test (F-X.6 and the random-walk false-positive
self-test); the plan lists them by id.
Depends on: T12, T13, T14 (the three stages and their artifacts), T10b (executor, registry).

## 1. Why T15 is split

T15 was one task: orchestrator, report and calibration. It is split (D-652):

- **T15a (this task)** builds the machinery: one command runs the whole funnel with its control,
  the funnel can run on synthetic universes whose truth we know, and every run produces one Persian
  report. **It changes no threshold.**
- **T15b** calibrates the thresholds on the calibration list against a single target (D-656), using
  T15a's machinery, and re-runs the full scope with one command.

T15a first, because calibration re-runs every stage many times, and because the report is where the
effect of calibration will be read.

## 2. Decisions to record before implementing

Supervisor range, marked *(supervisor)*, each citing this task. Next free supervisor id: D-652.

| ID | Decision |
|---|---|
| D-652 | **T15 is split into T15a (orchestrator, synthetic universes, report) and T15b (calibration).** T15a changes no threshold; T15b depends on T15a. |
| D-653 | **Every funnel run runs its reshuffled-returns control alongside, by default** (the D-615 control, chained through the same stages). The control exposed the serious flaws of stages 1, 2 and 3 (D-618, D-629, D-647); no result is shown without it. Skipping it needs an explicit `--no-control`, which is recorded in the run row and printed on the report's first page. |
| D-654 | **Synthetic universes are a data source of the funnel, never of the store.** Two kinds: a **calibrated null** (a random walk per symbol with that symbol's drift and volatility — T12 showed the reshuffled control is conservative and the drifted random walk is the calibrated null) and a **planted edge** (a mean-reversion or trend effect of known strength injected into the null, over a ladder of strengths). Generated deterministically from a seed, held in memory or under the artifacts root, **never written to `SFAC_DATA_ROOT`** (stream B's). A synthetic run is marked as such in its run row and on every report page, and can never be mixed into a real run's results. |
| D-655 | **One self-contained HTML report per funnel run**: Plotly embedded in the file (`include_plotlyjs=True`, ADR-008), a Persian font embedded under a licence that permits it, right-to-left text with numbers, symbols and method names left-to-right, and no external request of any kind. A report must open identically offline, years later. Every number in the report is read from the artifacts, never recomputed. |
| D-656 | **T15b's calibration target, recorded now so T15a measures against it:** on the calibrated null, the share of symbols reaching the end of stage 3 is at most **1 %**; power is measured on the planted-edge ladder. The later stages (robustness, holdout, DSR) are further defences, but every false positive past stage 3 costs their compute and attention; at ~500 symbols, 1 % is about 5. |

## 3. The orchestrator

- `sfac funnel run <funnel-config>`: runs `s01_edge → s02_screen → s03_entry` per timeframe, each
  stage reading the previous stage's run through `stage_inputs`, and the control chain alongside
  (D-653). The data source is a field of the funnel config: `real` (the catalog), `null` or
  `planted` (D-654) with their seed and parameters.
- A **funnel run id** links the stage runs and the control's. How it is stored (a new registry table
  with an Alembic migration, or a parent field) is a plan question; stream A owns migrations.
- **Resume:** a failed or interrupted funnel resumes at the first unfinished stage without redoing a
  finished one; a finished stage is recognised by its content-addressed config (D-805, D-807), not by
  a timestamp.
- `sfac funnel reproduce <funnel-run-id>` rebuilds the whole chain from the registry rows.
- **Clean-up from T13 (calibration list item 9), because the orchestrator touches the same wiring:**
  `stages/screen.py` stops using stage 1's private `_cost_arrays` and `_require_research_engine`
  (whose message still says "stage 1"); `components/entries/methods_tf.py` stops importing the MR
  module's private parameter helpers. Shared helpers get a public home.

## 4. Synthetic universes (D-654)

- **Null:** per symbol and timeframe, a random walk with the real series' drift and volatility over
  the same calendar (sessions, early closes), with OHLC built consistently (high ≥ max(open, close),
  low ≤ min(open, close)). Deterministic by seed.
- **Planted edge:** the null plus an effect of known strength and type: mean reversion (a pullback of
  size s·ATR followed by a reversion over k bars) and trend (persistent drift segments). Strength is a
  ladder of at least five values, from barely detectable to obvious, so T15b can draw a power curve.
  The planted positions are recorded, so a run can report which planted edges it found.
- Costs: the real symbols' cost profiles, so the synthetic funnel sees the same frictions.
- **Tests:** the null's drift and volatility match the source within tolerance; the planted effect is
  detectable in its own statistic at the strong end and absent from the null; determinism by seed.

## 5. The report (D-655)

One HTML file per funnel run, in Persian, under the artifacts root.

- **First page:** the funnel table — per stage and timeframe, real against control side by side
  (and, for a synthetic run, against the truth); banners for the control status (D-653), the
  **D-802 parity gap** (D-335/D-336 unverified against TradingView), a synthetic run (D-654), and
  `--no-control` if used.
- **Per stage:** the counts, the gate's failing criteria by frequency, and for stage 1 the pass rate
  by data-quality status and timeframe (T12's requirement).
- **Per candidate that reaches stage 3:** the lineage (profile → method → parameters), stage 1's probe
  table and ESS breakdown, stage 2's grid heatmap and family score, stage 3's half-1 and half-2
  surfaces with the plateau outlined and the selected cell marked, the SPP histogram, zero-cost
  against after-cost, overlaps, the data caveats (D-610) and the `unconfirmed` flag.
- The surfaces are drawn from the artifacts' ordered axes (the T14 transposition bug must not come
  back): a test compares one drawn surface cell by cell with its artifact.
- **Tests:** every number on the first page equals its artifact value; the HTML contains no `http://`,
  `https://` or `//` resource reference; the file opens from a folder with no network (a headless
  check if one is available without a new dependency, otherwise the static check); RTL and LTR runs
  are marked correctly; the font licence is in the repository.

## 6. Acceptance

- **Real:** one `sfac funnel run` on the current configuration reproduces the merged T12–T14 results
  (the same passes at each stage, and 0 control passes at stages 2 and 3), with its control, in one
  command. The review states the wall time.
- **Null and planted:** a full funnel run on the calibrated null and on the planted-edge ladder, both
  timeframes. **With today's thresholds**, report the null's end-of-stage-3 pass rate against D-656's
  1 % and the planted ladder's power curve. This is T15b's starting point, not a verdict: if today's
  thresholds already miss 1 %, say so plainly.
- Every constant in config (rule 1). Fast suite, parity/leakage/oracle, db with 0 skipped, slow, ruff,
  format, mypy (Windows and `--platform linux`), stream guards. D-802 stated. Stop for "Approved".

## 7. Out of scope

Changing any threshold or constant on the calibration list (T15b); stage 4 onwards.

## 8. Raise, do not decide

- The funnel-run link: a new table or a parent field, with the migration if any.
- The Persian font and its licence.
- P-104 (the executor's `auto` budget on hybrid CPUs, calibration list item 7): the full funnel and its
  control will be the heaviest runs so far; measure and propose, do not change the budget alone.
- If the null's pass rate with today's thresholds is far above 1 %, report the numbers at each stage so
  T15b knows where the false positives enter.
