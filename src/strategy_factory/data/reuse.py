"""F-0.1.2 / F-0.1.8 (T04l): what to do at each re-use boundary, and where a series starts.

Pure: bars and evidence in, decisions out; ``cli_reuse`` does the store I/O.

**Candidates** (D-705, D-708): the boundaries T04k kept (D-700 names could not settle them) and
**every** gap of ``relisting.gap_days`` or more in a symbol's series -- the price jump is dropped
from the criterion, not weakened.

**Decision per boundary** (D-709, with D-712's evidence rules in :mod:`cusip_evidence`):

* a CUSIP on both sides, **different issuer** -> ``trim``; if the D-700 name evidence says the
  same company, the two disagree -> ``unsettled`` (``cusip_disagrees_with_name``);
* **same CUSIP or same issuer** -> ``keep``, but only after the known-split cross-check (D-397 /
  D-399): an unadjusted split -> ``unadjusted_split`` (the D-397 path);
* one side only, or none -> ``unsettled`` (D-399 (4)): the full history is kept and marked.
  Absence of a row is never evidence (D-712).

**Where the series starts** (D-713): at the **last** boundary that is either a proven re-use or
unsettled -- a derived snapshot from that date becomes the reference; the full history stays.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal

import polars as pl

from strategy_factory.data.crosscheck import UNADJUSTED_SPLIT
from strategy_factory.data.cusip_evidence import BOTH, DIFFERENT_ISSUER, Evidence
from strategy_factory.data.name_evidence import SAME_COMPANY

TRIM: Final = "trim"
KEEP: Final = "keep"
UNSETTLED: Final = "unsettled"
SPLIT: Final = "unadjusted_split"

Action = Literal["trim", "keep", "unsettled", "unadjusted_split"]


@dataclass(frozen=True, slots=True)
class Boundary:
    """One candidate break: the series resumes on ``resumes``."""

    resumes: dt.date
    source: str  # "T04k kept", "long gap 1D", "long gap 1H"
    name_verdict: str | None = None
    gap_days: int | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    boundary: Boundary
    action: Action
    reason: str  # the splice reason when unsettled, else ""
    evidence: Evidence
    split_verdict: str | None = None
    split_evidence: str = ""


@dataclass(frozen=True, slots=True)
class Plan:
    """What happens to one symbol: nothing, a trim, a research window, or the D-397 path."""

    kind: Literal["none", "trim", "research_window", "unadjusted_split"]
    start: dt.date | None
    unsettled: tuple[Decision, ...]  # the boundaries the full-history marker lists
    decisions: tuple[Decision, ...]


def long_gaps(ts: pl.Series, gap_days: int) -> list[tuple[dt.date, int]]:
    """``(resumes, gap in days)`` for every gap of ``gap_days`` or more between consecutive bar
    dates -- whatever the price does (D-708)."""
    dates = sorted(set(ts.dt.date().to_list()))
    return [(b, (b - a).days) for a, b in pairwise(dates) if (b - a).days >= gap_days]


def decide(boundary: Boundary, evidence: Evidence, split_verdict: str | None = None) -> Action:
    """The D-709 action for one boundary (see the module docstring)."""
    if evidence.coverage != BOTH:
        return UNSETTLED
    if evidence.relation == DIFFERENT_ISSUER:
        return UNSETTLED if boundary.name_verdict == SAME_COMPANY else TRIM
    return SPLIT if split_verdict == UNADJUSTED_SPLIT else KEEP


def splice_reason(boundary: Boundary, evidence: Evidence) -> str:
    """Why a boundary is unsettled, as the marker says it (``Splice.reason``)."""
    if evidence.coverage == BOTH:
        return "cusip_disagrees_with_name"
    return f"cusip_{evidence.coverage}"


def plan(decisions: list[Decision]) -> Plan:
    """D-713: the series starts at the last proven re-use or unsettled boundary."""
    ordered = tuple(sorted(decisions, key=lambda d: d.boundary.resumes))
    if any(d.action == SPLIT for d in ordered):
        return Plan("unadjusted_split", None, (), ordered)
    cuts = [d for d in ordered if d.action in (TRIM, UNSETTLED)]
    if not cuts:
        return Plan("none", None, (), ordered)
    start = max(d.boundary.resumes for d in cuts)
    last_trim = max((d.boundary.resumes for d in cuts if d.action == TRIM), default=None)
    # unsettled boundaries a proven trim does not already cut away stay on the marker
    unsettled = tuple(
        d
        for d in cuts
        if d.action == UNSETTLED and (last_trim is None or d.boundary.resumes >= last_trim)
    )
    kind: Literal["trim", "research_window"] = (
        "research_window" if any(d.boundary.resumes == start for d in unsettled) else "trim"
    )
    return Plan(kind, start, unsettled, ordered)
