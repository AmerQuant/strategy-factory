# T11 — TradingView parity (F-0.3.8) — review

**Critical task (D-402): stops here for "Approved".** Branch `a/T11-parity`.

## 1. D-011 result per reference

| reference | bars | TradingView trades | matched | net profit (engine / TV) | difference | D-011 |
|---|---|---|---|---|---|---|
| **MR — `BATS:SPY` 1D** | 8,467 (1993-01-29 … 2026-09-18) | 462 | **457 = 98.92 %** (5 differ in quantity by one share) | 185,784.36 / 185,810.06 | **−25.70 USD** = 0.0138 % of \|TV\|, 0.0257 % of capital | **PASS** |
| **TF long — `OANDA:XAUUSD` 1H** | 21,986 (2023-01-02 … 2026-09-18) | 519 (+1 still open, excluded) | **519 = 100.00 %** | 20,637.93 / 20,637.96 | **−0.03 USD** = 0.0001 % of \|TV\|, 0.0000 % of capital | **PASS** |
| **TF short — `OANDA:XAUUSD` 1H** | 21,986 (2023-01-02 … 2026-09-18) | 400 | **400 = 100.00 %** | −43,610.26 / −43,610.28 | **+0.02 USD** = 0.0000 % of \|TV\|, 0.0000 % of capital | **PASS** |

Every reference has **0 extra** and **0 missing** trades: the engine enters on exactly the
bars TradingView does. Reason tables — pinned by
`test_F_0_3_8_d011_the_reason_table_is_the_reviewed_one`: MR `{match: 457, quantity: 5}`, TF
long `{match: 519}`, TF short `{match: 400}`.

**MR was reported as 462/462 before this review, and that was overstated.** The comparison
did not check quantity, so five MR trades one share off were called matches. It does now, and
MR is **98.92 %** — still a pass, with **4 trades of headroom** above 98 %. The cause is
understood and is **P-48**: TradingView sizes on the close rounded to the tick (§7).

Both net-profit figures are reported per **D-364**. None of the three TradingView profits is
small against capital, so the small-profit flag does not fire. The tight relative basis the
supervisor anticipated for TF is real (§2): one wrong intrabar choice on TF long moves the
difference to ~5.2 % of \|TV\|.

The result is produced by `tests/parity/test_F_0_3_8_d011_gate.py`, which runs on the
**committed fixtures** (D-359) and therefore in CI, and is never skipped (CLAUDE.md rule 9).
A parity config that gets a `strategy` block but is not in the gate fails a test of its own,
so a mapped reference cannot go ungated.

## 2. What makes the references match

Two engine options, both **parity-only** and unreachable from a research run:

| decision | option |
|---|---|
| **D-366** | `parity_tick_size` — stop and target distances rounded to whole ticks, half away from zero, measured from the fill, as `math.round(k * ATR / syminfo.mintick)` does |
| **D-367** | `entry_requires_flat_at_signal` — the entry is gated on being flat at the **signal close**, as `flat = strategy.position_size == 0` does in both scripts; default **off** = D-336 |

Measured by switching each one off (with quantity compared):

| configuration | MR | TF long | TF short |
|---|---|---|---|
| neither | 96.54 %, +7,031.33 — FAIL | 100.00 %, −1,080.13 — **FAIL** | 99.75 %, −426.29 — PASS |
| D-366 only | 97.40 %, +7,030.75 — FAIL | 100.00 %, −1,080.29 — **FAIL** | 100.00 %, −426.60 — PASS |
| D-367 only | **98.05 %**, −18.81 — PASS | 100.00 %, +0.12 — PASS | 99.75 %, +0.33 — PASS |
| **both** | **98.92 %, −25.70** | **100.00 %, −0.03** | **100.00 %, +0.02** |

What this says, plainly:

- **D-367 is load-bearing.** Without it MR fails on both legs (18 extra, 7 missing trades), and
  TF long fails on net profit.
- **D-366 is not carried by the gate on any reference** — every configuration with D-367 on
  passes without it. But on MR it is **one trade** from carrying it: 98.05 % against the 98 %
  line. Its case is the result — MR from 98.05 % to 98.92 %, TF short from 99.75 % to 100 %,
  and the net-profit differences from tenths of a dollar to cents. If D-366 is questioned,
  this table is the argument, not the green check.
- **TF long matches 519/519 while failing** (rows 1–2): with D-367 off the engine takes **2
  extra** trades — same-close re-entries TradingView does not — and the trade share cannot
  see them, because it is `matched / TradingView trades`. Only the net-profit leg caught them.
  That is **P-47**.

## 3. The `to_verify` ledger (§5, D-338 rule 1, D-349, D-371)

**No TradingView export can ever close three of these five items.** D-371 settles them as
**confirmed by construction**, evidenced by the hand fixtures and `tests/oracle`, and takes
them off the `to_verify` list under that name so nobody later goes looking for an export that
cannot exist.

| # | item | outcome | evidence |
|---|---|---|---|
| 1 | O→H→L→C path and its tie (**D-335**) | **partly confirmed — still `to_verify`, P-46** | TF is the only reference with both a stop and a target. Over its 919 trades exactly **one** bar touched both levels: the path rule said target first, and the engine and TradingView both took the target. The **stop-first branch never occurs**, and there is **no exact tie**. See §4. |
| 2 | Exit + re-entry at one open (**D-336**) | **confirmed** against MR | 2 of the 462 engine entries fall on a bar that is also an exit bar (engine trades 337 and 366), and **both are full matches**, quantity included. |
| 3 | No swap on an intrabar exit in a rollover bar (**D-327**) | **confirmed by construction** (D-371) — not `to_verify` | TradingView models no swap at all, and a parity cost array carries none (D-362): the total swap cost of every parity run is exactly 0.00. |
| 4 | The trailing level moving only at the bar close (**D-349 (a)**) | **confirmed by construction** (D-371) — not `to_verify` | Neither reference script trails, and no further reference is commissioned. |
| 5 | The parity conversion rate, the signal bar's `fx_close` (**D-349 (h)**) | **confirmed by construction** (D-371) — not `to_verify` | Both references are USD-quoted, so no conversion is performed. |

The ATR warm-up note (HANDOFF §8.1) is **confirmed** for MR (first entry bar 14 on both
sides, no `atr_warm_up` classification). The script's own `not na(...)` guards keep
TradingView out of the warm-up, so this confirms agreement on *these* scripts.

The kernel docstring and this table say the same thing in the same words, and
`test_F_0_3_8_d371_the_to_verify_ledger_does_not_drift` holds them together.

**The acceptance criterion "every one of the five `to_verify` items is either confirmed or
replaced by a recorded decision" is therefore met for four of five.** D-335 is confirmed in
one of its three cases and waits on P-46 for the other two. I have not rounded that up.

## 4. D-335 — the evidence, and why it is thin

`test_F_0_3_8_d335_the_intrabar_path_on_every_bar_that_touched_both_levels` recomputes the
stop and target of every TF trade from the Pine rule — `math.round(k * ATR / mintick)` ticks
from the fill — **without using the engine's levels**, and first checks them: they equal the
engine's exit fill on **all 859** stop/target exits (or the open, where the bar gapped past
the level; 14 did). Then, on every bar that touched both levels, the path rule, the engine and
TradingView must all agree.

| case | bars | agreement |
|---|---|---|
| target first (the high/low in the trade's favour is nearer the open) | **1** (TF long) | engine TP, TradingView TP |
| stop first | **0** | — |
| exact tie (`high − open == open − low`) | **0** | — |

The counts are pinned in the test because they are this review's evidence. Mutating the
engine's path choice fails both that test and the TF long gate: flipping the one bar costs
~1,079 USD, 518/519, and the net-profit leg fails at ~5.2 % of \|TV\|.

Unlike items 3–5, the missing cases **can** be tested by TradingView — they are rare on
XAUUSD 1H, not impossible. **P-46** asks whether to close them by construction, as D-371 did,
or to commission a targeted reference (the TF script with a tight stop and target so both are
touched often, on a 2-decimal daily chart where exact ties occur).

## 5. Wilder's ATR, before any trade was compared

Supervisor note 3. The gate asserts, **before the first trade is compared**, that the engine's
ATR equals an **independently written Wilder RMA** (`wilder_atr` in the gate file, sharing no
code with the engine) on each exported chart: worst relative difference **1.52e-15** over
21,973 XAUUSD hourly bars, and likewise on SPY. A mismatch there would be its own finding.

Separately and **outside CI**, the engine's ATR equals TradingView's own exported `ATR_14` to
1.5e-15 on 21,973 XAUUSD hourly and 8,454 SPY daily bars (`tests/unit/test_F_0_4_2_golden.py`,
which needs `SFAC_RAW_ROOT` and so **skips in CI** — evidence, not a gate).

## 6. The TF references (D-600)

**Checked before anything else, as asked:**

1. **`OANDA_XAUUSD, 60 2026-09-20b.csv` is byte-identical to `OANDA_XAUUSD, 60.csv`** — same
   SHA-256 (`998d5ad9…`), both 983,456 bytes. The configs use **`OANDA_XAUUSD, 60.csv`**: it is
   the earlier-written file, already the committed fixture and already verified. The `b` copy
   is not copied into the fixtures; the fixture manifest records it under
   `duplicates_not_copied`.
2. **The one-sided script's settings match the Properties sheet of both reports.** Its
   `strategy()` call is unchanged from the superseded script; the only edit is the `Direction`
   input. `cross_check_properties` finds no disagreement for either report, and each sheet's
   `Direction` is the side its file name says (Long / Short) — pinned by
   `test_F_0_3_8_d600_each_one_sided_report_ran_the_direction_its_name_says`.

**Two things the user should know about the raw store** (read-only, CLAUDE.md rule 11, so
reported, not changed):

- The new script's file name **starts with two spaces**: `'  SF parity TF - Donchian 1H
  oneside.pine'`. It works, and the fixture keeps the exact name because the D-359 test
  compares fixture and raw names. If it is renamed in the raw store, rerun the manifest
  script and rename the fixture to match.
- The previous raw manifest listed `'OANDA_XAUUSD, 60 .csv'`, a name no longer in the folder —
  the same bytes as the `b` file, so it was evidently renamed after that manifest was written.
  The new manifest supersedes it; nothing else in it changed hash.

**The manifest.** `scripts/write_parity_manifest.ps1` was run by stream A on the supervisor's
instruction and now writes two kinds of note: **`superseded`** (the two-sided export and the
original script, with D-600 as the reason) and **`duplicate_of`**, found by hash. The first
run marked the duplicate the wrong way round — a space sorts before `.`, so the `b` file came
first — and I fixed the script to treat the **earliest-written** file as the original rather
than the first name in sort order. All 10 files are recorded; every previously recorded file
kept its hash.

**The fixtures.** The two one-sided reports and the one-sided script are copied
byte-for-byte (2.39 MB in total). The two superseded files stay as fixtures for the loader
tests, are marked `superseded` in the fixture manifest, and a test proves no parity config
reads them.

**The configs.** `xauusd_tf_1h.yaml` pointed at the superseded two-sided export; it is
replaced by **`xauusd_tf_1h_long.yaml`** and **`xauusd_tf_1h_short.yaml`**. The strategy maps
to `tf_donchian20_breakout`, which I checked equals the Pine rule `close > ta.highest(high,
20)[1]` (short: `close < ta.lowest(low, 20)[1]`) **on every one of the 21,986 bars**, both
sides — the component declares `trigger = "event"`, so I checked rather than assumed that it
is not an edge trigger. Exits: `sl_atr: 2.0`, `tp_atr: 4.0`, `time_exit_bars: 50`. The script
has no 3-ATR stop; the engine's disaster stop (D-130) sits at 3 ATR, beyond the 2-ATR stop, so
it can never fire first — on a gap either, where the level nearest the open wins.

## 7. Deviations, bugs found, and judgement calls

1. **A bug of mine, found on TF long and fixed.** The comparison read the engine's "open at the
   end" flag from `result.meta` behind a `hasattr` guard; the flag lives on the run, so it was
   `False` for **every** reference, and the difference report never said the engine's side was
   excluded. Matching was unaffected (an open position never enters the closed-trade list),
   but the MR test that checked this passed vacuously. Fixed, with a regression test, and the
   open-trade test now proves **both sides end the same way** — flat on both, or open on both
   **with the same trade** (TF long: TradingView's open #520 and the engine's open position
   both entered at bar 21955, 2026-09-17 13:00 UTC, at 4373.34). Reintroducing the bug fails
   both tests (checked).
2. **The comparison never compared quantity, and nothing tested its classification.** The
   task's Tests section asks for hand-built trade lists exercising a perfect match, a one-bar
   entry shift, a quantity difference, a missing trade and an extra trade; I had cited tests
   for this in the draft of this review, and they did not exist. They do now
   (`tests/unit/test_F_0_3_8_parity_compare.py`, 8 cases, each changing one thing on the
   TradingView side of a real engine run). Writing the quantity case showed that `_classify`
   had no quantity check at all, so a sizing difference was called a match. It now compares
   quantity to half a step and classifies a difference as **`quantity`** — a new reason, since
   none of the task's named ambiguities describes sizing (a deviation; the alternative was
   `unexplained` for a difference whose cause is known). Removing the check fails the test
   (checked). On the real references this found MR's five one-share differences:
   **TradingView sizes on `floor(notional / round(close, mintick))`**, which reproduces its
   quantity on **462 of 462** MR trades; the engine's parity sizing (D-347) uses the exact
   close, and the five misses are early SPY closes in 1/32 (44.09375, 46.0625, …) finer than
   the tick. They account for −18.09 of MR's −25.70 USD. TF is unaffected. The fix belongs in
   the parity branch, like D-366 — but your rule was to change it only if the gate fails, and
   it does not, so the engine is **unchanged** and it is **P-48**.
3. **D-370 — the MR exit signal.** `close > high[1]` is a signal exit with no registered
   component; it is named in the parity config and implemented in
   `selftest/parity_run.PARITY_EXIT_RULES`, reachable only from a parity config. Entry rules
   are unaffected. TF needs no exit signal.
4. **Stop mappings.** MR's 3-ATR stop is the engine's disaster stop (the script places it once
   and never moves it); TF's 2-ATR stop is `sl_atr`, with the disaster stop behind it.
5. **F-X.7 is partial** (D-365): reproducibility is proven for the three parity references
   (`test_F_X_7_the_gate_run_is_reproducible`, bit-identical trades and equity), not for the
   pipeline at large.
6. **Every guard test added here was mutation-checked**: the open-flag bug, the D-335 path
   choice, the quantity check and the ledger drift each fail their test when reintroduced.

## 8. How each acceptance criterion is tested

| criterion (`docs/features.md`, T11 task) | test |
|---|---|
| D-011: ≥ 98 % matched, net profit ≤ 3 %, never skipped | `test_F_0_3_8_d011_gate` × 3 references |
| ATR confirmed before trades are compared (note 3) | `test_F_0_3_8_d011_atr_is_wilders_before_any_trade_is_compared` |
| The open trade excluded on both sides (note 2) | `test_F_0_3_8_d011_the_open_trade_is_excluded_on_both_sides`, `test_F_0_3_8_the_engine_open_flag_is_read_from_the_run` |
| Both net-profit figures, flag rather than decide (D-364) | `test_F_0_3_8_d364_*`; the gate prints both |
| A missing reference fails loudly, never a skip (P-40, D-360) | `test_F_0_3_8_d011_a_missing_reference_fails_loudly` |
| Every mapped reference is gated | `test_F_0_3_8_d011_every_mapped_reference_is_in_the_gate` |
| Reference store: hashes, manifest, stamps unchanged, raw store never written | `tests/unit/test_F_0_3_8_parity_refs.py` (D-359, D-600 tests) |
| Config: every `pine.*`, `parity_qty_step`, `atr_length` required; hash covers every Pine value | `test_F_0_3_8_parity_config_*` |
| Costs from Pine settings only (D-362, D-347) | `test_F_0_3_8_d362_*` |
| Difference report with a reason per mismatch: a perfect match, a one-bar entry shift, a quantity difference, a missing and an extra trade (plus a later exit bar, a sub-tick exit and the opposite direction) | `tests/unit/test_F_0_3_8_parity_compare.py` (8 cases); the gate prints it and `test_F_0_3_8_d011_the_reason_table_is_the_reviewed_one` pins it |
| `to_verify` items confirmed or decided | §3 — **four of five**; D-335 partly, P-46 |
| Reproducibility (F-X.7) | `test_F_X_7_the_gate_run_is_reproducible` × 3 |

## 9. Files

| file | what |
|---|---|
| `src/strategy_factory/selftest/parity_refs.py` | the reference store: chart CSV, the `.xlsx` Trades and Properties sheets (openpyxl, lazy, D-317), the Pine parser, the manifest check on every load |
| `src/strategy_factory/selftest/parity_compare.py` | pairing, classification, the difference table, `round_like_tradingview`, the ATR check; **the open-flag fix** |
| `src/strategy_factory/selftest/parity_report.py` | both net-profit figures (D-364), the small-profit flag, the D-011 verdict |
| `src/strategy_factory/selftest/parity_run.py` | config + fixtures → engine → comparison |
| `src/strategy_factory/core/parity_config.py` | the parity config model; `StrategyRef.exit_signal` (D-370) |
| `src/strategy_factory/engine/kernel.py`, `engine/api.py`, `core/config.py` | `parity_tick`, `entry_requires_flat` (D-366, D-367); the `to_verify` ledger (D-371, P-46) |
| `configs/parity/spy_mr_1d.yaml`, `xauusd_tf_1h_long.yaml`, `xauusd_tf_1h_short.yaml` | the three references, each mapped |
| `scripts/write_parity_manifest.ps1` | `superseded` and `duplicate_of` notes |
| `tests/fixtures/parity/` | 9 fixtures + manifest (2 superseded, kept for the loader tests) |
| `tests/parity/test_F_0_3_8_d011_gate.py` | the gate, the D-335 evidence, the ledger drift test |
| `tests/unit/test_F_0_3_8_parity_refs.py` | the store, the config, the costs, the D-600 tests |

Dependencies: none added.

## 10. Open questions

- **P-46** — D-335 is confirmed only in its target-first case; the stop-first branch and the
  exact tie never occur in the TF references. Close them by construction (as D-371), or
  commission a targeted reference?
- **P-47** — D-011's trade share is `matched / TradingView trades`, so extra engine trades never
  lower it. No current result changes (all three references have 0 extras). Define it over the
  union instead?
- **P-48** — TradingView sizes on the close rounded to the tick; the engine's parity sizing
  (D-347) uses the exact close. Five MR trades are one share off; MR passes at 98.92 %. Round
  the sizing close in the parity branch only, as D-366 did for the levels?
- **D-368** stays queued as its own task **after** T11 (the metrics fixture; `@example` pinning;
  the weekly randomized Hypothesis job).

## 11. Acceptance

```
uv run pytest -m "not slow" -q                          see the commit
uv run pytest tests/parity tests/leakage tests/oracle -q
uv run pytest -m db -q                                  0 skipped
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run sfac streams check --base origin/main
```
