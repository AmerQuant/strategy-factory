# CLAUDE.md — Strategy Factory

Internal framework that runs every trading-strategy idea through one standard, reproducible, auditable funnel:
market edge → method screening → entry/exit optimization → diagnostics & filters → robustness → statistics
→ report package → analyst review → portfolio → sizing → forward lifecycle.

Package: `strategy_factory` (import as `sfac`) · CLI: `sfac` · Python 3.12 · managed with `uv`.

## Sources of truth (read before any task)

1. `docs/spec/spec_v1.2.md` (+ original .docx) — Specification v1.2 (Persian). Defines WHAT each stage does. "Phase-1 decisions" (green boxes in the docx, `تصمیمات قطعی فاز ۱` in the md) override proposal text.
2. `docs/features.md` (+ .xlsx) — Feature list v1.1. Every task references feature IDs (`F-0.3.1`, `F-1.4`, ...). **Acceptance criteria there are the definition of done.**
3. `docs/design.md` (+ .docx) — Design v1.0. Defines HOW (interfaces, schemas, engine conventions, registry tables).
4. `docs/adr/` — Architecture decisions (list in design §14). Do not contradict an ADR; if a task seems to require it, stop and report.
5. `docs/tasks/Txx_*.md` — the task you are executing. Only do what the task asks.

If these documents conflict or are silent on something that affects behaviour, **stop and ask** — do not invent a rule.

## Commands

```bash
uv sync                                  # install
docker compose up -d                     # postgres (registry)
uv run alembic upgrade head              # registry schema
uv run pytest -m "not slow"              # fast suite (must pass before any PR)
uv run pytest tests/parity tests/leakage # mandatory gates
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run sfac --help
```

## Non-negotiable rules

1. **No thresholds, weights or decision numbers in code.** They live in YAML configs validated by Pydantic models. Defaults are defined in the config model and documented in the spec.
2. **Holdout is only reachable through `SplitManager`.** `DataAccess` returns the development segment only. Holdout access is one-shot per candidate, logged in `holdout_access`, and a second access must raise.
3. **No look-ahead.** Signals use data up to the close of bar *i*; orders fill at the **open of bar i+1**. Auxiliary series (VIX, index) are joined as-of with lag (last *closed* value only). Every indicator/signal needs a leakage test (data-truncation test).
4. **Costs are mandatory.** A symbol without a cost profile cannot run. Metrics are reported after costs.
5. **Every evaluated configuration is a trial** and is written to the registry (batched). Monte-Carlo/bootstrap simulations are NOT trials; store only their distribution summaries.
6. **The engine is pure.** `engine/` depends only on NumPy/Numba: arrays in, arrays out. No file, DB, config or logging access inside kernels.
7. **Timestamps are UTC, bar-start.** Day boundary 00:00 UTC; FX/gold Sunday hours merge into Monday. `broker_session` resampling exists only for parity tests.
8. **Reproducibility.** Every run records config hash, data snapshot hash, git SHA and seed. `sfac reproduce --trial <id>` must give bit-identical results.
9. **Parity and leakage tests are never skipped, weakened or deleted.** If one fails, fix the code, not the test. Changing a tolerance requires an explicit decision recorded in an ADR.
10. **Data snapshots are immutable.** Never overwrite a parquet snapshot; write a new one.
11. **Raw source data folders are read-only.** Never modify, move or delete anything under the user's existing data folders. The snapshot store lives outside the repo; its root comes from the `SFAC_DATA_ROOT` environment variable (see `.env.example`).
12. **Cross-platform paths.** Development machine is Windows; CI is Ubuntu. Use `pathlib` everywhere, never hard-code separators or drive letters in code (only in local `.env`/configs).

## Engine conventions (details: design §6)

- Order of events per bar: scheduled fills at open (gaps through stops fill at open) → intrabar SL/TP/disaster stop via high/low → close: evaluate entry/exit/time signals, schedule for next open, record mark-to-market equity.
- Intrabar ambiguity: `intrabar_mode=tradingview` (parity only) or `pessimistic` (research; stop first). Minute-data resolution comes later (F-0.3.5).
- Fill price: base (trade or mid) ± half-spread ± slippage (fixed + fraction of signal-bar ATR). Commission per cost profile. Swap at the profile's rollover time, triple day from profile.
- Sizing default: fixed notional 100,000 USD; qty = notional / entry price. One position per strategy, no pyramiding.
- Disaster stop: entry ∓ 3 × ATR(signal bar). Fixed, never optimized.

## Metrics conventions (details: spec, F-0.5.x)

- Annual drawdown is reported in two versions; **the target metric and gates use "from start of each year"**. Drawdown is measured against **initial capital**.
- Partial years count fractionally in annual averages.
- Always report: avg annual profit, avg annual drawdown, their ratio, time exposure, return per exposure.

## Code conventions

- Layers: Polars only in `data/`; NumPy in `engine/`; pandas only at the edges (reports, stats libraries). Convert at module boundaries, never mid-logic.
- All domain objects are frozen Pydantic models; IDs are sha256 of canonical JSON.
- Stages implement `Stage.run(candidates, ctx) -> StageResult` and touch data/registry only through `RunContext`.
- Type hints everywhere. `mypy --strict` for `core`, `data`, `registry`, `gates`; relaxed for Numba kernels.
- Numba: `@njit(cache=True)`; parallel grids with `prange`. Keep kernels free of Python objects.
- Registry: SQLAlchemy Core + psycopg 3; bulk writes via `COPY`; schema changes only through Alembic migrations.
- Code, identifiers, comments and commit messages in English. User-facing reports are Persian, RTL, font Vazirmatn.

## Testing

- Test names start with the feature ID: `test_F_0_3_1_next_bar_open_fill`.
- Each feature's acceptance criteria from `docs/features.md` must be covered by tests.
- Engine invariants use Hypothesis (see design §6): P&L conservation, no same-bar execution, costs monotonic, truncation invariance, long/short mirror.
- `tests/oracle/` compares simple strategies against vectorbt. vectorbt is a **test-only** dependency; never import it from `src/`.
- Slow self-tests (random walk, planted edge) are marked `@pytest.mark.slow` and run nightly.

## Workflow for every task

1. Read the task file and the referenced feature IDs, spec sections and design sections.
2. If anything is ambiguous or conflicts with these rules, stop and list the questions before coding.
3. Branch: `feat/<task-id>-<short-name>` (e.g. `feat/T08-engine-core`). One task = one PR.
4. Write tests from the acceptance criteria first, then the implementation.
5. Run the fast suite, parity, leakage, ruff and mypy. All must pass.
6. Commit messages reference IDs: `F-0.3.1: next-bar-open fills`.
7. Finish with a **review summary** for the supervisor: what was built, files changed, how each acceptance criterion is tested, deviations or open questions, and anything you were unsure about. Do not claim a criterion is met unless a test proves it.

## Do not

- Add dependencies without listing them in the review summary with the reason.
- Touch holdout data, parity fixtures or tolerances outside an explicit task.
- Store full equity curves/trade lists for every grid cell (only for candidates that pass a gate).
- Call any LLM API. Stage 8 produces a package (`evidence.json`, `PROMPT.md`, `REPORT_SPEC.md`); the Word report is made outside the framework and checked with `sfac report verify`.
