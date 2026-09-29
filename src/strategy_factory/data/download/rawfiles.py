"""Immutable raw files: versioned names, no overwrite, sha256 manifests, read-only.

A raw file is written to a temporary name and then *hard-linked* to its final name, which
fails if the name exists (on Windows and POSIX), so a completed raw file can never be
overwritten. A re-download of the same chunk goes to ``<stem>.v2<suffix>``, ``.v3`` ... and
older versions are kept.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from strategy_factory.core.env import resolve_env
from strategy_factory.core.errors import ConfigError
from strategy_factory.data.hashing import file_sha256

RAW_ROOT_ENV = "SFAC_RAW_ROOT"
MANIFEST_SUFFIX = ".manifest.json"
_VERSION = re.compile(r"^(?P<base>.+?)(?:\.v(?P<n>\d+))?$")


def raw_root() -> Path:
    """``SFAC_RAW_ROOT`` from the environment or ``.env``; raises ``ConfigError`` if unset."""
    value, _ = resolve_env((RAW_ROOT_ENV,))[RAW_ROOT_ENV]
    if not value:
        raise ConfigError(f"{RAW_ROOT_ENV} is not set: define it in the environment or in .env")
    return Path(value)


def set_read_only(path: Path) -> None:
    path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def version_of(path: Path, suffix: str) -> tuple[str, int]:
    """(base name, version) for ``<base>[.vN]<suffix>``; unversioned = version 1."""
    stem = path.name[: -len(suffix)]
    m = _VERSION.match(stem)
    assert m is not None
    return m.group("base"), int(m.group("n") or 1)


def versions(directory: Path, base: str, suffix: str) -> list[Path]:
    """Existing versions of ``<base><suffix>`` in ``directory``, oldest first."""
    if not directory.is_dir():
        return []
    found = [
        p
        for p in directory.iterdir()
        if p.name.endswith(suffix)
        and not p.name.endswith(MANIFEST_SUFFIX)
        and version_of(p, suffix)[0] == base
    ]
    return sorted(found, key=lambda p: version_of(p, suffix)[1])


def next_version_path(directory: Path, base: str, suffix: str) -> Path:
    existing = versions(directory, base, suffix)
    if not existing:
        return directory / f"{base}{suffix}"
    n = version_of(existing[-1], suffix)[1] + 1
    return directory / f"{base}.v{n}{suffix}"


def manifest_path(data_path: Path) -> Path:
    return data_path.with_name(data_path.name + MANIFEST_SUFFIX)


def write_immutable(data_path: Path, payload: bytes, manifest: dict[str, Any]) -> Path:
    """Write ``payload`` to ``data_path`` (must not exist) plus its manifest; both read-only.

    The manifest gains ``file``, ``sha256`` (of ``payload``), ``size_bytes`` and
    ``written_at``. Raises ``FileExistsError`` instead of overwriting.
    """
    data_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = data_path.with_name(data_path.name + ".partial")
    if tmp.exists():
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp.unlink()
    tmp.write_bytes(payload)
    try:
        os.link(tmp, data_path)  # fails if data_path exists: never overwrite
    finally:
        tmp.unlink()
    set_read_only(data_path)
    full = {
        **manifest,
        "file": data_path.name,
        "sha256": file_sha256(data_path),
        "size_bytes": len(payload),
        "written_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
    mpath = manifest_path(data_path)
    mtmp = mpath.with_name(mpath.name + ".partial")
    mtmp.write_text(json.dumps(full, indent=2, sort_keys=True, default=str), encoding="utf-8")
    try:
        os.link(mtmp, mpath)
    finally:
        mtmp.unlink()
    set_read_only(mpath)
    return data_path


def is_settled(path: Path) -> bool:
    """A raw month file that is finished being written, so it may be read while the download runs.

    ``write_immutable`` writes the payload to ``<name>.partial``, links it to its final name, and
    only then writes the manifest the same way; the manifest is the last thing written. So a month
    counts only when its data file **and** its manifest exist and neither ``.partial`` is left.
    Only the manifest's *existence* is the write-completion marker; its fields never decide
    coverage (D-711)."""
    manifest = manifest_path(path)
    partials = (
        path.with_name(path.name + ".partial"),
        manifest.with_name(manifest.name + ".partial"),
    )
    return path.is_file() and manifest.is_file() and not any(p.exists() for p in partials)


def read_manifest(data_path: Path) -> dict[str, Any] | None:
    mpath = manifest_path(data_path)
    if not mpath.is_file():
        return None
    data: dict[str, Any] = json.loads(mpath.read_text(encoding="utf-8"))
    return data
