"""Synthetic-universe settings (D-654, D-664, D-665): validated models, defaults here (rule 1).

``configs/synthetic/null.yaml`` and ``planted.yaml`` restate the defaults with their decision ids.
A run stores the validated settings **in full** in its config (``PipelineConfig.source``), so the
run hash covers them and a stage never re-reads a file that may have changed since.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from strategy_factory.core.errors import ConfigError

DEFAULT_NULL_CONFIG = Path("configs") / "synthetic" / "null.yaml"
DEFAULT_PLANTED_CONFIG = Path("configs") / "synthetic" / "planted.yaml"

#: A planted cell: (edge type, direction, strength). TF plants are two-sided (D-665): "both".
Cell = tuple[str, str, float]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NullConfig(_Frozen):
    """D-664: the calibrated null ``t_vp`` (T15a plan §2, measured as M1)."""

    #: ``student_t``: unit-variance Student-t, df from the real kurtosis; ``gaussian``: the
    #: sensitivity variant
    innovations: Literal["student_t", "gaussian"] = "student_t"
    df_min: float = Field(default=4.5, gt=4.0)  # t excess kurtosis 6 / (df - 4): finite above 4
    df_max: float = Field(default=60.0, gt=4.0)
    #: the excess kurtosis used for df is at least this (a near-Gaussian series gets df_max)
    kurtosis_floor: float = Field(default=0.1, gt=0)
    #: multiply the innovations by the real series' own causal EWMA volatility path
    vol_path: bool = True
    #: EWMA half-life of the volatility path, in bars of each timeframe
    half_life_bars: dict[str, float] = Field(default_factory=lambda: {"1D": 20.0, "1H": 140.0})
    #: a bar's session slot is its position in its UTC trading date, capped here (1D: one slot)
    slot_cap: dict[str, int] = Field(default_factory=lambda: {"1D": 0, "1H": 6})
    #: draws used to scale the Brownian-bridge wicks so the mean wick equals the real one
    wick_calibration_draws: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def _df_order(self) -> NullConfig:
        if self.df_min > self.df_max:
            raise ValueError("df_min must not exceed df_max")
        return self

    def half_life(self, timeframe: str) -> float:
        return _per_timeframe(self.half_life_bars, timeframe, "half_life_bars")

    def cap(self, timeframe: str) -> int:
        return int(_per_timeframe(self.slot_cap, timeframe, "slot_cap"))


class MrPlant(_Frozen):
    """D-665: a pullback of ``s`` x ATR(14) at an event bar, reverting in equal steps."""

    events_per_year: float = Field(default=12.0, gt=0)
    reversion_bars: int = Field(default=5, ge=1)
    atr_length: int = Field(default=14, ge=1)
    ladder: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0, 6.0)
    directions: tuple[Literal["long", "short"], ...] = ("long", "short")


class TfPlant(_Frozen):
    """D-665: trend segments of both signs, alternating, ``d`` x the bar volatility per bar."""

    segments_per_year: float = Field(default=1.0, gt=0)
    segment_bars: dict[str, int] = Field(default_factory=lambda: {"1D": 60, "1H": 420})
    ladder: tuple[float, ...] = (0.1, 0.2, 0.3, 0.5, 0.8)

    def length(self, timeframe: str) -> int:
        return int(_per_timeframe(self.segment_bars, timeframe, "segment_bars"))


class PlantedConfig(_Frozen):
    """D-665: the null plus a planted edge on an equal share of the scope per cell."""

    base: NullConfig = Field(default_factory=NullConfig)  # the null underneath
    mr: MrPlant = Field(default_factory=MrPlant)
    tf: TfPlant = Field(default_factory=TfPlant)
    #: share of the scope left as the pure null, so a planted run counts its own false positives
    null_share: float = Field(default=0.2, ge=0.0, lt=1.0)
    bars_per_year: dict[str, float] = Field(default_factory=lambda: {"1D": 252.0, "1H": 1764.0})
    #: symbol -> "MR|long|2.0", "TF|both|0.3" or "null"; filled when the funnel resolves its scope
    assignment: dict[str, str] = Field(default_factory=dict)

    def cells(self) -> list[Cell]:
        out: list[Cell] = [("MR", d, s) for d in self.mr.directions for s in self.mr.ladder]
        out += [("TF", "both", d) for d in self.tf.ladder]
        return out

    def per_year(self, timeframe: str) -> float:
        return _per_timeframe(self.bars_per_year, timeframe, "bars_per_year")


def _per_timeframe(table: dict[str, Any], timeframe: str, name: str) -> float:
    if timeframe not in table:
        raise ConfigError(f"synthetic {name} has no value for timeframe {timeframe!r}")
    return float(table[timeframe])


def cell_key(cell: Cell | None) -> str:
    return "null" if cell is None else f"{cell[0]}|{cell[1]}|{cell[2]:g}"


def parse_cell(key: str) -> Cell | None:
    if key == "null":
        return None
    kind, direction, strength = key.split("|")
    return (kind, direction, float(strength))


def _load(path: Path, model: type[BaseModel]) -> Any:
    if not path.is_file():
        raise ConfigError("synthetic config not found", config_path=path)
    try:
        return model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read synthetic config: {exc}", config_path=path) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid synthetic config: {exc}", config_path=path) from exc


def load_null_config(path: Path | None = None) -> NullConfig:
    cfg: NullConfig = _load(path or DEFAULT_NULL_CONFIG, NullConfig)
    return cfg


def load_planted_config(path: Path | None = None) -> PlantedConfig:
    cfg: PlantedConfig = _load(path or DEFAULT_PLANTED_CONFIG, PlantedConfig)
    return cfg
