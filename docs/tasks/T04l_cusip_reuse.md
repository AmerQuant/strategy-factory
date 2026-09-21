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
