"""Exception hierarchy (F-X.10).

Every error can carry the stage, symbol and config file that caused it; when known they
are appended to the message so a failure always says *where* it happened, e.g.::

    DataError: missing cost profile [stage=s03_entry, symbol=US30, config=configs/costs/x.yaml]
"""

from __future__ import annotations

from pathlib import Path


class SfacError(Exception):
    """Base class for all Strategy Factory errors."""

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        symbol: str | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self.message = message
        self.stage = stage
        self.symbol = symbol
        self.config_path = Path(config_path) if config_path is not None else None
        super().__init__(self._render())

    def context(self) -> dict[str, str]:
        """Known context fields, in a fixed order."""
        ctx: dict[str, str] = {}
        if self.stage is not None:
            ctx["stage"] = self.stage
        if self.symbol is not None:
            ctx["symbol"] = self.symbol
        if self.config_path is not None:
            ctx["config"] = self.config_path.as_posix()
        return ctx

    def _render(self) -> str:
        ctx = self.context()
        if not ctx:
            return self.message
        details = ", ".join(f"{k}={v}" for k, v in ctx.items())
        return f"{self.message} [{details}]"

    def __str__(self) -> str:
        return self._render()


class ConfigError(SfacError):
    """Invalid, missing or inconsistent configuration."""


class DataError(SfacError):
    """Market data is missing, malformed or fails a quality check."""


class HoldoutAccessError(SfacError):
    """Holdout accessed outside SplitManager, or accessed a second time for a candidate."""


class RegistryError(SfacError):
    """Trial-registry (PostgreSQL) read/write failure."""


class ExecutorError(SfacError):
    """A work unit failed in the executor (F-0.3.7).

    ``results`` keeps what the finished units returned, in input order, with ``None`` where a
    unit failed, so a long batch does not lose the work that did succeed. ``failed`` maps each
    failed unit's key to its exception.
    """

    def __init__(
        self,
        message: str,
        *,
        results: list[object] | None = None,
        failed: dict[str, BaseException] | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(message, stage=stage)
        self.results: list[object] = results if results is not None else []
        self.failed: dict[str, BaseException] = failed if failed is not None else {}
