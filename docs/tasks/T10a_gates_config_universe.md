# T10a — Gate engine, pipeline config and universe

**Features:** F-0.8.1 (declarative gate engine), F-0.8.2 (pipeline config), F-0.9.1 (universe registry) · **Priority:** MVP · **Depends on:** T02, T03, T06 (on the batch branch)
(The executor, F-0.3.7, moves to T10b after the engine exists.)

Read first: `CLAUDE.md`, `docs/design.md` §4 (Gate models), §8 (config), the gate tables in the spec (`docs/spec/spec_v1.2.md` and its phase-1 decision boxes), and `docs/reviews/T03_review.md` (open question 2).

## Scope

### 1. Gate engine (F-0.8.1, `gates/`)
- **YAML format** (`configs/gates/default.yaml`): per stage, a list of criteria `{metric, op, threshold, critical?}`. It also has `overrides` keyed by `asset_class` and/or `timeframe` that replace or add criteria.
- `GateEngine.evaluate(stage, candidate, metrics: dict, context: {asset_class, timeframe}) -> GateResult` with one `CriterionResult` per criterion (value, threshold, passed, reason). A missing metric is a failure with reason `metric_missing`, never a silent pass.
- **Borderline rule (decided):** exactly one failed **non-critical** criterion whose value is within 10 % of its threshold. If any failure is critical, the result is never borderline. The 10 % is in config.
- Results are written through the T03 `RegistryWriter`.
- `configs/gates/default.yaml` holds all MVP gate values from the spec (stages 1–3), plus the stage 4–7 values from the decisions, commented as "used from P1". **No number in code.**

### 2. Pipeline config (F-0.8.2, `core/config.py`)
- `PipelineConfig` (Pydantic): `universe`, `symbols`, `timeframes`, `stages`, `gates`, `intrabar_mode`, `seed`, `cost_stress`, and `data_snapshots`.
  - `data_snapshots` is resolved at run start from the catalog's references into a mapping `{symbol: {timeframe: {source, snapshot_hash}}}` and **stored in the run config**.
  - `start_run` refuses a config without resolved snapshots. This resolves T03 open question 2: enforce it in the pipeline config layer and make the registry writer validate that the key exists.
- `config_hash` = sha256 of the canonical JSON of the resolved config.
- CLI: `sfac config validate <file>` and `sfac config resolve <file>` (prints the resolved config with its snapshot hashes).

### 3. Universe registry (F-0.9.1, `core/universe.py`)
- `configs/universe.yaml` lists symbols with: `asset_class` (the enum), `reference_source`, `timeframes`, `cost_profile` (via the T06 assignments), `calendar` (nyse / 24x5 / 24x7) and `group` (for the cross-symbol validation later).
- Generate it from what exists: the Alpaca universes (daily and hourly), the Dukascopy universe and Yahoo aux (aux symbols are not tradable: `tradable: false`).
- **Validation:** exactly one reference source per (symbol, timeframe); every tradable symbol has a cost profile; the asset class matches the catalog metadata.
- CLI: `sfac universe list [--asset-class] [--group]` and `sfac universe validate`.

## Tests
- **Gate engine:**
  - each operator;
  - overrides by asset class and timeframe;
  - a missing metric is a failure;
  - the borderline rule (one non-critical failure within 10 % → borderline; two failures → not; a critical failure → not);
  - results are written to the registry (DB test).
- **Config:**
  - resolution picks the catalog references;
  - an unresolved snapshot is refused;
  - `config_hash` is stable under key reordering.
- **Universe:**
  - generation from existing universes;
  - each validation error;
  - aux symbols are non-tradable.

## Acceptance
ruff, format, mypy (strict for `gates` and `core`), pytest pass; CI green. `sfac universe validate` works, and `sfac config resolve` works on a sample config against **whatever references exist in the current catalog**. Today these are the Dukascopy h1 pilot snapshots (EURUSD, XAUUSD, USA500IDXUSD), so write `configs/pipeline/sample_h1.yaml` for them. Also add `configs/pipeline/mvp_daily.yaml` for SPY, QQQ and AAPL 1D, which will resolve once the Alpaca daily ingest has run.

## Review summary
Write it to `docs/reviews/T10a_review.md`. Include the full default gate table as loaded, the universe counts per asset class, deviations and open questions.
