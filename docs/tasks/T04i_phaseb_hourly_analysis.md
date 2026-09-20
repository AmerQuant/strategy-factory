# T04i — T04e phase-B analysis on the hourly data, and the daily-session decision (D-033)

**Features:** F-0.1.2 (Alpaca adapter: session filter and metadata), F-0.1.6 (quality evidence), F-0.1.9 groundwork (split-adjustment control) · **Priority:** MVP · **Depends on:** **T04f**, **T04h** · **Blocks:** T04g
**Branch:** `feat/T04i-phaseb-hourly` from `feat/T04h-alpaca-hourly-ingest`.

Read first: `CLAUDE.md`, `docs/tasks/T04e_data_followup.md` **§8 phase B**, decisions **D-010**,
**D-021**, **D-022**, **D-023**, **D-025**, **D-033** (the decision this task closes), and
`docs/reviews/T04a_review.md`.

This is the analysis half of T04e that never ran because phase A was replaced by the full downloads.
It is scoped, per the batch brief, to **the hourly evidence and the daily-session decision**. The
Yahoo and Dukascopy parts of T04e phase B stay open and are listed under "Out of scope".

## Why this runs before the 1D ingest

`configs/data/alpaca.yaml` still carries `daily_session: exchange` with the comment *"decided in
T04e phase B"*. `session` is **metadata**, and the snapshot hash covers **content only**: once a 1D
snapshot exists, re-ingesting the same bars with `daily_session: RTH` returns the stored metadata and
writes nothing (`SnapshotStore.write_snapshot`, `store.py:100`). Snapshots are immutable (rule 10),
so a wrong label cannot be corrected in place — it would need 6,711 new snapshots with artificially
changed content, which is not acceptable. **D-033 therefore has to be decided before T04g runs.**

## Scope

### 1. No snapshots are written (D-382)
The daily side of the comparison is produced **in memory**: `AlpacaAdapter.to_canonical(...,
timeframe="1D")` on the raw year files of the sample symbols. Nothing goes into `SFAC_DATA_ROOT`,
nothing is registered in the catalog. The task's only outputs are a report and a config value.

Deliver the analysis as a committed, tested module + CLI (`sfac data analysis daily-session`, or a
script under `scripts/analysis/`) so the numbers are reproducible, not as a throwaway notebook.

### 2. The daily-session decision — D-033 (the main deliverable)
For every symbol that has both a 1H snapshot (T04h) and 1D raw files, over every session date
present in **both**:

- `rth_high = max(high)` and `rth_low = min(low)` of that date's 1H bars (09:00–15:00 New York, D-023);
- `daily_high`, `daily_low` from the in-memory 1D bars;
- `breach_high = daily_high - rth_high`, `breach_low = rth_low - daily_low`, as an absolute value
  **and** in basis points of the daily close, and as a fraction of that day's ATR-like range.

Report:

| statistic | what to print |
|---|---|
| days compared | total, and per symbol |
| days where the daily range is fully inside the RTH range | count and share |
| days with a high breach / a low breach / both | count, share |
| breach size | median, p95, max in bps; the 20 largest with symbol and date |
| breaches by year | a table, to show whether it is a feed-era artefact |
| breaches by symbol class | large-cap single names vs ETFs (`SPY`, `QQQ`, `GLD`, …) |

**Decision rule, stated before looking at the result** (so the result is not fitted):

- If the daily range stays inside the RTH hourly range on **every** compared day, set
  `daily_session: RTH` in `configs/data/alpaca.yaml` and record D-033 as accepted with that value.
- Otherwise keep `daily_session: exchange` and report **how often and by how much** it differs.
  A value between the two (for example "RTH except N days") is **not** allowed: `Session` is a fixed
  enum (`schema.py:40`) and a per-day label is not representable.

The evidence table goes in the review verbatim; the chosen value is the one T04g will use.

Caveat to state explicitly: the 1H sample covers only the years present in the raw set (2016–2020,
2023–2026 partially — see T04h), and only the 827 hourly symbols. The decision is made on that
sample and the report says so. If the hourly download is later completed (D-386), the check is
**re-run** and the review is amended; the decision is only revisited if the new years contradict it.

### 3. The remaining phase-B hourly items (T04e §8)
- **Hourly bars per day:** the 7-per-regular-day / 4-per-early-close table and every exception,
  taken from T04h's evidence and cross-checked against `nyse_sessions.csv`. Include the known
  `AAPL 2018-05-02/03` single-bar days.
- **META before 2022-06-09:** confirm that the `META` series carries Meta's pre-rename history.
  Measured while planning: `META` and `FB` return **identical** 2016–2020 bars (2016: 252 daily /
  3,812 hourly rows each; 2020 close range 146.01–303.91 for both), so Alpaca does serve pre-rename
  history under the new symbol. Confirm this on the ingested snapshot and state the first
  `META` timestamp.
- **Split check (F-0.1.9 groundwork):** the `alpaca_split_check_1H.csv` report from T04h, with the
  verdict distribution. The known-split expectations from T04e (including **AVGO 2024-07-15**) are
  checked on the 1D adapter output in memory, since the 1D snapshots do not exist yet; measured on a
  scratch run, `AAPL 2020-08-31` and `NVDA 2021-07-20`, `2024-06-10` already come back `adjusted`.
- **Relisted-ticker hazard (new, see P-67):** list every symbol whose daily close series has a gap of
  ≥ 200 calendar days followed by a level break beyond `split_check.jump_threshold` that no known
  split explains. `FB` is the worked example (2020 close 146–304, 2026 close 42.0–45.6). This is the
  candidate exclusion list for T04g; the decision on each candidate is the supervisor's.

## Out of scope
- Writing any snapshot (see §1) and any 1D ingest (T04g).
- The Yahoo part of T04e phase B (first/last dates, `^TNX` scale) and the Dukascopy part
  (v1 → v2 re-ingest of the three Q1-2024 pilot snapshots, which are still `hash_version 1` in the
  catalog). Both stay open; see the runbook's "Deferred" section.
- Changing the adapter, the session filter or the quality config.

## Acceptance
- The analysis module/CLI is committed with unit tests on a fixture (a synthetic day where the daily
  range exceeds the RTH range must be detected).
- The breach statistics are produced over **all** symbols that have both timeframes, and the counts
  are stated (no sampling without saying so).
- `configs/data/alpaca.yaml` carries the decided `daily_session` value, with the comment replaced by
  a reference to D-033 and to the review.
- The review contains: the breach tables, the bars-per-day table, the META evidence, the split-check
  verdict distribution with the known-split table, and the relisted-ticker candidate list.
- `SFAC_DATA_ROOT` contains **no new snapshot** created by this task (checked against the catalog row
  count before and after).
- `uv run pytest -m "not slow"`, `tests/parity tests/leakage`, `ruff check`, `ruff format --check`,
  `mypy src` all pass; no network in tests.

## Review summary
`docs/reviews/T04i_review.md`, structured as T04e §8 phase B asks: the daily-session decision with its
evidence and the rule that produced it; the hourly tables; META; splits; the relisted-ticker
candidates; what the incomplete 1H coverage means for the decision; deviations and open questions.
