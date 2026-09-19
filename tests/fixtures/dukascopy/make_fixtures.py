"""Generate tiny Dukascopy h1 bid/ask fixtures (hand-built, dukascopy-node CSV format).

Week 2024-03-08 (Fri) .. 2024-03-12 (Tue): FX closes Friday 22:00 UTC (last bar 21:00),
reopens Sunday 21:00 UTC (US DST started 2024-03-10), so the files contain a weekend gap
and the DST-shifted Sunday open. Format as written by ``dukascopy-node --format csv``:
``timestamp`` in epoch milliseconds (UTC, bar start), ``--volumes --volume-units units``.
The ask side lacks one bid bar (2024-03-11 03:00) to exercise the one-sided rule.

    uv run python tests/fixtures/dukascopy/make_fixtures.py
"""

from __future__ import annotations

import datetime as dt
import gzip
from pathlib import Path

HERE = Path(__file__).resolve().parent
MISSING_ON_ASK = dt.datetime(2024, 3, 11, 3, tzinfo=dt.UTC)


def hours() -> list[dt.datetime]:
    out = []
    t = dt.datetime(2024, 3, 8, 0, tzinfo=dt.UTC)
    end = dt.datetime(2024, 3, 12, 23, tzinfo=dt.UTC)
    while t <= end:
        friday_close = t.weekday() == 4 and t.hour >= 22
        saturday = t.weekday() == 5
        sunday_before_open = t.weekday() == 6 and t.hour < 21
        if not (friday_close or saturday or sunday_before_open):
            out.append(t)
        t += dt.timedelta(hours=1)
    return out


def side_csv(side: str) -> bytes:
    lines = ["timestamp,open,high,low,close,volume"]
    for i, t in enumerate(hours()):
        if side == "ask" and t == MISSING_ON_ASK:
            continue
        mid = 1.09 + i * 0.0001
        half = 0.00004 if side == "ask" else -0.00004
        o, c = mid + half, mid + 0.00005 + half
        h, lo = max(o, c) + 0.0002, min(o, c) - 0.0002
        vol = 1_500_000 + i * 1000 if side == "bid" else 1_400_000 + i * 1000
        ms = int(t.timestamp() * 1000)
        lines.append(f"{ms},{o:.5f},{h:.5f},{lo:.5f},{c:.5f},{vol}")
    return ("\n".join(lines) + "\n").encode()


def main() -> None:
    for side in ("bid", "ask"):
        d = HERE / "h1" / "EURUSD" / side
        d.mkdir(parents=True, exist_ok=True)
        (d / "2024-03.csv.gz").write_bytes(gzip.compress(side_csv(side), mtime=0))


if __name__ == "__main__":
    main()
