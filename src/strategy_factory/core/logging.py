"""Standard-library logging setup with one consistent, UTC-timestamped format (F-X.10).

Every module obtains its logger through :func:`get_logger`, which places it under the
``strategy_factory`` namespace so a single handler/format applies everywhere.
"""

from __future__ import annotations

import logging
import sys
import time

ROOT_LOGGER_NAME = "strategy_factory"
LOG_FORMAT = "%(asctime)s.%(msecs)03dZ %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
DEFAULT_LEVEL = "INFO"

_HANDLER_ATTR = "_sfac_handler"


def utc_converter(secs: float | None = None) -> time.struct_time:
    """Timestamp converter used by :class:`UTCFormatter` (seconds since epoch -> UTC)."""
    return time.gmtime(secs)


class UTCFormatter(logging.Formatter):
    """Formatter whose timestamps are always UTC (ISO-8601 with a trailing ``Z``)."""

    def __init__(self, fmt: str | None = None, datefmt: str | None = None) -> None:
        super().__init__(fmt, datefmt)
        self.converter = utc_converter


def _parse_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    value = logging.getLevelNamesMapping().get(level.strip().upper())
    if value is None:
        raise ValueError(f"unknown log level: {level!r}")
    return value


def setup_logging(level: str | int = DEFAULT_LEVEL) -> logging.Logger:
    """Configure the ``strategy_factory`` root logger (idempotent) and return it.

    Calling it again only changes the level; it never adds a second handler.
    """
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(_parse_level(level))
    if not any(getattr(h, _HANDLER_ATTR, False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(UTCFormatter(LOG_FORMAT, DATE_FORMAT))
        setattr(handler, _HANDLER_ATTR, True)
        root.addHandler(handler)
    root.propagate = False
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger inside the ``strategy_factory`` namespace.

    ``get_logger(__name__)`` from a package module returns that module's logger; any other
    name is nested under ``strategy_factory.``.
    """
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if not any(getattr(h, _HANDLER_ATTR, False) for h in root.handlers):
        setup_logging()
    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
