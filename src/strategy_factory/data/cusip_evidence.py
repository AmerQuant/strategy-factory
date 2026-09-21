"""F-0.1.2 (T04l, D-705, D-709, D-712): who held a ticker on each side of a break, by CUSIP.

The evidence is the Alpaca corporate-actions feed (D-710; the **latest version** of each answer key
under ``SFAC_RAW_ROOT/reference/alpaca/corporate_actions/``). Every row that names a ticker **with a
CUSIP** is a dated statement about the security behind it; a row without one is no evidence.

**Roles.** ``id`` -- the security held the ticker on that date (dividends, splits, spin-off and
rights sources, merger acquirers); ``id_before`` -- a reverse split's old CUSIP held it until that
date; ``into`` / ``away`` -- a rename into / away from the ticker; ``ceased`` -- the security ended
(an acquiree of a merger, a worthless removal, a redemption).

**Sides of a break** (``resumes`` = the first bar after it), with the two rules of **D-712** -- the
feed is not point-in-time (about 5 % of rows sit under a ticker the security took later):

1. **Re-keyed rows:** a row of a CUSIP under the ticker, dated before that CUSIP renamed **into**
   the ticker, is not evidence of who held the ticker then -- dropped.
2. **The arriving holder:** a rename into the ticker, or any ``id`` row, dated within
   ``window_days`` before the resumption counts on the **after** side; a rename away and a
   cessation stay on the before side until the resumption.

``CTRA`` (D-712's worked example): without rule 1 Cabot's 2021 dividends -- filed under ``CTRA``
before Cabot renamed into it -- put Coterra's CUSIP on the before side and the break read *same
CUSIP*, a spliced series called clean. **Absence is never evidence**: no row means ``none``, never
"no merger". Pure: no file access except :func:`load_events`.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from strategy_factory.data.download.alpaca_reference import action_date, latest_action_files

#: The issuer part of a CUSIP: its first six characters (a property of the CUSIP format).
ISSUER_LEN: Final = 6

BOTH: Final = "both"
BEFORE_ONLY: Final = "before_only"
AFTER_ONLY: Final = "after_only"
NONE: Final = "none"
SAME_CUSIP: Final = "same_cusip"
SAME_ISSUER: Final = "same_issuer"
DIFFERENT_ISSUER: Final = "different_issuer"

#: (symbol field, cusip field, role) per answer key.
FIELDS: Final[dict[str, tuple[tuple[str, str, str], ...]]] = {
    "name_changes": (("old_symbol", "old_cusip", "away"), ("new_symbol", "new_cusip", "into")),
    "cash_dividends": (("symbol", "cusip", "id"),),
    "stock_dividends": (("symbol", "cusip", "id"),),
    "forward_splits": (("symbol", "cusip", "id"),),
    "reverse_splits": (("symbol", "old_cusip", "id_before"), ("symbol", "new_cusip", "id")),
    "unit_splits": (
        ("old_symbol", "old_cusip", "away"),
        ("new_symbol", "new_cusip", "into"),
        ("alternate_symbol", "alternate_cusip", "into"),
    ),
    "spin_offs": (("source_symbol", "source_cusip", "id"), ("new_symbol", "new_cusip", "into")),
    "rights_distributions": (("source_symbol", "source_cusip", "id"),),
    "cash_mergers": (
        ("acquiree_symbol", "acquiree_cusip", "ceased"),
        ("acquirer_symbol", "acquirer_cusip", "id"),
    ),
    "stock_mergers": (
        ("acquiree_symbol", "acquiree_cusip", "ceased"),
        ("acquirer_symbol", "acquirer_cusip", "id"),
    ),
    "stock_and_cash_mergers": (
        ("acquiree_symbol", "acquiree_cusip", "ceased"),
        ("acquirer_symbol", "acquirer_cusip", "id"),
    ),
    "worthless_removals": (("symbol", "cusip", "ceased"),),
    "redemptions": (("symbol", "cusip", "ceased"),),
}


@dataclass(frozen=True, slots=True)
class Event:
    """One dated CUSIP statement about a ticker."""

    type: str
    role: str
    cusip: str
    date: str  # ISO date: string comparison is date order


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the CUSIPs say about one break."""

    coverage: str
    relation: str | None
    before: tuple[str, ...]
    after: tuple[str, ...]
    types_before: tuple[str, ...]
    types_after: tuple[str, ...]
    ceased_before: tuple[str, ...]
    dropped_rekeyed: int

    def describe(self) -> str:
        return (
            f"CUSIP before {'|'.join(self.before) or '-'} ({'|'.join(self.types_before) or '-'}), "
            f"after {'|'.join(self.after) or '-'} ({'|'.join(self.types_after) or '-'})"
            + (f", ceased before: {'|'.join(self.ceased_before)}" if self.ceased_before else "")
            + (f", {self.dropped_rekeyed} re-keyed row(s) dropped" if self.dropped_rekeyed else "")
        )


def load_events(folder: Path) -> tuple[dict[str, list[Event]], dict[str, int]]:
    """``symbol -> events`` from the latest file of each answer key; and, per answer key, the
    number of symbol fields that came without a CUSIP (not evidence, counted apart)."""
    by_symbol: dict[str, list[Event]] = defaultdict(list)
    no_cusip: dict[str, int] = defaultdict(int)
    for key, path in latest_action_files(folder).items():
        spec = FIELDS.get(key)
        if spec is None:
            continue
        rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            date = action_date(row)
            for sym_f, cus_f, role in spec:
                sym, cus = row.get(sym_f), row.get(cus_f)
                if not sym:
                    continue
                if not cus:
                    no_cusip[key] += 1
                    continue
                by_symbol[str(sym)].append(Event(key, role, str(cus), date))
    return dict(by_symbol), dict(no_cusip)


def classify(events: list[Event], resumes: dt.date, window_days: int) -> Evidence:
    """The CUSIPs on each side of a break that resumes on ``resumes`` (D-709, D-712)."""
    r = resumes.isoformat()
    arriving = (resumes - dt.timedelta(days=window_days)).isoformat()
    arrived: dict[str, str] = {}
    for e in events:
        if e.role == "into":
            arrived[e.cusip] = min(arrived.get(e.cusip, e.date), e.date)
    before: dict[str, set[str]] = defaultdict(set)
    after: dict[str, set[str]] = defaultdict(set)
    ceased: set[str] = set()
    dropped = 0
    for e in events:
        if e.role not in ("into", "away") and e.cusip in arrived and e.date < arrived[e.cusip]:
            dropped += 1  # D-712 rule 1: filed under a ticker the security took later
            continue
        if e.role in ("into", "id"):
            side = after if e.date >= arriving else before  # D-712 rule 2
        elif e.role == "id_before":
            side = before if e.date <= r else after
        else:  # away, ceased: the old holder leaving
            side = before if e.date < r else after
        side[e.cusip].add(e.type)
        if e.role == "ceased" and e.date < r:
            ceased.add(e.type)
    b, a = set(before), set(after)
    coverage = BOTH if b and a else BEFORE_ONLY if b else AFTER_ONLY if a else NONE
    relation = None
    if coverage == BOTH:
        if b & a:
            relation = SAME_CUSIP
        elif {x[:ISSUER_LEN] for x in b} & {x[:ISSUER_LEN] for x in a}:
            relation = SAME_ISSUER
        else:
            relation = DIFFERENT_ISSUER
    return Evidence(
        coverage,
        relation,
        tuple(sorted(b)),
        tuple(sorted(a)),
        tuple(sorted({t for ts in before.values() for t in ts})),
        tuple(sorted({t for ts in after.values() for t in ts})),
        tuple(sorted(ceased)),
        dropped,
    )
