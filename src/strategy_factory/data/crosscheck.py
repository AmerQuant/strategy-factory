"""D-399: settle an ambiguous re-use signature against the all-adjusted MS-US-1D series (T04k).

A frozen stretch or a long gap with a level break is what **three** different things look like:

* a ticker genuinely re-used by another company,
* an **unadjusted (reverse) split** the feed never applied -- `AVGO` proves those exist (D-397),
* a long **trading halt** that resumes at a different level.

The ingested series cannot tell them apart, and **D-399 forbids trimming on an ambiguous
signature**. The all-adjusted cross-check can: it applies every corporate action, so it runs
**continuously** across a split and **breaks** across a change of company. That is the test that
settled AVGO, and this module applies it to each `trim_to_boundary` candidate.

Verdicts and what T04k does with each (D-399):

``unadjusted_split``
    the cross-check is continuous where the ingested series jumps. **Not a boundary**: the symbol
    takes the D-397 path (it fails ingest and is listed with its ``--refresh`` command) and its
    history is left **untouched**.
``halt``
    both series resume at about the same level relative to each other and the break is a gap rather
    than a change of company. **Not a boundary**: the frozen stretch is still cut under D-398 (1),
    the history on both sides is kept, and the gap is stated in the quality report.
``re_use``
    the cross-check breaks too. **A boundary**: trim under D-398 (2).
``unsettled``
    no cross-check file, no overlapping bars, or the two disagree. **Not a boundary**: the full
    history is kept and the symbol is listed for the supervisor.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Final

import polars as pl

UNADJUSTED_SPLIT: Final = "unadjusted_split"
HALT: Final = "halt"
RE_USE: Final = "re_use"
UNSETTLED: Final = "unsettled"

#: A boundary is applied for this verdict only (D-399).
TRIMMABLE: Final = frozenset({RE_USE})


@dataclass(frozen=True, slots=True)
class CrosscheckVerdict:
    """What the all-adjusted series says about one boundary break."""

    symbol: str
    verdict: str
    evidence: str
    ratio_ingested: float | None = None
    ratio_crosscheck: float | None = None

    @property
    def may_trim(self) -> bool:
        return self.verdict in TRIMMABLE


def settle_boundary(
    symbol: str,
    before: dt.date,
    after: dt.date,
    ratio_ingested: float,
    crosscheck: pl.DataFrame | None,
    match_tolerance: float,
    jump_threshold: float,
) -> CrosscheckVerdict:
    """Classify one boundary break against the all-adjusted series (``date, close``).

    ``before`` / ``after`` are the last date before the break and the first date after it, and
    ``ratio_ingested`` is ``close_after / close_before`` in the ingested series. The cross-check's
    own ratio is taken over the **same two dates**; when it has no bar on one of them, the nearest
    bar within a week is used, and failing that the case is ``unsettled``.
    """
    if crosscheck is None or crosscheck.height == 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "no MS-US-1D cross-check file")
    c_before = _close_near(crosscheck, before)
    c_after = _close_near(crosscheck, after)
    if c_before is None or c_after is None:
        return CrosscheckVerdict(
            symbol,
            UNSETTLED,
            f"cross-check has no bar near {before if c_before is None else after}",
        )
    if c_before <= 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "cross-check close is not positive")
    ratio_cross = c_after / c_before
    broke = abs(ratio_cross - 1.0) > jump_threshold
    evidence = (
        f"ingested {ratio_ingested:.4f} vs all-adjusted {ratio_cross:.4f} over {before}..{after}"
    )
    if not broke:
        return CrosscheckVerdict(symbol, UNADJUSTED_SPLIT, evidence, ratio_ingested, ratio_cross)
    if _same_move(ratio_ingested, ratio_cross, match_tolerance):
        # Both series make the same move, so the level break is a real price move across a halt,
        # not a different company: the two feeds agree about what happened.
        return CrosscheckVerdict(symbol, HALT, evidence, ratio_ingested, ratio_cross)
    return CrosscheckVerdict(symbol, RE_USE, evidence, ratio_ingested, ratio_cross)


def _same_move(a: float, b: float, tolerance: float) -> bool:
    if a <= 0 or b <= 0:
        return False
    return abs(math.log(a / b)) <= tolerance


def _close_near(crosscheck: pl.DataFrame, day: dt.date, window_days: int = 7) -> float | None:
    """The cross-check close on ``day``, or the nearest bar within ``window_days``."""
    exact = crosscheck.filter(pl.col("date") == day)
    if exact.height:
        return float(exact["close"][0])
    lo, hi = day - dt.timedelta(days=window_days), day + dt.timedelta(days=window_days)
    near = crosscheck.filter(pl.col("date").is_between(lo, hi))
    if near.height == 0:
        return None
    nearest = near.with_columns(
        (pl.col("date") - pl.lit(day)).dt.total_days().abs().alias("_d")
    ).sort("_d")
    return float(nearest["close"][0])
