"""F-0.1.2 / F-0.1.8 (T04l): what to do at each re-use boundary, and where a series starts.

Pure: bars and evidence in, decisions out; ``cli_reuse`` does the store I/O.

**Candidates** (D-705, D-708): the boundaries T04k kept (D-700 names could not settle them) and
**every** gap of ``relisting.gap_days`` or more in a symbol's series -- the price jump is dropped
from the criterion, not weakened.

**Decision per boundary** (D-709, with D-712's evidence rules in :mod:`cusip_evidence`):

* CUSIPs on both sides, **different issuer** -> ``trim`` -- unless the D-700 names say the same
  company (``cusip_disagrees_with_name``, unsettled);
* **mixed** issuers -> unsettled (``cusip_mixed``): a disagreement is never read as "same";
* **same CUSIP or same issuer** -> the **known-split test** first (D-709 change 1, ``split_test``):
  no price jump across the break -> ``keep``; a jump that matches a split the feed records ->
  ``unadjusted_split`` (the D-397 path); any other jump -> unsettled
  (``same_issuer_split_unsettled``) -- a check that cannot tell is never "no split". If the names
  say a re-use while the CUSIPs say the same security, the two disagree (unsettled);
* one side only, or none -> unsettled (D-399 (4)). Absence of a row is never evidence (D-712).

**Where the series starts** (D-713): at the **last** boundary that is a proven re-use or unsettled;
a derived snapshot from that date becomes the reference, the full history stays and is marked.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal

import polars as pl

from strategy_factory.data.cusip_evidence import (
    BOTH,
    DIFFERENT_ISSUER,
    ISSUER_LEN,
    MIXED,
    Evidence,
    SplitRecord,
)
from strategy_factory.data.name_evidence import RE_USE, SAME_COMPANY

TRIM: Final = "trim"
KEEP: Final = "keep"
UNSETTLED: Final = "unsettled"
SPLIT: Final = "unadjusted_split"

#: Outcomes of the known-split test.
NO_BREAK: Final = "no_break"
SPLIT_MATCH: Final = "unadjusted_split"
SPLIT_UNEXPLAINED: Final = "unexplained_jump"

Action = Literal["trim", "keep", "unsettled", "unadjusted_split"]


@dataclass(frozen=True, slots=True)
class Boundary:
    """One candidate break: the series resumes on ``resumes``."""

    resumes: dt.date
    source: str  # "T04k kept", "long gap 1D", "long gap 1H", joined with "+" when merged
    name_verdict: str | None = None
    gap_days: int | None = None

    @property
    def break_start(self) -> dt.date | None:
        """The last bar before the break, when the break is a gap."""
        return self.resumes - dt.timedelta(days=self.gap_days) if self.gap_days else None


@dataclass(frozen=True, slots=True)
class Decision:
    boundary: Boundary
    action: Action
    reason: str  # the splice reason when unsettled or an unadjusted split, else ""
    evidence: Evidence
    split_verdict: str | None = None
    split_evidence: str = ""


@dataclass(frozen=True, slots=True)
class Plan:
    """What happens to one symbol: nothing, a trim, a research window, or the D-397 path."""

    kind: Literal["none", "trim", "research_window", "unadjusted_split"]
    start: dt.date | None
    #: the boundaries the **full-history** marker lists (unsettled ones a proven trim does not
    #: already cut away; the unadjusted splits on the D-397 path)
    marked: tuple[Decision, ...]
    #: the boundary the **research window** starts at (its marker)
    window: tuple[Decision, ...]
    decisions: tuple[Decision, ...]


def long_gaps(ts: pl.Series, gap_days: int) -> list[tuple[dt.date, int]]:
    """``(resumes, gap in days)`` for every gap of ``gap_days`` or more between consecutive bar
    dates -- whatever the price does (D-708)."""
    dates = sorted(set(ts.dt.date().to_list()))
    return [(b, (b - a).days) for a, b in pairwise(dates) if (b - a).days >= gap_days]


def split_test(
    ratio: float,
    before: dt.date,
    after: dt.date,
    evidence: Evidence,
    splits: list[SplitRecord],
    jump_threshold: float,
    match_tolerance: float,
) -> tuple[str, str]:
    """D-709 change 1, the known-split test: the close ratio across the break against the splits
    the feed records for these CUSIPs between the two bars (AVGO was settled this way).

    ``no_break`` -- the price does not jump (``|ratio - 1| <= jump_threshold``);
    ``unadjusted_split``
    -- it jumps by the recorded split factor (``|ln ratio - ln factor| <= match_tolerance``);
    ``unexplained_jump`` -- any other jump, which is never taken to mean "no split"."""
    if abs(ratio - 1.0) <= jump_threshold:
        return NO_BREAK, f"close ratio {ratio:.4f} across {before}..{after}: no break"
    issuers = {c[:ISSUER_LEN] for c in evidence.before + evidence.after}
    lo, hi = before.isoformat(), after.isoformat()
    inside = [
        s for s in splits if lo < s.date <= hi and any(c[:ISSUER_LEN] in issuers for c in s.cusips)
    ]
    factor = math.prod(s.factor for s in inside) if inside else None
    listed = ", ".join(f"{s.date} x{s.factor:g}" for s in inside) or "none recorded"
    if factor is not None and abs(math.log(ratio) - math.log(factor)) <= match_tolerance:
        return SPLIT_MATCH, (
            f"close ratio {ratio:.4f} across {before}..{after} matches the recorded split(s) "
            f"{listed} (factor {factor:g}): the history is not adjusted for it"
        )
    return SPLIT_UNEXPLAINED, (
        f"close ratio {ratio:.4f} across {before}..{after} is a jump the recorded split(s) "
        f"({listed}) do not explain"
    )


def decide(
    boundary: Boundary, evidence: Evidence, split_verdict: str | None = None
) -> tuple[Action, str]:
    """``(action, reason)`` for one boundary (see the module docstring)."""
    if evidence.coverage != BOTH:
        return UNSETTLED, f"cusip_{evidence.coverage}"
    if evidence.relation == DIFFERENT_ISSUER:
        if boundary.name_verdict == SAME_COMPANY:
            return UNSETTLED, "cusip_disagrees_with_name"
        return TRIM, ""
    if evidence.relation == MIXED:
        return UNSETTLED, "cusip_mixed"
    if boundary.name_verdict == RE_USE:
        return UNSETTLED, "cusip_disagrees_with_name"
    if split_verdict == NO_BREAK:
        return KEEP, ""
    if split_verdict == SPLIT_MATCH:
        return SPLIT, "unadjusted_split"
    return UNSETTLED, "same_issuer_split_unsettled"


def plan(decisions: list[Decision]) -> Plan:
    """D-713: the series starts at the last proven re-use or unsettled boundary."""
    ordered = tuple(sorted(decisions, key=lambda d: d.boundary.resumes))
    splits = tuple(d for d in ordered if d.action == SPLIT)
    if splits:
        return Plan("unadjusted_split", None, splits, (), ordered)
    cuts = [d for d in ordered if d.action in (TRIM, UNSETTLED)]
    if not cuts:
        return Plan("none", None, (), (), ordered)
    start = max(d.boundary.resumes for d in cuts)
    last_trim = max((d.boundary.resumes for d in cuts if d.action == TRIM), default=None)
    marked = tuple(
        d
        for d in cuts
        if d.action == UNSETTLED and (last_trim is None or d.boundary.resumes >= last_trim)
    )
    window = tuple(d for d in marked if d.boundary.resumes == start)
    kind: Literal["trim", "research_window"] = "research_window" if window else "trim"
    return Plan(kind, start, marked, window, ordered)
