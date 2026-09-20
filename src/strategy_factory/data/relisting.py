"""Frozen stretches and re-used tickers in a daily series (T04i, D-383 amended by **D-398**).

Alpaca serves whatever currently trades under a symbol, and it pads the stretches in which
nothing trades with the last price. Two things therefore hide in a raw daily series:

* **padding** -- runs of bars with an identical close and **zero true range** (``high == low ==
  close``, volume 0). `PX` is the worked example: Praxair 2016-2018 at 96-169, then **749 bars at
  exactly 164.50**, then RPC Inc. from late 2021 at 12-15. Every indicator over such a stretch is
  meaningless, and a frozen price is silently "tradeable" where a gap is visibly missing data;
* **a re-used ticker** -- the old company up to its delisting, then the padding or a trading gap,
  then a different company. `FB` is Meta to 2022, then an unrelated instrument at 42-46 in 2026.

**D-398** settles what to do with both, and it is not "exclude the symbol":

1. **Any frozen stretch is removed from the series, whatever caused it** -- feed padding is not
   data. The threshold is config (``relisting.frozen_min_sessions``, 10 sessions).
2. Where a ticker was re-used and **the boundary is identifiable**, the series is kept **from that
   boundary onward** instead of the symbol being excluded; the boundary and the dropped span are
   recorded. This amends D-383's "re-used ticker excluded for now" and resolves the D-388
   collisions: `MBLY`, `SNOW`, `SE`, `CTRA` and `MARA` stay as broker-tradable symbols with
   honest, shorter histories.
3. **Leading** pre-listing padding is trimmed and the symbol stays.
4. Where the boundary is **not** identifiable from the series, the symbol is excluded and listed.

A symbol whose remaining history is then too short for a split (D-008) simply fails the split and
drops out of the candidate universe -- it is never hand-excluded for being short.

This module is pure: it takes arrays and returns the evidence rows plus one
:class:`SeriesVerdict` per symbol. Applying the verdict to the bars is **T04k** (the derived clean
daily snapshot, D-396); here it produces the artefact the supervisor reads.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Final

#: A break this far apart in time is a relisting, not a holiday or a trading halt.
DEFAULT_GAP_DAYS: Final = 200
#: Identical close **and** zero true range for this many sessions in a row is feed padding, not a
#: quiet market: a listed instrument prints a different high or low within two trading weeks.
#: D-398 sets the starting value; the configured one is ``relisting.frozen_min_sessions``.
DEFAULT_FROZEN_SESSIONS: Final = 10

#: The ratios a **reverse split** produces (1:n, so the price multiplies by n). A level break of
#: this shape is ambiguous: it is what an *unadjusted* reverse split looks like **and** what a
#: re-used ticker looks like. See P-74 -- the all-adjusted cross-check is what tells them apart.
REVERSE_SPLIT_RATIOS: Final = (
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    6.0,
    7.0,
    8.0,
    10.0,
    12.0,
    15.0,
    16.0,
    20.0,
    25.0,
    30.0,
    40.0,
    50.0,
    60.0,
    75.0,
    100.0,
    120.0,
    150.0,
    200.0,
    250.0,
    300.0,
    500.0,
    1000.0,
)
#: Relative tolerance around one of those ratios.
REVERSE_SPLIT_TOLERANCE: Final = 0.05

#: The verdicts of D-398, one per symbol.
TRIM: Final = "trim_to_boundary"  # (2)/(3) keep from the boundary onward
FROZEN_ONLY: Final = "frozen_removed"  # (1) only interior padding is cut; the history stays
CLEAN: Final = "clean"  # nothing found
EXCLUDE: Final = "exclude_boundary_unidentifiable"  # (4)


@dataclass(frozen=True, slots=True)
class SeriesVerdict:
    """What D-398 says about one symbol, with the evidence rows that produced it."""

    symbol: str
    verdict: str
    #: First date of the kept series; empty when nothing is trimmed from the front.
    boundary_date: str = ""
    #: The span dropped ahead of the boundary (old company + its padding).
    dropped_from: str = ""
    dropped_to: str = ""
    dropped_bars: int = 0
    #: Frozen bars cut out of the **kept** series (interior padding), and the stretch count
    #: over the whole series. Padding ahead of the boundary is counted in ``dropped_bars``.
    frozen_bars_cut: int = 0
    frozen_stretches: int = 0
    #: Bars and dates left after applying the verdict.
    kept_bars: int = 0
    kept_from: str = ""
    kept_to: str = ""
    #: What set the boundary: ``leading_padding``, ``stale_run`` or ``trading_gap``.
    boundary_reason: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        """The per-symbol artefact row (the evidence rows are written separately)."""
        return {
            "symbol": self.symbol,
            "verdict": self.verdict,
            "boundary_date": self.boundary_date,
            "boundary_reason": self.boundary_reason,
            "dropped_from": self.dropped_from,
            "dropped_to": self.dropped_to,
            "dropped_bars": self.dropped_bars,
            "frozen_stretches": self.frozen_stretches,
            "frozen_bars_cut": self.frozen_bars_cut,
            "kept_bars": self.kept_bars,
            "kept_from": self.kept_from,
            "kept_to": self.kept_to,
        }


def looks_like_reverse_split(ratio: float, tolerance: float = REVERSE_SPLIT_TOLERANCE) -> bool:
    """True when an **upward** level break sits within ``tolerance`` of a reverse-split ratio.

    A flag for the evidence artefact only -- it never changes a verdict. It marks the rows where
    the fingerprint cannot distinguish a re-used ticker from a reverse split the feed did not
    apply (AVGO proves those exist, D-397), which is the question P-74 asks.
    """
    return ratio > 1.0 and any(abs(ratio / r - 1.0) <= tolerance for r in REVERSE_SPLIT_RATIOS)


def frozen_stretches(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    min_sessions: int = DEFAULT_FROZEN_SESSIONS,
) -> list[tuple[int, int]]:
    """Maximal runs ``[start, end]`` (inclusive) of padded bars, at least ``min_sessions`` long.

    A bar is padded when ``high == low == close``: its true range against the previous padded bar
    is exactly zero, which is what D-398 names. **Only padded bars count towards the length** --
    the real bar before the run is not part of it even when the pad repeats its close, so a run
    that a close-only rule reports as 10 bars can be 9 here and fall below the threshold. That is
    the intended reading: nine padded sessions are nine padded sessions.

    The run's **first** padded bar is the one that sets the frozen level, so its true range
    against the last real bar may be non-zero (``PX``: 165.49 then 749 bars at 164.50). It is part
    of the pad and is removed with it.
    """
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(len(closes)):
        flat = highs[i] == lows[i] == closes[i]
        if flat and start is not None and closes[i] == closes[start]:
            continue
        if start is not None and i - start >= min_sessions:
            out.append((start, i - 1))
        start = i if flat else None
    if start is not None and len(closes) - start >= min_sessions:
        out.append((start, len(closes) - 1))
    return out


def _explained_by_split(
    dates: list[dt.date], lo: int, hi: int, split_dates: frozenset[dt.date]
) -> bool:
    return any(dates[lo] < d <= dates[hi] for d in split_dates)


def _level_break(before: float, after: float, jump_threshold: float) -> bool:
    return before > 0 and after > 0 and abs(after / before - 1.0) > jump_threshold


def analyse_series(
    symbol: str,
    dates: list[dt.date],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    jump_threshold: float,
    split_dates: frozenset[dt.date] = frozenset(),
    gap_days: int = DEFAULT_GAP_DAYS,
    frozen_sessions: int = DEFAULT_FROZEN_SESSIONS,
) -> SeriesVerdict:
    """Apply D-398 to one sorted daily series and return its verdict plus the evidence rows.

    The boundary is the first **kept** bar after the last structural break -- the end of a leading
    pad, a padded stretch across which the price level breaks, or a trading gap with the same
    level break. When no kept bar follows it, the boundary cannot be placed and the symbol is
    excluded (D-398 (4)).
    """
    n = len(closes)
    if n == 0:
        return SeriesVerdict(symbol=symbol, verdict=CLEAN)

    stretches = frozen_stretches(highs, lows, closes, frozen_sessions)
    removed = {i for start, end in stretches for i in range(start, end + 1)}
    rows: list[dict[str, Any]] = []
    breaks: list[tuple[int, str]] = []  # (index of the first bar after the break, reason)

    for start, end in stretches:
        run = end - start + 1
        leading = start == 0
        before = closes[start - 1] if start > 0 else closes[start]
        after = closes[end + 1] if end + 1 < n else float("nan")
        broke = (
            not leading
            and end + 1 < n
            and _level_break(before, after, jump_threshold)
            and not _explained_by_split(dates, start - 1, min(end + 1, n - 1), split_dates)
        )
        if leading:
            reason = "pre_listing_padding"
            breaks.append((end + 1, "leading_padding"))
        elif broke:
            reason = "stale_run"
            breaks.append((end + 1, "stale_run"))
        else:
            reason = "padding_only"
        last = after if end + 1 < n else before
        rows.append(_row(symbol, reason, dates[start], dates[end], run, before, last))

    for i in range(1, n):
        gap = (dates[i] - dates[i - 1]).days
        if gap < gap_days or not _level_break(closes[i - 1], closes[i], jump_threshold):
            continue
        if _explained_by_split(dates, i - 1, i, split_dates):
            continue  # a split inside the gap explains the level break
        rows.append(
            _row(symbol, "trading_gap", dates[i - 1], dates[i], 0, closes[i - 1], closes[i], gap)
        )
        breaks.append((i, "trading_gap"))

    rows.sort(key=lambda r: str(r["last_date_before_gap"]))
    return _verdict(symbol, dates, removed, stretches, breaks, rows, n)


def _row(
    symbol: str,
    reason: str,
    first: dt.date,
    last: dt.date,
    stale_bars: int,
    before: float,
    after: float,
    gap: int | None = None,
) -> dict[str, Any]:
    ratio = after / before if before > 0 else 0.0
    return {
        "symbol": symbol,
        "reason": reason,
        "last_date_before_gap": first.isoformat(),
        "first_date_after_gap": last.isoformat(),
        "gap_days": (last - first).days if gap is None else gap,
        "stale_bars": stale_bars,
        "close_before": round(before, 4),
        "close_after": round(after, 4),
        "ratio": round(ratio, 6),
    }


def _verdict(
    symbol: str,
    dates: list[dt.date],
    removed: set[int],
    stretches: list[tuple[int, int]],
    breaks: list[tuple[int, str]],
    rows: list[dict[str, Any]],
    n: int,
) -> SeriesVerdict:
    common: dict[str, Any] = {"symbol": symbol, "frozen_stretches": len(stretches), "rows": rows}
    if not breaks:
        kept = [i for i in range(n) if i not in removed]
        return SeriesVerdict(
            verdict=FROZEN_ONLY if removed else CLEAN,
            frozen_bars_cut=len(removed),
            kept_bars=len(kept),
            kept_from=dates[kept[0]].isoformat() if kept else "",
            kept_to=dates[kept[-1]].isoformat() if kept else "",
            **common,
        )

    boundary, reason = max(breaks, key=lambda b: b[0])
    while boundary < n and boundary in removed:
        boundary += 1  # the break lands inside another pad; the honest series starts after it
    if boundary >= n:
        # D-398 (4): the series never resumes with a real bar, so no boundary can be placed.
        return SeriesVerdict(
            verdict=EXCLUDE,
            boundary_reason=reason,
            dropped_from=dates[0].isoformat(),
            dropped_to=dates[-1].isoformat(),
            dropped_bars=n,
            frozen_bars_cut=0,
            **common,
        )
    kept = [i for i in range(boundary, n) if i not in removed]
    return SeriesVerdict(
        verdict=TRIM,
        boundary_date=dates[boundary].isoformat(),
        boundary_reason=reason,
        dropped_from=dates[0].isoformat(),
        dropped_to=dates[boundary - 1].isoformat(),
        dropped_bars=boundary,
        frozen_bars_cut=sum(1 for i in removed if i > boundary),
        kept_bars=len(kept),
        kept_from=dates[kept[0]].isoformat() if kept else "",
        kept_to=dates[kept[-1]].isoformat() if kept else "",
        **common,
    )


def relisting_candidates(
    symbol: str,
    dates: list[dt.date],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    jump_threshold: float,
    split_dates: frozenset[dt.date] = frozenset(),
    gap_days: int = DEFAULT_GAP_DAYS,
    frozen_sessions: int = DEFAULT_FROZEN_SESSIONS,
) -> list[dict[str, Any]]:
    """The evidence rows alone, for callers that do not need the verdict."""
    return analyse_series(
        symbol, dates, highs, lows, closes, jump_threshold, split_dates, gap_days, frozen_sessions
    ).rows
