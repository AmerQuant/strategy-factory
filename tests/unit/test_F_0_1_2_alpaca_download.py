"""F-0.1.2: Alpaca downloader -- resume, rate limit, retries, immutability, missing, secrets."""

from __future__ import annotations

import csv
import datetime as dt
import logging
import random
from pathlib import Path

import pytest
from fixtures.alpaca_helpers import FakeClient, load_fixture, make_config

from strategy_factory.core.errors import ConfigError
from strategy_factory.data.download import alpaca as dl
from strategy_factory.data.download.ratelimit import (
    GaveUpError,
    PermanentError,
    TLSVerificationError,
    TokenBucket,
    TransientError,
    call_with_retry,
)
from strategy_factory.data.download.rawfiles import read_manifest, write_immutable

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


def run(client: FakeClient, symbols: list[str], tmp_path: Path, **kw: object) -> dl.DownloadReport:
    return dl.run_download(
        client,
        symbols,
        kw.pop("timeframe", "1D"),  # type: ignore[arg-type]
        kw.pop("start", dt.date(2020, 1, 1)),  # type: ignore[arg-type]
        kw.pop("end", dt.date(2020, 12, 31)),  # type: ignore[arg-type]
        tmp_path,
        make_config(),
        now=kw.pop("now", NOW),  # type: ignore[arg-type]
        sleep=lambda s: None,
        rng=random.Random(0),
    )


# -- resume / immutability ---------------------------------------------------------------
def test_F_0_1_2_download_writes_raw_chunks_with_manifest(tmp_path: Path) -> None:
    client = FakeClient(load_fixture("daily_2020.json"))
    report = run(client, ["AAPL", "TSLA"], tmp_path)
    assert report.chunks_written == 2 and report.rows_written == 15
    f = tmp_path / "us_equity" / "alpaca_sip_split" / "1D" / "AAPL" / "2020.parquet"
    m = read_manifest(f)
    assert m is not None
    assert m["complete"] is True and m["row_count"] == 11 and len(m["sha256"]) == 64
    assert m["request"]["feed"] == "sip" and m["request"]["adjustment"] == "split"
    assert client.calls[0][0] == ("AAPL", "TSLA")  # multi-symbol request


def test_F_0_1_2_resume_skips_completed_chunks(tmp_path: Path) -> None:
    client = FakeClient(load_fixture("daily_2020.json"))
    run(client, ["AAPL", "TSLA"], tmp_path)
    again = run(client, ["AAPL", "TSLA"], tmp_path)
    assert again.chunks_written == 0 and again.chunks_skipped == 2
    assert len(client.calls) == 1


def test_F_0_1_2_incomplete_year_is_redownloaded_to_new_version(tmp_path: Path) -> None:
    client = FakeClient(load_fixture("daily_2020.json"))
    run(
        client,
        ["AAPL"],
        tmp_path,
        end=dt.date(2020, 9, 30),
        now=dt.datetime(2020, 10, 1, tzinfo=dt.UTC),
    )
    run(client, ["AAPL"], tmp_path, end=dt.date(2020, 12, 31))
    d = tmp_path / "us_equity" / "alpaca_sip_split" / "1D" / "AAPL"
    names = sorted(p.name for p in d.glob("*.parquet"))
    assert names == ["2020.parquet", "2020.v2.parquet"]
    assert read_manifest(d / "2020.parquet")["complete"] is False  # type: ignore[index]
    assert read_manifest(d / "2020.v2.parquet")["complete"] is True  # type: ignore[index]


def test_F_0_1_2_raw_files_are_never_overwritten(tmp_path: Path) -> None:
    p = tmp_path / "x" / "2020.parquet"
    write_immutable(p, b"first", {"a": 1})
    with pytest.raises(FileExistsError):
        write_immutable(p, b"second", {"a": 2})
    assert p.read_bytes() == b"first"
    with pytest.raises(PermissionError):
        p.write_bytes(b"third")


def test_F_0_1_2_missing_symbols_are_reported(tmp_path: Path) -> None:
    client = FakeClient(load_fixture("daily_2020.json"))
    report = run(client, ["AAPL", "DLSTD"], tmp_path)
    assert report.missing_symbols == ["DLSTD"]
    path = tmp_path / "_reports" / "alpaca_missing_1D.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["symbol"] for r in rows] == ["DLSTD"]
    # the empty chunk is complete -> not requested again
    again = run(client, ["AAPL", "DLSTD"], tmp_path)
    assert again.chunks_written == 0


# -- rate limit / retries ----------------------------------------------------------------
class SimClock:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def test_F_0_1_2_rate_limiter_never_exceeds_budget() -> None:
    clock = SimClock()
    bucket = TokenBucket(180, 10, clock=clock.time, sleep=clock.sleep)
    stamps = []
    for _ in range(1000):
        bucket.acquire()
        stamps.append(clock.t)
    worst = max(sum(1 for s in stamps if t <= s < t + 60.0) for t in stamps)
    assert worst <= 180
    assert stamps[-1] > 290  # 1000 requests need > 5 minutes at 180/min


def test_F_0_1_2_retries_on_429_then_succeeds(tmp_path: Path) -> None:
    client = FakeClient(load_fixture("daily_2020.json"), [TransientError("HTTP 429", 429)] * 2)
    report = run(client, ["AAPL"], tmp_path)
    assert report.chunks_written == 1 and not report.failed_batches
    assert len(client.calls) == 3


def test_F_0_1_2_gives_up_after_retries_and_continues(tmp_path: Path) -> None:
    client = FakeClient(load_fixture("daily_2020.json"), [TransientError("HTTP 503", 503)] * 4)
    report = run(client, ["AAPL", "TSLA"], tmp_path, start=dt.date(2019, 1, 1))
    # 2019 batch fails after 3 retries (4 attempts); 2020 batch succeeds
    assert [b["year"] for b in report.failed_batches] == [2019]
    assert report.chunks_written == 2
    assert report.missing_symbols == []  # failed symbols are not reported as missing


def test_F_0_1_2_backoff_is_exponential_with_jitter_and_capped() -> None:
    sleeps: list[float] = []
    attempts = iter([TransientError("x")] * 5)

    def fn() -> int:
        exc = next(attempts, None)
        if exc:
            raise exc
        return 1

    assert call_with_retry(fn, 5, 1.0, 8.0, sleep=sleeps.append, rng=random.Random(1)) == 1
    bases = [1, 2, 4, 8, 8]
    assert all(0.5 * b <= s < 1.5 * b for s, b in zip(sleeps, bases, strict=True))


def test_F_0_1_2_permanent_error_is_not_retried() -> None:
    calls = []

    def fn() -> None:
        calls.append(1)
        raise PermanentError("HTTP 403", 403)

    with pytest.raises(PermanentError):
        call_with_retry(fn, 5, 1.0, 8.0, sleep=lambda s: None)
    assert len(calls) == 1
    with pytest.raises(GaveUpError):
        call_with_retry(lambda: (_ for _ in ()).throw(TransientError("x")), 0, 1.0, 1.0)


def test_F_0_1_2_tls_error_stops_the_download(tmp_path: Path) -> None:
    client = FakeClient({}, [TLSVerificationError("certificate verify failed")])
    with pytest.raises(TLSVerificationError):
        run(client, ["AAPL"], tmp_path)


# -- secrets -----------------------------------------------------------------------------
FAKE_KEY = "PKFAKEKEY1234567890"
FAKE_SECRET = "fakeSecretValue0987654321abcdef"


def test_F_0_1_2_credentials_only_from_env_and_never_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env
    monkeypatch.delenv(dl.KEY_ENV, raising=False)
    monkeypatch.delenv(dl.SECRET_ENV, raising=False)
    with pytest.raises(ConfigError) as exc:
        dl.load_credentials()
    assert FAKE_KEY not in str(exc.value)

    monkeypatch.setenv(dl.KEY_ENV, FAKE_KEY)
    monkeypatch.setenv(dl.SECRET_ENV, FAKE_SECRET)
    creds = dl.load_credentials()
    assert FAKE_KEY not in repr(creds) and FAKE_SECRET not in repr(creds)

    caplog.set_level(logging.DEBUG)
    logging.getLogger("strategy_factory").propagate = True
    try:
        client = dl.make_client(make_config())  # builds the real alpaca-py client (no request)
        assert client.library_version.startswith("alpaca-py")
        fake = FakeClient(load_fixture("daily_2020.json"), [TransientError("HTTP 429", 429)])
        run(fake, ["AAPL", "DLSTD"], tmp_path)
    finally:
        logging.getLogger("strategy_factory").propagate = False
    assert caplog.records  # something was logged (retry, progress)
    for rec in caplog.records:
        assert FAKE_KEY not in rec.getMessage() and FAKE_SECRET not in rec.getMessage()
    for f in tmp_path.rglob("*.json"):
        text = f.read_text(encoding="utf-8")
        assert FAKE_KEY not in text and FAKE_SECRET not in text
