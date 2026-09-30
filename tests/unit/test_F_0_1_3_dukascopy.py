"""F-0.1.3: Dukascopy wrapper (mocked subprocess) and bid/ask adapter."""

from __future__ import annotations

import datetime as dt
import gzip
import json
import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest

from strategy_factory.core.errors import DataError
from strategy_factory.data.adapters.dukascopy import DukascopyAdapter, repair_ohlc
from strategy_factory.data.config import DukascopyConfig
from strategy_factory.data.download import dukascopy as dk
from strategy_factory.data.download.ratelimit import TLSVerificationError
from strategy_factory.data.download.rawfiles import read_manifest
from strategy_factory.data.schema import validate_bars

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "dukascopy" / "h1" / "EURUSD"
CFG = DukascopyConfig()
TOOL = dk.Tool(node="node", cli=Path("cli") / "index.js", version="1.50.0", tool_dir=Path("."))
EURUSD = dk.Instrument("eurusd", "EURUSD", "fx", "EUR/USD; h1 from 2003-05-04; m1 from 2003-05-04")
CSV = b"timestamp,open,high,low,close,volume\n1704153600000,1.1,1.2,1.0,1.15,100\n"


class FakeRunner:
    """Mocked subprocess: writes ``out.csv`` into the --directory given on the command line."""

    def __init__(self, payload: bytes = CSV, returncode: int = 0, stderr: str = "") -> None:
        self.payload, self.returncode, self.stderr = payload, returncode, stderr
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if self.returncode == 0:
            out_dir = Path(cmd[cmd.index("--directory") + 1])
            (out_dir / "out.csv").write_bytes(self.payload)
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)


def flag(cmd: list[str], name: str) -> str:
    return cmd[cmd.index(name) + 1]


# -- wrapper -------------------------------------------------------------------------------
def test_F_0_1_3_command_line(tmp_path: Path) -> None:
    cmd = dk.build_command(TOOL, CFG, "eurusd", "ask", "h1", dt.date(2024, 12, 1), tmp_path)
    assert cmd[:2] == ["node", str(Path("cli") / "index.js")]
    assert flag(cmd, "--instrument") == "eurusd"
    assert (flag(cmd, "--date-from"), flag(cmd, "--date-to")) == ("2024-12-01", "2025-01-01")
    assert (flag(cmd, "--timeframe"), flag(cmd, "--price-type")) == ("h1", "ask")
    assert (flag(cmd, "--format"), flag(cmd, "--volume-units")) == ("csv", "units")
    assert flag(cmd, "--utc-offset") == "0" and "--volumes" in cmd
    assert (flag(cmd, "--retries"), flag(cmd, "--retry-pause")) == ("3", "1000")
    assert (flag(cmd, "--batch-size"), flag(cmd, "--batch-pause")) == ("10", "1000")
    assert flag(cmd, "--directory") == str(tmp_path)


def test_F_0_1_3_download_stores_gzip_with_manifest(tmp_path: Path) -> None:
    runner = FakeRunner()
    rep = dk.run_dukascopy_download(
        [EURUSD], "h1", dt.date(2024, 1, 1), dt.date(2024, 2, 1), tmp_path, CFG, TOOL,
        today=dt.date(2024, 6, 15), runner=runner,
    )  # fmt: skip
    assert rep.stored == 4 and len(runner.calls) == 4  # 2 months x bid/ask, one call each
    f = tmp_path / "fx_metals_cfd" / "dukascopy" / "h1" / "EURUSD" / "bid" / "2024-01.csv.gz"
    assert gzip.decompress(f.read_bytes()) == CSV  # lossless
    m = read_manifest(f)
    assert m is not None
    assert m["tool"] == "dukascopy-node 1.50.0" and m["row_count"] == 1
    assert m["command"][1] == "dukascopy-node" and "--price-type" in m["command"]
    assert len(m["sha256_uncompressed"]) == 64 and m["sha256_uncompressed"] != m["sha256"]


def test_F_0_1_3_download_skips_completed_months_and_never_overwrites(tmp_path: Path) -> None:
    kw = {"today": dt.date(2024, 6, 15)}
    dk.run_dukascopy_download(
        [EURUSD],
        "h1",
        dt.date(2024, 1, 1),
        dt.date(2024, 1, 1),
        tmp_path,
        CFG,
        TOOL,
        runner=FakeRunner(),
        **kw,
    )  # type: ignore[arg-type]
    f = tmp_path / "fx_metals_cfd" / "dukascopy" / "h1" / "EURUSD" / "bid" / "2024-01.csv.gz"
    mtime = f.stat().st_mtime_ns
    runner = FakeRunner(payload=b"timestamp,open,high,low,close,volume\n")
    rep = dk.run_dukascopy_download(
        [EURUSD],
        "h1",
        dt.date(2024, 1, 1),
        dt.date(2024, 1, 1),
        tmp_path,
        CFG,
        TOOL,
        runner=runner,
        **kw,
    )  # type: ignore[arg-type]
    assert rep.skipped == 2 and not runner.calls
    assert f.stat().st_mtime_ns == mtime
    with pytest.raises(PermissionError):
        f.write_bytes(b"x")


def test_F_0_1_3_current_month_is_never_stored(tmp_path: Path) -> None:
    runner = FakeRunner()
    rep = dk.run_dukascopy_download(
        [EURUSD], "m1", dt.date(2024, 5, 1), dt.date(2024, 6, 1), tmp_path, CFG, TOOL,
        today=dt.date(2024, 6, 15), runner=runner,
    )  # fmt: skip
    months = {flag(c, "--date-from") for c in runner.calls}
    assert months == {"2024-05-01"} and rep.stored == 2


def test_F_0_1_3_months_before_instrument_start_are_not_requested(tmp_path: Path) -> None:
    runner = FakeRunner()
    late = dk.Instrument("ussc2000idxusd", "USSC2000IDXUSD", "index_cfd", "h1 from 2018-08-08")
    dk.run_dukascopy_download(
        [late], "h1", dt.date(2018, 6, 1), dt.date(2018, 9, 1), tmp_path, CFG, TOOL,
        today=dt.date(2024, 1, 1), runner=runner,
    )  # fmt: skip
    assert sorted({flag(c, "--date-from") for c in runner.calls}) == ["2018-08-01", "2018-09-01"]


def test_F_0_1_3_empty_months_are_reported(tmp_path: Path) -> None:
    runner = FakeRunner(payload=b"timestamp,open,high,low,close,volume\n")
    rep = dk.run_dukascopy_download(
        [EURUSD], "h1", dt.date(2024, 1, 1), dt.date(2024, 1, 1), tmp_path, CFG, TOOL,
        today=dt.date(2024, 6, 15), runner=runner,
    )  # fmt: skip
    assert len(rep.empty) == 2
    report = pl.read_csv(tmp_path / "_reports" / "dukascopy_empty.csv")
    assert report.select("instrument", "side", "month").rows() == [
        ("eurusd", "ask", "2024-01"),
        ("eurusd", "bid", "2024-01"),
    ]


def test_F_0_1_3_tls_error_stops(tmp_path: Path) -> None:
    runner = FakeRunner(returncode=1, stderr="Error: unable to get local issuer certificate")
    with pytest.raises(TLSVerificationError):
        dk.run_dukascopy_download(
            [EURUSD], "h1", dt.date(2024, 1, 1), dt.date(2024, 1, 1), tmp_path, CFG, TOOL,
            today=dt.date(2024, 6, 15), runner=runner,
        )  # fmt: skip


def test_F_0_1_3_failed_call_is_reported_not_stored(tmp_path: Path) -> None:
    runner = FakeRunner(returncode=1, stderr="Error: 503 Service Unavailable")
    rep = dk.run_dukascopy_download(
        [EURUSD], "h1", dt.date(2024, 1, 1), dt.date(2024, 1, 1), tmp_path, CFG, TOOL,
        today=dt.date(2024, 6, 15), runner=runner,
    )  # fmt: skip
    assert rep.stored == 0 and len(rep.failed) == 2
    assert not list(tmp_path.rglob("*.csv.gz"))


# -- adapter ---------------------------------------------------------------------------
def fixture_paths() -> list[Path]:
    return [FIX / "bid" / "2024-03.csv.gz", FIX / "ask" / "2024-03.csv.gz"]


def adapt(paths: list[Path], cfg: DukascopyConfig | None = None) -> tuple[pl.DataFrame, object]:
    return DukascopyAdapter(cfg or DukascopyConfig(max_one_sided_share=0.02)).to_canonical(
        paths, series="h1", symbol="EURUSD", instrument="eurusd", asset_class="fx"
    )


def test_F_0_1_3_mid_and_spread_math() -> None:
    df, meta = adapt(fixture_paths())
    bid = pl.read_csv(FIX / "bid" / "2024-03.csv.gz")
    ask = pl.read_csv(FIX / "ask" / "2024-03.csv.gz")
    j = bid.join(ask, on="timestamp", suffix="_a")
    first = df.row(0, named=True)
    b, a = j.row(0, named=True), j.row(0, named=True)
    for c in ("open", "high", "low", "close"):
        assert first[c] == pytest.approx((b[c] + a[f"{c}_a"]) / 2)
    assert first["spread"] == pytest.approx(a["close_a"] - b["close"])
    assert first["volume"] == b["volume"]  # bid-side volume
    assert (df["spread"] >= 0).all()
    assert validate_bars(df, meta) == []  # type: ignore[arg-type]


def test_F_0_1_3_utc_bar_start_and_weekend_gap() -> None:
    df, _ = adapt(fixture_paths())
    ts = df["ts"]
    assert ts.dtype == pl.Datetime("us", "UTC")
    assert ts.min() == dt.datetime(2024, 3, 8, 0, tzinfo=dt.UTC)  # bar start, not end
    assert ts.dt.weekday().filter(ts.dt.weekday() == 6).len() == 0  # no Saturday bars
    sunday = ts.filter(ts.dt.weekday() == 7)
    assert sunday.min() == dt.datetime(2024, 3, 10, 21, tzinfo=dt.UTC)  # DST-shifted open
    friday = ts.filter(ts.dt.date() == dt.date(2024, 3, 8))
    assert friday.max() == dt.datetime(2024, 3, 8, 21, tzinfo=dt.UTC)


def test_F_0_1_3_one_sided_bars_rule() -> None:
    df, meta = adapt(fixture_paths())  # 1 of 73 one-sided, limit 2 %
    assert dt.datetime(2024, 3, 11, 3, tzinfo=dt.UTC) not in df["ts"].to_list()
    assert "One-sided bars dropped: 1." in meta.notes  # type: ignore[attr-defined]
    with pytest.raises(DataError, match="one side only"):
        adapt(fixture_paths(), DukascopyConfig())  # default limit 0.1 %


def test_F_0_1_3_negative_spread_is_critical(tmp_path: Path) -> None:
    for side in ("bid", "ask"):
        (tmp_path / side).mkdir()
    (tmp_path / "bid" / "2024-03.csv.gz").write_bytes(
        gzip.compress(b"timestamp,open,high,low,close,volume\n1704153600000,1.1,1.2,1.0,1.15,1\n")
    )
    (tmp_path / "ask" / "2024-03.csv.gz").write_bytes(
        gzip.compress(b"timestamp,open,high,low,close,volume\n1704153600000,1.1,1.2,1.0,1.14,1\n")
    )
    with pytest.raises(DataError, match="negative spread"):
        adapt([tmp_path / "bid" / "2024-03.csv.gz", tmp_path / "ask" / "2024-03.csv.gz"])


def test_F_0_1_3_utc_offset_from_manifest_is_corrected(tmp_path: Path) -> None:
    for side in ("bid", "ask"):
        d = tmp_path / side
        d.mkdir()
        shutil.copy(FIX / side / "2024-03.csv.gz", d / "2024-03.csv.gz")
        (d / "2024-03.csv.gz.manifest.json").write_text(
            json.dumps({"utc_offset_minutes": 120}), encoding="utf-8"
        )
    df, _ = adapt([tmp_path / "bid" / "2024-03.csv.gz", tmp_path / "ask" / "2024-03.csv.gz"])
    assert df["ts"].min() == dt.datetime(2024, 3, 7, 22, tzinfo=dt.UTC)


def test_F_0_1_3_metadata() -> None:
    _, meta = adapt(fixture_paths())
    m = meta  # type: ignore[assignment]
    assert (m.source, m.price_type, m.session, m.bar_label) == ("dukascopy", "mid", "24x5", "start")  # type: ignore[attr-defined]
    assert (m.adjustment, m.volume_quality, m.feed, m.timeframe) == ("raw", "partial", "none", "1H")  # type: ignore[attr-defined]
    assert (m.symbol, m.source_symbol, m.asset_class) == ("EURUSD", "eurusd", "fx")  # type: ignore[attr-defined]
    assert "approximation" in m.notes and len(m.raw_refs) == 2  # type: ignore[attr-defined]


class ThrottledRunner(FakeRunner):
    """Fails with HTTP 429 ``fails`` times, then succeeds."""

    def __init__(self, fails: int) -> None:
        super().__init__()
        self.fails = fails

    def __call__(self, cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        if self.fails > 0:
            self.fails -= 1
            self.calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, "", "Request failed with status 429")
        return super().__call__(cmd, cwd, timeout)


def test_F_0_1_3_throttled_month_is_retried_with_backoff(tmp_path: Path) -> None:
    runner, sleeps = ThrottledRunner(fails=2), []
    rep = dk.run_dukascopy_download(
        [EURUSD], "m1", dt.date(2024, 1, 1), dt.date(2024, 1, 1), tmp_path, CFG, TOOL,
        today=dt.date(2024, 6, 15), runner=runner, sleep=sleeps.append,
    )  # fmt: skip
    assert rep.stored == 2 and not rep.failed
    assert sleeps == [30.0, 60.0]  # config backoff 30 s x 2**attempt


# -- D-673: the bounded OHLC repair -------------------------------------------------------------


def _side(rows: list[tuple[str, float, float, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [dt.datetime.fromisoformat(r[0]).replace(tzinfo=dt.UTC) for r in rows],
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [1.0] * len(rows),
        }
    ).with_columns(pl.col("ts").dt.cast_time_unit("us"))


def test_F_0_1_3_D673_an_excess_within_the_limit_widens_the_range_and_keeps_every_price() -> None:
    side = _side(
        [
            ("2024-10-10 20:00", 1.09344, 1.09376, 1.09286, 1.09285),  # close 1 pip under the low
            ("2024-10-10 21:00", 1.09386, 1.09385, 1.09347, 1.09362),  # open 1 pip over the high
            ("2024-11-01 00:00", 1.08000, 1.08010, 1.07990, 1.08000),  # consistent
        ]
    )
    fixed, counts = repair_ohlc(side, 0.00002)
    assert counts == {"2024-10": 2}
    assert fixed["low"][0] == 1.09285 and fixed["high"][0] == 1.09376
    assert fixed["high"][1] == 1.09386 and fixed["low"][1] == 1.09347
    assert fixed.select("ts", "open", "close", "volume").equals(
        side.select("ts", "open", "close", "volume")
    )  # never an open or close
    assert fixed.row(2) == side.row(2)


def test_F_0_1_3_D673_an_excess_above_the_limit_is_left_for_the_store_to_refuse() -> None:
    side = _side([("2024-10-10 20:00", 1.09344, 1.09376, 1.09286, 1.09283)])  # 3 pips under
    fixed, counts = repair_ohlc(side, 0.00002)
    assert counts == {} and fixed.equals(side)


def test_F_0_1_3_D673_the_adapter_counts_the_repair_per_month_in_the_notes(tmp_path: Path) -> None:
    for side in ("bid", "ask"):
        d = tmp_path / side
        d.mkdir()
        df = pl.read_csv(FIX / side / "2024-03.csv.gz")
        if side == "bid":  # push one close 1 pip under its low
            df = df.with_columns(
                pl.when(pl.int_range(pl.len()) == 5)
                .then(pl.col("low") - 0.00001)
                .otherwise(pl.col("close"))
                .alias("close")
            )
        (d / "2024-03.csv.gz").write_bytes(gzip.compress(df.write_csv().encode("utf-8")))
    bars, meta = adapt([tmp_path / "bid" / "2024-03.csv.gz", tmp_path / "ask" / "2024-03.csv.gz"])
    assert "OHLC repair (D-673): 1 side bar(s)" in meta.notes
    assert "2024-03: bid 1, ask 0" in meta.notes
    assert bars.select((pl.col("low") <= pl.min_horizontal("open", "close")).all()).item()
    _, clean = adapt(fixture_paths())
    assert "D-673" not in clean.notes  # an untouched series keeps its notes (and its hash)
