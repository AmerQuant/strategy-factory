"""D-399: settle an ambiguous re-use signature against the all-adjusted MS-US-1D series (T04k).

A frozen stretch or a long gap with a level break is what **three** different things look like:

* a ticker genuinely re-used by another company,
* an **unadjusted (reverse) split** the feed never applied -- `AVGO` proves those exist (D-397),
* a long **trading halt** that resumes at a different level.

The ingested series cannot tell them apart, and **D-399 forbids trimming on an ambiguous
signature**.

**Measured limit of this test (T04k, 2026-09-21).** D-399 expects the all-adjusted series to be
continuous across a corporate action and to break where the company actually changed. The first
half holds -- it is what settled `AVGO`. **The second half does not**, because MS-US-1D is keyed by
**ticker**, exactly like the Alpaca feed, so a re-used ticker splices **identically in both**.
Measured on `PX`: the cross-check goes 156.80 -> 11.51 on 2021-10-21, the same day and the same
shape as the ingested series, and it carries the same frozen padding at 156.80 before it. `MBLY` is
the same. A shared break therefore proves only that the break is in the data, which a re-use and a
halt both satisfy.

So this test yields two useful answers, not four:

``unadjusted_split``
    the cross-check is **continuous** where the ingested series jumps. **Not a boundary**: the
    symbol takes the D-397 path (it fails ingest and is listed with its ``--refresh`` command) and
    its history is left **untouched**. This is the `AVGO` case and the test is decisive here.
``unsettled``
    anything else -- both feeds break alike (the common case), they break differently, there is no
    cross-check file, or there is no overlapping bar. **Not a boundary**: the full history is kept,
    nothing is trimmed, and the symbol is listed for the supervisor, exactly as D-399 (4) says.

``re_use`` and ``halt`` remain defined because D-399 names them and a future discriminator may
reach them, but **this** test never returns them: nothing here can prove either one.

**What ``unadjusted_split`` requires, and why each condition is there.** A first version declared
four symbols ``unadjusted_split`` and all four were wrong (T04k, 2026-09-21):

* ``AMLX`` and ``ATAI`` -- the cross-check has **no bar before the IPO**; the nearest-bar fallback
  took the IPO bar for *both* sides and reported a "continuous" 1.0000 ratio of a bar with itself.
  So the two cross-check bars must be **distinct**, one strictly before the other.
* ``TBRG`` -- the ingested bar before the boundary was **padding** at a stale 13.31 while the
  cross-check was trading near 9; the ingested "jump" measured the pad. So the caller compares
  the last **real** bar before the break, never a padded one.
* ``NRGZ`` -- both feeds made the same 0.693 move, which is **not** a break at the configured
  threshold in either. So the ingested series must itself break at the compared dates.

An unadjusted split is a jump between two real bars that the all-adjusted series does not make.
Anything short of that is ``unsettled``.
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
    window_days: int,
) -> CrosscheckVerdict:
    """Classify one boundary break against the all-adjusted series (``date, close``).

    ``before`` / ``after`` are the last date before the break and the first date after it, and
    ``ratio_ingested`` is ``close_after / close_before`` in the ingested series. The cross-check's
    own ratio is taken over the **same two dates**; when it has no bar on one of them, the nearest
    bar within a week is used, and failing that the case is ``unsettled``.
    """
    if crosscheck is None or crosscheck.height == 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "no MS-US-1D cross-check file")
    if abs(ratio_ingested - 1.0) <= jump_threshold:
        return CrosscheckVerdict(
            symbol,
            UNSETTLED,
            f"the ingested series does not break at {before}..{after} (ratio {ratio_ingested:.4f})",
        )
    # Each side looks only outward from its own date, so the two bars can never be the same one
    # (S2: with a short gap, a single bar between the two dates could satisfy both windows).
    b = _bar_near(crosscheck, before, window_days, not_after=before)
    a = _bar_near(crosscheck, after, window_days, not_before=after)
    if b is None or a is None:
        return CrosscheckVerdict(
            symbol,
            UNSETTLED,
            f"cross-check has no bar near {before if b is None else after} on its own side",
        )
    (_, c_before), (_, c_after) = b, a
    if c_before <= 0:
        return CrosscheckVerdict(symbol, UNSETTLED, "cross-check close is not positive")
    ratio_cross = c_after / c_before
    broke = abs(ratio_cross - 1.0) > jump_threshold
    evidence = (
        f"ingested {ratio_ingested:.4f} vs all-adjusted {ratio_cross:.4f} over {before}..{after}"
    )
    if not broke:
        return CrosscheckVerdict(symbol, UNADJUSTED_SPLIT, evidence, ratio_ingested, ratio_cross)
    # The cross-check breaks too. Both feeds are keyed by ticker, so they splice a re-used ticker
    # the same way: a shared break proves the break is real, never *what* caused it. Nothing here
    # separates a re-use from a halt, so the case is not settled and nothing is trimmed (D-399).
    alike = _same_move(ratio_ingested, ratio_cross, match_tolerance)
    why = "both feeds break alike" if alike else "the feeds break by different factors"
    return CrosscheckVerdict(
        symbol,
        UNSETTLED,
        f"{evidence}; {why}, and MS-US-1D is ticker-keyed like the ingested feed, "
        f"so it cannot separate a re-use from a halt",
        ratio_ingested,
        ratio_cross,
    )


def _same_move(a: float, b: float, tolerance: float) -> bool:
    if a <= 0 or b <= 0:
        return False
    return abs(math.log(a / b)) <= tolerance


def _bar_near(
    crosscheck: pl.DataFrame,
    day: dt.date,
    window_days: int,
    not_before: dt.date | None = None,
    not_after: dt.date | None = None,
) -> tuple[dt.date, float] | None:
    """The cross-check bar on ``day``, or the nearest within ``window_days`` **on its own side**.

    ``not_before`` / ``not_after`` keep the before-bar strictly before the after-bar, so the two
    sides can never collapse onto one bar (the `AMLX`/`ATAI` failure).
    """
    lo, hi = day - dt.timedelta(days=window_days), day + dt.timedelta(days=window_days)
    if not_before is not None:
        lo = max(lo, not_before)
    if not_after is not None:
        hi = min(hi, not_after)
    if lo > hi:
        return None
    near = crosscheck.filter(pl.col("date").is_between(lo, hi))
    if near.height == 0:
        return None
    nearest = near.with_columns(
        (pl.col("date") - pl.lit(day)).dt.total_days().abs().alias("_d")
    ).sort("_d", "date")
    return nearest["date"][0], float(nearest["close"][0])
