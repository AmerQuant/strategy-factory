# RUNBOOK — T15a: funnel orchestrator, synthetic universes, the Persian report (stream A)

One task. Stops: the plan (**"Plan approved"**, D-403), the **planted pilot** (P-127), and the
review before the merge (**"Approved"**). Task file:
`docs/tasks/T15a_orchestrator_synthetic_report.md` (supervisor's, unchanged). Plan and
measurements: `docs/tasks/T15a_plan.md`. Decisions: **D-652 … D-656** and the answers to
**P-124 … P-133**. Features: F-X.1 … F-X.5, F-X.6 (P1, pulled in); touches F-0.7.1, F-0.7.3, F-0.7.4,
F-0.8.2, F-0.3.7. **No threshold changes (D-652).**

## Branches

| step | branch | base | stop |
|---|---|---|---|
| plan | `a/T15a-plan` | `main` (after #57) | **"Plan approved"** |
| 1 … 11 | `a/T15a-orchestrator` (one task, one review file) | stacked on `a/T15a-plan` (plan and decisions), as T13, T14 | the planted pilot (P-127); after the review, **"Approved"** |

Paths: `stages/`, `configs/stages/`, `configs/gates/`, the Alembic migrations, `pyproject.toml`,
`uv.lock` and `.github/` are stream A's (D-611, D-612, D-357 (2)) — the PR body carries the
supervisor notice; `pipeline/`, `reports/`, `synthetic/` (new), `components/`, `core/`,
`registry/` (tables), `configs/funnel/`, `configs/synthetic/`, `tests/`, `scripts/` as listed in
`ownership.yaml`. `data/` and `engine/` are not touched; nothing is written to `SFAC_DATA_ROOT`.

## Preconditions

1. P-124 … P-133 answered, or their proposals accepted with "Plan approved".
2. `main` green; `uv sync`; Docker Postgres up (port 5433, D-305).
3. **The user runs `scripts/fetch_vazirmatn.ps1`** (P-128, D-031) — the font and `OFL.txt` in place
   before step 7.
4. `uv add plotly jinja2` (ADR-008, D-400) — the only new dependencies, listed in the review.

## Order of work

1. **Clean-up** (plan §8): `stages/common.py` (`cost_arrays`, `require_research_engine(ctx, stage)`,
   `UnsupportedSymbol`), `components/entries/method_base.py` (the shared method base and parameter
   helpers under public names). The existing suites unchanged and green; a test that no stage
   module imports a private name from another.
2. **Synthetic** (`synthetic/`, plan §6, P-126, P-127, P-132): `null.py`, `planted.py`,
   `access.py` (`SyntheticDataAccess`), `configs/synthetic/null.yaml`, `planted.yaml`. Tests first:
   exact drift and volatility per slot, OHLC consistency, ATR within tolerance on fixtures from the
   M1 series, determinism by seed, the planted own statistic (present at the top, absent on the
   null), no store write.
3. **Identity** (P-132): `source` in the stage identities, the candidate-id payloads and
   `PipelineConfig` (left out of the canonical JSON when real); refusal of a mixed-source input.
   Test: every T12–T14 artifact's candidate id and every stored `config_hash` recompute unchanged.
4. **Registry** (P-125): migration `0002_funnel_runs` (`funnel_runs`, `funnel_stage_runs`,
   `pipeline_runs.source`); writer and queries; db tests (upgrade / downgrade, one head).
5. **Orchestrator** (`pipeline/funnel.py`, `pipeline/funnel_config.py`, plan §5, P-124): the six
   stage runs per timeframe, `stage_key`, resume, empty stages, `--no-control` recorded;
   `configs/funnel/mvp.yaml`, `null.yaml`, `planted.yaml`. Tests: resume after an injected failure =
   uninterrupted; a finished stage not re-run; a dirty tree never resumes; empty stages.
6. **CLI** (`sfac funnel run | status | reproduce | report`, F-X.2) and **reproduce** (F-0.7.4): the
   command-tree test; reproduce identical on a fixture funnel, failing on a mutated artifact.
7. **Report** (`reports/`, plan §7, P-128, P-130): reader, figures, template, font; the tests of plan
   §7.4 (first-page numbers against the artifacts, the surface cell by cell in axis order, no
   external reference, headless offline render with no network request, RTL / LTR marking, the font
   licence and hash), each guard mutation-checked.
8. **Planted pilot** (P-127): 30 daily symbols at the ladder's top two strengths through the funnel.
   **Stop with the numbers**; widen the ladder if the top is below 80 % at stage 1.
9. **P-104** (P-129): the executor timings **while stream B is idle**; a proposal, not a change.
10. **Acceptance runs** (plan §12): the real funnel (1D + 1H with the control, reproducing
    T12–T14: 14 / 25 / 2 and 4 / 6 / 4, and 0 control passes at stages 2 and 3; wall time); the
    null funnel (both timeframes, three seeds); the planted funnel (both timeframes); one report
    each.
11. **Review** `docs/reviews/T15a_review.md`: the null's end-of-stage-3 share against D-656 first,
    then the control, the planted power curve per stage, the real funnel's reproduction, the reports,
    D-802 stated. Fast suite, parity / leakage / oracle, db (0 skipped), slow, ruff, format, mypy
    (Windows and `--platform linux`), `sfac streams check`; the `acceptance-reviewer`; push, PR,
    **stop for "Approved"**.

## Rules for this task

- No threshold, weight or constant in code (rule 1): the synthetic, funnel and report constants are
  config.
- Development data only; no stage or orchestrator holds a `SplitManager` (rule 2, D-616).
- Synthetic series never reach `SFAC_DATA_ROOT` and never mix with real results (D-654).
- No calibration: every gate and stage value stays as merged (D-652).
- The engine is not changed; if anything needs it, stop (D-402).
- Every report number is read from an artifact or a registry row, never recomputed (D-655).
