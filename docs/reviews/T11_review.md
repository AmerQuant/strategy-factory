# T11 — TradingView parity (F-0.3.8) — **draft, not finished**

> **State.** The MR reference is complete, gated and reproducible from the repository. The TF
> reference is **waiting on the user's re-export** (D-600: the two-sided export is superseded;
> TF Long, TF Short, a fresh OHLC export and the new `.pine` are being produced). Everything
> below that concerns TF is marked *pending*. The review is finished, and stops for
> "Approved" (D-402), once those files arrive.

## 1. D-011 result per reference

| reference | bars | TradingView trades | matched | net profit (engine / TV) | difference | D-011 |
|---|---|---|---|---|---|---|
| **MR — `BATS:SPY` 1D** | 8,467 | 462 | **462 = 100.00 %** | 185,784.36 / 185,810.06 | **−25.70 USD** = 0.0138 % of \|TV\|, 0.0257 % of capital | **PASS** |
| TF — `OANDA:XAUUSD` 1H, long | — | — | — | — | — | *pending the re-export* |
| TF — `OANDA:XAUUSD` 1H, short | — | — | — | — | — | *pending the re-export* |

Both net-profit figures are reported per **D-364**. The MR figures are far inside D-011's 3 %
on either basis, so the small-profit flag does not apply; TF's \|TV net profit\| on the
superseded export was 24,372.65 USD, which makes the relative basis tight, and it will be
reported and flagged rather than decided.

The result is produced by `tests/parity/test_F_0_3_8_d011_gate.py`, which runs on the
**committed fixtures** (D-359) and therefore in CI, and is never skipped (CLAUDE.md rule 9).
Reason table for MR: `{'match': 462}` — no unmatched or differing trade.

## 2. What makes the MR reference match

Two engine options, both **parity-only** and both unreachable from a research run:

| decision | option | effect on MR |
|---|---|---|
| **D-366** | `parity_tick_size` — stop and target distances rounded to whole ticks, half away from zero, measured from the fill | see below |
| **D-367** | `entry_requires_flat_at_signal` — the entry is gated on being flat at the **signal close**, as `flat = strategy.position_size == 0` does in both scripts; default **off** = the D-336 behaviour | see below |

Measured on the MR reference by turning each one off:

| configuration | matched | D-011 |
|---|---|---|
| neither | 97.62 % | FAIL |
| D-366 only (`entry_requires_flat_at_signal: false`) | 98.48 % | **FAIL** — the trade threshold is met, the net-profit leg is not |
| D-367 only (`parity_tick_size` unset) | 99.13 % | PASS |
| **both** | **100.00 %** | PASS |

Worth stating plainly: **the gate would still pass without D-366.** It is not carried by the
gate but by the result — 99.13 % against 100.00 % — so if it is ever questioned, this table,
not the gate, is the argument for it. D-367 is load-bearing: without it the net-profit leg
fails.

## 3. The `to_verify` ledger (§5, D-338 rule 1, D-349)

| # | item | outcome | evidence |
|---|---|---|---|
| 1 | O→H→L→C path and its tie (**D-335**) | *pending TF* | MR has **no target and no trailing stop**, so only one level can be hit in a bar and a tie cannot arise. TF has a 2-ATR stop and a 4-ATR target and can show one. |
| 2 | Exit + re-entry at one open (**D-336**) | **confirmed** | 2 of the 462 engine entries fall on a bar that is also an exit bar, and all 462 trades match TradingView, so both sides exit and re-enter at the same open. |
| 3 | No swap on intrabar exits in rollover bars (**D-327**) | **not verifiable by any TradingView reference** — raised as **P-45** | TradingView models no swap, and a parity cost array carries none (D-362): the MR run's total swap cost is exactly 0.00. There is nothing to disagree with. |
| 4 | The trailing level moving only at the bar close (**D-349 (a)**) | **stays `to_verify`** | Neither Pine script uses a trailing stop. It needs a third reference with `strategy.exit(trail_points=…)`, or an explicit decision to leave it unverified. |
| 5 | The parity conversion rate, the signal bar's `fx_close` (**D-349 (h)**) | **not verifiable by these references** — raised as **P-45** | Both references are USD-quoted, so no conversion is performed. |

The ATR warm-up note (HANDOFF §8.1) is **confirmed** for MR: the first engine entry and the
first TradingView entry are both bar 14, and no trade is classified `atr_warm_up`. The Pine
script's own `not na(r) and not na(a)` guard is what keeps TradingView out of the warm-up, so
this confirms agreement on *these* scripts, not that TradingView never enters during a warm-up.

**Three of the five items (3, 4, 5) cannot be closed by any TradingView reference.** That is a
question for the supervisor, not a judgement for this task: **P-45** asks whether to record
them as confirmed-by-construction / permanently unverifiable, or to commission a third export.

## 4. Wilder's ATR, before any trade was compared

Supervisor note 3. The gate asserts the engine's ATR equals an **independently written Wilder
RMA** (`wilder_atr` in the gate file, sharing no code with the engine) on the exported bars,
before the first trade is compared; a mismatch there is its own finding, not a trade reason.

Separately, and **outside CI**, the engine's ATR was compared with TradingView's own exported
`ATR_14`: equal to 1.5e-15 relative on 21,973 XAUUSD hourly bars and 8,454 SPY daily bars.
That check lives in `tests/unit/test_F_0_4_2_golden.py`, which needs `SFAC_RAW_ROOT` and
therefore **skips in CI** — it is evidence, not a gate.

## 5. Deviations and judgement calls

1. **D-370 — the MR exit signal.** `close > high[1]` is a *signal* exit with no registered
   component. No exit components exist yet, which is exactly why `BacktestSpec` is interim
   (D-344) and takes the signal as an array. The rule is named in the parity config
   (`exit_signal: close_above_prev_high`) and implemented in
   `selftest/parity_run.PARITY_EXIT_RULES`, reachable only from a parity config. **Entry**
   rules are unaffected: an entry without a registered component still stops the task (T11 §3).
   This is the one place where T11 wrote a rule rather than mapping one, and it is recorded.
2. **The 3-ATR stop is the engine's disaster stop, not `sl_atr`.** The script places it once at
   entry and never moves it, which is what D-130's disaster stop is.
3. **F-X.7 is partial** (D-365): reproducibility is proven for the two parity references, not
   for the pipeline at large.

## 6. Files

| file | what |
|---|---|
| `src/strategy_factory/selftest/parity_refs.py` | the reference store: chart CSV, the `.xlsx` Trades and Properties sheets (openpyxl, lazy, D-317), the Pine `strategy()` parser, the manifest check on every load |
| `src/strategy_factory/selftest/parity_compare.py` | pairing, classification, the difference table, `round_like_tradingview`, the ATR check |
| `src/strategy_factory/selftest/parity_report.py` | both net-profit figures (D-364), the small-profit flag, the D-011 verdict |
| `src/strategy_factory/selftest/parity_run.py` | **new** — config + fixtures → engine → comparison; the glue the gate needs |
| `src/strategy_factory/core/parity_config.py` | the parity config model; `StrategyRef.exit_signal` (D-370) |
| `configs/parity/spy_mr_1d.yaml` | MR, with its strategy block filled |
| `configs/parity/xauusd_tf_1h.yaml` | TF — no strategy block yet, on purpose |
| `tests/parity/test_F_0_3_8_d011_gate.py` | **new** — the gate |
| `src/strategy_factory/engine/kernel.py`, `engine/api.py`, `core/config.py` | `parity_tick`, `entry_requires_flat` (D-366, D-367) |

## 7. Open questions

- **P-45** — items 3, 4 and 5 of the `to_verify` ledger (above).
- **D-368** is answered and queued as its own task **after** T11: the metrics fixture scales
  `qty`; a falsifying example is pinned as an `@example`; the per-PR Hypothesis job stays
  derandomized and a weekly randomized job reports without gating.

## 8. Still to do before this review is finished

1. The TF Long, TF Short, fresh OHLC and new `.pine` exports arrive → add them to
   `tests/fixtures/parity/` with their manifest (D-359), mark the two-sided export
   **superseded** in the manifest notes (D-600).
2. Map the TF strategy in `configs/parity/xauusd_tf_1h.yaml`; the gate then picks it up
   automatically (`test_F_0_3_8_d011_every_mapped_reference_is_in_the_gate` fails until it is
   listed, so it cannot be forgotten).
3. Run both one-sided comparisons; both must pass D-011. Report both net-profit figures and
   flag the tight relative basis rather than deciding it (D-364).
4. Close item 1 of the ledger (D-335) with the TF tie evidence.
