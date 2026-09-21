"""T04h: the evidence that the 1H snapshots are sound, read from the **written snapshots**.

Local only -- reads `SFAC_DATA_ROOT` and the committed calendar; writes CSVs under `docs/reviews/`;
changes nothing in the store::

    uv run python scripts/analysis/T04h_verify.py

* the New-York hours kept (must be exactly 09..15, D-023);
* bars per session against `configs/calendars/nyse_sessions.csv` (7 regular, 4 on a 13:00 close)
  and **every** session with fewer bars than its calendar implies -> `T04h_short_sessions.csv`;
* bars outside the session (before 09:00 or ending after the close);
* every universe symbol has a 1H reference, `hash_version = 2`; no snapshot for a dropped old
  ticker (T04f); `META` records `FB`;
* the hourly wick count per symbol under the D-703/D-706 rule (P-81 (c), report only)
  -> `T04h_hourly_wick_flags.csv`;
* the quality aggregate of the 1H references (after `sfac data quality --timeframe 1H`).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.clean_daily import wick_outliers
from strategy_factory.data.config import load_alpaca_config, load_quality_config
from strategy_factory.data.daily_session import expected_bars
from strategy_factory.data.download.alpaca_reference import load_sessions
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.store import SnapshotStore

OUT = Path("docs") / "reviews"
UNIVERSE = Path("configs") / "universe" / "us_equity_hourly.csv"
DROPPED = OUT / "T04f_symbol_changes_accounting.csv"


def _dropped_old_tickers() -> list[str]:
    """The old tickers T04f removed from the hourly universe (D-383)."""
    if not DROPPED.is_file():
        return []
    with DROPPED.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return sorted({r["removed_symbol"] for r in rows if r["action"].startswith("exclude old row")})


def main() -> None:
    store, catalog = SnapshotStore(), Catalog()
    alpaca, quality = load_alpaca_config(), load_quality_config()
    tz = alpaca.hourly_session.timezone
    sessions = load_sessions(alpaca.hourly_session.sessions_file)
    expected = expected_bars(sessions, alpaca.hourly_session.first_bar)
    close_of = pl.DataFrame(
        {"session_date": list(sessions), "close_local": [c for _, c in sessions.values()]},
        schema={"session_date": pl.Date(), "close_local": pl.Utf8()},
    )
    universe = pl.read_csv(UNIVERSE, infer_schema_length=None)
    table = catalog.table().filter((pl.col("source") == "alpaca") & (pl.col("timeframe") == "1H"))
    refs = table.filter(pl.col("is_reference"))
    OUT.mkdir(parents=True, exist_ok=True)

    hours: dict[int, int] = {}
    per_day: list[pl.DataFrame] = []
    outside = 0
    wick_rows: list[dict[str, object]] = []
    for r in refs.iter_rows(named=True):
        bars = store.read_snapshot("alpaca", r["symbol"], "1H", r["snapshot_hash"])
        ny = bars.with_columns(pl.col("ts").dt.convert_time_zone(tz).alias("ny")).with_columns(
            pl.col("ny").dt.hour().alias("hour"), pl.col("ny").dt.date().alias("session_date")
        )
        for h, n in ny.group_by("hour").len().rows():
            hours[h] = hours.get(h, 0) + n
        # a bar is outside when it starts before the first bar or ends after the session close
        late = ny.join(close_of, on="session_date", how="left").filter(
            pl.col("close_local").is_null()
            | (pl.col("hour") < int(alpaca.hourly_session.first_bar[:2]))
            | (
                (pl.col("hour") + 1) * 60
                > pl.col("close_local").str.slice(0, 2).cast(pl.Int32) * 60
                + pl.col("close_local").str.slice(3, 2).cast(pl.Int32)
            )
        )
        outside += late.height
        per_day.append(
            ny.group_by("session_date")
            .len("bars")
            .with_columns(pl.lit(r["symbol"]).alias("symbol"))
        )
        w = wick_outliers(
            bars.select("ts", "open", "high", "low", "close"), quality.daily_wick_outlier
        )
        flagged = w.filter(pl.col("flag_high") | pl.col("flag_low")).height
        if flagged:
            wick_rows.append({"symbol": r["symbol"], "bars": bars.height, "flagged": flagged})

    days = pl.concat(per_day).join(expected, on="session_date", how="left")
    dist = days.group_by("expected_bars", "bars").len().sort("expected_bars", "bars")
    short = days.filter(pl.col("bars") < pl.col("expected_bars")).sort("symbol", "session_date")
    short.select("symbol", "session_date", "bars", "expected_bars").write_csv(
        OUT / "T04h_short_sessions.csv"
    )
    extra = days.filter(pl.col("bars") > pl.col("expected_bars")).height
    wicks = pl.DataFrame(
        wick_rows, schema={"symbol": pl.Utf8, "bars": pl.Int64, "flagged": pl.Int64}
    ).sort("flagged", descending=True)
    wicks.write_csv(OUT / "T04h_hourly_wick_flags.csv")

    # -- acceptance: references, hash version, dropped tickers, META/FB --------------------------
    want = set(universe["symbol"].to_list())
    have = set(refs["symbol"].to_list())
    dropped = _dropped_old_tickers()
    dropped_with = sorted(set(dropped) & set(table["symbol"].to_list()))
    meta_notes = refs.filter(pl.col("symbol") == "META")["notes"].to_list()

    print("hours kept (New York):", dict(sorted(hours.items())))
    print(f"1H snapshots {table.height}, references {refs.height} over {refs['symbol'].n_unique()}")
    print(f"universe {len(want)}; without a reference: {sorted(want - have)}")
    print(f"references not in the universe: {sorted(have - want)}")
    print("hash_version:", table.group_by("hash_version").len().rows())
    print(f"dropped old tickers (T04f) {len(dropped)}; with a 1H snapshot: {dropped_with}")
    print("FB snapshots:", table.filter(pl.col("symbol") == "FB").height)
    print("META notes record FB:", bool(meta_notes) and "FB" in meta_notes[0], meta_notes[:1])
    print("bars per session (expected -> actual, sessions):")
    print(dist)
    print(f"sessions short of the calendar: {short.height} on {short['symbol'].n_unique()} symbols")
    print(
        f"sessions with more bars than the calendar: {extra}; bars outside the session: {outside}"
    )
    aapl = short.filter(
        (pl.col("symbol") == "AAPL")
        & pl.col("session_date").cast(pl.Utf8).str.starts_with("2018-05-0")
    )
    print("AAPL 2018-05-02/03:", aapl.rows())
    print(
        f"hourly wick flags (D-703/D-706, report only): {wicks['flagged'].sum()} bars on {wicks.height} symbols"
    )

    # -- quality aggregate --------------------------------------------------------------------------
    statuses = refs.group_by("quality_status").len().sort("quality_status")
    print("quality_status of the 1H references:", statuses.rows())
    skipped: dict[str, int] = {}
    missing_pct: list[tuple[str, float]] = []
    violations: list[str] = []
    for sym, digest in refs.select("symbol", "snapshot_hash").rows():
        path = store.root / QUALITY_DIR / f"{digest}.json"
        if not path.is_file():
            skipped["<no report>"] = skipped.get("<no report>", 0) + 1
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        for c in report["checks"]:
            if c["status"] == "skipped":
                skipped[c["code"]] = skipped.get(c["code"], 0) + 1
            if c["code"] == "missing_bars":
                pct = c.get("details", {}).get("pct") if c["status"] == "fail" else 0.0
                missing_pct.append((sym, float(pct or 0.0)))
            if c["code"] == "session_violations" and c["status"] == "fail":
                violations.append(sym)
    print("skipped checks:", skipped)
    print("ten worst missing_pct:", sorted(missing_pct, key=lambda x: -x[1])[:10])
    print("session_violations:", violations)


if __name__ == "__main__":
    main()
