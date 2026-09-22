# State of the data at the handover into T12

Written by stream B after T04l (PR #34, `99d2912`). Measured **2026-09-22** on `SFAC_DATA_ROOT` with
read-only queries of the catalog, the snapshots and the quality reports. The data layer is complete for
the MVP; T12 is stream A's (D-611). Re-measure before relying on these numbers after any later
ingest or derivation pass.

## The references

| | 1D | 1H |
|---|---|---|
| alpaca references (exactly one per symbol) | **6,708** | **805** |
| … raw | 3,430 | 778 |
| … T04k clean (D-396, D-398, D-700 … D-706) | 2,976 | — |
| … T04l trim (a proven re-use, D-709) | 46 | 4 |
| … T04l research window (starts at an unsettled boundary, D-713) | 256 | 23 |
| quality `ok` / `warning` / `critical` | 4,217 / 2,491 / **0** | 392 / 413 / **0** |
| references carrying a splice marker (`research_window`) | 256 | 23 |
| **pass D-008 — a split is possible (the candidate universe)** | **5,470** | **770** |
| … of which a T04l research window | 108 | 11 |
| … of which quality `warning` | 1,967 | 400 |

- 752 of the 806 hourly-universe symbols pass D-008 in **both** timeframes.
- Plus 3 Dukascopy 1H pilot references (`EURUSD`, `XAUUSD`, `USA500IDXUSD`, hash version 1; T04j).
- Plus **7 Yahoo aux references** (T04m, 2026-09-22): VIX, SPX, NDX, RUT, DJI, TNX, DXY, `1D`,
  `asset_class aux`, hash version 2. They are **never candidates** (the data layer refuses them as
  a traded symbol; no split, no holdout) and are read only through `DataAccess.aux` (below). Quality:
  NDX and RUT `ok`; VIX, SPX, DJI, TNX and DXY `warning`, all with schedule checks run on their own
  calendars (D-720).
- No reference is `critical`, so `ensure_usable` blocks none.
- Warning checks on the references: 1D `price_spikes` 2,099, `zero_volume` 936, `stale_prices` 899,
  `missing_bars` 382, `daily_wick_outlier` 38 (hourly symbols, D-396); 1H `price_spikes` 401,
  `missing_bars` 28, `stale_prices` 7, `zero_volume` 1. One symbol can fail several.

## What stage 1 must know (items 1–8, with the supervisor's answers of 2026-09-22)

1. **Warnings.** A warning **does not block entry and does not weight anything**. It is recorded in the
   EdgeProfile (T12, D-610), and stage 1 also **reports its pass rate split by quality status**. If
   flagged symbols pass materially more often than clean ones, that is bad data showing up as edge, which
   makes this a free diagnostic. Excluding 36 % of the candidate universe on suspicion is not justified.
   *(Supervisor; carried to stream A as a T12 requirement.)*
2. **Research windows** (108 1D, 11 1H candidates) are **short-history symbols, full stop**. Their
   history before the boundary is absent on purpose. `DataAccess.splices()` and `sfac data show` return
   the marker. **Never** read the full-history snapshot, lower D-008's minimum, or re-join the halves
   (D-713). The 182 daily series that fall below D-008 once cut were never usable. Only new identity
   evidence, through `sfac data reuse`, can restore a full history.
3. **Hourly data is raw by decision** (D-707). It has 156 wick flags on 105 symbols, 29,445 zero-bar
   sessions (mostly relisting spans; 889 are ordinary missing days), and feed-defect dates where hundreds
   of symbols have 1–2 bars (2021-04-19, 2021-10-25, 2022-03-08, 2022-01-24). **T12's review states the
   1H pass rate separately.** *(Supervisor.)*
4. **Relayed to stream A** *(supervisor)*:
   - **Universe:** check that `configs/universe.yaml` has been regenerated since T04f changed the hourly
     universe (827 → 806; D-394).
   - **Hash-only lookup:** `scripts/analysis/T04k_assert_provenance.py` indexes by hash alone. It is
     harmless today (0 hashes shared across symbols in 11,084 catalog rows), but it should key by
     `(source, symbol, timeframe, snapshot_hash)` when next touched (T04l review §6.1.4).
5. **Open from T04f, affecting a handful of symbols, not the pipeline:**
   - **P-68:** the rejected-rename rule.
   - **P-69:** `PX → RPC` inherits Praxair's index membership.
   - **P-70:** five rename destinations have no 1H raw data (`BFH`, `DINO`, `FBIN`, `GAP`, `TNL`).
6. **Aux series (T04m, done 2026-09-22) and the full Dukascopy h1 (T04j, paused).**
   - The seven Yahoo series are ingested and joined as-of (F-0.1.11). A stage-5 filter reads
     `DataAccess.aux(aux, traded, timeframe)` -> `AuxView`, computes its indicator on the aux bars
     and reads it at `idx` (`-1` = none or stale). At stage 6 it reads them inside the candidate's
     one access: `SplitManager.open_holdout_with_inputs(..., aux=(...))`. The run records
     `AuxView.key` (rule 8).
   - Timing: an equity at the close of d reads VIX, NDX, DXY of d-1 and the unverified SPX, RUT,
     DJI, TNX of d-2 (D-718); an FX bar reads VIX of d once 16:15 New York has passed.
   - The full Dukascopy h1 (T04j) waits for the user's download.

   Neither is needed for stage 1; both are for P1 filters. This is stream B's likely next work, in an
   order the supervisor sets.
7. **The registry's `data_snapshots` table is empty** (P-63). A run resolves references through the
   catalog and pins their hashes (`core/config.py`), which is what reproducibility needs for now.
8. **Quarantine folders** `<store>/_quarantine/T04k_D-702_*` and `T04l_D-714_20260922T080918Z` hold
   retired, never-referenced snapshots (moved, never deleted, with manifests). They are for the
   supervisor and the user to empty.

## Where the evidence lives

`docs/reviews/T04g_review.md` (1D ingest), `T04h_review.md` (1H ingest), `T04k_review.md` (clean daily),
`T04l_review.md` (re-used tickers), `T04m_review.md` (aux series), and their CSVs under `docs/reviews/`; per-snapshot logs and
provenance under `<store>/_clean/` and `<store>/_reuse/`; the decisions D-380 … D-399 and D-700 …
D-721 in `docs/decisions/decisions_log.md`.
