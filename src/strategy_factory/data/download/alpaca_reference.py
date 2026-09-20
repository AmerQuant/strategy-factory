"""Alpaca reference data: NYSE session calendar and symbol (name) changes (T04e).

Network fetches (run by the user's pilot script, never in tests) store the raw API answer
immutably under ``SFAC_RAW_ROOT/reference/alpaca/``; the ``build_*`` functions then derive
the config files from those raw files (pure, unit-tested):

* ``configs/calendars/nyse_sessions.csv`` -- ``date, open_local, close_local`` (America/New_York)
  for every session day; the hourly adapter takes each day's close from it.
* ``configs/universe/symbol_changes.csv`` -- ``old_symbol, new_symbol, effective_date, source``
  for the name changes that touch S&P 500 point-in-time tickers. Alpaca's ``NameChange``
  corporate action provides ``old_symbol, new_symbol, process_date`` (used as the effective
  date) plus CUSIPs. Rows of ``symbol_changes_manual.csv`` (same columns) override API rows
  with the same ``old_symbol``.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.data.download.alpaca import Credentials
from strategy_factory.data.download.ratelimit import PermanentError, TLSVerificationError
from strategy_factory.data.download.rawfiles import next_version_path, write_immutable

REF_DIR = ("reference", "alpaca")
SESSIONS_COLUMNS = ["date", "open_local", "close_local"]
CHANGES_COLUMNS = ["old_symbol", "new_symbol", "effective_date", "source"]


def _wrap_network(exc: Exception, what: str) -> Exception:
    import requests

    if isinstance(exc, requests.exceptions.SSLError):
        return TLSVerificationError(f"TLS certificate verification failed ({what}): {exc}")
    return exc


# --------------------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------------------
def fetch_calendar(creds: Credentials, start: dt.date, end: dt.date, raw_root: Path) -> Path:
    """Session calendar from the Alpaca trading API (paper endpoint first, then live)."""
    from alpaca.common.exceptions import APIError
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest

    last: Exception | None = None
    for paper in (True, False):
        client = TradingClient(creds.key, creds.secret, paper=paper, raw_data=True)
        try:
            rows = client.get_calendar(GetCalendarRequest(start=start, end=end))
        except APIError as exc:
            if exc.status_code in (401, 403):
                last = exc
                continue  # keys belong to the other environment
            raise PermanentError(f"calendar: HTTP {exc.status_code}") from exc
        except Exception as exc:
            raise _wrap_network(exc, "calendar") from exc
        payload = json.dumps(rows, indent=1, sort_keys=True).encode("utf-8")
        target = next_version_path(
            raw_root.joinpath(*REF_DIR, "calendar"), f"{dt.date.today():%Y%m%d}", ".json"
        )
        return write_immutable(
            target,
            payload,
            {
                "source": "alpaca trading API /v2/calendar",
                "endpoint": "paper" if paper else "live",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "rows": len(rows),
                "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            },
        )
    raise PermanentError(f"calendar: keys rejected by paper and live endpoints ({last})")


def build_sessions_csv(raw_calendar: Path, out: Path) -> int:
    rows = json.loads(raw_calendar.read_text(encoding="utf-8"))
    sessions = sorted((r["date"], r["open"], r["close"]) for r in rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(SESSIONS_COLUMNS)
        w.writerows(sessions)
    return len(sessions)


def load_sessions(path: Path) -> dict[dt.date, tuple[str, str]]:
    """date -> (open_local, close_local) from ``nyse_sessions.csv``."""
    if not path.is_file():
        raise ConfigError(
            "NYSE session calendar not found; run `sfac data reference alpaca-calendar`",
            config_path=path,
        )
    with path.open(encoding="utf-8", newline="") as fh:
        return {
            dt.date.fromisoformat(r["date"]): (r["open_local"], r["close_local"])
            for r in csv.DictReader(fh)
        }


# --------------------------------------------------------------------------------------
# Symbol (name) changes
# --------------------------------------------------------------------------------------
def fetch_name_changes(creds: Credentials, start: dt.date, end: dt.date, raw_root: Path) -> Path:
    """All NAME_CHANGE corporate actions in [start, end], fetched year by year."""
    from alpaca.common.exceptions import APIError
    from alpaca.data.enums import CorporateActionsType
    from alpaca.data.historical.corporate_actions import CorporateActionsClient
    from alpaca.data.requests import CorporateActionsRequest

    client = CorporateActionsClient(creds.key, creds.secret, raw_data=True)
    rows: list[dict[str, Any]] = []
    for year in range(start.year, end.year + 1):
        lo = max(start, dt.date(year, 1, 1))
        hi = min(end, dt.date(year, 12, 31))
        req = CorporateActionsRequest(types=[CorporateActionsType.NAME_CHANGE], start=lo, end=hi)
        try:
            raw = client.get_corporate_actions(req)
        except APIError as exc:
            raise PermanentError(f"corporate actions: HTTP {exc.status_code}") from exc
        except Exception as exc:
            raise _wrap_network(exc, "corporate actions") from exc
        rows += list(dict(raw).get("name_changes", []))
    payload = json.dumps(rows, indent=1, sort_keys=True, default=str).encode("utf-8")
    target = next_version_path(
        raw_root.joinpath(*REF_DIR, "corporate_actions"),
        f"name_changes_{dt.date.today():%Y%m%d}",
        ".json",
    )
    return write_immutable(
        target,
        payload,
        {
            "source": "alpaca market data API /v1/corporate-actions, types=name_change",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": len(rows),
            "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        },
    )


def read_changes_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def build_symbol_changes(
    raw_name_changes: Path, pit_symbols: Iterable[str], manual: Path, out: Path
) -> int:
    """Name changes reachable from the PIT tickers (following chains), manual rows winning."""
    api = [
        {
            "old_symbol": r["old_symbol"],
            "new_symbol": r["new_symbol"],
            "effective_date": str(r["process_date"])[:10],
            "source": "alpaca_corporate_actions",
        }
        for r in json.loads(raw_name_changes.read_text(encoding="utf-8"))
        if r.get("old_symbol") and r.get("new_symbol") and r["old_symbol"] != r["new_symbol"]
    ]
    manual_rows = [dict(r, source=r.get("source") or "manual") for r in read_changes_csv(manual)]
    overridden = {r["old_symbol"] for r in manual_rows}
    by_old: dict[str, list[dict[str, str]]] = {}
    for r in [r for r in api if r["old_symbol"] not in overridden] + manual_rows:
        by_old.setdefault(r["old_symbol"], []).append(r)
    selected: dict[tuple[str, str, str], dict[str, str]] = {}
    frontier = list(dict.fromkeys(pit_symbols))
    seen: set[str] = set()
    while frontier:
        sym = frontier.pop()
        if sym in seen:
            continue
        seen.add(sym)
        for r in by_old.get(sym, []):
            selected[(r["old_symbol"], r["new_symbol"], r["effective_date"])] = r
            frontier.append(r["new_symbol"])
    rows = sorted(selected.values(), key=lambda r: (r["effective_date"], r["old_symbol"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=CHANGES_COLUMNS, lineterminator="\n", extrasaction="ignore"
        )
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def current_symbol(
    pit_symbol: str, changes: list[dict[str, str]], since: dt.date | None = None
) -> str:
    """Follow renames of ``pit_symbol`` (effective on/after ``since``) to the latest symbol."""
    by_old: dict[str, list[dict[str, str]]] = {}
    for r in changes:
        by_old.setdefault(r["old_symbol"], []).append(r)
    sym, when, hops = pit_symbol, since or dt.date.min, 0
    while True:
        nxt = [r for r in by_old.get(sym, []) if dt.date.fromisoformat(r["effective_date"]) >= when]
        if not nxt:
            return sym
        step = min(nxt, key=lambda r: r["effective_date"])
        sym, when = step["new_symbol"], dt.date.fromisoformat(step["effective_date"])
        hops += 1
        if hops > 20:
            raise DataError(
                f"symbol-change chain too long or cyclic from {pit_symbol}", symbol=pit_symbol
            )
