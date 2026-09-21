"""Data-quality report per snapshot (F-0.1.6).

Checks (each with a severity from ``configs/data/quality.yaml``):

==================  =====================================================================
schema              duplicates, high < low, OHLC outside range, non-positive, NaN
                    (re-run of :func:`~strategy_factory.data.schema.validate_bars`)
missing_bars        expected schedule (:mod:`strategy_factory.data.schedule`) minus bars;
                    info up to ``warning_above_pct`` %, warning above
session_violations  bars outside the expected schedule
price_spikes        |r - median| > k * MAD over the trailing window **and** the next return
                    reverses at least ``reversal_fraction`` of the move
stale_prices        runs of >= ``min_run`` identical OHLC bars
zero_volume         share of zero-volume bars (skipped when ``volume_quality`` is none)
dst                 exchange-local sources only: the local time of the first bar of the
                    day changes across a DST transition
==================  =====================================================================

The status of a snapshot is the worst severity of a failed check (``info`` counts as
``ok``). Reports go to ``SFAC_DATA_ROOT/_quality/<snapshot_hash>.json`` (+ ``.md``) and the
status to the catalog column ``quality_status``; a ``critical`` status blocks the snapshot
from the pipeline (:func:`ensure_usable`).
"""

from __future__ import annotations

import datetime as dt
import json
import zoneinfo
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict

from strategy_factory.core.errors import DataError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import QualityConfig
from strategy_factory.data.schedule import expected_schedule
from strategy_factory.data.schema import SeriesMetadata, Severity, SnapshotKey, validate_bars
from strategy_factory.data.store import SnapshotStore

QUALITY_DIR = "_quality"
CheckStatus = Literal["pass", "fail", "skipped"]
QualityStatus = Literal["ok", "warning", "critical"]
_RANK = {"info": 0, "warning": 1, "critical": 2}
_SAMPLE = 10  # timestamps listed per check in the report


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    status: CheckStatus
    severity: Severity | None = None  # set when status == "fail"
    count: int = 0
    message: str = ""
    details: dict[str, Any] = {}


class QualityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: SnapshotKey
    asset_class: str
    session: str
    rows: int
    first_ts: dt.datetime | None
    last_ts: dt.datetime | None
    status: QualityStatus
    checks: tuple[CheckResult, ...]
    schedule: dict[str, Any]
    checked_at: dt.datetime
    config: dict[str, Any]

    def check(self, code: str) -> CheckResult:
        return next(c for c in self.checks if c.code == code)

    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == "fail"]


def _sample(ts: Iterable[Any]) -> list[str]:
    out = []
    for i, t in enumerate(ts):
        if i >= _SAMPLE:
            break
        out.append(t.isoformat() if isinstance(t, dt.datetime) else str(t))
    return out


def _pass(code: str, message: str = "", **details: Any) -> CheckResult:
    return CheckResult(code=code, status="pass", message=message, details=details)


def _skip(code: str, reason: str) -> CheckResult:
    return CheckResult(code=code, status="skipped", message=reason)


def _fail(code: str, severity: Severity, count: int, message: str, **details: Any) -> CheckResult:
    return CheckResult(
        code=code, status="fail", severity=severity, count=count, message=message, details=details
    )


# -- individual checks -------------------------------------------------------------------
def check_schema(df: pl.DataFrame, meta: SeriesMetadata, cfg: QualityConfig) -> CheckResult:
    issues = validate_bars(df, meta)
    if not issues:
        return _pass("schema")
    by_code = {i.code: i.count for i in issues}
    total = sum(max(i.count, 1) for i in issues)
    msg = "; ".join(f"{i.code} ({i.count})" for i in issues)
    return _fail("schema", cfg.schema_checks.severity, total, msg, issues=by_code)


def check_price_spikes(df: pl.DataFrame, cfg: QualityConfig) -> CheckResult:
    c = cfg.price_spikes
    close = df["close"].to_numpy().astype(np.float64)
    if close.size < c.window + 3 or np.any(~np.isfinite(close)) or np.any(close <= 0):
        return _skip("price_spikes", "too few bars or non-positive closes")
    r = np.diff(np.log(close))  # r[i] = return into bar i + 1
    n = r.size
    hits: list[int] = []
    chunk = 100_000
    for lo in range(c.window, n - 1, chunk):
        hi = min(lo + chunk, n - 1)
        win = np.lib.stride_tricks.sliding_window_view(r[lo - c.window : hi], c.window)
        win = win[: hi - lo]
        med = np.median(win, axis=1)
        mad = np.median(np.abs(win - med[:, None]), axis=1)
        cur, nxt = r[lo:hi], r[lo + 1 : hi + 1]
        dev = np.abs(cur - med)
        spike = (mad > 0) & (dev > c.k * mad)
        big_enough = np.abs(nxt) >= c.reversal_fraction * np.abs(cur)
        reverse = (np.sign(nxt) == -np.sign(cur)) & big_enough
        hits.extend((np.flatnonzero(spike & reverse) + lo + 1).tolist())  # bar index
    if not hits:
        return _pass("price_spikes")
    ts = df["ts"].gather(hits)
    return _fail(
        "price_spikes",
        c.severity,
        len(hits),
        f"{len(hits)} spike bar(s) (> {c.k} x MAD, reversed)",
        bars=_sample(ts),
    )


def check_stale(df: pl.DataFrame, cfg: QualityConfig) -> CheckResult:
    c = cfg.stale_prices
    cols = ["open", "high", "low", "close"]
    same = pl.all_horizontal([pl.col(x) == pl.col(x).shift(1) for x in cols]).fill_null(False)
    runs = (
        df.select(pl.col("ts").shift(1).alias("prev_ts"), same.alias("same"))
        .with_columns(run=(pl.col("same") != pl.col("same").shift(1)).cum_sum())
        .filter(pl.col("same"))
        .group_by("run", maintain_order=True)
        .agg(pl.col("prev_ts").first().alias("from"), (pl.len() + 1).alias("bars"))
        .filter(pl.col("bars") >= c.min_run)
    )
    if runs.height == 0:
        return _pass("stale_prices")
    longest = max(runs["bars"].to_list())
    return _fail(
        "stale_prices",
        c.severity,
        runs.height,
        f"{runs.height} run(s) of >= {c.min_run} identical OHLC bars (longest {longest})",
        longest=longest,
        runs_from=_sample(runs["from"]),
    )


def check_zero_volume(df: pl.DataFrame, meta: SeriesMetadata, cfg: QualityConfig) -> CheckResult:
    if meta.volume_quality == "none":
        return _skip("zero_volume", "volume_quality is none")
    if df.height == 0:
        return _skip("zero_volume", "empty series")
    zeros = int((df["volume"] == 0).sum())
    share = zeros / df.height
    if zeros == 0:
        return _pass("zero_volume", share=0.0)
    sev: Severity = "warning" if share > cfg.zero_volume.warning_above_share else "info"
    return _fail("zero_volume", sev, zeros, f"{share:.2%} zero-volume bars", share=round(share, 6))


def check_dst(df: pl.DataFrame, meta: SeriesMetadata, cfg: QualityConfig) -> CheckResult:
    if meta.original_tz.upper() in ("UTC", "ETC/UTC", "Z"):
        return _skip("dst", "source is UTC, not exchange-local")
    if meta.timeframe == "1D":
        return _skip("dst", "daily bars")
    try:
        tz = zoneinfo.ZoneInfo(meta.original_tz)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return _skip("dst", f"unknown time zone {meta.original_tz!r}")
    if df.height == 0:
        return _skip("dst", "empty series")
    first = df.select(
        pl.col("ts").dt.convert_time_zone(meta.original_tz).alias("local")
    ).with_columns(day=pl.col("local").dt.date(), tod=pl.col("local").dt.time())
    first = first.group_by("day").agg(pl.col("tod").min()).sort("day")
    days: list[dt.date] = first["day"].to_list()
    tods: list[dt.time] = first["tod"].to_list()
    lo, hi = days[0], days[-1]
    transitions = []
    d = lo
    while d < hi:
        nxt = d + dt.timedelta(days=1)
        a = dt.datetime.combine(d, dt.time(12), tzinfo=tz).utcoffset()
        b = dt.datetime.combine(nxt, dt.time(12), tzinfo=tz).utcoffset()
        if a != b:
            transitions.append(nxt)
        d = nxt
    w = dt.timedelta(days=cfg.dst.window_days)
    bad: list[str] = []

    def modal(values: list[dt.time]) -> dt.time | None:
        if not values:
            return None
        return max(sorted(set(values)), key=values.count)

    for t in transitions:
        before = modal([x for day, x in zip(days, tods, strict=True) if t - w <= day < t])
        after = modal([x for day, x in zip(days, tods, strict=True) if t <= day < t + w])
        if before is not None and after is not None and before != after:
            bad.append(f"{t}: first bar {before} -> {after} local")
    if not bad:
        return _pass("dst", transitions=len(transitions))
    return _fail(
        "dst",
        cfg.dst.severity,
        len(bad),
        f"{len(bad)} DST transition(s) shift the local session",
        transitions=bad[:_SAMPLE],
    )


def check_daily_wick_outlier(
    df: pl.DataFrame, meta: SeriesMetadata, cfg: QualityConfig
) -> CheckResult:
    """D-396: a daily high or low beyond the body by **both** k1 x ATR(14) and k2 % (T04k).

    Runs for **every** daily symbol, hourly data or not -- it is the arm that works on all 6,707.
    Counts are reported per symbol (the count itself) and per date (the sample), because T04i
    showed the date-wide clusters that point at the feed rather than at an instrument.
    """
    from strategy_factory.data.clean_daily import wick_outliers

    if meta.timeframe != "1D":
        return _skip("daily_wick_outlier", "not a daily series")
    if df.height == 0:
        return _skip("daily_wick_outlier", "empty series")
    flagged = wick_outliers(df, cfg.daily_wick_outlier)
    hits = flagged.filter(pl.col("flag_high") | pl.col("flag_low"))
    if hits.height == 0:
        return _pass("daily_wick_outlier", bars=df.height)
    return _fail(
        "daily_wick_outlier",
        cfg.daily_wick_outlier.severity,
        hits.height,
        f"{hits.height} bar(s) with a wick beyond the body by both "
        f"{cfg.daily_wick_outlier.k1_atr} x ATR(14) and {cfg.daily_wick_outlier.k2_pct} %",
        dates=[str(d) for d in hits["session_date"].to_list()[:_SAMPLE]],
        high_side=int(hits["flag_high"].sum()),
        low_side=int(hits["flag_low"].sum()),
    )


def unsupported_beyond_body(
    breaches: pl.DataFrame, daily: pl.DataFrame, eps_bps: float
) -> pl.DataFrame:
    """The correctable breach days whose extreme lies outside the RTH range **and** the body.

    D-701: the official close is the closing-auction print, a traded price; an extreme that sits
    on the open or the close is supported by definition. T04k measured every one of the 8,750
    residual breach days on the clean series on the close (median 2.7 bps), because the auction
    print is filed in the 16:00 hourly bar D-023 drops. The bound is the one ``extreme_cap``
    already respects, so the check and the correction agree.
    """
    from strategy_factory.data.clean_daily import CORRECTABLE

    body = daily.select(
        pl.col("ts").dt.date().alias("session_date"),
        pl.max_horizontal("open", "close").alias("body_high"),
        pl.min_horizontal("open", "close").alias("body_low"),
    )
    bps = 1e4 / pl.col("daily_close")
    return (
        breaches.filter(pl.col("breach_class").is_in(sorted(CORRECTABLE)))
        .join(body, on="session_date", how="inner")
        .with_columns(
            ((pl.col("daily_high") - pl.max_horizontal("rth_high", "body_high")) * bps).alias(
                "beyond_high_bps"
            ),
            ((pl.min_horizontal("rth_low", "body_low") - pl.col("daily_low")) * bps).alias(
                "beyond_low_bps"
            ),
        )
        .filter((pl.col("beyond_high_bps") > eps_bps) | (pl.col("beyond_low_bps") > eps_bps))
    )


def check_daily_extreme_unsupported(
    df: pl.DataFrame,
    meta: SeriesMetadata,
    cfg: QualityConfig,
    breaches: pl.DataFrame | None,
    coverage: pl.DataFrame | None = None,
) -> CheckResult:
    """D-396: a daily extreme the hourly feed does not support, where hourly data exists (T04k).

    **A short or missing hourly day is not evidence** (supervisor, 2026-09-21): it is never counted
    as a defect **and never counted as clean**. It is reported separately with the bar count it
    held against the calendar's expectation, **whether or not the daily bar breaches** -- so a
    pass can never be mistaken for a check that ran on a day it could not check.

    ``coverage`` (``session_date, rth_bars, expected_bars``, one row per session the hourly series
    has any bar on) is what finds the short days; ``breaches`` only holds the days that breach, so
    a short day inside the hourly range would otherwise pass silently. A daily session with no
    hourly bar at all is ``no_raw_hours`` and is reported the same way.
    """

    code = "daily_extreme_unsupported"
    if meta.timeframe != "1D":
        return _skip(code, "not a daily series")
    if breaches is None and coverage is None:
        return _skip(code, "no hourly series for this symbol")
    details: dict[str, Any] = {}
    if coverage is not None:
        days = df.select(pl.col("ts").dt.date().alias("session_date"))
        seen = days.join(coverage, on="session_date", how="left")
        short = seen.filter(pl.col("rth_bars") < pl.col("expected_bars"))
        missing = seen.filter(pl.col("rth_bars").is_null())
        details = {
            "not_evidence_days": short.height + missing.height,
            "short_hourly_days": short.height,
            "no_hourly_days": missing.height,
            "not_evidence_bars": [
                f"{d}: {b} of {e} hourly bars"
                for d, b, e in short.select("session_date", "rth_bars", "expected_bars").rows()[
                    :_SAMPLE
                ]
            ],
            "no_hourly_dates": [str(d) for d in missing["session_date"].to_list()[:_SAMPLE]],
        }
    real = (
        unsupported_beyond_body(breaches, df, cfg.daily_extreme_unsupported.eps_bps)
        if breaches is not None
        else pl.DataFrame()
    )
    if real.height == 0:
        return _pass(code, breach_days=0, **details)
    per_class = dict(real.group_by("breach_class").len().rows())
    return _fail(
        code,
        cfg.daily_extreme_unsupported.severity,
        real.height,
        f"{real.height} day(s) whose daily extreme the hourly feed does not support "
        f"({', '.join(f'{k} {v}' for k, v in sorted(per_class.items()))})",
        dates=[str(d) for d in real["session_date"].to_list()[:_SAMPLE]],
        **details,
    )


def schedule_checks(
    df: pl.DataFrame, meta: SeriesMetadata, cfg: QualityConfig, sessions_file: Path | None
) -> tuple[CheckResult, CheckResult, dict[str, Any]]:
    sched = expected_schedule(
        df["ts"], meta.asset_class, meta.timeframe, cfg, meta.notes, sessions_file
    )
    info: dict[str, Any] = {"basis": sched.reason}
    if sched.break_info is not None:
        info.update(sched.break_info.as_dict())
    if sched.starts is None:
        return _skip("missing_bars", sched.reason), _skip("session_violations", sched.reason), info
    ts = df["ts"]
    expected = sched.starts
    if sched.coverage is not None:
        lo, hi = sched.coverage
        ts = ts.filter((ts >= lo) & (ts < hi))
        info["coverage"] = [lo.isoformat(), hi.isoformat()]
    missing = expected.filter(~expected.is_in(ts.implode()))
    extra = ts.filter(~ts.is_in(expected.implode()))
    info["expected_bars"] = expected.len()
    pct = 100.0 * missing.len() / expected.len() if expected.len() else 0.0
    if missing.len() == 0:
        miss = _pass("missing_bars", expected=expected.len())
    else:
        sev: Severity = "warning" if pct > cfg.missing_bars.warning_above_pct else "info"
        miss = _fail(
            "missing_bars",
            sev,
            missing.len(),
            f"{missing.len()} of {expected.len()} expected bars missing ({pct:.2f} %)",
            pct=round(pct, 4),
            expected=expected.len(),
            first_missing=_sample(missing),
        )
    if extra.len() == 0:
        viol = _pass("session_violations")
    else:
        viol = _fail(
            "session_violations",
            cfg.session_violations.severity,
            extra.len(),
            f"{extra.len()} bar(s) outside the expected schedule",
            bars=_sample(extra),
        )
    return miss, viol, info


def run_quality(
    df: pl.DataFrame,
    meta: SeriesMetadata,
    cfg: QualityConfig,
    sessions_file: Path | None = None,
    breaches: pl.DataFrame | None = None,
    coverage: pl.DataFrame | None = None,
) -> QualityReport:
    """All checks on one stored snapshot."""
    df = df.sort("ts")
    checks = [check_schema(df, meta, cfg)]
    miss, viol, sched = schedule_checks(df, meta, cfg, sessions_file)
    checks += [
        miss,
        viol,
        check_price_spikes(df, cfg),
        check_stale(df, cfg),
        check_zero_volume(df, meta, cfg),
        check_dst(df, meta, cfg),
        check_daily_wick_outlier(df, meta, cfg),
        check_daily_extreme_unsupported(df, meta, cfg, breaches, coverage),
    ]
    worst = max((_RANK[c.severity] for c in checks if c.severity is not None), default=0)
    levels: dict[int, QualityStatus] = {0: "ok", 1: "warning", 2: "critical"}
    status = levels[worst]
    return QualityReport(
        snapshot=meta.key(),
        asset_class=meta.asset_class,
        session=meta.session,
        rows=df.height,
        first_ts=df["ts"].min() if df.height else None,  # type: ignore[arg-type]
        last_ts=df["ts"].max() if df.height else None,  # type: ignore[arg-type]
        status=status,
        checks=tuple(checks),
        schedule=sched,
        checked_at=dt.datetime.now(dt.UTC),
        config=cfg.model_dump(mode="json"),
    )


# -- files, catalog, gate ----------------------------------------------------------------
def report_markdown(rep: QualityReport) -> str:
    k = rep.snapshot
    lines = [
        f"# Quality: {k.symbol} {k.timeframe} ({k.source})",
        "",
        f"- snapshot: `{k.snapshot_hash}`",
        f"- status: **{rep.status}**",
        f"- rows: {rep.rows} ({rep.first_ts} .. {rep.last_ts})",
        f"- schedule: {rep.schedule.get('basis', '')}",
    ]
    if rep.schedule.get("break_hour_local") is not None:
        lines.append(
            f"- daily break: {rep.schedule['break_hour_local']:02d}:00 "
            f"{rep.schedule['timezone']} (modal UTC hour "
            f"{rep.schedule['modal_break_hour_utc']:02d}, share {rep.schedule['share']})"
        )
    lines += ["", "| check | status | severity | count | message |", "|---|---|---|---|---|"]
    for c in rep.checks:
        lines.append(f"| {c.code} | {c.status} | {c.severity or ''} | {c.count} | {c.message} |")
    return "\n".join(lines) + "\n"


def write_report(rep: QualityReport, root: Path) -> Path:
    """``<root>/_quality/<snapshot_hash>.json`` and ``.md``; returns the JSON path."""
    out = root / QUALITY_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{rep.snapshot.snapshot_hash}.json"
    path.write_text(
        json.dumps(rep.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    path.with_suffix(".md").write_text(report_markdown(rep), encoding="utf-8")
    return path


def check_snapshot(
    meta: SeriesMetadata,
    store: SnapshotStore,
    catalog: Catalog,
    cfg: QualityConfig,
    sessions_file: Path | None = None,
    breaches: pl.DataFrame | None = None,
    coverage: pl.DataFrame | None = None,
) -> QualityReport:
    """Run the checks on a registered snapshot, write the report, record the status."""
    key = meta.key()
    df = store.read_snapshot(key.source, key.symbol, key.timeframe, key.snapshot_hash)
    rep = run_quality(df, meta, cfg, sessions_file, breaches, coverage)
    write_report(rep, store.root)
    failed = ", ".join(f"{c.code}:{c.severity}" for c in rep.failed())
    catalog.set_quality_status(key, rep.status, note=failed or "all checks passed")
    return rep


def ensure_usable(catalog: Catalog, key: SnapshotKey) -> str:
    """Raise ``DataError`` if the snapshot's quality status is ``critical``; else the status."""
    status = catalog.quality_status(key)
    if status == "critical":
        raise DataError(
            f"snapshot {key.short()} failed a critical quality check; see "
            f"{QUALITY_DIR}/{key.snapshot_hash}.md -- it cannot be used by the pipeline",
            stage="quality",
            symbol=key.symbol,
        )
    return status
