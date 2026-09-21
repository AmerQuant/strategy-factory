"""D-700: settle a re-used ticker by the **company name**, not the price series (T04k).

D-399 asked the all-adjusted MS-US-1D series to tell a re-use from a halt. T04k measured that it
cannot: MS-US-1D is keyed by ticker exactly like the Alpaca feed, so a re-used ticker splices
identically in both. D-700 moves the discriminator to evidence that does not come from prices:

* the **Alpaca assets file** -- one row per ticker, the name of the security that holds it today
  (33,276 rows including inactive, the source T06b used for the Moneta mapping);
* the **`NAME_CHANGE` feed** -- ``old_symbol -> new_symbol`` on a ``process_date``.

The assets file alone carries **one** name per ticker: today's holder. The name of the company
that held the ticker **before** the break exists only when that company **renamed away** from it
-- its current name is then the assets file's name for the rename's destination. So:

``re_use``
    a rename **away** from the ticker falls inside the break window, and the destination's name
    and the ticker's current name are **different strings**. Trim at the boundary (D-398 (2)).
``same_company``
    the two names are **identical**: a rename of the same company. Not a re-use; keep everything.
``one_name``
    no rename away from the ticker, or one of the two names is missing from the assets file. The
    file knows only one company, so nothing is settled: keep the full history and list the symbol.
``disagrees``
    a rename away exists but outside the window: the name evidence and the frozen-stretch boundary
    tell different stories. Keep the full history and list the symbol (D-700 (2)).
``ambiguous``
    more than one rename away inside the window. Keep the full history and list the symbol.

**Matching is exact identity** (D-700 (4)): only surrounding whitespace is stripped. The question
is whether the feed calls it a different company, not how alike two names look. Exact identity
errs towards *different*, which is the direction that trims, so a pair that differs only in case,
punctuation or spacing is marked ``near_identical`` -- the verdict is unchanged, but the review
lists every such trim so none rests on a full stop unnoticed.

A rename **into** the ticker (``COG -> CTRA``) says who arrived, not who left, so it is recorded
in the evidence but never decides on its own.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import polars as pl

RE_USE: Final = "re_use"
SAME_COMPANY: Final = "same_company"
ONE_NAME: Final = "one_name"
DISAGREES: Final = "disagrees"
AMBIGUOUS: Final = "ambiguous"

_NOISE = re.compile(r"[\W_]+")


@dataclass(frozen=True, slots=True)
class NameChange:
    """One ``NAME_CHANGE`` corporate action: the ticker ``old_symbol`` became ``new_symbol``."""

    old_symbol: str
    new_symbol: str
    process_date: dt.date


@dataclass(frozen=True, slots=True)
class NameVerdict:
    """What the company names say about one boundary."""

    symbol: str
    verdict: str
    evidence: str
    name_before: str = ""
    name_after: str = ""
    near_identical: bool = False

    @property
    def may_trim(self) -> bool:
        return self.verdict == RE_USE


def _near(a: str, b: str) -> bool:
    """Equal after dropping case, punctuation and spacing -- a *flag*, never a verdict."""
    return _NOISE.sub("", a).casefold() == _NOISE.sub("", b).casefold()


def settle_by_name(
    symbol: str,
    break_start: dt.date,
    boundary: dt.date,
    assets: Mapping[str, str],
    changes: Iterable[NameChange],
    window_days: int,
) -> NameVerdict:
    """Classify one boundary by the names the assets file gives either side of it.

    ``break_start`` is where the break begins in the series (the last real bar before a gap, or
    the first padded bar of a frozen stretch); ``boundary`` is the first bar of the new holder. A
    rename **away** from ``symbol`` agrees with the boundary when its ``process_date`` lies in
    ``[break_start - window_days, boundary]``.
    """
    rows = list(changes)
    arrived = [c for c in rows if c.new_symbol == symbol and c.old_symbol != symbol]
    arrival_note = "".join(f"; arrived from {c.old_symbol} on {c.process_date}" for c in arrived)
    after = assets.get(symbol, "").strip()
    away = [c for c in rows if c.old_symbol == symbol and c.new_symbol != symbol]
    if not away:
        return NameVerdict(
            symbol,
            ONE_NAME,
            f"no rename away from {symbol}; only today's holder is known" + arrival_note,
            name_after=after,
        )
    lo = break_start - dt.timedelta(days=window_days)
    inside = [c for c in away if lo <= c.process_date <= boundary]
    if not inside:
        dates = ", ".join(f"{c.old_symbol}->{c.new_symbol} {c.process_date}" for c in away)
        return NameVerdict(
            symbol,
            DISAGREES,
            f"rename away ({dates}) outside {lo}..{boundary}" + arrival_note,
            name_after=after,
        )
    if len(inside) > 1:
        dates = ", ".join(f"{c.old_symbol}->{c.new_symbol} {c.process_date}" for c in inside)
        return NameVerdict(
            symbol,
            AMBIGUOUS,
            f"{len(inside)} renames away inside the window: {dates}" + arrival_note,
            name_after=after,
        )
    change = inside[0]
    before = assets.get(change.new_symbol, "").strip()
    if not after or not before:
        missing = symbol if not after else change.new_symbol
        return NameVerdict(
            symbol,
            ONE_NAME,
            f"{missing} is not in the assets file; {symbol}->{change.new_symbol} "
            f"{change.process_date}" + arrival_note,
            name_before=before,
            name_after=after,
        )
    evidence = (
        f"{symbol}->{change.new_symbol} {change.process_date}: before '{before}', "
        f"after '{after}'" + arrival_note
    )
    if before == after:
        return NameVerdict(symbol, SAME_COMPANY, evidence, before, after)
    return NameVerdict(symbol, RE_USE, evidence, before, after, near_identical=_near(before, after))


def load_assets(path: Path) -> dict[str, str]:
    """``symbol -> name`` from the Alpaca assets CSV (one row per ticker, D-341)."""
    frame = pl.read_csv(path, columns=["symbol", "name"], infer_schema_length=None)
    return {s: (n or "") for s, n in frame.iter_rows()}


def load_name_changes(path: Path) -> list[NameChange]:
    """Every ``NAME_CHANGE`` row of the raw corporate-actions JSON (a list of objects)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: list[NameChange] = []
    for r in rows:
        old, new, day = r.get("old_symbol"), r.get("new_symbol"), r.get("process_date")
        if old and new and day:
            out.append(NameChange(old, new, dt.date.fromisoformat(day)))
    return out


def changes_by_symbol(changes: Iterable[NameChange]) -> dict[str, list[NameChange]]:
    """Index the feed so each symbol sees the renames away from it and into it."""
    index: dict[str, list[NameChange]] = {}
    for c in changes:
        index.setdefault(c.old_symbol, []).append(c)
        if c.new_symbol != c.old_symbol:
            index.setdefault(c.new_symbol, []).append(c)
    return index
