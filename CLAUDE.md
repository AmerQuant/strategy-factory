# CLAUDE.md — Strategy Factory

**Two parallel streams run (D-355, D-357): read `docs/streams/PROTOCOL.md` and your
`docs/streams/<A|B>.md` first.**

Internal framework that runs every trading-strategy idea through one standard, reproducible, auditable funnel:
market edge → method screening → entry/exit optimization → diagnostics & filters → robustness → statistics
→ report package → analyst review → portfolio → sizing → forward lifecycle.

Package: `strategy_factory` (import as `sfac`) · CLI: `sfac` · Python 3.12 · managed with `uv`.

## Sources of truth (read before any task)

0. `docs/decisions/decisions_log.md` — the supervisor's decisions log (`D-nnn`, pending `P-nn`). **Where it is more specific than the spec, the design or the feature list, it wins.** Open questions raised by Claude Code go to `docs/decisions/pending.md`.
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
- **Encodings are explicit (D-377).** Every text-mode `subprocess` call and every text file access (`open`, `Path.open`, `read_text`, `write_text`) passes `encoding=` (UTF-8 unless documented otherwise); Windows defaults to cp1252 while CI is UTF-8, so CI cannot catch a missing one. `tests/unit/test_F_X_9_explicit_encoding.py` enforces it statically.
- Code, identifiers, comments and commit messages in English. User-facing reports are Persian, RTL, font Vazirmatn.

## Testing

- Test names start with the feature ID: `test_F_0_3_1_next_bar_open_fill`.
- Each feature's acceptance criteria from `docs/features.md` must be covered by tests.
- Engine invariants use Hypothesis (see design §6): P&L conservation, no same-bar execution, costs monotonic, truncation invariance, long/short mirror.
- `tests/oracle/` compares the engine with a **naive pure-Python reference engine** written from the rules (D-330, D-346); it shares no code with `engine/` and is never skipped. vectorbt is **not** a dependency (D-346); the external check is the TradingView parity test (T11).
- Slow self-tests (random walk, planted edge) are marked `@pytest.mark.slow` and run nightly.

## Workflow (two phases per batch — standing prompt in `docs/STANDING_PROMPT.md`)

**Phase 1 — Plan** (D-403). Read `HANDOFF.md` (section "Next batch") and the decisions log. Draft one task file per task in `docs/tasks/` from the acceptance criteria in `docs/features.md`, the spec, the design and the decisions log, citing feature and decision IDs, plus `docs/tasks/RUNBOOK_<batch>.md`. Every assumption or open question goes to `docs/decisions/pending.md`. Commit on branch `docs/<batch>`, then **stop** and print a plan summary (tasks, features covered, decisions used, assumptions, open questions).

**Phase 2 — Execute**, only after the user writes **"Plan approved"** (possibly with corrections). Per task:
1. Branch `feat/<task-id>-<short-name>` as the runbook says (stacked branches allowed). One task = one review file.
2. If anything is ambiguous or conflicts with these rules or the decisions log, stop and ask (and record it in `pending.md`).
3. Write tests from the acceptance criteria first, then the implementation.
4. Run the acceptance commands: fast suite, parity, leakage, db (0 skipped), ruff, format, mypy. All must pass.
5. Run the **`acceptance-reviewer` subagent** (`.claude/agents/acceptance-reviewer.md`) on the task and fix its findings.
6. Commit with IDs in the messages (`F-0.3.1: next-bar-open fills`); write `docs/reviews/<task>_review.md`: what was built, files changed, how each acceptance criterion is tested, decisions used, deviations, open questions. Do not claim a criterion is met unless a test proves it.
7. **Critical tasks (D-402: engine T08, parity T11, split/holdout manager, gate engine)**: stop after the review and wait for **"Approved"** before starting the next task.

At the end of the batch: open the PR(s) with `gh` (body = the reviews), update the status in `HANDOFF.md`, print the batch report. **Merge only after the user writes "Approved. Merge …"** and CI is green (D-401).

Environment rules:
- **Network runs are done by the user** in PowerShell scripts that Claude Code writes (pilots, downloads, reference fetches); Claude Code makes no network calls to data sources and uses no CA-bundle workarounds (D-031).
- The local registry DB is Docker Postgres on port **5433** (`SFAC_DB_URL` in `.env`); a native Windows Postgres holds 5432 (D-305).

## Do not

- Add dependencies without listing them in the review summary with the reason.
- Touch holdout data, parity fixtures or tolerances outside an explicit task.
- Store full equity curves/trade lists for every grid cell (only for candidates that pass a gate).
- Call any LLM API. Stage 8 produces a package (`evidence.json`, `PROMPT.md`, `REPORT_SPEC.md`); the Word report is made outside the framework and checked with `sfac report verify`.
