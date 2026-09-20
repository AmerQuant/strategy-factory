"""Detect a ticker that was re-used by another company (T04i, D-383).

Alpaca serves whatever currently trades under a symbol. When a ticker is retired and later
re-assigned, the series it returns is **two different companies spliced together**: the old
company up to its delisting, then a gap, then the new one. `FB` is the worked example -- Meta to
2022, then an unrelated instrument at 42-46 USD in 2026.

There are two fingerprints, and a real universe has both.

``trading_gap``
    no daily bar for at least ``gap_days`` calendar days, the closes on either side differ by
    more than ``jump_threshold`` (the threshold the split check uses), and no known split falls
    inside the gap. `FB` is this shape: Meta to 2022-06-08, then 1,114 days of nothing, then an
    unrelated instrument at 39.91.

``stale_run``
    no gap at all, because the feed **pads the dead stretch with the last price**, and the level
    breaks across the frozen stretch. `PX` is this shape: Praxair 2016-2018 (96-169), then
    **every bar of 2019 and 2020 is exactly 164.50**, then RPC Inc. from late 2021 at 12-15,
    identical to `RPC` day for day. A gap test cannot see it, and it is the more dangerous of the
    two: a frozen price is silently tradeable, and every indicator over it is meaningless.

Both require the **same level break** (``jump_threshold``), because that is what D-383's "re-used
by another company" means. A frozen stretch with **no** level break is a different defect -- a
dead listing padded with its last price, not a new company -- and is reported as

``padding_only``
    **not** a D-383 candidate. `FI` is this shape: 315 frozen bars from 2.94 to 3.15. It is
    already a `stale_prices` finding of the T05 quality checks (F-0.1.6); it is listed here so the
    two can be told apart rather than silently merged.

``pre_listing_padding``
    a frozen stretch at the **very start** of the series: the company had not listed yet and the
    feed pads backwards from its first real price. **Not** a re-used ticker and **not** a reason
    to exclude anything -- `MBLY` (1,297 padded bars before the 2022 IPO), `SNOW`, `GRAB`, `SE`
    and `DOW` are all live, broker-tradable companies. Without this case the rule would drop
    Moneta mapping targets, which D-388 forbids. The padded bars are still unusable, so the
    history simply starts at the first real bar.

D-383 excludes a re-used ticker "for now", so the output is a **candidate list with its
evidence**; the supervisor confirms rows into `configs/universe/us_equity_daily_excluded.csv`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

#: A break this far apart in time is a relisting, not a holiday or a trading halt.
DEFAULT_GAP_DAYS: Final = 200
#: Identical closes for this many trading days in a row is a padded dead stretch, not a quiet
#: market: even the most illiquid listed name prints a different close within a quarter.
DEFAULT_STALE_DAYS: Final = 60


def relisting_candidates(
    symbol: str,
    dates: list[dt.date],
    closes: list[float],
    jump_threshold: float,
    split_dates: frozenset[dt.date] = frozenset(),
    gap_days: int = DEFAULT_GAP_DAYS,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> list[dict[str, Any]]:
    """One row per gap or frozen stretch that looks like a re-used ticker (``dates`` sorted)."""
    out: list[dict[str, Any]] = _gap_candidates(
        symbol, dates, closes, jump_threshold, split_dates, gap_days
    )
    out += _stale_candidates(symbol, dates, closes, stale_days, jump_threshold)
    return sorted(out, key=lambda r: str(r["last_date_before_gap"]))


def _gap_candidates(
    symbol: str,
    dates: list[dt.date],
    closes: list[float],
    jump_threshold: float,
    split_dates: frozenset[dt.date],
    gap_days: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap < gap_days:
            continue
        before, after = closes[i - 1], closes[i]
        if before <= 0 or after <= 0:
            continue
        ratio = after / before
        if abs(ratio - 1.0) <= jump_threshold:
            continue
        if any(dates[i - 1] < d <= dates[i] for d in split_dates):
            continue  # a split inside the gap explains the level break
        out.append(
            {
                "symbol": symbol,
                "reason": "trading_gap",
                "last_date_before_gap": dates[i - 1].isoformat(),
                "first_date_after_gap": dates[i].isoformat(),
                "gap_days": gap,
                "stale_bars": 0,
                "close_before": round(before, 4),
                "close_after": round(after, 4),
                "ratio": round(ratio, 6),
            }
        )
    return out


def _stale_candidates(
    symbol: str,
    dates: list[dt.date],
    closes: list[float],
    stale_days: int,
    jump_threshold: float,
) -> list[dict[str, Any]]:
    """Maximal runs of identical closes at least ``stale_days`` trading days long.

    A run whose level breaks by more than ``jump_threshold`` is a ``stale_run`` (a D-383
    candidate); one that resumes at about the same price is ``padding_only``.
    """
    out: list[dict[str, Any]] = []
    start = 0
    for i in range(1, len(closes) + 1):
        if i < len(closes) and closes[i] == closes[start]:
            continue
        run = i - start
        if run >= stale_days:
            before = closes[start - 1] if start > 0 else closes[start]
            after = closes[i] if i < len(closes) else closes[-1]
            ratio = after / before if before > 0 else 0.0
            broke = before > 0 and abs(ratio - 1.0) > jump_threshold
            if start == 0:
                reason = "pre_listing_padding"  # the feed pads backwards from the first real bar
            elif broke:
                reason = "stale_run"
            else:
                reason = "padding_only"
            out.append(
                {
                    "symbol": symbol,
                    "reason": reason,
                    "last_date_before_gap": dates[start].isoformat(),
                    "first_date_after_gap": dates[i - 1].isoformat(),
                    "gap_days": (dates[i - 1] - dates[start]).days,
                    "stale_bars": run,
                    "close_before": round(before, 4),
                    "close_after": round(after, 4),
                    "ratio": round(ratio, 6),
                }
            )
        start = i
    return out
