"""F-X.10: every error names its stage, symbol and config; loggers share one UTC format."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

from strategy_factory.core.errors import (
    ConfigError,
    DataError,
    HoldoutAccessError,
    RegistryError,
    SfacError,
)
from strategy_factory.core.logging import ROOT_LOGGER_NAME, get_logger, setup_logging

ALL_ERRORS = [SfacError, ConfigError, DataError, HoldoutAccessError, RegistryError]


def _sfac_handlers() -> list[logging.Handler]:
    root = logging.getLogger(ROOT_LOGGER_NAME)
    return [h for h in root.handlers if getattr(h, "_sfac_handler", False)]


@pytest.mark.parametrize("cls", ALL_ERRORS)
def test_F_X_10_error_message_includes_stage_symbol_config(cls: type[SfacError]) -> None:
    err = cls(
        "something failed",
        stage="s03_entry",
        symbol="US30",
        config_path=Path("configs") / "costs" / "us30.yaml",
    )
    text = str(err)
    assert text == (
        "something failed [stage=s03_entry, symbol=US30, config=configs/costs/us30.yaml]"
    )
    assert (err.stage, err.symbol, err.message) == ("s03_entry", "US30", "something failed")


def test_F_X_10_error_message_lists_only_known_context() -> None:
    assert str(DataError("bad bar", symbol="AAPL")) == "bad bar [symbol=AAPL]"
    assert str(RegistryError("db down", stage="s02_method")) == "db down [stage=s02_method]"
    assert str(ConfigError("plain")) == "plain"


@pytest.mark.parametrize("cls", ALL_ERRORS[1:])
def test_F_X_10_subclasses_derive_from_base(cls: type[SfacError]) -> None:
    with pytest.raises(SfacError, match=r"\[stage=s00\]"):
        raise cls("x", stage="s00")


def test_F_X_10_get_logger_returns_configured_logger() -> None:
    logger = get_logger("tests.errors")
    assert isinstance(logger, logging.Logger)
    assert logger.name == f"{ROOT_LOGGER_NAME}.tests.errors"
    assert get_logger("strategy_factory.core").name == "strategy_factory.core"
    handlers = _sfac_handlers()
    assert len(handlers) == 1
    fmt = handlers[0].formatter
    assert fmt is not None
    assert fmt.converter(86_400.5) == time.gmtime(86_400.5)  # UTC timestamps


def test_F_X_10_setup_logging_is_idempotent_and_sets_level() -> None:
    setup_logging("DEBUG")
    setup_logging("WARNING")
    assert logging.getLogger(ROOT_LOGGER_NAME).level == logging.WARNING
    assert len(_sfac_handlers()) == 1
    setup_logging("INFO")
    with pytest.raises(ValueError, match="unknown log level"):
        setup_logging("LOUD")


def test_F_X_10_log_line_has_utc_timestamp_level_and_name() -> None:
    setup_logging("INFO")
    formatter = _sfac_handlers()[0].formatter
    assert formatter is not None
    record = logging.LogRecord("strategy_factory.x", logging.INFO, __file__, 1, "hello", None, None)
    record.created = 0.0  # 1970-01-01T00:00:00Z regardless of the machine's timezone
    record.msecs = 0.0
    assert formatter.format(record) == "1970-01-01T00:00:00.000Z INFO     strategy_factory.x: hello"
