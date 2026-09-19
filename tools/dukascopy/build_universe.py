"""Build configs/universe/dukascopy.csv from the pinned dukascopy-node instrument metadata.

Every id is looked up in the tool's own ``instrumentMetaData``; an unknown id aborts.
Run from the repo root:  uv run python tools/dukascopy/build_universe.py
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "dukascopy"
OUT = REPO / "configs" / "universe" / "dukascopy.csv"

INSTRUMENTS: list[tuple[str, str]] = [
    *[(i, "fx") for i in ("eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad", "nzdusd")],
    *[
        (i, "fx")
        for i in ("eurjpy", "gbpjpy", "eurgbp", "eurchf", "audjpy", "euraud", "gbpchf", "cadjpy")
    ],
    ("xauusd", "metal"),
    ("xagusd", "metal"),
    ("lightcmdusd", "energy_cfd"),
    ("brentcmdusd", "energy_cfd"),
    *[
        (i, "index_cfd")
        for i in (
            "usa500idxusd",
            "usa30idxusd",
            "usatechidxusd",
            "ussc2000idxusd",
            "deuidxeur",
            "gbridxgbp",
            "jpnidxjpy",
            "fraidxeur",
            "ausidxaud",
            "hkgidxhkd",
        )
    ],
]


def main() -> None:
    ids = [i for i, _ in INSTRUMENTS]
    out = subprocess.run(
        ["node", str(TOOL / "list_instruments.js"), *ids],
        capture_output=True,
        text=True,
        check=True,
        cwd=TOOL,
    ).stdout
    meta = {m["id"]: m for m in map(json.loads, out.splitlines())}
    missing = [i for i in ids if not meta[i]["found"]]
    if missing:
        raise SystemExit(f"unknown dukascopy-node instrument ids: {missing}")
    version = json.loads((TOOL / "node_modules" / "dukascopy-node" / "package.json").read_text())[
        "version"
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["instrument_id", "symbol", "asset_class", "notes"])
        for iid, asset in INSTRUMENTS:
            m = meta[iid]
            note = (
                f"{m['name']} - {m['description']}; verified in dukascopy-node {version}; "
                f"h1 from {m['startMonthForHourlyCandles'][:10]}; "
                f"m1 from {m['startDayForMinuteCandles'][:10]}"
            )
            w.writerow([iid, iid.upper(), asset, note])
    print(f"wrote {OUT} ({len(INSTRUMENTS)} instruments, dukascopy-node {version})")


if __name__ == "__main__":
    main()
