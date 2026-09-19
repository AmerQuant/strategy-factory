"""Resolve environment settings from the process environment or a local ``.env`` file.

Only a minimal ``KEY=VALUE`` parser is needed (no extra dependency): blank lines and
``#`` comments are skipped, an optional ``export`` prefix and matching quotes are stripped.
Process environment variables take precedence over ``.env``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

ENV_KEYS = ("SFAC_DATA_ROOT", "SFAC_ARTIFACTS_ROOT", "SFAC_DB_URL")


def parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a ``.env`` file; a missing file yields an empty dict."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def resolve_env(
    keys: tuple[str, ...] = ENV_KEYS,
    dotenv_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, tuple[str | None, str]]:
    """Return ``{key: (value, origin)}``; origin is ``environment``, ``.env`` or ``not set``."""
    env = os.environ if environ is None else environ
    dotenv = parse_dotenv(dotenv_path if dotenv_path is not None else Path.cwd() / ".env")
    out: dict[str, tuple[str | None, str]] = {}
    for key in keys:
        if env.get(key):
            out[key] = (env[key], "environment")
        elif dotenv.get(key):
            out[key] = (dotenv[key], ".env")
        else:
            out[key] = (None, "not set")
    return out
