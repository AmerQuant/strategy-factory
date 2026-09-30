# T15a — Funnel orchestrator, synthetic universes and the Persian report — review

Branch `a/T15a-orchestrator` (plan merged in #59). Features **F-X.1 … F-X.5** (MVP, T15) and
**F-X.6** (P1, pulled in); touches F-0.7.1, F-0.7.3, F-0.7.4, F-0.8.2, F-0.3.7. Decisions **D-652 …
D-656** (task), **D-662 … D-671** (the plan's answers), **D-673** (the planted ladder). Plan
`docs/tasks/T15a_plan.md`; pilot `docs/reviews/T15a_pilot.md`. **T15a changes no threshold
(D-652).** Stopped for "Approved".

> **Open parity gap (D-802).** D-335 and D-336 are unverified against TradingView (T11b is
> parked). D-336 is the research default and shapes every MR run here. Every report carries the
> banner.

<!-- HEADLINE -->

## What was built

| module | content |
|---|---|
| `stages/common.py`, `components/entries/method_base.py` | calibration item 9: the helpers stages 2 and 3 borrowed from stage 1 (`cost_arrays`, `require_research_engine` naming its stage, `UnsupportedSymbol`) and the helpers `methods_tf` borrowed from `methods_mr` get public homes; a static guard |
| `synthetic/` (`config.py`, `null.py`, `planted.py`, `access.py`), `configs/synthetic/` | D-654, D-664, D-665: the calibrated null `t_vp` (exact moments per session slot, Student-t × the real causal volatility path, bridge wicks), the planted MR / two-sided TF edge, equal-share assignment and truth, `SyntheticDataAccess` (in memory, never the store) |
| `core/config.py` (`SourceRef`, `PipelineConfig.source`), `stages/*` identities and ids | D-670: `source` in the identities and candidate-id payloads only when synthetic; stages 2 and 3 refuse a run of another source |
| `pipeline/stage_run.py` | one runner for every stage run (`run_pipeline_config`), picking `SyntheticDataAccess` for a synthetic config; `sfac run` unchanged |
| `registry/alembic/versions/0002_funnel_runs.py`, `registry/tables.py`, `registry/funnel.py`, `registry/writer.py` | D-663: `funnel_runs`, `funnel_stage_runs`, `pipeline_runs.source` |
| `pipeline/funnel.py`, `funnel_config.py`, `funnel_run.py`, `funnel_reproduce.py`, `cli_funnel.py`, `configs/funnel/` | F-X.1, F-X.2, F-0.7.4: the orchestrator (six stage runs per timeframe, the control on the real arm's inputs, content-addressed resume, empty stages, `--no-control` recorded), `sfac funnel run / status / reproduce / report` |
| `reports/` (`config.py`, `read.py`, `figures.py`, `render.py`, `templates/funnel.html.j2`, `assets/fonts/`), `configs/reports/funnel.yaml` | F-X.3, F-X.4, D-655, D-666, D-668: the Persian report |
| `.github/workflows/ci.yml`, `pyproject.toml` | the browser test must not be skipped in CI; the `browser` marker; `plotly`, `jinja2`; mypy ignores plotly's missing stubs |
| `scripts/analysis/T15a_*.py`, `scripts/fetch_vazirmatn.ps1` | the plan's measurements, the pilot and acceptance analysis; the font fetch (run by the user, D-031) |

**New dependencies:** `plotly` 7.1.0 and `jinja2` 3.1.6 — ADR-008 and D-400 chose them; the lock
gained nothing else; numpy 2.5.3, numba 0.67.0 and llvmlite 0.49.0 unchanged. (`arch` arrived with
#60 for T16.) **No engine change.**

<!-- RESULTS -->
