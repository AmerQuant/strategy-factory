"""Report settings (D-655, D-666, D-668): defaults here (rule 1), restated in
``configs/reports/funnel.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.core.errors import ConfigError

DEFAULT_REPORT_CONFIG = Path("configs") / "reports" / "funnel.yaml"
#: inside the package, so the report builds from any working directory
FONTS = Path(__file__).resolve().parent / "assets" / "fonts"


class ReportConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_candidate_sections: int = Field(default=40, ge=1)  # D-668
    spp_bins: int = Field(default=30, ge=2)
    heatmap_max_symbols: int = Field(default=600, ge=1)
    font_file: Path = FONTS / "Vazirmatn-VariableFont_wght.ttf"  # D-666
    font_licence: Path = FONTS / "OFL.txt"
    #: D-656: T15b's target on the calibrated null, printed on a null run's first page
    null_target_share: float = Field(default=0.01, gt=0, lt=1)


def load_report_config(path: Path | None = None) -> ReportConfig:
    target = path or DEFAULT_REPORT_CONFIG
    if not target.is_file():
        if path is not None:  # an explicit config that is missing is an error
            raise ConfigError("report config not found", config_path=path)
        return ReportConfig()
    try:
        return ReportConfig.model_validate(yaml.safe_load(target.read_text(encoding="utf-8")) or {})
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read report config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid report config: {exc}", config_path=target) from exc
