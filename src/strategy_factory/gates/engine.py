"""Declarative gate engine (F-0.8.1).

Gates live in YAML (``configs/gates/default.yaml``)::

    borderline_tolerance: 0.10
    stages:
      s01_edge:
        - {metric: ess, op: ">=", threshold: 50}
    overrides:
      asset_class: {fx: {s01_edge: [...]}}
      timeframe:   {1H: {s01_probe: [{metric: min_trades, op: ">=", threshold: 100}]}}
      combined:    {"fx/1H": {...}}

An override criterion **replaces** the base criterion with the same metric or is **added**.
Precedence: base < asset_class < timeframe < combined (``"<asset_class>/<timeframe>"``).

:meth:`GateEngine.evaluate` returns one :class:`CriterionResult` per criterion. A missing
(or NaN) metric is a failure with reason ``metric_missing`` (``metric_nan``), never a pass.

**Metric names (D-309, T10b):** :func:`load_gate_config` validates every metric of every
stage and every override against the one registry in
:mod:`strategy_factory.metrics.names`. An unknown metric is a :class:`ConfigError` at load
time, so a typo can never silently become a permanently failing ``metric_missing`` criterion.
:class:`GateConfig` built in code is not checked, so tests and experiments can use synthetic
names; :func:`validate_metric_names` is the check itself.

**Borderline (spec, stage 8 decisions):** exactly one failed criterion, it is not critical,
and its value lies within ``borderline_tolerance`` (relative) of its threshold. A result with
any critical failure is never borderline. A threshold of 0 has no relative distance, so such
a failure is never borderline.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from strategy_factory.core.errors import ConfigError

Op = Literal[">=", "<=", ">", "<", "=="]
OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}
DEFAULT_GATES = Path("configs") / "gates" / "default.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GateCriterion(_Frozen):
    metric: str = Field(min_length=1)
    op: Op
    threshold: float
    critical: bool = False
    note: str = ""


StageGates = dict[str, tuple[GateCriterion, ...]]


class GateOverrides(_Frozen):
    asset_class: dict[str, StageGates] = Field(default_factory=dict)
    timeframe: dict[str, StageGates] = Field(default_factory=dict)
    combined: dict[str, StageGates] = Field(default_factory=dict)  # "fx/1H"

    @field_validator("combined")
    @classmethod
    def _combined_keys(cls, value: dict[str, StageGates]) -> dict[str, StageGates]:
        for key in value:
            if key.count("/") != 1:
                raise ValueError(f"combined override key must be 'asset_class/timeframe': {key!r}")
        return value


class GateConfig(_Frozen):
    borderline_tolerance: float = Field(default=0.10, ge=0)
    stages: StageGates
    overrides: GateOverrides = Field(default_factory=GateOverrides)

    @field_validator("stages")
    @classmethod
    def _unique_metrics(cls, value: StageGates) -> StageGates:
        for stage, crits in value.items():
            names = [c.metric for c in crits]
            if len(names) != len(set(names)):
                raise ValueError(f"stage {stage!r} lists a metric twice")
        return value


def metrics_used(cfg: GateConfig) -> dict[str, list[str]]:
    """Metric name -> where it is used (``stage`` / ``asset_class:fx/stage`` ...), sorted."""
    used: dict[str, list[str]] = {}
    layers: list[tuple[str, StageGates]] = [("", cfg.stages)]
    ov = cfg.overrides
    for kind, table in (
        ("asset_class", ov.asset_class),
        ("timeframe", ov.timeframe),
        ("combined", ov.combined),
    ):
        layers += [(f"{kind}:{key}/", stages) for key, stages in table.items()]
    for prefix, stages in layers:
        for stage, crits in stages.items():
            for crit in crits:
                used.setdefault(crit.metric, []).append(f"{prefix}{stage}")
    return {name: sorted(where) for name, where in sorted(used.items())}


def validate_metric_names(cfg: GateConfig, config_path: Path | None = None) -> None:
    """Every metric of ``cfg`` must be in the metric-name registry (D-309)."""
    from strategy_factory.metrics import names as metric_names

    used = metrics_used(cfg)
    unknown = metric_names.unknown(used)
    if unknown:
        detail = "; ".join(f"{name} (in {', '.join(used[name])})" for name in unknown)
        raise ConfigError(
            f"unknown metric(s) in the gate config: {detail}. Every gate metric must be "
            "registered in strategy_factory.metrics.names (D-309)",
            config_path=config_path,
        )


def load_gate_config(path: Path | None = None) -> GateConfig:
    target = path if path is not None else DEFAULT_GATES
    if not target.is_file():
        raise ConfigError("gate config not found", config_path=target)
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        cfg = GateConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read gate config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid gate config: {exc}", config_path=target) from exc
    validate_metric_names(cfg, target)
    return cfg


class CriterionResult(_Frozen):
    metric: str
    op: Op
    threshold: float
    value: float | None
    passed: bool
    critical: bool
    reason: str


class GateResult(_Frozen):
    candidate_id: str
    stage: str
    items: tuple[CriterionResult, ...]
    passed: bool
    borderline: bool

    def failed(self) -> list[CriterionResult]:
        return [i for i in self.items if not i.passed]


class HasId(Protocol):
    @property
    def id(self) -> str: ...


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)


def check(criterion: GateCriterion, value: Any) -> CriterionResult:
    """Evaluate one criterion; missing and NaN values fail with a reason."""
    v = _as_float(value)

    def result(passed: bool, reason: str) -> CriterionResult:
        return CriterionResult(
            metric=criterion.metric,
            op=criterion.op,
            threshold=criterion.threshold,
            critical=criterion.critical,
            value=v,
            passed=passed,
            reason=reason,
        )

    if v is None:
        return result(False, "metric_missing")
    if math.isnan(v):
        return result(False, "metric_nan")
    ok = OPS[criterion.op](v, criterion.threshold)
    word = "ok" if ok else "failed"
    return result(ok, f"{word}: {v:g} {criterion.op} {criterion.threshold:g}")


def is_borderline(items: tuple[CriterionResult, ...], tolerance: float) -> bool:
    failed = [i for i in items if not i.passed]
    if len(failed) != 1 or failed[0].critical:
        return False
    f = failed[0]
    if f.value is None or math.isnan(f.value) or f.threshold == 0:
        return False
    return abs(f.value - f.threshold) / abs(f.threshold) <= tolerance


class GateEngine:
    """Evaluates the configured gates of a stage for one candidate."""

    def __init__(self, config: GateConfig) -> None:
        self.config = config

    @classmethod
    def from_file(cls, path: Path | None = None) -> GateEngine:
        return cls(load_gate_config(path))

    def criteria(self, stage: str, context: Mapping[str, str]) -> tuple[GateCriterion, ...]:
        """Effective criteria of ``stage`` for ``{asset_class, timeframe}`` (overrides applied)."""
        if stage not in self.config.stages:
            raise ConfigError(f"no gates configured for stage {stage!r}")
        merged = {c.metric: c for c in self.config.stages[stage]}
        cls, tf = context.get("asset_class"), context.get("timeframe")
        ov = self.config.overrides
        layers = [
            ov.asset_class.get(cls or "", {}),
            ov.timeframe.get(tf or "", {}),
            ov.combined.get(f"{cls}/{tf}", {}),
        ]
        for layer in layers:
            for crit in layer.get(stage, ()):
                merged[crit.metric] = crit
        return tuple(merged.values())

    def evaluate(
        self,
        stage: str,
        candidate: str | HasId,
        metrics: Mapping[str, Any],
        context: Mapping[str, str],
    ) -> GateResult:
        cid = candidate if isinstance(candidate, str) else candidate.id
        items = tuple(check(c, metrics.get(c.metric)) for c in self.criteria(stage, context))
        passed = all(i.passed for i in items)
        return GateResult(
            candidate_id=cid,
            stage=stage,
            items=items,
            passed=passed,
            borderline=not passed and is_borderline(items, self.config.borderline_tolerance),
        )


def to_registry_rows(result: GateResult, run_id: Any) -> list[Any]:
    """``GateResultRecord`` rows (one per criterion) for :class:`RegistryWriter`."""
    from strategy_factory.registry.writer import GateResultRecord

    return [
        GateResultRecord(
            run_id=run_id,
            candidate_id=result.candidate_id,
            stage=result.stage,
            criterion=i.metric,
            metric_value=i.value if i.value is not None and not math.isnan(i.value) else None,
            op=i.op,
            threshold=i.threshold,
            passed=i.passed,
            critical=i.critical,
            reason=i.reason,
        )
        for i in result.items
    ]


def record(result: GateResult, run_id: Any, writer: Any) -> None:
    """Write every criterion of ``result`` through the T03 ``RegistryWriter``."""
    writer.add_gate_results(to_registry_rows(result, run_id))
