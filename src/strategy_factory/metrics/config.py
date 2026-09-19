"""Validated metrics configuration (YAML -> Pydantic).

Defaults live here and are documented in the spec; values are read from
``configs/metrics/default.yaml``. A missing default file means "use the defaults".
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.core.errors import ConfigError

DEFAULT_METRICS_CONFIG = Path("configs") / "metrics" / "default.yaml"


class MetricsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Periods per year used to annualise daily Sharpe/Sortino, keyed by market calendar.
    periods_per_year: dict[str, int] = Field(
        default_factory=lambda: {"us_equity": 252, "24x5": 260}
    )

    def annualisation(self, calendar: str) -> int:
        try:
            value = self.periods_per_year[calendar]
        except KeyError as exc:
            raise ConfigError(f"no periods_per_year for calendar {calendar!r}") from exc
        if value <= 0:
            raise ConfigError(f"periods_per_year for {calendar!r} must be > 0")
        return value


def load_metrics_config(path: Path | None = None) -> MetricsConfig:
    """Load ``configs/metrics/default.yaml`` (or ``path``); defaults if the default is absent."""
    target = path if path is not None else DEFAULT_METRICS_CONFIG
    if not target.is_file():
        if path is not None:
            raise ConfigError("config file not found", config_path=target)
        return MetricsConfig()
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read config: {exc}", config_path=target) from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping", config_path=target)
    try:
        return MetricsConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid metrics config: {exc}", config_path=target) from exc
