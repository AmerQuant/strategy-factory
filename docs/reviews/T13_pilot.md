# T13 — pilot (RUNBOOK_T13 step 7), stopped before the full run

Branch `a/T13-method-screening` (stacked on `a/T13-plan`), commit `e3b25a5` plus this report.
Decisions: D-622 … D-636. The pilot is runbook step 7; the full run (step 8) waits for the
supervisor, as T12's did.

> **Open parity gap (D-802).** D-335 and D-336 are unverified against TradingView. D-336 is
> the research default and shaped every MR run here (an exit at a close may be followed by a
> re-entry at the same open). If T11b later shows an engine difference, these results may need
> re-running; every run records its `code_version`.

## 1. The controls first (D-629)

| run | profiles | methods screened | pass the gate | selected |
|---|---|---|---|---|
| **1D control** (MSFT long, K short; returns reshuffled, D-615) | 2 | 40 | **0** | 0 |
| **1H control** (BAC long) | 1 | 15 | **0** | 0 |

**D-629 is doing the work it was added for.** On MSFT's control, **9 methods pass every
criterion except `method_q_value`** (median target > 0, ≥ 60 % profitable cells, trade minimum,
no overlap yet): the drift of a strongly rising stock. Their BH q-values are 0.20–0.74. On
K's and BAC's controls every method also fails the target criteria.

## 2. The runs and their reproduction

| run | run id | profiles | methods | gate | selected | wall time |
|---|---|---|---|---|---|---|
| 1D, run 1 | `26d2541e…` | 2 | 40 | 5 | 5 | 10 s |
| 1D, run 2 | `8739dc55…` | 2 | 40 | 5 | 5 | 10 s |
| 1H, run 1 | `d813c549…` | 1 | 15 | 1 | 1 | 7 s |
| 1H, run 2 | `72ca9a42…` | 1 | 15 | 1 | 1 | 7 s |
| 1D control | `62d00317…` | 2 | 40 | 0 | 0 | 10 s |
| 1H control | `3208682e…` | 1 | 15 | 0 | 0 | 7 s |

- **Reproduced:** all 55 `summary.json` files are identical between the two runs apart from the
  run id, and both `index.csv` files are byte-identical.
- **BAC 1H is flagged `unconfirmed`** (D-621, D-628) in every artifact.
- **Cost, projected:** about 5 s per daily profile (20 methods, 304 cells, 2 legs, 20 baselines of
  1,000 draws, registry writes included) and 7 s per hourly profile. The full scope (14 + 4
  profiles) and its control take **about 4 minutes** together.

## 3. What each profile did

Before diversity, the draft criteria plus `method_q_value` pass **MSFT 17, K 9, BAC 9 methods —
exactly the plan's measurement** (T13 plan §1). Then the diversity walk (F-2.6) selects:

| profile | selected (rank) | failed on overlap only | failed on other criteria |
|---|---|---|---|
| MSFT long | `mr_ibs_after_new_high` (1), `mr_zscore` (2), `mr_macd_hist_falling` (12) | 14 | 3 (`mr_daily_drop`, `mr_macd_hist_trough` on q; `mr_macd_hist_turn` on q) |
| K short | `mr_stochastic_k` (1), `mr_macd_hist_falling` (3) — **fewer than 3 (D-625)** | 7 | 11 |
| BAC long (unconfirmed) | `tf_keltner_breakout` (1) — **fewer than 3** | 8 | 6 |

Of the user's methods (T13 §10): selected — `mr_ibs_after_new_high` (#14) and
`mr_macd_hist_falling` (#17, on both daily profiles); passed the gate but lost to overlap —
`mr_n_day_low` (#5), `mr_down_closes` (#4), `mr_ma_distance_pct` / `_atr` (#8, #9),
`mr_lower_lows` (#3), `mr_ibs` (#0), `mr_rsi` (#1, #19), `mr_rsi_sum` (#2), `mr_ema_slope_drop`
(#10), `mr_candle_score` (#18), `mr_williams_confirm` (#22). On K short, `mr_candle_score` and
`mr_ema_slope_drop` fail on the target itself.

## 4. The finding: the diversity rule selects one method per cluster (P-115)

Mean-reversion methods with 5-bar exits are in position on the same pullback bars. On the
good-region median cells, the overlap (the stage's definition: the share of the **smaller**
candidate's in-position bars that the other shares) is **0.66–0.98** among MSFT's top six, and
**0.73–0.92** among BAC's. With the 60 % threshold, each "cluster" contributes one method.

F-2.6 does not say what the overlap is measured against, and D-636 does not either; the stage
uses the smaller candidate's bars (my reading, stated in the code). Replaying the pilot's own
walk with the other natural reading, **intersection over union**, on the same cells
(`scripts/analysis/T13_pilot_overlap.py`):

| profile | share of the smaller (the stage) | intersection / union |
|---|---|---|
| MSFT long | 3: `ibs_after_new_high`, `zscore`, `macd_hist_falling` | 5: `ibs_after_new_high`, `zscore`, `n_day_low`, `down_closes`, `ma_distance_pct` |
| K short | **2**: `stochastic_k`, `macd_hist_falling` | 5: + `zscore`, `keltner_lower`, `macd_hist_trough` |
| BAC long | **1**: `keltner_breakout` | 3: + `aroon_cross`, `sma_cross` |

The difference is nesting: `mr_down_closes` is in position on 87 % of `mr_ibs_after_new_high`'s
bars (a rare method inside a frequent one), but their union overlap is 10 %. Under the union
reading a method nested inside another counts as diverse although it adds no independent
trade. **I recommend keeping the stage's reading** and running the full scope as is, reporting
how many profiles get fewer than 3 (D-625 already says what happens then). The union reading
is one line to switch; it would send about twice as many candidates to stage 3.

## 5. Found and fixed during implementation

- **Connors RSI's short was broken by its ROC.** The textbook one-bar ROC `(c − c[1]) / c[1]` is a
  ratio: under `p → −p` it keeps its sign, so the mirrored Connors RSI kept the long's
  percent-rank third and the short almost never fired (0–5 signals in 400 bars against 15–93 for
  the long). **Found by the engine-truncation gate's vacuity check** (T08's F-0.3.9 test, which
  runs every registered entry). Fixed with the D-632 `|ref|` form; for positive prices it equals
  the T07 golden-tested indicator (tested). **Consequence for the plan:** its measurement script
  used the textbook indicator, so the plan's `mr_connors_rsi` numbers on the **short** profiles
  (T13 plan §1, §3) came from the broken mirror. The long profiles are unaffected.
- **Three stage-2 names collided with stage-1 probes** (`tf_bb_upper_cross`, `tf_supertrend_flip`,
  `tf_ichimoku_cloud`): the stage-2 methods are `tf_bb_upper`, `tf_supertrend`, `tf_ichimoku`.
- **Two warm-ups were one bar late** (Connors 101 → 100, ADX/DI 2n → 2n − 1) and one early bar
  was missed (KAMA n + 1 → n): found by the warm-up test over every cell before it was committed.
- **The T07 tests were scoped to the stage-1 probes**, which is what they were written for (they
  listed "every entry" when only probes existed). The T07 positive-scale mirror test cannot hold
  for a ratio rule under any reflection; the stage-2 methods have their own mirror tests
  (negation for all, positive scale for the 31 translation-invariant ones). Nothing was weakened:
  the engine-truncation gate now also runs all 35 new methods.

## 6. Interpretation made while implementing (for the supervisor to confirm)

- **D-633, Williams %R:** `confirm` is `{off, same_bar, latched}`. D-633 names the two readings of
  the confirmation; `off` is F-2.1's plain Williams %R (T13 §4.2: "one method, `confirm` is the
  user's variant"), so it is kept as the third value (48 cells). Removing it is one config value.

## 7. Acceptance so far (Windows)

Fast suite **2,455 passed**; parity + leakage + oracle **858**; `-m db -rs` **23 passed, 0
skipped**; `-m slow` **20 passed**; ruff, `ruff format --check`, mypy `src` and
`--platform linux`, `sfac streams check` clean. The acceptance reviewer runs before the review
(step 9). Mutation checks: ranking on the after-cost leg
fails the D-623 wiring test; the textbook Connors ROC fails 10 tests; a one-bar look-ahead in
`mr_ibs` fails the truncation test; a late warm-up and a registered duplicate method are caught
by their guards.

## 8. Before the full run

**P-115** (non-blocking): which overlap does F-2.6 mean — the share of the smaller candidate
(the stage, recommended) or intersection over union? Everything else is ready: the full run and
its control are about 4 minutes.
