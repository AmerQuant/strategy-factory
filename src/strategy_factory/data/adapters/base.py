"""Adapter interface: raw source files -> canonical bars + metadata (F-0.1.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import polars as pl

from strategy_factory.data.schema import SeriesMetadata


@runtime_checkable
class Adapter(Protocol):
    """Converts raw files of one source into the canonical schema.

    Implementations must return bars that pass :func:`~strategy_factory.data.schema.validate_bars`
    without critical issues, with ``ts`` as bar-start UTC, and metadata whose ``raw_refs`` list
    every raw file used (path + sha256).
    """

    def to_canonical(
        self, raw_paths: list[Path], **params: Any
    ) -> tuple[pl.DataFrame, SeriesMetadata]: ...
