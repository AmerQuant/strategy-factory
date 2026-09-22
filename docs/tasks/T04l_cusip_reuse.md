# T04l — Re-used tickers by CUSIP: settle the 221 splices D-700 keeps

**Features:** F-0.1.2 (frozen stretches, re-use boundary), F-0.1.8 (derived snapshots) · **Priority:** MVP · **Depends on:** **T04k** (merged, clean references set) and **T04h** · **Must be done before:** the **first real stage-1 run (T12)**, so the research reference does not move mid-research (D-705)
**Branch:** `b/T04l-cusip-reuse` from `main`.

Read first: `CLAUDE.md` (rules 1, 10, 11), **D-705** (the decision this task implements), **D-700**
(the name rule it extends), D-398, D-399, D-702, D-704, and `docs/reviews/T04k_review.md` §3 and §5.

## Why

T04k decided re-used tickers by **company name** (D-700). The Alpaca assets file holds one name per
ticker — today's holder — so the old company's name exists only when it **renamed away** from the
ticker. That settled **10 of the 231** re-use candidates; **221 stay spliced** (their padding cut,
their history kept), among them four of the five Moneta targets D-398 named: `MBLY`, `SE`, `SNOW`
and `CTRA`. `194` of the 221 are `one_name`: an acquisition, bankruptcy or plain delisting leaves
no rename, so no second name.

The raw `NAME_CHANGE` feed (`reference/alpaca/corporate_actions/name_changes_20260920.json`, 3,650
rows) carries **`old_cusip` and `new_cusip`**. A CUSIP identifies the **security**, not its name,
so it can separate two companies that shared a ticker even where no name is left to compare, and it
cannot be fooled by a company renaming itself (D-705).

## Update 2026-09-21 — scope after D-707/D-708, and the measured coverage (§1 done)

**Branch:** `b/T04l-cusip-reuse` from `main` (`d2ebc6a`: T04k, T04h and the provenance follow-up merged).

### Candidates (D-705, D-708)

| set | where from | rows |
|---|---|---|
| T04k kept | the re-use candidates D-700 left spliced (`T04k_boundaries.csv`, outcome `kept …`) | 221 (1D) |
| D-708 long gaps | every gap ≥ `relisting.gap_days` (200) **without** a price-level break in a current reference (`T04h_long_gaps.csv`) — the price jump is **dropped** from the criterion (D-708) | 92 gaps on 87 symbols (1D), 4 (1H: `CSRA`, `DOW`, `EMC`, `Q`) |

317 rows, 304 distinct symbols. Every boundary T04l trims in a 1D series is applied to that symbol's 1H
series too (D-707, D-708).

### What the `NAME_CHANGE` feed can and cannot speak to (measured: `scripts/analysis/T04l_coverage.py` → `docs/reviews/T04l_cusip_coverage.csv`)

The feed is the **only CUSIP source in the raw store**: the Alpaca and quantplatform asset lists carry
today's name per ticker and no CUSIP; the S&P PIT list and MS-US-1D are ticker-keyed. The feed (3,650
rows, 813 with a CUSIP change) holds a CUSIP **only on a rename row** — `old_symbol/old_cusip →
new_symbol/new_cusip`. So a ticker has CUSIP evidence only where a holder **renamed into or away from
it**. A re-listing years later by an unrelated company (an IPO, a SPAC, a spin-off listing under a free
ticker) and an old holder that left by **merger, acquisition or delisting** produce **no rename row** —
the feed is silent on exactly the typical re-use. Per side of the break (before: a rename away before
the series resumes, or a rename into it before the break; after: a rename into it from the break on,
or away after it resumes):

| candidates | CUSIP both sides | before only | after only | none |
|---|---|---|---|---|
| T04k kept (221, 1D) | **9** | 19 | 35 | **158** |
| D-708 long gaps (92, 1D) | **6** | 23 | 11 | **52** |
| D-708 long gaps (4, 1H) | 0 | 0 | 1 (`Q`) | 3 |

Where both sides have a CUSIP (15 rows, 14 symbols — `REED` is in both sets):

| relation | symbols | reading |
|---|---|---|
| **different issuer** (first 6 characters differ) | `AACI`, `BRPM`, `CMII`, `HYAC`, `SVAC` (long gaps); `CTRA`, `GRAF` (T04k kept) | a different security → **re-use** |
| **same issuer, new CUSIP** | `REED`, `AIM`, `BURU`, `PAPL`, `PTN`, `QTI`, `WW` | a corporate action of one issuer — here the pattern of a **reverse-split CUSIP reissue** → same company |
| same CUSIP | — | same security |

So on today's evidence the CUSIP settles **6 of the 92 daily long gaps** (5 re-uses, 1 same issuer) and
**0 of the 4 hourly** ones, and **9 of the 221** T04k kept (2 re-uses: `CTRA`, `GRAF`; 7 same issuer).
Of the named Moneta targets only **`CTRA`** is settled (a re-use: Contura/Alpha `020764106` → Coterra
`127097103`); `MBLY`, `SE`, `SNOW` have **no feed row**. `PCL`, `Q`, `CSRA`, `AYA`, `HAWK`, `DOW`, `EMC` —
the long gaps that prompted D-708 — have none either (`Q` after-side only).

**Fallback for the rest.** Inside the store there is none beyond what T04k already used: D-700's company
names (today's holder only) and the ticker-keyed cross-check (D-399: it cannot see a re-use). By
**D-399 (4)** every candidate the CUSIP cannot settle **keeps its full history and is listed**. Whether
to fetch more identity evidence — a user network run (D-031) — is **P-84**.

### How a trimmed symbol's reference moves, and what that touches

- **1D:** `sfac data clean --set-reference` derives a **new** clean snapshot from the **raw** one with the
  CUSIP boundary applied (`derived_from` raw, config hash, log, provenance naming D-705/D-708) and makes it
  the reference. The **previous clean reference stays** in the store and the catalog (rule 10); it was a
  reference, so it is **not** retired (D-702 does not extend to it). The catalog logs a `set_reference`
  event with the note `T04l CUSIP boundary`.
- **1H:** a **derived 1H snapshot** of the raw 1H series, trimmed at the same boundary, with the same log
  discipline and its own quality report, becomes the `(symbol, 1H)` reference; the raw 1H snapshot stays.
- **Every moved reference is listed** in `docs/reviews/T04l_references_moved.csv` (symbol, timeframe, old
  hash, new hash, boundary, evidence) and in `docs/streams/B.md` for stream A — nothing is re-pointed
  silently.
- **What was computed from the old references: nothing.** Stream B's registry (`sfac_b`) has 0 trials, 0
  pipeline runs, 0 `data_snapshots` rows (checked 2026-09-21); T12 has not started; stream A's parity (T11)
  reads the TradingView fixtures, not the Alpaca store. A run resolves references when it starts and
  records their hashes (`core/config.py`), so a run made before T04l would still reproduce from the old
  snapshot, which stays; a run after T04l reads the new one. That is why T04l must merge before T12
  (D-705).
- Symbols the CUSIP does not settle: **no reference moves**.

### Stop

Per §1 and §2: the coverage is measured and **thin** (15 of 317 rows can be decided). T04l **stops here**
for the supervisor to confirm the rule with this coverage (**P-83**) and to decide on more evidence
(**P-84**). No rule is implemented and no reference moves before that.

## Update 2026-09-21 (2) — D-709 (the rule) and D-710 (more evidence)

### Order of work

1. **Evidence (D-710)** — the user runs `scripts/pilots/T04l_corporate_actions.ps1`: every
   corporate-action type the endpoint offers except `name_change`, 2016 → today, immutable under
   `SFAC_RAW_ROOT/reference/alpaca/corporate_actions/` with manifests. New code: the fetch
   `fetch_corporate_actions` (download layer, beside T04f's `fetch_name_changes`, run only by the user),
   the command `sfac data reference alpaca-corporate-actions`; tests with a fake client, no network.
2. **Re-measure (D-710)** — `T04l_coverage.py` extended to every action type; the coverage over the
   317 candidate rows is reported **per action type** (how many each settles) — **stop and report**.
3. Only then **implement D-709**, re-derive the affected symbols, set the markers, move the references.

### The first download was truncated (2026-09-21) — found before any use

The user's first run returned **11,000 rows: exactly 1,000 per year** for every year 2016–2026. alpaca-py's
`CorporateActionsRequest.limit` defaults to **1,000 as a cap on the total**, not a page size, so each
yearly request stopped after its first page, which is ordered by symbol: dividends end at `A…`
(`AAPL` present, `JNJ`/`KO` absent), and the known events are missing — `AVGO` 2024-07-15, `GOOGL`
2022-07-18, `TSLA` 2022-08-25 forward splits, Plum Creek's 2016 merger. Only 1,134 symbols, 197 of them
in our daily universe. It was a **truncation, not a scope limit of the feed**, and nothing was measured
on it. Fixed: `limit=None`, the manifest records rows per year and flags a year that ends on a whole
page (`suspect_truncation`); two tests. T04f's `name_changes` file is **not** affected (its largest
year has 700 rows) and its fetch now also sets `limit=None`. The truncated files stay in the raw store
(immutable); every reader takes the **latest version** of each answer key. 3,971 of the 11,000 rows
carried **no CUSIP at all** — to be re-counted on the full download, because a row without a CUSIP is
not identity evidence. The re-run and a re-check of the known events come **before** the coverage.

### The full download (2026-09-21, v2) — scope, and what it can say (D-711)

- **Complete by page:** 387,840 rows (376,840 of the 12 new types); rows per year 24,401 ... 47,871;
  the tested check (`sfac data reference alpaca-corporate-actions-check`) finds **no year on a page
  boundary**. Known events present: `AVGO` 2024-07-15 10:1, `GOOGL` 2022-07-18 20:1, `TSLA` 2022-08-25
  3:1 (and `NVDA`, `AAPL`); 28,039 distinct symbols, market-wide (not only tradable or listed ones).
- **But its evidence is time-bound.** Mergers start 2019-20 (cash 2020, stock 2 rows before 2019),
  worthless removals 2023, redemptions 2023 only; cash-dividend CUSIPs are **blank for all of 2016-18**
  (93 % of 2019, 0 % from 2021). The Plum Creek 2016 merger into Weyerhaeuser is **absent**; `PCL`'s only
  rows are the new holder's 2025-26 dividends. **Before 2020 a missing row is evidence of nothing**, and
  D-709 never reads absence as evidence at any date.
- **Rows without a CUSIP** are not evidence and are counted apart: cash dividends 102,766 (28 %),
  reverse splits 1,840 field values (old/new), forward splits 224; every other type 0.
- **Some rows are filed under a later ticker.** For 2,563 same-CUSIP renames, rows dated before the
  rename are under the **old** ticker in most cases (dividends 5,198) but under the **new** one in 268
  (≈ 5 %; reverse splits 29 of 387) — `CTRA`'s May/Aug 2021 dividends are Cabot's (then `COG`), `CIVI`'s
  2017 reverse split is Bonanza Creek's. Evidence rule: a row of a CUSIP under the ticker dated before
  that CUSIP renamed **into** the ticker is dropped; a row of the new holder within `rename_window_days`
  before the resumption counts on the after side. Without these two rules `CTRA` read "same CUSIP";
  with them it reads a different issuer (Alpha/Contura `020764106` → Coterra `127097103`).

### How each action type speaks to identity

| type | CUSIP field(s) | what it proves |
|---|---|---|
| `cash_merger`, `stock_merger`, `stock_and_cash_merger` | `acquiree_cusip` (+ acquirer) | the acquiree **ceased** on that date |
| `worthless_removal`, `redemption` | `cusip` | the security **ceased** |
| `cash_dividend`, `stock_dividend`, `forward_split`, `reverse_split` (`old/new_cusip`), `spin_off` (`source_cusip`), `rights_distribution` (`source_cusip`), `unit_split` (`old/new/alternate`) | the security's CUSIP | **which security held the ticker on that date** — evidence for a side of the break |
| `name_change` (T04f) | `old_cusip`, `new_cusip` | as before |

A side of the break gets a CUSIP from any of them dated on that side; a **cessation** of the
before-side CUSIP before the series resumes is evidence that the old security is gone. Whether a
cessation alone (no after-side CUSIP) may trim is **not** in D-709 — it will be brought back with the
measured counts as its own question, not assumed.

### The rule (D-709)

- **Different issuer** across the break → **trim** at the boundary in **1D and 1H**.
- **Same CUSIP or same issuer** → keep — but each **same-issuer** case is first settled with the
  known-split cross-check that settled AVGO (D-397/D-399: the MS-US-1D ratio at the break against the
  ingested series); the verdict is recorded per symbol in `T04l_same_issuer.csv`. An **unadjusted
  split** takes the **D-397 path**: the symbol's references leave the store's research set, it is listed,
  and the `--refresh` download command is printed for the user — it is **not** "kept".
- **One-sided, missing, or CUSIP and D-700 names disagree** → **keep and list** (D-399 (4)), **with the
  splice marker below**.

### The splice marker (D-709 change 2)

**Why not in the snapshot's own metadata.** A snapshot is content-addressed and its metadata is
immutable: identical bars return the metadata of whoever wrote them first (D-392; T04k §7.6 and D-702
showed it on 3,180 snapshots). A kept series does not change its bars, so a marker written into
`.meta.json` would be silently dropped for exactly the series that need it.

**Representation.** The marker attaches to the **snapshot key** in the store, the way `quality_status`
does (F-0.1.6):

- a catalog column **`splices`** (CATALOG_ONLY, like `is_reference` and `quality_status`): a JSON list,
  one entry per unsettled boundary — `{"boundary": "YYYY-MM-DD", "break_start": "YYYY-MM-DD",
  "reason": "<why unsettled>", "evidence": "<what was found>", "decision": "D-709"}`; `reason` is one of
  `cusip_none`, `cusip_before_only`, `cusip_after_only`, `cusip_disagrees_with_name`,
  `same_issuer_split_unsettled`; empty for every other snapshot;
- every change goes through `Catalog.mark_splices(key, splices, note)`, which appends a **`splice`
  event** to `catalog_events` (the audit trail, as `quality` events are);
- a quality check **`known_splice`** (severity `warning`, in `configs/data/quality.yaml`) writes the
  marker into the snapshot's `_quality/<hash>.json|.md` and so into `quality_status`, next to the bars.

**Reading it.** `Catalog.splices(key) -> list[Splice]` (typed, frozen); `DataAccess.splices(symbol,
timeframe)` gives stage 1 the marker of the reference it reads, beside `bars()` and `split()`;
`sfac data show SYMBOL TIMEFRAME` prints it. Stage 1 decides what to do with it (T12); T04l only
guarantees it is there. `DataAccess` lives in `data/split.py`, next to the split manager (a D-402
critical component): the change is one **read-only** method and touches no split or holdout logic.

**Which snapshots.** Every **current reference** (1D and 1H) of a candidate the evidence does not
settle. "Cannot settle" includes "cannot tell a halt from a re-use": the marker says which, so the
series is never silently treated as one company. A trimmed series carries no marker (its boundary is
applied); the previous reference keeps whatever it had.

### References (D-709)

Moving a reference affects **only future runs**: a run pins the snapshot hashes it read
(`core/config.py` resolves references when the run starts and records them), which is why the previous
snapshot is kept (rule 10) and every move is listed (`T04l_references_moved.csv`, `docs/streams/B.md`).

## Scope

1. **Measure first.** For each of the 221 kept candidates (`docs/reviews/T04k_boundaries.csv`,
   outcome `kept …`), collect every CUSIP the feed associates with the ticker and when. Report how
   many have two or more distinct CUSIPs on either side of the boundary, how many have one, how many
   none. Stop and report before changing any rule if the coverage is thin — as D-700 was.
2. **The rule** (to be confirmed by the supervisor with the measured coverage): a ticker whose
   CUSIP changes to a **different security** across the break is a re-use → trim at the boundary
   (D-398 (2)); a CUSIP that stays the same is the same security (a halt or a rename) → keep. Exact
   identity, as in D-700. Where the CUSIP evidence and the name evidence disagree, or only one side
   has a CUSIP, keep the full history and list the symbol (D-399 (4) stands). A CUSIP change that
   is a **corporate action of the same issuer** (a reorganisation keeps the issuer prefix — the first
   six characters) must be told apart from a change of issuer; state which one the rule uses and
   test both.
3. **Re-derive only the affected symbols' clean snapshots** through `sfac data clean`, with the D-702
   discipline: the superseded clean snapshots were references (T04k set them), so they are **not**
   retired — the new clean snapshot becomes the reference and the old one stays in the store
   (rule 10). Every changed reference is listed.
4. Every threshold or window in config (rule 1); every added rule recorded with its measured cost
   and whether it can remove real data, as D-704 does.

## Out of scope
- The 10 trims D-700 already made, unless the CUSIP evidence contradicts one — then report it.
- Hourly snapshots (T04h's), `configs/costs/` (D-388) and `configs/universe.yaml` (D-394).

## Acceptance
- The coverage table (§1) is in the review before any rule is applied.
- Tests: a CUSIP change of issuer trims; the same CUSIP across a halt keeps; a CUSIP present on one
  side only keeps and lists; CUSIP and name disagreeing keeps and lists; an issuer-prefix
  reorganisation is classified as the rule states.
- Every re-derived symbol's new clean snapshot has `derived_from`, the config hash, the boundary and
  a log whose replay reproduces it; the previous reference is still in the store and the catalog.
- Before/after for `MBLY`, `SE`, `SNOW`, `CTRA` stated explicitly.
- Acceptance commands green; `sfac streams check` clean.

## Review summary
`docs/reviews/T04l_review.md`: the CUSIP coverage over the 221, the rule and its failure modes, the
symbols trimmed and kept with their evidence, the references that moved, deviations and open
questions.
