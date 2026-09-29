# T15a — the planted pilot (RUNBOOK_T15a step 8, D-665): stop with its numbers

Funnel run **`a3ace3cb-584a-421b-8f6a-6c099b11b8f8`**, `sfac funnel run configs/funnel/planted_pilot.yaml`,
on the committed tree `2f3053cd` (clean). Source `planted:b43d0e72675e`: the null of D-664, with the
**top two strengths** of each ladder planted (`configs/synthetic/planted_pilot.yaml`). **30 daily
symbols** (the plan's M3 sample), **5 per cell**, no pure-null share. Stages 1 → 2 → 3, each with its
control arm (D-662). Per-symbol table: `docs/reviews/T15a_planted_pilot.csv`; script
`scripts/analysis/T15a_planted_pilot.py`.

> D-335 / D-336 remain unverified against TradingView (D-802); D-336 shapes every MR run here.

## 1. Power per cell (the planted profile passes; 5 symbols, so 20 % per symbol)

| cell | own statistic (mean) | stage 1 | stage 2 | stage 3 | other profiles passing stage 1 |
|---|---|---|---|---|---|
| MR long, 4 ATR | 3.90 | 60 % | 60 % | **60 %** | 3 (MR short) |
| MR long, 6 ATR | 5.21 | **100 %** | 100 % | **80 %** | 5 (MR short) |
| MR short, 4 ATR | 3.69 | **0 %** | 0 % | 0 % | 4 (MR long) |
| MR short, 6 ATR | 5.06 | 60 % | 60 % | **0 %** | 5 (MR long) |
| TF two-sided, 0.5 σ | 0.52 | 60 % | 60 % | 20 % | 0 |
| TF two-sided, 0.8 σ | 0.75 | **0 %** | 0 % | 0 % | 0 |

The own statistic recovers the planted strength (3.9 for 4, 5.2 for 6; 0.52 for 0.5, 0.75 for 0.8):
the plant is there. **D-665's pilot criterion — the top of each ladder reaches at least 80 % at stage
1 — is met by MR long only** (100 %). MR short tops out at 60 %, and TF at 60 % at 0.5 σ and **0 % at
0.8 σ**.

## 2. What the pilot shows about stage 1 (for T15b, D-671)

1. **Stage 1's MR verdict is not direction-specific.** A planted MR-long edge also passes the MR
   *short* profile (5 of 5 symbols at 6 ATR), and a planted MR-short edge passes the MR *long*
   profile more often than its own (4 of 5 against 0 of 5 at 4 ATR). A plausible mechanism, not yet
   tested: the matched random baseline holds the planted reversion bars too, so a probe that
   *avoids* them (a short entered after the rebound, a long after the decline) beats its baseline
   although it has no edge of its own.
2. **An MR-short plant fires only two probe groups** at 4 ATR (band/channel and oscillator; breadth
   15) where the MR-long plant fires three (with momentum; breadth 22.5): a one-bar spike does not
   produce the up-streaks the short sequence probes look for, so the breadth criterion stops it.
3. **TF power is not monotone in strength.** At 0.8 σ fewer TF probe groups are accepted (breadth
   6–12, momentum and moving-average groups only) than at 0.5 σ (12–24, with channel breakout and
   ichimoku), and nothing passes. Widening the TF ladder upwards would not raise power.
4. **The control arms**: stage 1's control passes nothing; stage 2's selects 1 (DOW MR short);
   **stage 3's passes 2** — AMD TF long `tf_atr_band` (plateau 386 cells, area 0.21) and SE MR long
   `mr_daily_drop` (12 cells, 0.46) — the real stage-2 selections on the reshuffled planted series
   (D-662). On real data D-644 says a stage-3 control pass stops the stage; here it is a synthetic
   pilot, and reshuffling a planted series keeps its fat-tailed shocks while destroying their timing.
   It is reported, not decided.

## 3. Timing

6 stage runs, **454 s** in all on 6 workers × 1 Numba thread: stage 1 43 s + 42 s (30 symbols), stage 2
114 s + 114 s (20 profiles), stage 3 56 s + 56 s (20 candidates).

## 4. The decision this stop asks for (P-134)

D-665 says: widen the ladder if the top does not reach 80 %, before the full planted run. The pilot
shows widening cannot fix TF (power falls from 0.5 to 0.8 σ) and would only partly fix MR short. The
options, with my recommendation first:

- **(a) Keep the ladders (MR 1, 2, 3, 4, 6; TF 0.1, 0.2, 0.3, 0.5, 0.8) and run the full planted funnel
  as planned.** The power curve then shows exactly what the pilot found — MR long reaches 80 %+, MR
  short and TF never do, TF is non-monotone — which is T15b's evidence that stage 1 must be redesigned
  (D-671), not a ladder to tune until it looks good.
- (b) Extend MR to include 8 ATR (MR 1, 2, 4, 6, 8) to see where MR short saturates; TF unchanged.
- (c) Stop and redesign the planted TF edge first (for example longer, weaker segments) — this moves
  towards T15b's work.

**Next, after the answer:** step 7 (the report). **It needs the font first: please run**
`scripts/fetch_vazirmatn.ps1` (D-666, D-031), which places `Vazirmatn-VariableFont_wght.ttf` and
`OFL.txt` under `src/strategy_factory/reports/assets/fonts/` and prints both hashes. Step 7 also adds
`plotly` and `jinja2` (ADR-008). The report was moved after the pilot because the pilot does not
depend on it and the font was not yet in place; nothing else in the runbook's order changed.
