"""Validated configuration for the data layer (YAML -> Pydantic).

No decision number lives in code: defaults are defined here, values are read from
``configs/data/*.yaml``. A missing config file means "use the defaults".
"""

from __future__ import annotations

import csv
import datetime as dt
import zoneinfo
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
from strategy_factory.data.relisting import DEFAULT_FROZEN_SESSIONS, DEFAULT_GAP_DAYS
from strategy_factory.data.schema import Severity

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
    sessions_file: Path = Path("configs") / "calendars" / "nyse_sessions.csv"

    @field_validator("first_bar", "regular_close")
    @classmethod
    def _times(cls, value: str) -> str:
        return _hhmm(value)


class SplitCheckConfig(_Frozen):
    jump_threshold: float = Field(default=0.40, gt=0)
    match_tolerance: float = Field(default=0.02, gt=0)
    #: D-399/T04k: how far the cross-check may look for a bar on its own side of a break.
    crosscheck_window_days: int = Field(default=7, ge=0)
    known_splits_file: Path = Path("configs") / "data" / "known_splits.csv"


class RelistingConfig(_Frozen):
    """Thresholds of the re-used-ticker / frozen-stretch rule (D-383, amended by **D-398**).

    They are here and not in the analysis script because D-398 makes the frozen-stretch removal a
    rule of the data itself (T04k applies it), and no threshold may live in code
    (``CLAUDE.md`` rule 1).
    """

    frozen_min_sessions: int = Field(default=DEFAULT_FROZEN_SESSIONS, gt=0)
    gap_days: int = Field(default=DEFAULT_GAP_DAYS, gt=0)
    #: D-700: a rename away from the ticker agrees with the boundary when it lies in
    #: ``[break start - rename_window_days, boundary]``.
    rename_window_days: int = Field(default=7, ge=0)
    #: D-700 evidence, both under ``SFAC_RAW_ROOT`` (read-only, D-028).
    names_file: Path = Path("reference") / "alpaca" / "alpaca_assets_2026-09-20.v2.csv"
    name_changes_file: Path = (
        Path("reference") / "alpaca" / "corporate_actions" / "name_changes_20260920.json"
    )


GatedTimeframe = Literal["1D", "1H"]


def _hourly_only() -> list[GatedTimeframe]:
    return ["1H"]


class CoverageConfig(_Frozen):
    """The raw coverage gate in front of an ingest (T04h, D-386, P-62: no ``--allow-gaps``)."""

    #: Timeframes whose ingest refuses to run on a gap. 1D was ingested by T04g without a gate;
    #: **1H is always gated** -- a config without it is refused, so the gate cannot be switched off.
    gate_timeframes: list[GatedTimeframe] = Field(default_factory=_hourly_only)
    #: Where a symbol's required years start. ``history_start`` (default): every year from
    #: ``history_start`` -- the downloader writes an empty file for a year before a listing, so a
    #: later listing still has its files. ``first_data_year`` starts at the first year with a bar;
    #: it cannot see a missing *leading* year and is only for a source that writes no empty files.
    require_from: Literal["history_start", "first_data_year"] = "history_start"

    @field_validator("gate_timeframes")
    @classmethod
    def _hourly_gated(cls, value: list[GatedTimeframe]) -> list[GatedTimeframe]:
        if "1H" not in value:
            raise ValueError("coverage.gate_timeframes must include 1H (D-386, P-62)")
        return value


class ReuseConfig(_Frozen):
    """T04l (D-705, D-708, D-709, D-713): re-used tickers decided by CUSIP.

    The gap that makes a candidate is ``relisting.gap_days`` (D-708: no price-jump condition) and
    the arriving-holder window is ``relisting.rename_window_days`` (D-712); this block only says
    where the evidence is."""

    #: The corporate-action files (D-710), under ``SFAC_RAW_ROOT`` (read-only, D-028).
    corporate_actions_dir: Path = Path("reference") / "alpaca" / "corporate_actions"


class AlpacaConfig(_Frozen):
    history_start: dt.date = dt.date(2016, 1, 1)
    feed: Literal["sip"] = "sip"
    adjustment: Literal["split"] = "split"
    daily_session: Literal["exchange", "RTH"] = "exchange"
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    batch_size: dict[str, int] = Field(default_factory=lambda: {"1D": 100, "1H": 10})
    hourly_session: HourlySessionConfig = Field(default_factory=HourlySessionConfig)
    split_check: SplitCheckConfig = Field(default_factory=SplitCheckConfig)
    relisting: RelistingConfig = Field(default_factory=RelistingConfig)
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)
    reuse: ReuseConfig = Field(default_factory=ReuseConfig)

    @field_validator("batch_size")
    @classmethod
    def _batches(cls, value: dict[str, int]) -> dict[str, int]:
        if set(value) != {"1D", "1H"} or any(v <= 0 for v in value.values()):
            raise ValueError("batch_size needs positive values for exactly 1D and 1H")
        return value


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


def load_known_splits(path: Path) -> list[KnownSplit]:
    if not path.is_file():
        raise ConfigError("known-splits file not found", config_path=path)
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return [KnownSplit.model_validate(row) for row in csv.DictReader(fh)]
    except ValidationError as exc:
        raise ConfigError(f"invalid known-splits file: {exc}", config_path=path) from exc


DEFAULT_DUKASCOPY_CONFIG = Path("configs") / "data" / "dukascopy.yaml"


class DukascopyToolConfig(_Frozen):
    """Flags passed to the pinned dukascopy-node CLI (recorded in every manifest)."""

    directory: Path = Path("tools") / "dukascopy"
    retries: int = Field(default=3, ge=0)
    retry_pause_ms: int = Field(default=1000, ge=0)
    batch_size: int = Field(default=10, gt=0)
    batch_pause_ms: int = Field(default=1000, ge=0)
    volume_units: Literal["millions", "thousands", "units"] = "units"
    utc_offset_minutes: int = 0
    timeout_seconds: int = Field(default=900, gt=0)
    call_retries: int = Field(default=3, ge=0)
    call_backoff_seconds: float = Field(default=30.0, ge=0)


class VerifiedEvent(_Frozen):
    """A flagged bar confirmed as a real market move (D-672): kept unchanged, reported by the D-717
    re-measure and never a stop. Correcting or removing it would make backtests optimistic."""

    symbol: str
    ts: dt.datetime  # the bar's start, UTC
    family: Literal["wick_flags"]
    source: str  # what verifies it
    decision: str  # the decision that admits it


class DukascopyConfig(_Frozen):
    h1_start: dt.date = dt.date(2010, 1, 1)
    m1_months: int = Field(default=24, gt=0)
    universe_file: Path = Path("configs") / "universe" / "dukascopy.csv"
    max_one_sided_share: float = Field(default=0.001, ge=0)
    tool: DukascopyToolConfig = Field(default_factory=DukascopyToolConfig)
    verified_events: tuple[VerifiedEvent, ...] = ()


def load_dukascopy_config(path: Path | None = None) -> DukascopyConfig:
    """Load ``configs/data/dukascopy.yaml`` (or ``path``); defaults if that file is absent."""
    target = path if path is not None else DEFAULT_DUKASCOPY_CONFIG
    if not target.is_file():
        if path is not None:
            raise ConfigError("config file not found", config_path=target)
        return DukascopyConfig()
    try:
        return DukascopyConfig.model_validate(_read_yaml(target))
    except ValidationError as exc:
        raise ConfigError(f"invalid Dukascopy config: {exc}", config_path=target) from exc


DEFAULT_YAHOO_CONFIG = Path("configs") / "data" / "yahoo.yaml"


class YahooConfig(_Frozen):
    """yfinance call parameters and politeness settings (T04c)."""

    universe_file: Path = Path("configs") / "universe" / "aux_yahoo.csv"
    period: str = "max"
    interval: Literal["1d"] = "1d"
    auto_adjust: Literal[False] = False
    actions: Literal[False] = False
    pause_seconds: float = Field(default=2.0, ge=0)
    retry: RetryConfig = Field(
        default_factory=lambda: RetryConfig(
            max_retries=3, backoff_base_seconds=5.0, backoff_max_seconds=60.0
        )
    )

    def call_params(self) -> dict[str, object]:
        """Explicit keyword arguments for ``yfinance.Ticker.history``."""
        return {
            "period": self.period,
            "interval": self.interval,
            "auto_adjust": self.auto_adjust,
            "actions": self.actions,
        }


def load_yahoo_config(path: Path | None = None) -> YahooConfig:
    """Load ``configs/data/yahoo.yaml`` (or ``path``); defaults if that file is absent."""
    target = path if path is not None else DEFAULT_YAHOO_CONFIG
    if not target.is_file():
        if path is not None:
            raise ConfigError("config file not found", config_path=target)
        return YahooConfig()
    try:
        return YahooConfig.model_validate(_read_yaml(target))
    except ValidationError as exc:
        raise ConfigError(f"invalid Yahoo config: {exc}", config_path=target) from exc


DEFAULT_AUX_CONFIG = Path("configs") / "data" / "aux_series.yaml"


class AuxAsOfConfig(_Frozen):
    """As-of join rules for auxiliary series (F-0.1.11, D-014, D-719)."""

    unverified_extra_lag_days: int = Field(default=1, ge=0)
    # D-719: how many traded sessions of the consuming symbol may pass after an aux value became
    # usable before it is too stale to use (addendum section 5.3: 5).
    max_stale_sessions: int = Field(default=5, ge=0)
    sessions_file: Path = Path("configs") / "calendars" / "nyse_sessions.csv"


class AuxConfig(_Frozen):
    aux: AuxAsOfConfig = Field(default_factory=AuxAsOfConfig)


def load_aux_config(path: Path | None = None) -> AuxConfig:
    """Load ``configs/data/aux_series.yaml`` (or ``path``); defaults if that file is absent."""
    target = path if path is not None else DEFAULT_AUX_CONFIG
    if not target.is_file():
        if path is not None:
            raise ConfigError("config file not found", config_path=target)
        return AuxConfig()
    try:
        return AuxConfig.model_validate(_read_yaml(target))
    except ValidationError as exc:
        raise ConfigError(f"invalid aux config: {exc}", config_path=target) from exc


# --------------------------------------------------------------------------------------
# T05: expected schedules, quality checks, resampling, split (F-0.1.6, F-0.1.7, F-0.6.1)
# --------------------------------------------------------------------------------------
_WEEKDAYS = {"MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 7}


def _iana(value: str) -> str:
    try:
        zoneinfo.ZoneInfo(value)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA time zone {value!r}") from exc
    return value


def week_minute(value: str) -> int:
    """Minutes since Monday 00:00 of a ``DDD HH:MM`` value (e.g. ``SUN 17:00``)."""
    day, _, hhmm = value.partition(" ")
    t = dt.time.fromisoformat(hhmm)
    return (_WEEKDAYS[day.upper()] - 1) * 1440 + t.hour * 60 + t.minute


class WeeklyWindowConfig(_Frozen):
    """Trading week of the 24x5 markets (fx, metal, energy_cfd, index_cfd), in local time.

    A bar is expected when its local start lies in ``[week_open, week_close)`` and its local
    hour is not the daily break (learned from the data).
    """

    timezone: str = "America/New_York"
    week_open: str = "SUN 17:00"
    week_close: str = "FRI 17:00"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return _iana(value)

    @field_validator("week_open", "week_close")
    @classmethod
    def _day_time(cls, value: str) -> str:
        day, _, hhmm = value.partition(" ")
        if day.upper() not in _WEEKDAYS:
            raise ValueError(f"expected 'DDD HH:MM' (e.g. 'SUN 17:00'), got {value!r}")
        _hhmm(hhmm)
        return value


class BreakDetectionConfig(_Frozen):
    """Learning the daily break of 24x5 markets from the data."""

    min_share: float = Field(default=0.5, gt=0, le=1)
    max_gap_hours: int = Field(default=3, gt=0)


class MissingBarsConfig(_Frozen):
    warning_above_pct: float = Field(default=2.0, ge=0)


class SchemaCheckConfig(_Frozen):
    severity: Severity = "critical"


class PriceSpikeConfig(_Frozen):
    window: int = Field(default=50, gt=2)
    k: float = Field(default=15.0, gt=0)
    reversal_fraction: float = Field(default=0.5, gt=0)
    severity: Severity = "warning"


class StalePriceConfig(_Frozen):
    min_run: int = Field(default=5, ge=2)
    severity: Severity = "warning"


class ZeroVolumeConfig(_Frozen):
    warning_above_share: float = Field(default=0.05, ge=0, le=1)


class DstCheckConfig(_Frozen):
    window_days: int = Field(default=10, gt=0)
    severity: Severity = "warning"


class SessionViolationConfig(_Frozen):
    severity: Severity = "warning"


class DailyWickOutlierConfig(_Frozen):
    """A wick beyond the body by **both** ``k1_atr`` x ATR(14) and ``k2_pct`` % (D-396).

    Both conditions, never one: a wide-but-real day exceeds the percentage and not the ATR
    multiple, a bad print exceeds both. T04g measured 931 daily snapshots whose only failing check
    is ``price_spikes``, which is the population this check is aimed at.
    """

    #: A multiple of the **body-range** ATR (D-703), not of the true-range ATR.
    k1_atr: float = Field(default=9.0, gt=0)
    k2_pct: float = Field(default=10.0, gt=0)
    #: D-703: the ATR is of **body ranges** (|open - close|), so clipping cannot move it.
    atr_length: int = Field(default=14, gt=0)
    #: D-703: `wick_clip` iterates to a fixed point, at most this many passes.
    max_passes: int = Field(default=3, gt=0)
    severity: Severity = "warning"


class DailyExtremeUnsupportedConfig(_Frozen):
    """A daily extreme the hourly feed does not support (D-396), where hourly data exists.

    ``eps_bps`` is the same noise floor the T04i breach analysis uses: below it the difference
    between the two feeds is rounding, not a price level. A day whose hourly side is short
    (``incomplete_hourly_day``) or absent (``no_raw_hours``) is **never** flagged and never
    corrected -- the hourly series is not evidence there (supervisor, 2026-09-21).
    """

    eps_bps: float = Field(default=0.05, gt=0)
    severity: Severity = "warning"


class KnownSpliceConfig(_Frozen):
    """D-709: a snapshot carrying an unsettled re-use boundary (``full_history`` marker)."""

    severity: Severity = "warning"


class QualityConfig(_Frozen):
    weekly_window: WeeklyWindowConfig = Field(default_factory=WeeklyWindowConfig)
    break_detection: BreakDetectionConfig = Field(default_factory=BreakDetectionConfig)
    missing_bars: MissingBarsConfig = Field(default_factory=MissingBarsConfig)
    schema_checks: SchemaCheckConfig = Field(default_factory=SchemaCheckConfig)
    price_spikes: PriceSpikeConfig = Field(default_factory=PriceSpikeConfig)
    stale_prices: StalePriceConfig = Field(default_factory=StalePriceConfig)
    zero_volume: ZeroVolumeConfig = Field(default_factory=ZeroVolumeConfig)
    dst: DstCheckConfig = Field(default_factory=DstCheckConfig)
    session_violations: SessionViolationConfig = Field(default_factory=SessionViolationConfig)
    daily_wick_outlier: DailyWickOutlierConfig = Field(default_factory=DailyWickOutlierConfig)
    daily_extreme_unsupported: DailyExtremeUnsupportedConfig = Field(
        default_factory=DailyExtremeUnsupportedConfig
    )
    known_splice: KnownSpliceConfig = Field(default_factory=KnownSpliceConfig)
    sessions_file: Path = Path("configs") / "calendars" / "nyse_sessions.csv"
    # D-720: US bond-market closures on NYSE sessions (the `nyse_bond` aux calendar, TNX)
    bond_closures_file: Path = Path("configs") / "calendars" / "us_bond_market_closures.csv"
    us_equity_timezone: str = "America/New_York"
    us_equity_first_bar: str = "09:00"

    @field_validator("us_equity_first_bar")
    @classmethod
    def _first_bar(cls, value: str) -> str:
        return _hhmm(value)

    @field_validator("us_equity_timezone")
    @classmethod
    def _eq_tz(cls, value: str) -> str:
        return _iana(value)


class BrokerSessionConfig(_Frozen):
    """Session start of the ``broker_session`` resampling mode (parity tests only)."""

    timezone: str = "America/New_York"
    start: str = "17:00"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return _iana(value)

    @field_validator("start")
    @classmethod
    def _start(cls, value: str) -> str:
        return _hhmm(value)


class ResampleConfig(_Frozen):
    min_source_fraction: float = Field(default=0.5, gt=0, le=1)
    broker_session: BrokerSessionConfig = Field(default_factory=BrokerSessionConfig)


class SplitConfig(_Frozen):
    holdout_fraction: float = Field(default=0.20, gt=0, lt=1)
    holdout_min_months: int = Field(default=18, ge=1)
    max_lookback_bars: int = Field(default=200, ge=0)
    max_holding_bars: int = Field(default=50, ge=0)
    min_expected_holdout_trades: float = Field(default=30, ge=0)

    @property
    def embargo_bars(self) -> int:
        """Embargo = max indicator lookback + max holding period (bars)."""
        return self.max_lookback_bars + self.max_holding_bars


DEFAULT_QUALITY_CONFIG = Path("configs") / "data" / "quality.yaml"
DEFAULT_RESAMPLE_CONFIG = Path("configs") / "data" / "resample.yaml"
DEFAULT_SPLIT_CONFIG = Path("configs") / "data" / "split.yaml"


def _load_model[M: BaseModel](model: type[M], default: Path, path: Path | None, label: str) -> M:
    target = path if path is not None else default
    if not target.is_file():
        if path is not None:
            raise ConfigError("config file not found", config_path=target)
        return model()
    try:
        return model.model_validate(_read_yaml(target))
    except ValidationError as exc:
        raise ConfigError(f"invalid {label} config: {exc}", config_path=target) from exc


def load_quality_config(path: Path | None = None) -> QualityConfig:
    """Load ``configs/data/quality.yaml`` (or ``path``); defaults if that file is absent."""
    return _load_model(QualityConfig, DEFAULT_QUALITY_CONFIG, path, "quality")


def load_resample_config(path: Path | None = None) -> ResampleConfig:
    """Load ``configs/data/resample.yaml`` (or ``path``); defaults if that file is absent."""
    return _load_model(ResampleConfig, DEFAULT_RESAMPLE_CONFIG, path, "resample")


def load_split_config(path: Path | None = None) -> SplitConfig:
    """Load ``configs/data/split.yaml`` (or ``path``); defaults if that file is absent."""
    return _load_model(SplitConfig, DEFAULT_SPLIT_CONFIG, path, "split")
