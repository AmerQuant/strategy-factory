# Stream A — main folder

Working copy: `D:\AmerAndish\Projects\Trade\StrategyFactory` (the repository's main worktree).
Governed by **D-355** and **D-357**; the full rules are in `docs/streams/PROTOCOL.md` and the
path ownership in `docs/streams/ownership.yaml`. This file is stream A's status; `HANDOFF.md` is
written **only by stream A**, at merges, from this file and `docs/streams/B.md`.

New branches here carry the **`a/`** prefix. Run the guards locally with
`uv run sfac streams check --base origin/main`.

## Scope

1. The **batch-2b merges** — **done** (2026-09-21).
2. **T11 — TradingView parity** (F-0.3.8, critical per D-402), on the references of D-348
   (`BATS:SPY` 1D and `OANDA:XAUUSD` 1H, run on the exported OHLC as-is). The open parity
   questions are in `HANDOFF.md` §8.

## ID ranges (D-355)

| | decisions | pending |
|---|---|---|
| supervisor | D-355 … D-359 | — |
| **stream A (this one)** | **D-360 … D-379** | **P-40 … P-59** |
| stream B | D-380 … D-399 (used up) and D-700 … D-799 | P-60 … P-79 |

Next free here: **D-360**, **P-40**.

## Rules that bind this stream (D-355)

- **Database:** `.env` here points at `sfac` on the shared Postgres (port 5433, D-305).
  Stream B uses `sfac_b` on the same server. Never point this `.env` at stream B's database.
- **Data root:** **stream A does not write to `SFAC_DATA_ROOT`.** Only stream B ingests and
  writes snapshots. Stream A reads the store and reads `SFAC_RAW_ROOT` read-only (D-028).
- **`configs/universe.yaml` is stream A's (D-394).** After every stream-B merge, stream A runs
  `sfac universe generate` from the symbol list in `docs/streams/B.md`.
- **Docs:** decision and pending edits go on stream A's own docs branch; a conflict in
  `decisions_log.md` or `pending.md` is resolved by **keeping every row in ID order**, one row
  per ID (the most-resolved version of a repeated ID wins).
- **Benchmarks** (`scripts/bench_engine.py`, `scripts/bench_executor.py`) run only when stream
  B is idle — they take every core.
- Every branch **rebases onto `main`** before its merge. D-401 (merge only on "Approved.
  Merge …", CI green) and D-402 (critical tasks need supervisor review) are unchanged.

## Status — 2026-09-21

**Branch `a/T11-parity`, commit `7416278`** (pushed, CI green). Everything below is on that
branch unless it says otherwise. Read with `HANDOFF.md`; together they are enough to resume
this stream from scratch.

### Merged (nothing outstanding)

| PR | content |
|---|---|
| #13 #14 #15 #16 #17 | batch 2b: T06b, T08, T10b, D-355/D-356, HANDOFF v6 |
| #18 | D-357 stream protocol, `ownership.yaml`, the three CI guards |
| #20 | D-394 universe regeneration after T04f, plus the supervisor range D-600…D-699 |

### T11 parity — in progress, **critical (D-402)**

| section | state |
|---|---|
| §1 reference store (`selftest/parity_refs.py`) | **done** — chart CSV, the `.xlsx` Trades and Properties sheets (openpyxl lazy, D-317), the Pine `strategy()` parser, the Properties cross-check (no disagreement on either reference), manifest verified on every load |
| §2 parity config (`core/parity_config.py`, `configs/parity/`) | **done** — every D-348 Pine setting required; mintick required and equal to `pine.tick_size` (D-366) |
| §3 costs (`costs/parity.py`) | **done** — from the `pine` block alone (D-362) |
| §3 strategy mapping | **done for MR** (`mr_rsi2_below_10`); TF maps to `tf_donchian20_breakout` |
| §4 comparison (`selftest/parity_compare.py`) | **MR done and passing**; TF blocked, see below |
| §5 `to_verify` | D-349 (a) **cannot** be verified by these references (neither script trails) — it stays `to_verify` and the review must say so |
| §6 report (`selftest/parity_report.py`) | **done** — both net-profit figures and the small-profit flag (D-364), the D-011 verdict |
| review `docs/reviews/T11_review.md` | **not written yet** — written after TF, then stop for "Approved" |

**MR / BATS:SPY 1D — D-011 PASS.** 462/462 matched (100.00 %); net profit 185,784.36 vs
185,810.06 = **−25.70 USD**, 0.0138 % of |TV| and 0.0257 % of capital.

Two engine options got it there, both **parity-only** and both proven unreachable from a
research run: **D-366** tick rounding (whole ticks, half away from zero, measured from the
fill) and **D-367** `entry_requires_flat_at_signal` (default off = D-336). The naive oracle
implements both from the decision text; oracle and property suites pass.

### Blocked, and on whom

- **TF / OANDA:XAUUSD — waiting on the user.** The current export is two-sided while the
  engine runs one direction per run. **D-600** settles it: the two-sided export is superseded,
  and the user is re-exporting **TF Long, TF Short, fresh OHLC and the new `.pine`**, then
  re-running `scripts/write_parity_manifest.ps1`. The supervisor will send the file names.
  Next steps once they arrive: add them to `tests/fixtures/parity/` with their manifest
  (D-359), mark the two-sided export superseded in the manifest notes, run both one-sided
  comparisons, then write the review.
- **P-44 — waiting on the supervisor.** A cached Hypothesis example fails a metrics property
  test and the `ci` profile hides it. Diagnosed: the **fixture** is wrong, not the invariant.
  Not fixed inside T11; a separate session is doing the fixture half on
  `a/fix-metrics-fixture-prices`.

### ⚠️ Protocol incident (D-357 (1))

On 2026-09-21 the spawned metrics-fixture session took over **this** working folder: it
switched the checkout from `a/T11-parity` to `a/fix-metrics-fixture-prices` and edited files
there, while stream A was mid-task. D-357 (1) requires each session to work only in its own
folder. Stream A recovered by backing its own edit out of that branch and using a scratch
worktree for `a/T11-parity`; nothing was lost (all T11 work was already committed and pushed).
**A spawned session must get its own worktree.**

### Next actions, in order

1. TF exports arrive → fixtures, manifest note, both one-sided comparisons.
2. `docs/reviews/T11_review.md`, then **stop for "Approved"** (D-402).
3. After the merge: `HANDOFF.md` from this file and `docs/streams/B.md`.
4. Owed to stream B: `sfac universe generate` after each stream-B merge (D-394). Done for
   #19; nothing outstanding. Nothing under `configs/costs/` needs changing for D-388.

### ID ranges used so far

Stream A decisions **D-360 … D-367** used (next free **D-368**); pending **P-40 … P-44** used
(next free **P-45**). The supervisor keeps D-355 … D-359 (used up) and D-600 … D-699.
