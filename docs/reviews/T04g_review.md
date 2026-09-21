# T04g review — Alpaca 1D ingest: 6,711 symbols → snapshots, catalog and quality reports

**Task:** `docs/tasks/T04g_alpaca_daily_ingest.md` · **Branch:** `b/T04g-alpaca-daily-ingest` from `main` (T04i merged, PR #21)
**Features:** F-0.1.2 (Alpaca adapter), F-0.1.6 (quality report per symbol), F-0.1.8 (immutable snapshots, catalog), F-0.1.9 groundwork (split check)
**Decisions used:** D-010, D-021, D-022, D-025, D-028, D-029, D-033, D-355, D-357, D-358, D-383, D-385, D-390, D-391, D-394, D-395, D-397, D-398, D-399

## 1. What was built

| File | What |
|---|---|
| `src/strategy_factory/data/ingest.py` | **D-397**: an `unadjusted` known split returns `unadjusted_split` and writes **nothing** |
| `src/strategy_factory/data/cli_alpaca.py` | `--universe` / `--excluded` on `sfac data ingest alpaca`; the summary counts every outcome |
| `src/strategy_factory/data/cli_prep.py` | **D-391**: one `_quality/summary_<source>_<timeframe>.md` per group plus the index, and `--max-rows` |
| `scripts/ingest/T04g_ingest_daily.py` | the chunked run (D-385), one CLI invocation per 250 symbols, timestamped log |
| `scripts/ingest/T04g_verify.py` | the catalog/store integrity assertions of the task's §4 |
| `scripts/ingest/T04g_report.py` | the split-check and quality aggregates quoted below |
| `docs/reviews/T04g_known_splits_1D.csv`, `T04g_split_warnings_1D.csv`, `T04g_quality_1D.csv` | the evidence behind every table |
| tests | **9 new** — see §8 |

## 2. The ingest

```
uv run python scripts/ingest/T04g_ingest_daily.py --chunk 250
```

**27 chunks, 16.8 minutes wall clock**, every chunk `rc=0`, log
`<SFAC_DATA_ROOT>/_logs/T04g_ingest_1D.log`. (The chunk-3 line in that log ends with the
`unadjusted known split …` line rather than the counts: the script picked the command's **last**
output line, and it now picks the counts line. The committed script is therefore one line different
from the one that produced the log; the counts in this review come from the log's own per-chunk
lines plus chunk 3's detail line, and they reconcile exactly with the catalog.) The task budgeted 1.5–3 hours; the measured cost is
**0.15 s per symbol**, and the per-chunk time grows from **18.5 s** (chunk 1, empty catalog) to
**64.2 s** (chunk 27, 6,700 rows) — the catalog rewrite is the growing part, exactly as the task
predicted. It never dominated enough to need the batched `register_many` the task allows, so
**no such change was made**.

| outcome | symbols |
|---|---|
| universe (`configs/universe/us_equity_daily.csv`) | 6,711 |
| excluded (`us_equity_daily_excluded.csv`, empty under D-398) | 0 |
| **ingested** | **6,707** |
| `no_data` | 3 — `BHGE`, `FBHS`, `JEC` |
| `unadjusted_split` (D-397) | 1 — **`AVGO`** |
| `failed` | **0** |

### Which symbols are not in the store, and why

- **`BHGE`, `FBHS`, `JEC`** — the download returned **no bars at all** for them
  (`SFAC_RAW_ROOT/_reports/alpaca_missing_1D.csv`); every year file is empty, so the adapter has
  nothing to ingest. This is the expected result the task file names.
- **`AVGO`** — its 10:1 split of **2024-07-15 is not applied** in the raw series (T04i §4). Under
  **D-397** that fails the symbol, not the run: the ingest logged
  `AVGO 1D: known split unadjusted on 2024-07-15 - not ingested`, chunk 3 still finished `rc=0`
  with its other 249 symbols, and the split-check report carries the `unadjusted` row. It returns
  when the user runs the `--refresh` commands (`docs/reviews/T04i_review.md` §6b).

Nothing else failed. The full 6,711-symbol universe was attempted because T04i's exclusion file is
empty under D-398 — no symbol is excluded by the re-used-ticker rule any more.

## 3. Split check (F-0.1.9 groundwork)

`SFAC_RAW_ROOT/_reports/alpaca_split_check_1D.csv`: **11,398 rows over 2,727 symbols**.

| verdict | rows |
|---|---|
| `market_move_both` | 10,642 |
| `no_crosscheck` | 645 |
| `unexplained_ingested` | 63 |
| `unexplained_crosscheck` | 23 |
| `mismatch` | 14 |
| `adjusted` | 10 |
| **`unadjusted`** | **1** |

**Every known split, with its verdict** (`docs/reviews/T04g_known_splits_1D.csv`):

| symbol | date | ratio | verdict |
|---|---|---|---|
| `AAPL` | 2020-08-31 | 4 | adjusted |
| `TSLA` | 2020-08-31 | 5 | adjusted |
| `NVDA` | 2021-07-20 | 4 | adjusted |
| `AMZN` | 2022-06-06 | 20 | adjusted |
| `GOOGL` | 2022-07-18 | 20 | adjusted |
| `TSLA` | 2022-08-25 | 3 | adjusted |
| `WMT` | 2024-02-26 | 3 | adjusted |
| `NVDA` | 2024-06-10 | 10 | adjusted |
| `CMG` | 2024-06-26 | 50 | adjusted |
| **`AVGO`** | **2024-07-15** | **10** | **unadjusted** |
| `SMCI` | 2024-10-01 | 10 | adjusted |

10 of 11 are `adjusted`, which is T04e's expectation. The single exception is `AVGO`, already
diagnosed in T04i and handled by D-397 — it is a finding, not a rounding issue, and the symbol is
out of the store until the refresh.

- **79 symbols have a warning verdict** in the report
  (`docs/reviews/T04g_split_warnings_1D.csv`, 101 rows: 63 `unexplained_ingested`,
  23 `unexplained_crosscheck`, 14 `mismatch`, 1 `unadjusted`). **78 snapshots carry the warning in
  their `notes`** — the 79th is `AVGO`, which D-397 kept out of the store.
- **How many symbols had no cross-check file: zero.** All 6,711 MS-US-1D files exist, and no
  snapshot carries the `No cross-check file (MS-US-1D) for this symbol.` note. An earlier draft of
  this review read the 645 `no_crosscheck` rows (393 symbols) as missing files; they are not. A
  `no_crosscheck` row means the cross-check **series has no bar on that date** — the ingested
  series jumped on a day the all-adjusted copy does not cover (`AVIR` 2018-02-14 is one), so the
  jump could not be confirmed either way. The two are different findings and only the second
  occurred.

## 4. Quality reports (F-0.1.6, D-391)

```
uv run sfac data quality --all --max-rows 5
```

**6,710 snapshots checked** (6,707 Alpaca 1D + the 3 Dukascopy pilots), every one with a report
file.

| `quality_status` | snapshots |
|---|---|
| `ok` | 4,002 |
| `warning` | 2,705 |
| **`critical`** | **0** |

**The schedule checks ran — none is `skipped`.** `missing_bars` failed for **190** snapshots and
`session_violations` for **0**; both were executed for all 6,707, which is what the calendar from
T04f bought (without it they were silently skipped and the snapshot still read `ok`).

The only skipped check is **`dst` (6,707 of 6,707)**, which is correct: it compares the modal
local first-bar time of *intraday* bars and has nothing to measure on a daily series.
`price_spikes` is skipped for 17 snapshots whose history is shorter than its 50-bar window.

Checks that failed (a snapshot can fail several):

| check | snapshots |
|---|---|
| `zero_volume` | 2,266 |
| `price_spikes` | 2,239 |
| `stale_prices` | 1,145 |
| `missing_bars` | 190 |
| `session_violations` | 0 |

3,261 of 6,707 snapshots fail at least one check. That is expected and is **reported, not
suppressed**: the universe is the full 6,711-symbol MS-US-1D listing including delisted micro caps,
where zero-volume days and frozen prices are the norm — and the frozen stretches are exactly what
**D-398** removes in T04k.

**The twenty worst `missing_pct`** are all the same shape, and it is worth naming because it is not
a defect of the ingest:

| symbol | missing | what it is |
|---|---|---|
| `MDA` | 94.0 % | 135 bars spanning 2017-10-05 … 2026-09-18 |
| `POM` | 89.1 % | 294 bars spanning 2016-01-04 … 2026-09-18 |
| `NPT` | 89.0 % | same shape |
| `XE` | 88.8 % | same shape |
| `CAM` | 88.8 % | same shape |

(`MOBI`, `PCL`, `MGN`, `CMII`, `AYA`, `LEGO`, `CHAC`, `CSRA`, `SPLS`, `NCT`, `BEBE`, `NUTR`,
`TMTS`, `Q`, `HAWK` complete the twenty — full list in `docs/reviews/T04g_quality_1D.csv`.)

Each is a **company that delisted years ago while the feed still returns a bar near the end of the
window**, so the snapshot's first→last span covers nearly the whole eleven years while only a few
hundred bars are real. `missing_bars` then measures the dead stretch. The check is right; the
series is the problem, and it is the same defect family D-398 and T04k address. **No `critical`
status anywhere**, so nothing is blocked from the pipeline.

**D-391 is implemented and used.** `_quality/summary.md` is now an index:

```
| source    | timeframe | snapshots | ok   | warning | report                    |
| alpaca    | 1D        | 6707      | 4002 | 2705    | summary_alpaca_1D.md      |
| dukascopy | 1H        | 3         | 2    | 1       | summary_dukascopy_1H.md   |
```

with the 6,707-row Alpaca table in its own file, and a run that touches one group rewrites only
that group's file plus the index (tested).

## 5. Catalog and store integrity (task §4)

```
uv run python scripts/ingest/T04g_verify.py
```

```
6707 catalog rows for alpaca 1D
  symbols: 6707   rows with >1 snapshot: 0
  symbols without a reference: 0   with >1: 0
  asset_class == 'us_equity': 6707/6707
  adjustment == 'split':      6707/6707
  feed == 'sip':              6707/6707
  hash_version == 2:          6707/6707
  session == 'exchange':      6707/6707        <- the D-395 value
  files checked: 13414   missing: 0   writable: 0
  register: 6707/6707 symbols, 0 with more than one
  set_reference: 6707/6707 symbols, 0 with more than one

all integrity checks passed
```

Every snapshot has both its `.parquet` and its `.meta.json`, and **all 13,414 files are
read-only** (rule 10). The events file holds exactly one `register` and one `set_reference` per
symbol; of its 13,423 `quality` events, **13,414 are 1D** — two per snapshot, because the
quality command was run twice (§7) — and 9 are the three Dukascopy 1H snapshots.

**Store size: 0.35 GB** for 6,707 daily snapshots — the task budgeted 0.4–0.6 GB. 164 GB free.

**Idempotence.** Re-running chunk 1 (250 symbols) after the full run:

```
250 symbols: 250 ingested, 0 no_data, 0 unadjusted_split, 0 failed, 0 excluded
catalog rows / events / sha256(catalog.parquet)  before: (6710, 26843, 88fe92988089)
catalog rows / events / sha256(catalog.parquet)  after : (6710, 26843, 88fe92988089)
```

The catalog file is **byte-identical** and no event row was added: identical content returns the
stored snapshot, `register` is a no-op for a known key and `set_reference` returns early (D-385).

## 6. D-399 (P-74) is recorded and T04k carries it

The supervisor's answer to P-74 is **D-399**: a trim is never applied on an ambiguous signature.
Each of the 29 `reverse_split_suspect` symbols is settled with the MS-US-1D cross-check — an
unadjusted (reverse) split takes the **D-397** path with its history untouched, a trading **halt**
keeps the history on both sides and states the gap, only a genuine re-use is trimmed, and an
unsettled case keeps the full history and is listed. `docs/tasks/T04k_clean_daily_snapshot.md` §1c
carries the rule and its acceptance test. **T04g proceeded as is**, which is what the decision says.

## 7. Two defects this run exposed, both fixed here

1. **`sfac data quality --all` crashed at 6,710 snapshots.** `pl.DataFrame(out)` infers the schema
   from the first 100 rows, where `break_local` / `break_utc` are null for every daily snapshot;
   the first row with a real break hour then raised
   `ComputeError: could not append value: 17 of type: i64`. Every per-snapshot report had already
   been written and every `quality_status` recorded — only the printed table and the summaries were
   lost — but the command exited 1. Fixed with `infer_schema_length=None` and a regression test
   that plants exactly that shape. This is why the events file holds two `quality` events per
   snapshot: the command ran once before the fix and once after.
2. **`sfac streams check` rejected answering a question raised on an earlier branch — already
   fixed by stream A, so nothing was changed here.** P-74 was added on the merged T04i branch;
   answering it on this branch rewrites that row, the diff shows it as an added `+ | P-74 | …`
   line, and the duplicate guard failed the build. I implemented a fix (treat an ID that the
   branch also *removes* as edited in place), and while checking the tests found that
   **stream A had already landed exactly that fix as D-369** — `an amendment in place is not a
   duplicate id`, commit `01ce80f`, merged in PR #22 while T04g was running, together with the
   `removed_rows` plumbing and eight tests of its own, including one that reads real `git` output.
   **My duplicate implementation was reverted and the branch rebased onto `a48f6f4`**, so
   `src/strategy_factory/core/streams.py` and `cli_streams.py` are untouched by stream B and the
   guard passes on stream A's code. The episode is worth recording because it is what the protocol
   is for: two streams hit the same defect within an hour, and the one that owns the file won.
3. **One of stream A's new D-369 tests depended on the shape of the branch's history — reported,
   not fixed here.** `test_F_X_9_d369_removed_rows_reads_real_git_output` diffed `HEAD~1..HEAD`
   over `docs/decisions/decisions_log.md` and asserted the diff has a `--- a/…` header; that holds
   only when the previous commit happened to edit the log, so it failed on this branch and would
   fail on **any** branch whose last commit does not. I first changed the range here; on the
   supervisor's instruction that edit was **dropped**. **Stream A fixed it in PR #23** by building
   a throw-away repository in `tmp_path`, which says the same thing on every branch and depends on
   no history at all — a better fix than mine. This branch is rebased onto `48ba1ac` and takes
   main's version of the file wholesale.

   Together with §7 (2) this is the same lesson twice in one task: **a stream-A file is reported in
   `docs/streams/B.md` and waited on, never edited.** Stream B's branch now changes nothing under
   `src/strategy_factory/core/` or `tests/unit/test_F_X_9_stream_guards.py`.

## 8. Tests added

| test | proves |
|---|---|
| `test_F_0_1_2_D_397_an_unadjusted_known_split_fails_that_symbol` | the symbol is not ingested, no catalog row, the `unadjusted` row is still in the report |
| `test_F_0_1_2_D_397_one_unadjusted_symbol_does_not_stop_the_others` | the run continues for the rest |
| `test_F_0_1_2_T04g_the_ingest_reads_the_universe_and_the_exclusion_file` | the symbol list is the universe minus the exclusion file, never hard-coded |
| `test_F_0_1_6_D_391_one_summary_per_source_and_timeframe` | one file per group, no mixing |
| `test_F_0_1_6_D_391_the_index_lists_every_group_with_its_counts` | the index and its counts |
| `test_F_0_1_6_D_391_a_partial_run_rewrites_only_its_own_group` | an untouched group's file survives; the index still lists it |
| `test_F_0_1_6_D_391_a_large_run_does_not_print_every_row` | `--max-rows` |
| `test_F_0_1_2_D_397_the_cli_still_exits_zero_when_a_symbol_is_unadjusted` | the run's exit code is 0 although one symbol failed |
| `test_F_0_1_6_T04g_the_summary_survives_a_late_first_break_hour` | the schema-inference crash of §7 (1): **120 rows**, so the default `infer_schema_length=100` really raises, and `summary_frame` really fixes it |

## 9. Acceptance commands

```
uv run pytest -m "not slow"                            1242 passed, 1 failed (see below)
uv run pytest tests/parity tests/leakage tests/oracle    283 passed
uv run pytest -m db                                       21 passed, 0 skipped
uv run ruff check . / ruff format --check .             clean
uv run mypy src                                         no issues in 100 source files
uv run sfac streams check --base origin/main            ownership, ids, alembic head: ok
```

**The one failure is not this task's.** `tests/property/test_F_0_5_metrics_properties.py::
test_F_0_5_1_scaling_pnl_scales_profit_and_dd_keeps_ratio` fails on a counterexample Hypothesis
found during this session: `tests/fixtures/metrics_runs.py:55` derives
`exit_price = entry_price + direction * pnl_gross / qty` with `entry_price = 100`, so scaling P&L
by `k = 10` drives the exit price to ≤ 0 and `TradeLog` correctly refuses it. It is a limit of
**stream A's T09 fixture**, not a product defect. The user reports that stream A has already
diagnosed it as their **P-44** and that the fix is to scale `qty`, not `entry_price` — scaling must
grow the position, not the price level, or the property changes meaning. That row is on stream A's
branch and is **not yet in this worktree's `pending.md`**, so it cannot be cited from here.
**Nothing on this branch touches `tests/fixtures/metrics_runs.py`,** and the failure is reproducible
from `origin/main` alone.

No new dependency. Nothing under `configs/costs/` or `configs/universe.yaml` was changed
(D-388, D-394); `configs/universe/us_equity_daily_excluded.csv` is unchanged (still empty).

## 10. Open questions

- **P-68, P-69, P-70** (T04f) remain open; none blocks the batch.
- The quality `warning` share (2,705 of 6,707) is dominated by delisted micro caps. No decision is
  needed now — **T04k** is where the frozen stretches and dead-listing padding are removed, and the
  clean snapshot becomes the research reference.
