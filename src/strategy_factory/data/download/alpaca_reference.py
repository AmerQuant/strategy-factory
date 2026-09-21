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

**Rejections (D-383).** A manual row with an **empty** ``new_symbol`` rejects the API's rename
for that ``old_symbol``: the feed reports a name change, but the two tickers are not the same
series -- the old ticker was re-used by another company, or the destination has no data. A
rejected hop is dropped from the chain graph and is **not** written to ``symbol_changes.csv``,
so the old symbol keeps its own universe row. The reason belongs in the manual row's ``source``
(``rejected: <why>``). The evidence is in ``docs/reviews/T04f_symbol_changes_accounting.csv``.

A rejection with an ``effective_date`` rejects **only the hop with that date**, so a ticker the
feed renames twice keeps the hops that were not rejected; an empty ``effective_date`` rejects
every hop out of that symbol. A non-empty ``new_symbol`` is a re-target and still replaces all
of the feed's rows for that ``old_symbol``.
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
        req = CorporateActionsRequest(
            types=[CorporateActionsType.NAME_CHANGE], start=lo, end=hi, limit=None
        )
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


#: T04l (D-710): every corporate-action type the endpoint offers except ``name_change`` (fetched
#: by T04f). Each carries a CUSIP: the mergers, redemptions and worthless removals show a security
#: ceasing to exist; dividends, splits, spin-offs and rights show which security held a ticker on a
#: date. They are identity evidence for re-used tickers, not price data (D-030 does not apply).
#: The endpoint's page size; a year that returns an exact multiple of it is suspect.
PAGE_SIZE = 1000
EVIDENCE_ACTION_TYPES = (
    "cash_merger",
    "stock_merger",
    "stock_and_cash_merger",
    "redemption",
    "worthless_removal",
    "spin_off",
    "unit_split",
    "reverse_split",
    "forward_split",
    "cash_dividend",
    "stock_dividend",
    "rights_distribution",
)


def fetch_corporate_actions(
    creds: Credentials,
    types: Iterable[str],
    start: dt.date,
    end: dt.date,
    raw_root: Path,
    client: Any = None,
) -> list[Path]:
    """Corporate actions of ``types`` in [start, end], fetched year by year and written as one
    immutable JSON per answer key (``<key>_<YYYYMMDD>.json``, e.g. ``cash_mergers_20260921.json``)
    with a manifest. ``client`` is injectable for tests; by default the alpaca-py client.

    **No row cap.** alpaca-py's ``CorporateActionsRequest.limit`` defaults to 1,000 and is a cap on
    the **total** rows, not a page size: the first run (2026-09-21) got exactly 1,000 rows per year
    and lost the rest, alphabetically. The request sets ``limit=None`` so the client follows
    ``next_page_token`` to the end; the manifest records the rows per year, and a year whose count
    is a whole multiple of the page size is flagged ``suspect_truncation`` for the reader."""
    from alpaca.data.enums import CorporateActionsType
    from alpaca.data.requests import CorporateActionsRequest

    wanted = list(types)
    try:
        enums = [CorporateActionsType(t) for t in wanted]
    except ValueError as exc:
        known = ", ".join(t.value for t in CorporateActionsType)
        raise ConfigError(f"unknown corporate-action type ({exc}); known: {known}") from exc
    if client is None:
        from alpaca.data.historical.corporate_actions import CorporateActionsClient

        client = CorporateActionsClient(creds.key, creds.secret, raw_data=True)
    by_key: dict[str, list[dict[str, Any]]] = {}
    per_year: dict[str, int] = {}
    for year in range(start.year, end.year + 1):
        lo = max(start, dt.date(year, 1, 1))
        hi = min(end, dt.date(year, 12, 31))
        req = CorporateActionsRequest(types=enums, start=lo, end=hi, limit=None)
        try:
            raw = client.get_corporate_actions(req)
        except TLSVerificationError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is not None:
                raise PermanentError(f"corporate actions: HTTP {status}") from exc
            raise _wrap_network(exc, "corporate actions") from exc
        got = 0
        for key, rows in dict(raw).items():
            if isinstance(rows, list):
                by_key.setdefault(key, []).extend(rows)
                got += len(rows)
        per_year[str(year)] = got
    out_dir = raw_root.joinpath(*REF_DIR, "corporate_actions")
    stamp = f"{dt.date.today():%Y%m%d}"
    written: list[Path] = []
    for key in sorted(by_key):
        rows = by_key[key]
        payload = json.dumps(rows, indent=1, sort_keys=True, default=str).encode("utf-8")
        target = next_version_path(out_dir, f"{key}_{stamp}", ".json")
        written.append(
            write_immutable(
                target,
                payload,
                {
                    "source": "alpaca market data API /v1/corporate-actions, types="
                    + ",".join(wanted),
                    "answer_key": key,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "rows": len(rows),
                    "rows_per_year_all_types": per_year,
                    "suspect_truncation": sorted(
                        y for y, n in per_year.items() if n and n % PAGE_SIZE == 0
                    ),
                    "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                },
            )
        )
    return written


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
    # D-383: a manual row with an empty new_symbol rejects a hop; it never reaches the graph
    retargets = [r for r in manual_rows if r["new_symbol"]]
    rejected_all = {
        r["old_symbol"] for r in manual_rows if not r["new_symbol"] and not r["effective_date"]
    }
    rejected_hops = {
        (r["old_symbol"], r["effective_date"])
        for r in manual_rows
        if not r["new_symbol"] and r["effective_date"]
    }
    retargeted = {r["old_symbol"] for r in retargets}
    kept_api = [
        r
        for r in api
        if r["old_symbol"] not in retargeted
        and r["old_symbol"] not in rejected_all
        and (r["old_symbol"], r["effective_date"]) not in rejected_hops
    ]
    by_old: dict[str, list[dict[str, str]]] = {}
    for r in kept_api + retargets:
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
        nxt = [
            r
            for r in by_old.get(sym, [])
            if r["new_symbol"] and dt.date.fromisoformat(r["effective_date"]) >= when
        ]
        if not nxt:
            return sym
        step = min(nxt, key=lambda r: r["effective_date"])
        sym, when = step["new_symbol"], dt.date.fromisoformat(step["effective_date"])
        hops += 1
        if hops > 20:
            raise DataError(
                f"symbol-change chain too long or cyclic from {pit_symbol}", symbol=pit_symbol
            )
