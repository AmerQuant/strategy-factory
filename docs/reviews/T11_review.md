# T11 — TradingView parity (F-0.3.8) — review

**Critical task (D-402): stops here for "Approved".** Branch `a/T11-parity`.

Every number below is pinned by a test unless it is explicitly marked *measured*. The
acceptance reviewer checked the first version of this review claim by claim; what it found,
and what changed because of it, is in §7.

## 1. D-011 result per reference

| reference | bars | TradingView trades | matched | net profit (engine / TV) | difference | D-011 |
|---|---|---|---|---|---|---|
| **MR — `BATS:SPY` 1D** | 8,467 (1993-01-29 … 2026-09-18) | 462 | **457 = 98.92 %** (5 differ in quantity by one share) | 185,784.36 / 185,810.06 | **−25.70 USD** = 0.0138 % of \|TV\|, 0.0257 % of capital | **PASS** |
| **TF long — `OANDA:XAUUSD` 1H** | 21,986 (2023-01-02 … 2026-09-18) | 519 (+1 still open, excluded on both sides) | **519 = 100.00 %** | 20,637.93 / 20,637.96 | **−0.03 USD** = 0.0001 % of \|TV\|, 0.0000 % of capital | **PASS** |
| **TF short — `OANDA:XAUUSD` 1H** | 21,986 (2023-01-02 … 2026-09-18) | 400 | **400 = 100.00 %** | −43,610.26 / −43,610.28 | **+0.02 USD** = 0.0000 % of \|TV\|, 0.0000 % of capital | **PASS** |

Reason tables (`test_F_0_3_8_d011_the_reason_table_is_the_reviewed_one`): MR
`{match: 457, quantity: 5}`, TF long `{match: 519}`, TF short `{match: 400}`. Engine net
profits are pinned to the cent (`…the_engine_net_profit_is_the_reviewed_one`), TradingView's
by the loader tests. No reference has an extra or a missing trade: the engine enters on
exactly the bars TradingView does.

**MR was reported as 462/462 before this review, and that was overstated.** The comparison
did not check quantity, so five trades one share off were called matches. It does now, and MR
is **98.92 %** — a pass with **4 trades of headroom**. The cause is understood and is **P-48**
(§7.2): TradingView sizes on the close rounded to the tick.

Both net-profit figures are reported per **D-364**. No TradingView profit is small against
capital, so no reference is flagged. The relative basis is tight on TF, as the supervisor
expected: flipping the one D-335 bar (§4) moves TF long to ~5.2 % of \|TV\| (*measured* by
mutating the engine, not a committed test).

The gate is `tests/parity/test_F_0_3_8_d011_gate.py`. It runs on the **committed fixtures**
(D-359) and therefore in CI, is never skipped (rule 9), takes both thresholds from the parity
config (rule 1), and fails a test of its own if a mapped reference is not gated.

## 2. What makes the references match

Two engine options, both **parity-only** and unreachable from a research run:

| decision | option |
|---|---|
| **D-366** | `parity_tick_size` — stop and target distances rounded to whole ticks, half away from zero, measured from the fill, as `math.round(k * ATR / syminfo.mintick)` does |
| **D-367** | `entry_requires_flat_at_signal` — the entry is gated on being flat at the **signal close**, as `flat = strategy.position_size == 0` does in both scripts; default **off** = D-336 |

Switching each one off (`test_F_0_3_8_d366_d367_the_option_table`, 12 runs):

| configuration | MR | TF long | TF short |
|---|---|---|---|
| neither | 446, +7,031.33 — FAIL | 519, −1,080.13 — **FAIL** | 399, −426.29 — PASS |
| D-366 only | 450, +7,030.75 — FAIL | 519, −1,080.29 — **FAIL** | 400, −426.60 — PASS |
| D-367 only | **453 (98.05 %)**, −18.81 — PASS | 519, +0.12 — PASS | 399, +0.33 — PASS |
| **both** | **457 (98.92 %), −25.70** | **519, −0.03** | **400, +0.02** |

With D-367 off, the difference report says *why*: MR has **17 `same_open_reentry`**, 1 other
extra and 7 knock-on misses; TF long 2 and TF short 1 `same_open_reentry`. That is D-336's
re-entry at the exit open, which the scripts' `flat` gate forbids.

- **D-367 is load-bearing.** Without it MR fails on both legs and TF long on net profit.
- **D-366 is not carried by the gate on any reference** — every configuration with D-367 on
  passes without it — but on MR it is **one trade** from carrying it (98.05 % against the 98 %
  line). Its case is the result: MR 98.05 % → 98.92 %, TF short 99.75 % → 100 %, and the
  net-profit differences from tenths of a dollar to cents. If D-366 is questioned, this
  table is the argument, not the green check.
- **TF long matches 519/519 while failing** with D-367 off: the 2 extra trades cannot lower a
  trade share defined as `matched / TradingView trades`. Only the net-profit leg caught them.
  That is **P-47**.

## 3. The `to_verify` ledger (§5, D-338 rule 1, D-349, D-371)

**No TradingView export can ever close three of these five items.** D-371 settles them as
**confirmed by construction** — evidenced by the hand fixtures and `tests/oracle` — and takes
them off the `to_verify` list under that name, so nobody later goes looking for an export
that cannot exist.

| # | item | outcome | evidence |
|---|---|---|---|
| 1 | O→H→L→C path and its tie (**D-335**) | **partly confirmed — still `to_verify`, P-46** | Over TF's 919 trades exactly **one** bar touched both levels: target first by the path rule, and the engine and TradingView both took the target. The **stop-first branch never occurs**, and there is **no exact tie** (§4). |
| 2 | Exit + re-entry at one open (**D-336**) | **not verified by any reference — still `to_verify`, P-49** | Neither reference exercises it, and neither can: both scripts gate entries on being flat at the signal close (D-367), which rules a re-entry at the exit's open out. `test_F_0_3_8_d336_is_never_exercised_under_the_flat_gate` pins 0 such events per reference. **The first version of this review said D-336 was confirmed against MR. That was wrong** (§7.3), and D-371 repeats it — hence P-49. |
| 3 | No swap on an intrabar exit in a rollover bar (**D-327**) | **confirmed by construction** (D-371) — not `to_verify` | TradingView models no swap at all, and a parity cost array carries none (D-362). |
| 4 | The trailing level moving only at the bar close (**D-349 (a)**) | **confirmed by construction** (D-371) — not `to_verify` | Neither reference script trails; no further reference is commissioned. |
| 5 | The parity conversion rate, the signal bar's `fx_close` (**D-349 (h)**) | **confirmed by construction** (D-371) — not `to_verify` | Both references are USD-quoted, so no conversion is performed. |

The kernel docstring says the same things in the same words, and
`test_F_0_3_8_d371_the_to_verify_ledger_does_not_drift` holds the two together — it now also
fails if either calls D-336 confirmed.

**The acceptance criterion "every one of the five `to_verify` items is either confirmed or
replaced by a recorded decision" is not met: three of five are.** D-335 is confirmed in one
of its three cases (P-46) and D-336 in none (P-49). Both are *testable* by TradingView with a
different script — unlike items 3–5 — so whether to close them by construction or by a
targeted reference is the supervisor's call.

The ATR warm-up note (HANDOFF §8.1): no TradingView trade enters before the engine's ATR is
usable on any reference — the `atr_warm_up` reason can now fire and never does. (In the first
version it could not fire at all; §7.5.) The scripts' own `not na(...)` guards keep
TradingView out of the warm-up, so this is agreement on *these* scripts.

## 4. D-335 — the evidence, and why it is thin

`test_F_0_3_8_d335_the_intrabar_path_on_every_bar_that_touched_both_levels` recomputes every
TF trade's stop and target from the Pine rule — `math.round(k * ATR / mintick)` ticks from the
fill — **without the engine's levels**, and checks them first: they equal the engine's exit
fill on all **859** stop/target exits (**845** at the level, **14** at an open that gapped
past it). Then, on every bar that touched both levels, the path rule, the engine and
TradingView must all agree.

| case | bars | agreement |
|---|---|---|
| target first | **1** (TF long) | engine TP, TradingView TP |
| stop first | **0** | — |
| exact tie (`high − open == open − low`) | **0** | — |

Mutating the engine's path choice fails that test and the TF long gate (checked).

## 5. Wilder's ATR, before any trade was compared

Supervisor note 3. For every reference the gate asserts, before the first trade is compared,
that the engine's ATR equals an **independently written Wilder RMA** (`wilder_atr`, sharing
no code with the engine) to a relative **1e-12**; the worst difference *measured* on XAUUSD is
1.52e-15 over 21,973 bars. Separately and **outside CI** the engine's ATR equals TradingView's
exported `ATR_14` to 1.5e-15 (`tests/unit/test_F_0_4_2_golden.py`, which needs the raw store
and skips in CI — evidence, not a gate).

## 6. The TF references (D-600)

**Checked before anything else, as asked:**

1. **`OANDA_XAUUSD, 60 2026-09-20b.csv` is byte-identical to `OANDA_XAUUSD, 60.csv`** (same
   SHA-256, `998d5ad9…`; both 983,456 bytes). The configs use **`OANDA_XAUUSD, 60.csv`** — the
   earlier-written file, already the fixture. The `b` copy is not a fixture; the fixture
   manifest records it under `duplicates_not_copied` (tested).
2. **The one-sided script's settings match the Properties sheet of both reports.** Its
   `strategy()` call is unchanged; the only edit is the `Direction` input. `cross_check_properties`
   finds no disagreement on either report, and each sheet's `Direction` is the side its file
   name says (`test_F_0_3_8_d600_each_one_sided_report_ran_the_direction_its_name_says`).

**For the user, about the raw store** (read-only, rule 11 — reported, not changed): the new
script's name **starts with two spaces** (`'  SF parity TF - Donchian 1H oneside.pine'`); the
fixture keeps it, because the D-359 test compares names. And the previous raw manifest listed
`'OANDA_XAUUSD, 60 .csv'`, a name no longer in the folder — the same bytes as the `b` file,
so evidently renamed afterwards.

**The manifest.** `scripts/write_parity_manifest.ps1`, run by stream A on the supervisor's
instruction, now writes `superseded` (the two-sided export and the original script, D-600) and
`duplicate_of` (by hash). Its first run marked the duplicate backwards — a space sorts before
`.` — so the original is now the **earliest-written** file of a group. Every previously
recorded file kept its hash.

**The fixtures and configs.** The two one-sided reports and the script are copied
byte-for-byte (2.39 MB in all; committed blobs verified against the raw manifest). The two
superseded files stay for the loader tests, marked, and no config reads them (tested).
`xauusd_tf_1h.yaml` is replaced by `xauusd_tf_1h_long.yaml` and `xauusd_tf_1h_short.yaml`:
`tf_donchian20_breakout` with `sl_atr 2`, `tp_atr 4`, `time_exit_bars 50`. The component
equals the Pine rule on all **21,986** bars, both sides
(`test_F_0_3_8_the_tf_component_is_the_pine_rule_on_every_bar`) — it declares
`trigger = "event"`, so this was checked rather than assumed. The engine's 3-ATR disaster
stop (D-130) sits behind the 2-ATR stop and can never fire first.

## 7. What was found, and what changed

**Found by me while doing §6:**

1. **The engine "open at the end" flag was never read.** The comparison read it from
   `result.meta` behind a `hasattr` guard; it lives on the run, so it was `False` for every
   reference and the report never said the engine's side was excluded. Matching was
   unaffected, but the MR test that checked it passed vacuously. Fixed; the open-trade test
   now proves both sides end the same way — flat on both, or open on both **with the same
   trade** (TF long: #520 and the engine's position both entered at bar 21955 at 4373.34).
2. **The comparison never compared quantity** — a sizing difference was called a match. It
   now compares to half a quantity step (quantities are whole steps) under a new reason,
   **`quantity`** (a deviation: none of the task's named ambiguities describes sizing). On MR
   this found five trades one share off. **TradingView sizes on
   `floor(notional / round(close[j−1], mintick))`**, which reproduces its quantity on all 462
   MR trades; the engine sizes on the exact close (D-347), and the five misses are early SPY
   closes in 1/32 (44.09375, 46.0625, …) finer than the tick. They carry −18.09 of MR's
   −25.70 USD (`test_F_0_3_8_p48_tradingview_sizes_on_the_tick_rounded_close`). TF is
   unaffected. The fix belongs in the parity branch, like D-366 — but the supervisor's rule was
   to change it only if the gate fails, and it does not: **the engine is unchanged; P-48.**

**Found by the acceptance reviewer, each verified before it was fixed:**

3. **The D-336 claim was wrong.** My evidence counted trades whose entry bar is *an* exit bar;
   the two it found exit on **their own** entry bar (same-bar disaster stops). There are no
   re-entries at an exit's open in any reference, and the `flat` gate means there cannot be.
   Corrected in the ledger, the kernel docstring and the drift test; D-371 repeats the wrong
   claim, so it goes back to the supervisor as **P-49**.
4. **D-364 was decided, not flagged.** When the TradingView profit was small, the verdict
   switched to the capital figure and passed on it; D-364 says the figure is *flagged* and the
   supervisor rules. The net-profit leg now has a third state, **`flagged`**, which does not
   pass — the gate fails with "the supervisor rules (D-364)" until a ruling. The 1 % threshold
   moved from code into the parity config (`small_net_profit_share`, rule 1). No current
   reference is affected.
5. **The classifier had the D-335 case backwards, and three reasons could not fire.** A path
   choice happens *within* one bar, so it is the **same exit bar at a different price**; the
   code labelled a *different* exit bar `intrabar_path` and the same-bar case `unexplained`.
   Now: same bar, a level exit, a different price → `intrabar_path`; a different exit bar →
   `unexplained` (or `sub_tick_level` if the price is within tolerance — a level one tick lower
   can be touched a bar later). `atr_warm_up` could never fire because nothing told the chart
   where the warm-up ends; `run_reference` now does. `same_open_reentry` was declared and never
   assigned; an extra engine trade entering at its previous trade's exit open is now labelled
   so. `rollover_swap`, `trailing_at_close` and `conversion_rate` cannot occur in TradingView
   parity (D-371) and are documented as such. The sub-tick tolerance moved into the parity
   config (`sub_tick_tolerance_ticks`, rule 1), and `compare()` now requires both tolerances —
   no caller can skip the quantity check.
6. **The naive oracle never ran D-366 or D-367.** It implemented both, but no oracle test
   passed them. The Hypothesis cases and the 600-seed sweep now draw both, the sweep asserts
   each option actually *changes* some run (an oracle that agrees only because an option never
   mattered proves nothing), and breaking either option in the naive engine alone fails the
   oracle (checked).
7. **No leakage test for the D-370 exit signal** (rule 3). Added:
   `tests/leakage/test_F_0_3_8_parity_exit_signal.py`, truncation invariance on the real MR
   chart for every rule in `PARITY_EXIT_RULES`, plus a non-vacuity check; a one-bar look-ahead
   fails it (checked).
8. **Two gate assertions could never fail** (`by_reason()["match"] == matched`, and a repeat of
   `trades_ok`). Replaced with checks that the verdict's thresholds are the config's.
9. **Numbers stated but not tested.** The option table, the engine net profits, the 859/845/14
   fill counts, the P-48 sizing evidence and the component-equals-Pine claim are now tests.

**Deviations and judgement calls:**

10. **File locations.** The task names `data/parity_refs.py` and `selftest/parity.py`; the code
    is `selftest/parity_refs.py`, `parity_compare.py`, `parity_report.py` and `parity_run.py`.
    `data/` is stream B's (D-357 (2)), and the move was the supervisor's instruction.
11. **D-370** — the MR exit signal `close > high[1]` has no registered component; it is named
    in the parity config and implemented in `selftest/parity_run.PARITY_EXIT_RULES`, reachable
    only from a parity config. Entry rules are unaffected.
12. **Stop mappings.** MR's 3-ATR stop is the engine's disaster stop (placed once, never
    moved); TF's 2-ATR stop is `sl_atr`, with the disaster stop behind it.
13. **F-X.7 is partial** (D-365): bit-identical reruns are proven for the three references
    (`test_F_X_7_the_gate_run_is_reproducible`), not for the pipeline at large.
14. **Every guard test added here was mutation-checked**: the open flag, the quantity check,
    the D-335 path choice, the classifier's same-bar rule, the warm-up, the re-entry label,
    both oracle options, the look-ahead, and the ledger drift each fail their test when broken.

## 8. How each acceptance criterion is tested

| criterion | proving test | result |
|---|---|---|
| D-011: ≥ 98 % matched and net profit ≤ 3 %, per reference, never skipped | `test_F_0_3_8_d011_gate` × 3 | **pass** |
| ATR confirmed before any trade is compared (note 3) | `…d011_atr_is_wilders_before_any_trade_is_compared` × 3 | pass |
| The open trade excluded on both sides (note 2) | `…open_trade_is_excluded_on_both_sides` × 3, `…engine_open_flag_is_read_from_the_run` | pass |
| D-364: both figures; a small TV profit flagged, not decided | `…d364_*`, `…d011_verdict_uses_the_config_thresholds` | pass |
| A missing reference fails loudly, never a skip (P-40, D-360) | `…d011_a_missing_reference_fails_loudly` | pass |
| Every mapped reference is gated | `…d011_every_mapped_reference_is_in_the_gate` | pass |
| Difference report with a reason per mismatch — match, one-bar shift, quantity, missing, extra (+ same-bar level swap, other exit bar, time exit, sub-tick, warm-up, re-entry, opposite direction) | `tests/unit/test_F_0_3_8_parity_compare.py` (12 cases), reason tables pinned per reference | pass |
| Store: hashes verified, tampering raises, stamps unchanged, no raw writes | `tests/unit/test_F_0_3_8_parity_refs.py` | pass |
| Config: every `pine.*`, `parity_qty_step`, `atr_length`, `parity_tick_size` required; the hash covers every Pine value | `…parity_config_*`, `…d366_parity_config_requires_the_mintick` | pass |
| Costs from the Pine settings only (D-362, D-347) | `…d362_*` | pass |
| D-366 / D-367 parity-only, and equal to the naive oracle | `…d366_tick_rounding_applies_only_in_parity_mode`, `…d367_*`, `tests/oracle` (both options drawn and swept) | pass |
| Leakage: the parity exit signal sees no future bar (rule 3) | `tests/leakage/test_F_0_3_8_parity_exit_signal.py` | pass |
| D-600: one-sided references; superseded files never read; duplicate not a fixture | `…d600_*` | pass |
| Reproducibility (F-X.7, partial per D-365) | `test_F_X_7_the_gate_run_is_reproducible` × 3 | pass |
| **Every one of the five `to_verify` items confirmed or replaced by a decision** | the ledger (§3), `…d371_the_to_verify_ledger_does_not_drift`, `…d336_…`, `…d335_…` | **not met — 3 of 5; D-335 and D-336 wait on P-46 / P-49** |

## 9. Files

| file | what |
|---|---|
| `src/strategy_factory/selftest/parity_refs.py` | the reference store: CSV, `.xlsx` Trades and Properties (openpyxl, lazy, D-317), the Pine parser, the manifest check on every load |
| `src/strategy_factory/selftest/parity_compare.py` | pairing and classification (quantity; the same-bar path rule; warm-up; same-open re-entry), the difference table, the ATR check |
| `src/strategy_factory/selftest/parity_report.py` | both net-profit figures, the `flagged` state (D-364), the D-011 verdict |
| `src/strategy_factory/selftest/parity_run.py` | config + fixtures → engine → comparison; the warm-up; D-370's exit signals |
| `src/strategy_factory/core/parity_config.py` | the parity config; `StrategyRef.exit_signal` (D-370), `small_net_profit_share`, `sub_tick_tolerance_ticks` |
| `src/strategy_factory/engine/kernel.py`, `engine/api.py`, `core/config.py` | `parity_tick`, `entry_requires_flat` (D-366, D-367); the `to_verify` ledger |
| `configs/parity/spy_mr_1d.yaml`, `xauusd_tf_1h_long.yaml`, `xauusd_tf_1h_short.yaml` | the three references, each mapped |
| `scripts/write_parity_manifest.ps1` | `superseded` and `duplicate_of` notes |
| `tests/fixtures/parity/` | 9 fixtures + manifest (2 superseded, kept for the loader tests) |
| `tests/parity/test_F_0_3_8_d011_gate.py` | the gate, the D-335 and D-336 evidence, the option table, the pinned numbers, the ledger drift test |
| `tests/unit/test_F_0_3_8_parity_compare.py` | **new** — the classifier, case by case |
| `tests/unit/test_F_0_3_8_parity_refs.py` | the store, the config, the costs, D-364, D-600 |
| `tests/leakage/test_F_0_3_8_parity_exit_signal.py` | **new** — truncation invariance of the D-370 signals |
| `tests/oracle/test_F_0_3_1_oracle.py`, `tests/fixtures/engine.py` | the oracle now runs D-366 and D-367 |

Dependencies: none added.

## 10. Open questions

- **P-46** — D-335 is confirmed only in its target-first case; the stop-first branch and the
  exact tie never occur in these references. By construction, or a targeted reference?
- **P-47** — D-011's trade share is `matched / TradingView trades`, so extra engine trades
  never lower it. No current result changes. Define it over the union?
- **P-48** — TradingView sizes on the tick-rounded close; the engine's parity sizing (D-347)
  uses the exact close. MR passes at 98.92 %. Round in the parity branch, as D-366 did?
- **P-49** — **D-371 says D-336 is confirmed against MR; it is not**, and my evidence for it
  was wrong. Amend the clause, and decide D-336 with P-46.
- **D-368** stays queued as its own task **after** T11.

## 11. Acceptance

See the commit message for the numbers of the final run: fast suite, `tests/parity
tests/leakage tests/oracle`, `pytest -m db` (0 skipped), ruff, format, mypy, the stream
guards.
