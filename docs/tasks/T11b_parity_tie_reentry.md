# T11b — a targeted parity reference for D-335 and D-336

**Status: parked, not cancelled (D-802, 2026-09-22).** The user is not exporting for now. D-335 and D-336 stay
unverified against TradingView and the `to_verify` ledger stays at **3 of 5**. If T11b later shows an engine difference,
research results produced in the meantime may need re-running. The plan below stands for when it resumes.

*(Before D-802: planned; the supervisor saw and approved the script, D-375.)*
Stream A, critical like T11 (D-402). Features: F-0.3.8 (parity), F-X.7 (reproducibility).
Decisions: D-011, D-335, D-336, D-359, D-360, D-366, D-367, D-371 (as amended), D-373, D-374,
D-375, D-600; open question P-50 (fill rounding).

## Why

T11 merged with the `to_verify` ledger at **3 of 5**. Two items are testable by TradingView but
no current reference exercises them (D-375):

- **D-335** — the intrabar path when one bar touches both the stop and the target. T11's TF
  references show the **target-first** branch once and never the **stop-first** branch or an
  **exact tie** (`high − open == open − low`, which takes the stop).
- **D-336** — exit and re-enter at the same open. Both T11 scripts gate entries on
  `strategy.position_size == 0` at the signal close (D-367), which rules it out.

T11b commissions **one** reference built to exercise both: Donchian entries, a very tight stop
and target, a one-bar time exit and **no `flat` gate**, exported on `OANDA:XAUUSD` 1H and
`BATS:SPY` 1D.

## The parameters, chosen by simulation, not guessed

The engine matches TradingView to the cent on the committed XAUUSD and SPY charts, so running
it with candidate inputs on those charts predicts what an export will contain
(`entry_requires_flat_at_signal` off, D-366 and D-374 on). Per symbol and side:

| inputs (stop / target ATR, max bars) | XAUUSD long | XAUUSD short | SPY long | SPY short |
|---|---|---|---|---|
| 0.2 / 0.2, 1 — stop-first / target-first / ties / D-336 re-entries | 412 / 356 / 0 / **0** | 263 / 237 / 0 / **0** | 162 / 174 / 9 / 3 | 118 / 114 / 1 / 1 |
| **0.3 / 0.3, 1** (proposed) | **245 / 229 / 0 / 11** | **176 / 157 / 0 / 7** | **57 / 79 / 6 / 40** | **81 / 83 / 1 / 1** |

The supervisor's starting point, 0.2 ATR, exercises the path rule and the ties but produces
almost no D-336 re-entries (4 in all, none on XAUUSD): a 0.2-ATR stop or target is touched
inside the entry bar, so a trade rarely survives to an exit at the next open. **0.3 ATR with
`maxBars = 1`** keeps hundreds of stop-first and target-first bars and the SPY ties, and gives
**59** re-entries across the four exports. The script defaults to 0.3; 0.2 is one input
change. Exact ties occur only on SPY (two decimals), as expected; XAUUSD, quoted to 0.001, has
none.

### A prediction the export will test

Seven SPY bars are exact ties in whole ticks (six long, one short). On four the raw prices
tie exactly and the engine takes the stop. On three the export's 5-decimal prices sit 1e-5 to
3e-5 off a tie; on one of those (1994-06-06) the float comparison happens to land on the stop,
and on **two** it takes the **target**:

| date | open / high / low (export) | in ticks | engine |
|---|---|---|---|
| **1994-08-29** (long) | 47.8125 / 47.98437 / 47.64062 | 47.81 / 47.98 / 47.64 → 0.17 = 0.17, a tie | **TP** |
| **2004-10-05** (long) | 113.85001 / 114.16 / 113.53999 | 113.85 / 114.16 / 113.54 → 0.31 = 0.31, a tie | **TP** |

P-50 shows TradingView fills on tick-rounded prices. **If it also applies the path rule to
tick-rounded OHLC, it takes the stop on both days**, the comparison reports two
`intrabar_path` differences on exactly these dates, and the engine's tie rule must compare
tick-rounded distances in the parity branch — which would widen P-50 from fills to OHLC.
If TradingView takes the target, the engine is right as it stands. Either answer closes the
tie case of D-335.

## The script

`SF parity TIE - Donchian`. It is the one-sided TF script of D-600 with four changes: no
`flat` gate, a tight stop and target, a one-bar time exit, and the time exit placed **before**
the entry in the source, so that on a bar whose close schedules the exit a new entry is
placed after it (the order a Pine author would write to re-enter).

```pine
//@version=6
strategy("SF parity TIE - Donchian", overlay = true,
     initial_capital = 100000, default_qty_type = strategy.cash, default_qty_value = 100000,
     pyramiding = 0, commission_type = strategy.commission.percent, commission_value = 0.02,
     slippage = 0, process_orders_on_close = false, calc_on_every_tick = false,
     calc_on_order_fills = false, use_bar_magnifier = false, fill_orders_on_standard_ohlc = true,
     margin_long = 0, margin_short = 0)

// T11b (D-375): a targeted parity reference, NOT a trading strategy.
//  - a very tight stop and target, so one bar routinely touches both (D-335: path and tie);
//  - a one-bar time exit and NO `flat` gate, so an entry signal on the bar whose close
//    schedules the exit can re-enter at the same open (D-336).
// Keep maxBars = 1: re-issuing strategy.exit on a position that is still open moves its
// levels to the current ATR, and with maxBars = 1 an open position never lives past the
// close where that could happen.
side    = input.string("Long", "Direction", options = ["Long", "Short"])
chLen   = input.int(20, "Donchian length")
atrLen  = input.int(14, "ATR length")
slAtr   = input.float(0.3, "Stop (ATR)")
tpAtr   = input.float(0.3, "Target (ATR)")
maxBars = input.int(1, "Max bars in trade")

up = ta.highest(high, chLen)[1]
dn = ta.lowest(low, chLen)[1]
a  = ta.atr(atrLen)

ready = not na(up) and not na(dn) and not na(a)
slT   = math.round(slAtr * a / syminfo.mintick)
tpT   = math.round(tpAtr * a / syminfo.mintick)

// the time exit first, so a re-entry on the same close is placed after it (D-336)
if strategy.position_size != 0
    barsHeld = bar_index - strategy.opentrades.entry_bar_index(0) + 1
    if barsHeld >= maxBars
        strategy.close_all(comment = "Time")

// no `flat` gate -- that is the point of this reference
if side == "Long" and ready and close > up
    strategy.entry("L", strategy.long)
    strategy.exit("L-X", "L", loss = slT, profit = tpT, comment_loss = "SL", comment_profit = "TP")
if side == "Short" and ready and close < dn
    strategy.entry("S", strategy.short)
    strategy.exit("S-X", "S", loss = slT, profit = tpT, comment_loss = "SL", comment_profit = "TP")
```

**What the export decides about D-336.** With `pyramiding = 0`, TradingView may refuse
`strategy.entry` while the position is still open at the signal close, even though the time
exit fills at the same open. Then the export has no re-entries and D-336 is *answered* —
TradingView does not re-enter at the exit's open — rather than confirmed. Both outcomes close
it; the comparison says which.

## Export instructions (for the user, after the supervisor has seen the script)

Four Strategy Tester reports, the script, and a chart export per symbol — the same way as the
T11 references:

1. **Add the script** to a chart as a new strategy and save it; keep the file as
   `SF parity TIE - Donchian.pine`.
2. **`OANDA:XAUUSD`, 1 hour**, chart timezone **America/New_York** (as for T11), full available
   history. Strategy settings exactly as in the script; inputs at their defaults
   (0.3 / 0.3 / 1, Donchian 20, ATR 14).
   - Direction **Long** → Strategy Tester → export the report (`.xlsx`) → it is named like
     `SF_parity_TIE_-_Donchian_OANDA_XAUUSD_<date>.xlsx`; rename it with `_Long` at the end.
   - Direction **Short** → the same, `_Short`.
3. **`BATS:SPY`, 1 day**, timezone America/New_York, full history back to 1993: Long and Short,
   as above.
4. **Chart data** for each symbol (Export chart data, ISO time). If it is byte-identical to the
   T11 export, the manifest marks it a duplicate and the configs keep the original, as with
   D-600.
5. Put all files in `SFAC_RAW_ROOT/reference/tradingview/parity/` and run
   `scripts/write_parity_manifest.ps1` (or tell stream A to run it).

Nothing else changes: no bar magnifier, no slippage, commission 0.02 %.

## Scope once the exports arrive

1. Fixtures + manifest (D-359); the four references mapped in `configs/parity/`
   (`tf_donchian20_breakout`, `sl_atr 0.3`, `tp_atr 0.3`, `time_exit_bars 1`,
   `entry_requires_flat_at_signal: false`, D-366 and D-374 on). The gate picks them up
   automatically (`…every_mapped_reference_is_in_the_gate`).
2. Check first, as for T11: the `.pine` settings against each Properties sheet, and each
   report's `Direction`.
3. The four comparisons against D-011 (union share, D-373). A difference is classified and
   explained, never tuned away; an engine change is a parity-branch decision in stream A's
   range, stopped for the supervisor.
4. **D-335**: the stop-first branch, the target-first branch and every tie — engine, path rule
   and TradingView agree on each, pinned as in T11 — with the two dates above checked by name.
5. **D-336**: re-entries at the exit's open present on both sides (confirmed), or absent from
   TradingView where the engine has them (answered: TradingView does not re-enter).
6. The ledger, the kernel docstring and the drift test updated; the review; stop for
   "Approved" (D-402).

## Tests

- The gate over every T11b reference, never skipped, on committed fixtures.
- The D-335 evidence test extended to the T11b references, with the counts pinned.
- A D-336 evidence test: the re-entries of each reference, pinned.
- The two predicted tie dates, asserted by name.

## Acceptance

Fast suite, `tests/parity tests/leakage tests/oracle`, `pytest -m db` (0 skipped), ruff,
format, mypy, the stream guards; the T11b review; the ledger at **5 of 5**, or each remaining
item explicitly decided by the supervisor.
