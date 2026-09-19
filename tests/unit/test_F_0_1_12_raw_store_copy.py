"""F-0.1.12 (T00b): byte-identical copy into the raw store -- copy, verify, idempotency."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "organize_raw_store.py"


@pytest.fixture(scope="module")
def ors() -> ModuleType:
    spec = importlib.util.spec_from_file_location("organize_raw_store", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _src(tmp_path: Path, content: bytes = b"Date,Open\n2020-01-02,1.5\n") -> Path:
    src = tmp_path / "source" / "us_AAPL.csv"
    src.parent.mkdir(parents=True)
    src.write_bytes(content)
    return src


def test_F_0_1_12_copy_is_byte_identical_and_verified(ors: ModuleType, tmp_path: Path) -> None:
    src = _src(tmp_path)
    dest = tmp_path / "raw" / "us_equity" / "alpaca_sip_all" / "1D" / "us_AAPL.csv"
    res = ors.copy_verified(src, dest)
    assert res.status == "copied"
    assert dest.read_bytes() == src.read_bytes()
    assert res.sha256 == ors.sha256_file(src) == ors.sha256_file(dest)
    assert not dest.with_name(dest.name + ".partial").exists()


def test_F_0_1_12_copy_is_read_only(ors: ModuleType, tmp_path: Path) -> None:
    src = _src(tmp_path)
    dest = tmp_path / "raw" / "x.csv"
    ors.copy_verified(src, dest)
    assert ors.is_read_only(dest)
    with pytest.raises(PermissionError):
        dest.write_bytes(b"tampered")
    assert not ors.is_read_only(src)  # the source is never touched


def test_F_0_1_12_identical_existing_file_is_skipped(ors: ModuleType, tmp_path: Path) -> None:
    src = _src(tmp_path)
    dest = tmp_path / "raw" / "x.csv"
    ors.copy_verified(src, dest)
    mtime = dest.stat().st_mtime_ns
    res = ors.copy_verified(src, dest)
    assert res.status == "identical"
    assert dest.stat().st_mtime_ns == mtime  # not rewritten


def test_F_0_1_12_differing_existing_file_is_an_error(ors: ModuleType, tmp_path: Path) -> None:
    src = _src(tmp_path)
    dest = tmp_path / "raw" / "x.csv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"Date,Open\n2020-01-02,9.9\n")
    with pytest.raises(ors.CopyConflictError):
        ors.copy_verified(src, dest)
    assert dest.read_bytes() == b"Date,Open\n2020-01-02,9.9\n"  # never overwritten


def test_F_0_1_12_same_size_different_content_is_an_error(ors: ModuleType, tmp_path: Path) -> None:
    src = _src(tmp_path, b"abc")
    dest = tmp_path / "raw" / "x.csv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"abd")
    with pytest.raises(ors.CopyConflictError):
        ors.copy_verified(src, dest)


def test_F_0_1_12_source_integrity_detects_changes(ors: ModuleType, tmp_path: Path) -> None:
    src = _src(tmp_path)
    other = src.parent / "us_MSFT.csv"
    other.write_bytes(b"x")
    before = ors.snapshot_roots([src.parent])
    assert ors.compare_snapshots(before, ors.snapshot_roots([src.parent])) == {
        "changed": [],
        "added": [],
        "removed": [],
    }
    src.write_bytes(b"changed content, different size")
    other.unlink()
    (src.parent / "new.csv").write_bytes(b"y")
    diff = ors.compare_snapshots(before, ors.snapshot_roots([src.parent]))
    assert diff["changed"] == [str(src)]
    assert diff["removed"] == [str(other)]
    assert diff["added"] == [str(src.parent / "new.csv")]
