"""Generate the Alpaca fixture responses (run once; output is committed).

These are HAND-BUILT responses in the shape alpaca-py returns with ``raw_data=True``
(``{symbol: [{"t", "o", "h", "l", "c", "v", "n", "vw"}, ...]}``); they were not recorded
from the live API (no API key was available when T04a was built). Prices are plausible,
split-adjusted values; timestamps follow Alpaca's conventions (daily bars at midnight
America/New_York in UTC, hourly bars at the hour start in UTC, extended hours included).

    uv run python tests/fixtures/alpaca/make_fixtures.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent


def bar(t: dt.datetime, close: float, volume: float, step: float = 0.5) -> dict[str, object]:
    o = round(close - step / 2, 2)
    return {
        "t": t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "o": o,
        "h": round(max(o, close) + step, 2),
        "l": round(min(o, close) - step, 2),
        "c": close,
        "v": volume,
        "n": int(volume // 100),
        "vw": round((o + close) / 2, 4),
    }


def daily(symbol_closes: dict[dt.date, float]) -> list[dict[str, object]]:
    return [
        bar(dt.datetime.combine(d, dt.time(0), NY), c, 1_000_000 + i * 1000)
        for i, (d, c) in enumerate(sorted(symbol_closes.items()))
    ]


def hourly(day: dt.date, hours: range, base: float) -> list[dict[str, object]]:
    out = []
    for h in hours:
        extended = h < 9 or h >= 16
        out.append(
            bar(
                dt.datetime.combine(day, dt.time(h), NY),
                round(base + h * 0.1, 2),
                500 if extended else 50_000,
                0.2,
            )
        )
    return out


def main() -> None:
    aapl = {
        dt.date(2020, 8, 25): 124.83,
        dt.date(2020, 8, 26): 126.52,
        dt.date(2020, 8, 27): 125.01,
        dt.date(2020, 8, 28): 124.81,
        dt.date(2020, 8, 31): 129.04,
        dt.date(2020, 9, 1): 134.18,
        dt.date(2020, 9, 2): 131.40,
        # DST switch (EDT -> EST on 2020-11-01)
        dt.date(2020, 10, 29): 115.32,
        dt.date(2020, 10, 30): 108.86,
        dt.date(2020, 11, 2): 108.77,
        dt.date(2020, 11, 3): 110.44,
    }
    tsla = {
        dt.date(2020, 8, 27): 447.75,
        dt.date(2020, 8, 28): 442.68,
        dt.date(2020, 8, 31): 498.32,
        dt.date(2020, 9, 1): 475.05,
    }
    (HERE / "daily_2020.json").write_text(
        json.dumps({"AAPL": daily(aapl), "TSLA": daily(tsla)}, indent=1) + "\n", encoding="utf-8"
    )
    hourly_aapl = (
        hourly(dt.date(2024, 3, 8), range(4, 20), 170.0)  # EST, full extended session 04:00-19:00
        + hourly(dt.date(2024, 3, 11), range(4, 20), 172.0)  # EDT after the DST switch
        + hourly(dt.date(2024, 11, 29), range(4, 18), 237.0)  # half day, close 13:00
    )
    (HERE / "hourly_2024.json").write_text(
        json.dumps({"AAPL": hourly_aapl}, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
