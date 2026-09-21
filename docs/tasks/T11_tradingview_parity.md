# T11 — TradingView parity — CRITICAL (D-402)

**Features:** F-0.3.8 (parity with TradingView), F-X.7 (regression on known strategies) · **Priority:** MVP · **Stream:** A · **Depends on:** T08 (engine, merged #14), T10b (parity config inputs, merged #15), F-0.1.5, F-0.1.7

**Critical (D-402):** T11 stops after its review and waits for **"Approved"** before anything is merged. The parity tests are a mandatory gate and are never skipped, weakened or deleted (CLAUDE.md rule 9); changing a tolerance needs an ADR.

Read first: `CLAUDE.md`, `docs/decisions/decisions_log.md`, `docs/reviews/T08_review.md` (the `to_verify` list and the event order), `docs/reviews/T10b_review.md` (the parity run inputs), `HANDOFF.md` §8, and decisions **D-001, D-002, D-010, D-011, D-326, D-327, D-335, D-336, D-337, D-338, D-343, D-347, D-348, D-349**.

## 0. Blocking inputs — the references are incomplete today

**Resolved 2026-09-21.** All six references are in place and read correctly, the fixtures of
**D-359** make them available to CI, and P-40 … P-43 are answered by D-360 … D-363. The
original finding is kept below for the record.

`SFAC_RAW_ROOT/reference/tradingview/parity/` held **only OHLC** when this task was planned:

| file | rows | range (UTC) | notes |
|---|---|---|---|
| `BATS_SPY, 1D.csv` | 8,467 | 1993-01-29 14:30 … 2026-09-18 13:30 | `time,open,high,low,close`; the stamp is the bar **open** in UTC (14:30 UTC = 09:30 New York), not 00:00 UTC |
| `OANDA_XAUUSD, 60.csv` | 21,986 | 2023-01-02 23:00 … 2026-09-18 20:00 | hourly, weekend gaps of 50 h |

D-348 also requires, per reference, a **trade list** and a **manifest with SHA-256**, and the
**Pine script settings** recorded in the parity config. None of those exist yet, and **without
the trade lists D-011 cannot be evaluated at all** (it is a trade-by-trade comparison). They are
raised as **P-40** and **P-41**; §1–§6 below are written so that everything except the
comparison itself can be built and tested before they arrive.

## Scope

### 1. Parity reference store (`data/parity_refs.py`, read-only)
- A reader for TradingView **"Export chart data"** CSVs (`time,open,high,low,close`, UNIX
  seconds) and for TradingView **Strategy Tester trade-list** exports.
- The `time` column is treated as **UTC, bar open**, and is **kept as exported**: D-348 says the
  parity run uses the exported OHLC **as-is** — no D-010 Sunday merge, no resampling, no
  Alpaca/Dukascopy bars, no re-bucketing to 00:00 UTC. A test asserts the SPY stamps stay at
  14:30/13:30 UTC and that the loader never shifts a bar.
- **Immutability and provenance (as in D-340):** a `manifest.json` next to the files lists each
  file with its SHA-256 and row count; the reader **verifies the hash on every load** and raises
  on a mismatch or a missing manifest. The raw folder is never written to (CLAUDE.md rule 11);
  the manifest is produced by a script the **user** runs (D-031) or by the export step, not by
  the loader.
- The parity references are **not** snapshots and never enter the catalog or `SFAC_DATA_ROOT`
  (stream A does not write it, D-355).

### 2. Parity run config (`configs/parity/<name>.yaml`, model in `core/config.py`)
One file per reference, holding **every setting D-348 lists**, so a parity run is reproducible
and its `config_hash` covers it (T10b):

- `reference`: the OHLC file, the trade-list file, the symbol and timeframe as exported;
- `pine`: `atr_length` (D-343), `initial_capital`, `qty_type` / `qty_value`, `commission`
  (type and value), `slippage` (ticks), `pyramiding`, `process_orders_on_close`,
  `calc_on_every_tick`, `bar_magnifier`, the fill assumptions and the **export timezone**;
- `engine`: `intrabar_mode: tradingview` plus `parity_qty_step` (**required**, D-347 —
  `BATS:SPY` = 1, `OANDA:XAUUSD` = 0.01) and the Pine `atr_length` stated explicitly (D-343);
- `strategy`: the `BacktestSpec` that reproduces the Pine strategy (§3).

The model is validated by Pydantic, lives in YAML (CLAUDE.md rule 1), and a config whose
`pine.*` block is incomplete is an error — a parity result is worthless if the settings it was
produced under are unknown.

### 3. The two reference strategies (§3 of the run config)
The Pine sources are inputs from the user (**P-41**). Each must be expressed as a
`BacktestSpec`: a registered entry component + params + an `ExitSpec`. The task is to **map**
them, not to invent them:
- **MR on `BATS:SPY` 1D** and **TF on `OANDA:XAUUSD` 1H**;
- if a Pine rule has no registered component, the task **stops and reports** (a new component is
  T07's contract, not T11's).
- Costs in parity mode come from the **Pine settings**, not from a Moneta profile: a
  parity `CostArrays` is built from `pine.commission` and `pine.slippage` (§2). The broker
  volume step and minimum never apply in parity mode (D-347).

### 4. Comparison and the D-011 gate (`selftest/parity.py`, `tests/parity/`)
- Match engine trades to TradingView trades on **(direction, entry bar)**, then report per pair:
  entry/exit bar and price, quantity, gross and net P&L, and the exit reason.
- **D-011:** **≥ 98 % of trades matched** and **net-profit difference ≤ 3 %**. Both thresholds
  live in the parity config, not in code; the default is D-011's.
- The gate is a test under `tests/parity/` and is **never skipped**: while the trade lists are
  missing it must **fail loudly with a clear reason**, not skip or xfail (CLAUDE.md rule 9). It
  is therefore added only together with the trade lists, or behind an explicit
  "references missing" failure — decided in **P-40**.
- **A difference report with a reason per mismatch** (F-0.3.8 acceptance): every unmatched or
  differing trade is classified against the known ambiguities — O→H→L→C path and its tie
  (D-335), exit + re-entry at one open (D-336), swap inside a rollover bar (D-327), trailing
  updated only at the close (D-349 a), the conversion rate (D-349 h), and ATR warm-up entries
  (HANDOFF §8.1). An unclassifiable difference is listed as such.

### 5. Resolving the `to_verify` items (D-338, D-349)
D-338 (1) says every parity-mode choice stays `to_verify` **until T11**. This task closes them:
each of the five items in the T08 review is either **confirmed** by the comparison, or the
engine is changed and the change is recorded as a decision (stream-A range **D-360 … D-379**).
The two HANDOFF §8 notes are checked explicitly:
1. **ATR warm-up entries** — the engine only enters when `atr[j] > 0`; TradingView may enter
   during the warm-up. Compare the **first** trades of each export.
2. **Trailing ATR basis** — **neither reference uses a trailing stop.** The MR script exits on
   `close > high[1]`, a 5-bar time limit or a 3-ATR stop; the TF script uses a 2-ATR stop, a
   4-ATR target and a 50-bar time limit. **D-349 (a) therefore cannot be verified by these
   references and stays `to_verify`** — it needs a third reference with `strategy.exit`
   trailing, or a decision to leave it unverified. This must be stated in the T11 review.

### 6. Report (`docs/reviews/T11_review.md` + a parity report artifact)
Per reference: bar count, date range, settings used, matched-trade share, net-profit difference,
the difference table with reasons, and the `to_verify` outcome for each of the five items.

## Tests
- **F-0.3.8 / D-011 (the gate):** both references — matched share ≥ 98 %, net-profit difference
  ≤ 3 %, under `tests/parity/`, never skipped.
- **Reference store:** the manifest hash is verified and a tampered byte raises; a missing
  manifest raises; the exported timestamps are used unchanged (no Sunday merge, no resampling,
  no shift to 00:00 UTC); the loader never writes to `SFAC_RAW_ROOT`.
- **Config:** a parity config missing any `pine.*` field, `parity_qty_step` or an explicit
  `atr_length` is refused (D-347, D-343 — T10b already refuses the last two at the pipeline
  level; the parity config must refuse them too); `config_hash` changes when any `pine.*` value
  changes.
- **Comparison:** hand-built pairs of trade lists exercise a perfect match, a one-bar entry
  shift, a quantity difference, a missing trade and an extra trade; each lands in the expected
  bucket of the difference report with the expected reason.
- **Costs from Pine settings:** a run with `commission` and `slippage` from the config produces
  the hand-computed fills; the broker step and minimum volume are ignored (D-347).
- **Regression (F-X.7):** the same two strategies re-run twice give bit-identical results
  (reproducibility, CLAUDE.md rule 8).

## Acceptance
- ruff, format, mypy, fast suite, **`pytest tests/parity tests/leakage tests/oracle`**,
  `pytest -m db` 0 skipped.
- The parity report for both references, in the review.
- Every one of the five `to_verify` items is either confirmed or replaced by a recorded decision.

## Review summary
`docs/reviews/T11_review.md`: the D-011 result per reference first (matched share, net-profit
difference, pass/fail), then the settings used, the difference table with a reason per
mismatch, the `to_verify` outcomes, deviations and open questions. A criterion is not claimed
without a proving test.

## Open questions
**P-40** (blocking) and **P-41** are in `docs/decisions/pending.md`. Execution of §4 cannot start
until P-40 is resolved; §1–§3, §5's preparation and §6's scaffolding can.
