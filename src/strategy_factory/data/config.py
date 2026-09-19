"""Validated configuration for the data layer (YAML -> Pydantic).

No decision number lives in code: defaults are defined here, values are read from
``configs/data/*.yaml``. A missing config file means "use the defaults".
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from strategy_factory.core.errors import ConfigError

DEFAULT_ALPACA_CONFIG = Path("configs") / "data" / "alpaca.yaml"


def _hhmm(value: str) -> str:
    try:
        dt.time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"expected HH:MM, got {value!r}") from exc
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RateLimitConfig(_Frozen):
    requests_per_minute: int = Field(default=180, gt=0)
    burst: int = Field(default=10, gt=0)

    @model_validator(mode="after")
    def _burst_below_budget(self) -> RateLimitConfig:
        if self.burst >= self.requests_per_minute:
            raise ValueError("burst must be smaller than requests_per_minute")
        return self


class RetryConfig(_Frozen):
    max_retries: int = Field(default=5, ge=0)
    backoff_base_seconds: float = Field(default=2.0, gt=0)
    backoff_max_seconds: float = Field(default=60.0, gt=0)


class HourlySessionConfig(_Frozen):
    timezone: str = "America/New_York"
    first_bar: str = "09:00"
    regular_close: str = "16:00"
    early_closes_file: Path = Path("configs") / "calendars" / "nyse_early_closes.yaml"

    @field_validator("first_bar", "regular_close")
    @classmethod
    def _times(cls, value: str) -> str:
        return _hhmm(value)


class SplitCheckConfig(_Frozen):
    jump_threshold: float = Field(default=0.40, gt=0)
    match_tolerance: float = Field(default=0.02, gt=0)
    known_splits_file: Path = Path("configs") / "data" / "known_splits.csv"


class AlpacaConfig(_Frozen):
    history_start: dt.date = dt.date(2016, 1, 1)
    feed: Literal["sip"] = "sip"
    adjustment: Literal["split"] = "split"
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    batch_size: dict[str, int] = Field(default_factory=lambda: {"1D": 100, "1H": 10})
    hourly_session: HourlySessionConfig = Field(default_factory=HourlySessionConfig)
    split_check: SplitCheckConfig = Field(default_factory=SplitCheckConfig)

    @field_validator("batch_size")
    @classmethod
    def _batches(cls, value: dict[str, int]) -> dict[str, int]:
        if set(value) != {"1D", "1H"} or any(v <= 0 for v in value.values()):
            raise ValueError("batch_size needs positive values for exactly 1D and 1H")
        return value


class EarlyCloses(_Frozen):
    close_time: str = "13:00"
    dates: tuple[dt.date, ...] = ()

    @field_validator("close_time")
    @classmethod
    def _time(cls, value: str) -> str:
        return _hhmm(value)


class KnownSplit(_Frozen):
    symbol: str
    date: dt.date
    ratio: float = Field(gt=0)
    source: str = ""


def _read_yaml(path: Path) -> dict[str, object]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read config: {exc}", config_path=path) from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping", config_path=path)
    return data


def load_alpaca_config(path: Path | None = None) -> AlpacaConfig:
    """Load ``configs/data/alpaca.yaml`` (or ``path``); defaults if the default file is absent."""
    target = path if path is not None else DEFAULT_ALPACA_CONFIG
    if not target.is_file():
        if path is not None:
            raise ConfigError("config file not found", config_path=target)
        return AlpacaConfig()
    try:
        return AlpacaConfig.model_validate(_read_yaml(target))
    except ValidationError as exc:
        raise ConfigError(f"invalid Alpaca config: {exc}", config_path=target) from exc


def load_early_closes(path: Path) -> EarlyCloses:
    if not path.is_file():
        raise ConfigError("early-close calendar not found", config_path=path)
    try:
        return EarlyCloses.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"invalid early-close calendar: {exc}", config_path=path) from exc


def load_known_splits(path: Path) -> list[KnownSplit]:
    if not path.is_file():
        raise ConfigError("known-splits file not found", config_path=path)
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return [KnownSplit.model_validate(row) for row in csv.DictReader(fh)]
    except ValidationError as exc:
        raise ConfigError(f"invalid known-splits file: {exc}", config_path=path) from exc
