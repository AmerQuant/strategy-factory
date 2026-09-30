"""Dukascopy bid/ask downloader: thin wrapper around the pinned ``dukascopy-node`` CLI (T04b).

* The CLI lives in ``tools/dukascopy`` (``package.json`` + lockfile, ``npm ci``); Node is an
  external tool, not a Python dependency. It is called with ``node <cli>`` via ``subprocess``,
  **one instrument x side x calendar month per call**, with the tool's own retry and
  batch-pause flags (from ``configs/data/dukascopy.yaml``).
* Raw output (immutable): ``<raw>/fx_metals_cfd/dukascopy/<series>/<INSTRUMENT>/<side>/
  <YYYY-MM>.csv.gz`` -- the tool's CSV gzip-compressed losslessly (deterministic header) --
  plus a manifest with the tool version, the exact command line, download time, row count
  and the sha256 of the uncompressed CSV.
* Resumable: stored months are skipped. The current, incomplete month is never stored.
  Months before the instrument's first data (tool metadata) are not requested. Months that
  return no bars are stored (header only) and listed in ``_reports/dukascopy_empty.csv``.
* A certificate error stops the run (verification is never disabled).
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.config import DukascopyConfig
from strategy_factory.data.download.ratelimit import TLSVerificationError
from strategy_factory.data.download.rawfiles import (
    is_settled,
    next_version_path,
    versions,
    write_immutable,
)

log = get_logger(__name__)

Series = Literal["h1", "m1"]
SIDES = ("bid", "ask")
RAW_SUBDIR = ("fx_metals_cfd", "dukascopy")
SUFFIX = ".csv.gz"
TLS_MARKERS = (
    "UNABLE_TO_VERIFY_LEAF_SIGNATURE",
    "SELF_SIGNED_CERT_IN_CHAIN",
    "DEPTH_ZERO_SELF_SIGNED_CERT",
    "CERT_HAS_EXPIRED",
    "unable to get local issuer certificate",
    "certificate",
)


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    symbol: str
    asset_class: str
    notes: str = ""


def load_instruments(path: Path) -> list[Instrument]:
    if not path.is_file():
        raise ConfigError("Dukascopy universe file not found", config_path=path)
    with path.open(encoding="utf-8", newline="") as fh:
        return [
            Instrument(**{k: r[k] for k in ("instrument_id", "symbol", "asset_class", "notes")})
            for r in csv.DictReader(fh)
        ]


# --------------------------------------------------------------------------------------
# Tool and command lines
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Tool:
    node: str
    cli: Path
    version: str
    tool_dir: Path

    @classmethod
    def locate(cls, cfg: DukascopyConfig) -> Tool:
        tool_dir = cfg.tool.directory
        pkg = tool_dir / "node_modules" / "dukascopy-node" / "package.json"
        if not pkg.is_file():
            raise ConfigError(
                "dukascopy-node is not installed: run `npm ci` in tools/dukascopy "
                "(Node.js LTS required)",
                config_path=tool_dir / "package.json",
            )
        node = shutil.which("node")
        if node is None:
            raise ConfigError("Node.js (`node`) not found on PATH; install Node.js LTS")
        meta = json.loads(pkg.read_text(encoding="utf-8"))
        bin_entry = meta["bin"]["dukascopy-node"] if isinstance(meta["bin"], dict) else meta["bin"]
        return cls(
            node=node,
            cli=(pkg.parent / bin_entry).resolve(),
            version=str(meta["version"]),
            tool_dir=tool_dir,
        )


def month_start(d: dt.date) -> dt.date:
    return d.replace(day=1)


def add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def last_complete_month(today: dt.date) -> dt.date:
    return add_months(month_start(today), -1)


def months(first: dt.date, last: dt.date) -> list[dt.date]:
    out, cur = [], month_start(first)
    while cur <= month_start(last):
        out.append(cur)
        cur = add_months(cur, 1)
    return out


def build_command(
    tool: Tool,
    cfg: DukascopyConfig,
    instrument: str,
    side: str,
    series: Series,
    month: dt.date,
    out_dir: Path,
) -> list[str]:
    """Exact CLI call for one instrument x side x month (``--date-to`` is exclusive)."""
    t = cfg.tool
    return [
        tool.node,
        str(tool.cli),
        "--instrument", instrument,
        "--date-from", month.isoformat(),
        "--date-to", add_months(month, 1).isoformat(),
        "--timeframe", series,
        "--price-type", side,
        "--utc-offset", str(t.utc_offset_minutes),
        "--volumes",
        "--volume-units", t.volume_units,
        "--format", "csv",
        "--directory", str(out_dir),
        "--batch-size", str(t.batch_size),
        "--batch-pause", str(t.batch_pause_ms),
        "--retries", str(t.retries),
        "--retry-pause", str(t.retry_pause_ms),
        "--file-name", "out",
        "--silent",
    ]  # fmt: skip


# --------------------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------------------
Runner = Callable[[list[str], Path, int], "subprocess.CompletedProcess[str]"]


def run_subprocess(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def month_dir(raw_root: Path, series: str, instrument: str, side: str) -> Path:
    return raw_root.joinpath(*RAW_SUBDIR, series, instrument.upper(), side)


def is_month_stored(
    raw_root: Path, series: str, instrument: str, side: str, month: dt.date
) -> bool:
    return bool(versions(month_dir(raw_root, series, instrument, side), f"{month:%Y-%m}", SUFFIX))


@dataclass
class DukascopyReport:
    series: str
    stored: int = 0
    skipped: int = 0
    empty: list[dict[str, str]] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    rows: int = 0


def _count_rows(csv_bytes: bytes) -> int:
    lines = [ln for ln in csv_bytes.splitlines() if ln.strip()]
    return max(0, len(lines) - 1)


def fetch_month(
    tool: Tool,
    cfg: DukascopyConfig,
    raw_root: Path,
    instrument: str,
    side: str,
    series: Series,
    month: dt.date,
    runner: Runner = run_subprocess,
) -> tuple[Path | None, int, str]:
    """Run the CLI for one month and store the result; returns (path, rows, error)."""
    with tempfile.TemporaryDirectory(prefix="sfac-duka-") as tmp:
        cmd = build_command(tool, cfg, instrument, side, series, month, Path(tmp))
        proc = runner(cmd, tool.tool_dir, cfg.tool.timeout_seconds)
        text = (proc.stdout or "") + (proc.stderr or "")
        if any(m.lower() in text.lower() for m in TLS_MARKERS) and proc.returncode != 0:
            where = f"{instrument} {side} {month:%Y-%m}"
            raise TLSVerificationError(
                f"dukascopy-node TLS error for {where}: {text.strip()[:300]}"
            )
        out = Path(tmp) / "out.csv"
        if proc.returncode != 0 or not out.is_file():
            return None, 0, f"exit {proc.returncode}: {text.strip()[:300]}"
        data = out.read_bytes()
    rows = _count_rows(data)
    target = next_version_path(
        month_dir(raw_root, series, instrument, side), f"{month:%Y-%m}", SUFFIX
    )
    manifest: dict[str, Any] = {
        "source": "dukascopy",
        "tool": f"dukascopy-node {tool.version}",
        "command": [Path(cmd[0]).name, "dukascopy-node", *cmd[2:]],
        "instrument": instrument,
        "side": side,
        "series": series,
        "month": f"{month:%Y-%m}",
        "utc_offset_minutes": cfg.tool.utc_offset_minutes,
        "volume_units": cfg.tool.volume_units,
        "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "row_count": rows,
        "sha256_uncompressed": _sha256(data),
    }
    path = write_immutable(target, gzip.compress(data, mtime=0), manifest)
    return path, rows, ""


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _is_throttled(err: str) -> bool:
    """HTTP 429 or 5xx reported by the CLI after its own retries."""
    return any(f"status {code}" in err for code in ("429", "500", "502", "503", "504"))


def instrument_start(notes: str, series: Series) -> dt.date | None:
    """First month with data from the universe notes ("h1 from YYYY-MM-DD; m1 from ...")."""
    key = f"{series} from "
    if key not in notes:
        return None
    return dt.date.fromisoformat(notes.split(key, 1)[1][:10])


def run_dukascopy_download(
    instruments: Sequence[Instrument],
    series: Series,
    first: dt.date,
    last: dt.date,
    raw_root: Path,
    cfg: DukascopyConfig,
    tool: Tool,
    today: dt.date | None = None,
    runner: Runner = run_subprocess,
    sleep: Callable[[float], None] = time.sleep,
) -> DukascopyReport:
    today = today or dt.datetime.now(dt.UTC).date()
    last = min(month_start(last), last_complete_month(today))  # never the current month
    report = DukascopyReport(series=series)
    for inst in instruments:
        start = instrument_start(inst.notes, series)
        for m in months(first, last):
            if start is not None and add_months(m, 1) <= start:
                continue
            for side in SIDES:
                if is_month_stored(raw_root, series, inst.instrument_id, side, m):
                    report.skipped += 1
                    continue
                path, rows, err = None, 0, ""
                for attempt in range(cfg.tool.call_retries + 1):
                    path, rows, err = fetch_month(
                        tool, cfg, raw_root, inst.instrument_id, side, series, m, runner
                    )
                    if path is not None or not _is_throttled(err):
                        break
                    if attempt < cfg.tool.call_retries:
                        delay = cfg.tool.call_backoff_seconds * (2**attempt)
                        log.warning(
                            "dukascopy %s %s %s %s throttled (%s); retry %d in %.0fs",
                            inst.instrument_id, side, series, m, err.splitlines()[-1][:80],
                            attempt + 1, delay,
                        )  # fmt: skip
                        sleep(delay)
                if path is None:
                    log.error(
                        "dukascopy %s %s %s %s failed: %s", inst.instrument_id, side, series, m, err
                    )
                    report.failed.append(
                        {
                            "instrument": inst.instrument_id,
                            "side": side,
                            "month": f"{m:%Y-%m}",
                            "error": err,
                        }
                    )
                    continue
                report.stored += 1
                report.rows += rows
                if rows == 0:
                    report.empty.append(
                        {
                            "instrument": inst.instrument_id,
                            "side": side,
                            "series": series,
                            "month": f"{m:%Y-%m}",
                        }
                    )
            log.info("dukascopy %s %s %s done", inst.instrument_id, series, m)
    if report.empty:
        write_empty_report(raw_root, report.empty)
    return report


def write_empty_report(raw_root: Path, rows: list[dict[str, str]]) -> Path:
    path = raw_root / "_reports" / "dukascopy_empty.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["instrument", "side", "series", "month", "checked_at"]
    existing: dict[tuple[str, str, str, str], dict[str, str]] = {}
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                existing[(r["instrument"], r["side"], r["series"], r["month"])] = r
    stamp = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    for r in rows:
        existing[(r["instrument"], r["side"], r["series"], r["month"])] = {**r, "checked_at": stamp}
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for k in sorted(existing):
            w.writerow(existing[k])
    tmp.replace(path)
    return path


def latest_months(raw_root: Path, series: str, instrument: str, side: str) -> list[Path]:
    d = month_dir(raw_root, series, instrument, side)
    if not d.is_dir():
        return []
    bases = sorted({p.name[:7] for p in d.iterdir() if p.name.endswith(SUFFIX)})
    return [versions(d, b, SUFFIX)[-1] for b in bases]


def raw_pairs(raw_root: Path, series: str, instrument: str) -> tuple[list[Path], list[Path]]:
    """The settled month files of each side (``is_settled``: never a month still being written
    by a download running alongside)."""
    bid = [p for p in latest_months(raw_root, series, instrument, "bid") if is_settled(p)]
    ask = [p for p in latest_months(raw_root, series, instrument, "ask") if is_settled(p)]
    if not bid or not ask:
        raise DataError(
            f"no raw {series} bid/ask files for {instrument}", symbol=instrument.upper()
        )
    return bid, ask
