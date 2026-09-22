"""Synthetic series and stage-1 work units for the T12 tests (random walk, planted edge)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from strategy_factory.core.config import EngineConfig, PipelineConfig, SnapshotRef
from strategy_factory.costs.arrays import CostArrays
from strategy_factory.data.schema import SnapshotKey
from strategy_factory.data.split import Split
from strategy_factory.stages.config import S01EdgeConfig, load_s01_config
from strategy_factory.stages.edge import ProfileTask, candidate_id, probe_params
from strategy_factory.stages.edge_profile import Caveat, Identity, SnapshotId

REPO = Path(__file__).resolve().parents[2]
GATES = REPO / "configs" / "gates" / "default.yaml"
DAY_US = 86_400_000_000
T0_US = int(dt.datetime(2012, 1, 2, tzinfo=dt.UTC).timestamp() * 1_000_000)


def synthetic_bars(n: int, seed: int, phi: float = 0.0, vol: float = 0.012) -> dict[str, Any]:
    """Daily bars whose log returns are AR(1) with coefficient ``phi`` (0 = a random walk;
    negative = a planted mean-reversion edge). Opens at the previous close; a wick each side."""
    rng = np.random.default_rng(seed)
    eps = rng.normal(0.0, vol, n)
    r = np.empty(n)
    r[0] = eps[0]
    for i in range(1, n):
        r[i] = phi * r[i - 1] + eps[i]
    close = 100.0 * np.exp(np.cumsum(r))
    open_ = np.concatenate(([100.0], close[:-1]))
    wick = np.abs(rng.normal(0.0, vol / 2, (2, n)))
    high = np.maximum(open_, close) * (1 + wick[0])
    low = np.minimum(open_, close) * (1 - wick[1])
    ts = T0_US + np.arange(n, dtype=np.int64) * DAY_US
    return {"ts": ts, "open": open_, "high": high, "low": low, "close": close}


def flat_costs(n: int, half_spread: float = 0.01) -> CostArrays:
    zeros = np.zeros(n)
    return CostArrays(
        half_spread=np.full(n, half_spread),
        slippage_fixed=zeros,
        slippage_atr_frac=0.0,
        swap_long_per_notional_day=zeros.copy(),
        swap_short_per_notional_day=zeros.copy(),
        rollover_mask=np.zeros(n, dtype=np.bool_),
        triple_mask=np.zeros(n, dtype=np.bool_),
        commission_params=(0, 0.0, 0.0, 0.0),
        profile_name="test",
        profile_status="verified",
        stress=1.0,
        volume_step=1.0,
        min_volume=1.0,
    )


def stage_config(simulations: int = 200, path: Path | None = None) -> S01EdgeConfig:
    cfg = load_s01_config(path or REPO / "configs" / "stages" / "s01_edge.yaml")
    return cfg.model_copy(
        update={"baseline": cfg.baseline.model_copy(update={"simulations": simulations})}
    )


def make_task(
    bars: dict[str, Any],
    *,
    edge_type: str = "MR",
    direction: str = "long",
    symbol: str = "SYN",
    cfg: S01EdgeConfig | None = None,
    gates: Path = GATES,
    run_seed: int = 42,
    quality: str = "ok",
) -> ProfileTask:
    cfg = cfg or stage_config()
    n = int(bars["close"].shape[0])
    cid = candidate_id(
        symbol=symbol,
        timeframe="1D",
        edge_type=edge_type,
        direction=direction,
        snapshot_hash="a" * 64,
        probes=probe_params(cfg, edge_type),
        control="none",
    )
    identity = Identity(
        candidate_id=cid,
        run_id=None,
        symbol=symbol,
        timeframe="1D",
        edge_type=edge_type,
        direction=direction,  # type: ignore[arg-type]
        asset_class="us_equity",
        snapshot=SnapshotId(source="synthetic", snapshot_hash="a" * 64),
        config_hash="c" * 64,
        stage_config_hash="s" * 64,
        code_version="test",
        dev_start="2012-01-02",
        dev_end="2020-01-01",
        dev_bars=n,
    )
    return ProfileTask(
        symbol=symbol,
        timeframe="1D",
        edge_type=edge_type,
        direction=direction,  # type: ignore[arg-type]
        asset_class="us_equity",
        candidate_id=cid,
        bars=bars,
        costs=flat_costs(n),
        engine=EngineConfig(),
        stage=cfg,
        gates_path=gates,
        run_seed=run_seed,
        identity=identity,
        caveats=Caveat(quality_status=quality),
    )


# -- a fake context for end-to-end stage runs (no catalog, no registry) -----------------------
@dataclass
class FakeRef:
    source: str
    snapshot_hash: str


@dataclass
class FakeReferences:
    hashes: dict[tuple[str, str], str]
    quality: dict[tuple[str, str], str] = field(default_factory=dict)

    def reference(self, symbol: str, timeframe: str) -> FakeRef:
        return FakeRef("alpaca", self.hashes[(symbol, timeframe)])

    def caveats(self, symbol: str, timeframe: str) -> Caveat:
        return Caveat(quality_status=self.quality.get((symbol, timeframe), "ok"))


@dataclass
class FakeData:
    series: dict[tuple[str, str], dict[str, Any]]
    too_short: set[tuple[str, str]] = field(default_factory=set)

    def split(self, symbol: str, timeframe: str) -> Split:
        from strategy_factory.data.split import HistoryTooShortError

        if (symbol, timeframe) in self.too_short:
            raise HistoryTooShortError("synthetic: too short", stage="split", symbol=symbol)
        ts = self.series[(symbol, timeframe)]["ts"]
        first = dt.datetime.fromtimestamp(int(ts[0]) / 1e6, tz=dt.UTC)
        last = dt.datetime.fromtimestamp(int(ts[-1]) / 1e6, tz=dt.UTC)
        return Split(
            key=SnapshotKey(
                source="alpaca", symbol=symbol, timeframe=timeframe, snapshot_hash="a" * 64
            ),
            dev_start=first,
            dev_end=last,
            embargo_bars=0,
            holdout_start=last + dt.timedelta(days=1),
            holdout_end=last + dt.timedelta(days=2),
        )

    def arrays(self, symbol: str, timeframe: str) -> dict[str, Any]:
        return dict(self.series[(symbol, timeframe)])


def resolved_config(symbols: tuple[str, ...], control: str = "none") -> PipelineConfig:
    """A resolved-looking config over real universe symbols (their real cost profiles)."""
    return PipelineConfig(
        symbols=symbols,
        timeframes=("1D",),
        stages=("s01_edge",),
        control=control,  # type: ignore[arg-type]
        data_snapshots={
            s: {"1D": SnapshotRef(source="alpaca", snapshot_hash=f"{i:064x}")}
            for i, s in enumerate(symbols)
        },
    )
