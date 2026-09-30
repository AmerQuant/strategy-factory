"""F-X.1 / F-X.2 (T15a §3; D-653, D-662, D-663): the funnel orchestrator.

The orchestrator is driven with a fake stage runner (deterministic "passes" per stage) and an
in-memory registry with the same interface as ``registry.funnel.FunnelRegistry`` (the db test
runs the real one). F-X.1's acceptance -- an interrupted and resumed funnel gives the same result
-- is tested by failing a stage, resuming, and comparing with an uninterrupted run.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from strategy_factory.core.config import (
    PipelineConfig,
    SourceRef,
    canonical_json,
    config_hash,
    load_pipeline_config,
)
from strategy_factory.pipeline.funnel import Funnel, Hashes, stage_config
from strategy_factory.pipeline.funnel_config import FunnelConfig, load_funnel_config
from strategy_factory.registry.funnel import StageRow, StageSlot

REPO = Path(__file__).resolve().parents[2]
HASHES = Hashes(stage_config={"s01_edge": "a", "s02_screen": "b", "s03_entry": "c"}, gates="g",
                code_version="f" * 40)  # fmt: skip


class MemoryRegistry:
    """``FunnelRegistry``'s interface, in memory."""

    def __init__(self) -> None:
        self.funnels: dict[uuid.UUID, dict[str, Any]] = {}
        self.rows: dict[uuid.UUID, dict[StageSlot, StageRow]] = {}

    def start_funnel(self, **kw: Any) -> uuid.UUID:
        fid = uuid.uuid4()
        self.funnels[fid] = {**kw, "status": "running", "n": len(self.funnels)}
        self.rows[fid] = {}
        return fid

    def resumable(self, funnel_key: str) -> uuid.UUID | None:
        open_ = ("failed",)
        hits = [
            f
            for f, r in self.funnels.items()
            if r["funnel_key"] == funnel_key and r["status"] in open_
        ]
        return max(hits, key=lambda f: self.funnels[f]["n"]) if hits else None

    def funnel(self, fid: uuid.UUID) -> dict[str, Any]:
        return self.funnels[fid]

    def reopen(self, fid: uuid.UUID) -> None:
        self.funnels[fid]["status"] = "running"

    def finish_funnel(self, fid: uuid.UUID, status: str) -> None:
        self.funnels[fid]["status"] = status

    def stages(self, fid: uuid.UUID) -> dict[StageSlot, StageRow]:
        return dict(self.rows[fid])

    def start_stage(self, fid: uuid.UUID, slot: StageSlot, key: str, inputs: int | None) -> None:
        self.rows[fid][slot] = StageRow(*slot, stage_key=key, run_id=None, status="running",
                                        inputs=inputs)  # fmt: skip

    def set_stage_run(self, fid: uuid.UUID, slot: StageSlot, run_id: str) -> None:
        r = self.rows[fid][slot]
        self.rows[fid][slot] = StageRow(r.timeframe, r.stage, r.arm, r.stage_key, run_id,
                                        r.status, r.inputs)  # fmt: skip

    def finish_stage(self, fid: uuid.UUID, slot: StageSlot, status: str) -> None:
        r = self.rows[fid][slot]
        self.rows[fid][slot] = StageRow(r.timeframe, r.stage, r.arm, r.stage_key, r.run_id,
                                        status, r.inputs)  # fmt: skip


class FakeRunner:
    """Stage runs are deterministic functions of their config; `fail_on` fails one stage run."""

    def __init__(self, passes: dict[str, dict[str, tuple[str, ...]]] | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.configs: dict[str, PipelineConfig] = {}
        self.fail_on: tuple[str, str, str] | None = None
        # stage -> timeframe -> symbols that go on
        self.passes = passes or {
            "s01_edge": {"1D": ("AAPL", "MSFT"), "1H": ("TSLA",)},
            "s02_screen": {"1D": ("MSFT",), "1H": ()},
        }

    def scope(self, cfg: FunnelConfig, timeframe: str) -> tuple[str, ...]:
        return ("AAPL", "MSFT", "SPY") if timeframe == "1D" else ("TSLA", "BAC")

    def resolve(self, cfg: PipelineConfig) -> PipelineConfig:
        if cfg.symbol_scope == "broker":
            return cfg.model_copy(update={"symbols": self.scope(FunnelConfig(timeframes=("1D",)),
                                                                cfg.timeframes[0])})  # fmt: skip
        return cfg

    def run(self, cfg: PipelineConfig, on_start: Callable[[str], None]) -> str:
        slot = (cfg.timeframes[0], cfg.stages[0], "control" if cfg.control != "none" else "real")
        run_id = str(
            uuid.UUID(hashlib.sha256(canonical_json(cfg.canonical()).encode()).hexdigest()[:32])
        )
        on_start(run_id)
        self.calls.append(slot)
        if slot == self.fail_on:
            raise RuntimeError(f"injected failure in {slot}")
        self.configs[run_id] = cfg
        return run_id

    def passed(self, stage: str, run_id: str, timeframe: str, source_id: str) -> tuple[str, ...]:
        cfg = self.configs[run_id]
        assert cfg.control == "none" and cfg.source_id == source_id  # D-662: real upstream
        return self.passes[stage][timeframe]


def funnel(cfg: FunnelConfig, reg: MemoryRegistry, runner: FakeRunner, **kw: Any) -> Funnel:
    return Funnel(cfg, reg, runner, kw.pop("hashes", HASHES), kw.pop("source", None))  # type: ignore[arg-type]


CFG = FunnelConfig(timeframes=("1D", "1H"))


# -- the chain (D-662) --------------------------------------------------------------------------
def test_F_X_1_d662_six_stage_runs_per_timeframe_control_on_the_real_inputs() -> None:
    reg, runner = MemoryRegistry(), FakeRunner()
    res = funnel(CFG, reg, runner).run()
    assert [o.slot for o in res.stages][:6] == [
        ("1D", s, a) for s in ("s01_edge", "s02_screen", "s03_entry") for a in ("real", "control")
    ]
    # every downstream run -- real and control -- reads the REAL upstream run
    s01_real = res.run_of("1D", "s01_edge", "real")
    for arm in ("real", "control"):
        cfg = runner.configs[str(res.run_of("1D", "s02_screen", arm))]
        assert cfg.stage_inputs == {"s01_edge": s01_real}
        assert cfg.symbols == ("AAPL", "MSFT")
        assert cfg.control == ("random_walk" if arm == "control" else "none")
    s02_real = res.run_of("1D", "s02_screen", "real")
    assert runner.configs[str(res.run_of("1D", "s03_entry", "control"))].stage_inputs == {
        "s02_screen": s02_real
    }


def test_F_X_1_d663_a_stage_without_input_is_empty_and_runs_nothing() -> None:
    reg, runner = MemoryRegistry(), FakeRunner()
    res = funnel(CFG, reg, runner).run()
    empty = [o.slot for o in res.stages if o.status == "empty"]
    assert empty == [("1H", "s03_entry", "real"), ("1H", "s03_entry", "control")]
    assert ("1H", "s03_entry", "real") not in runner.calls
    rows = reg.stages(uuid.UUID(res.funnel_id))
    assert rows[("1H", "s03_entry", "real")].status == "empty"


def test_F_X_2_d653_no_control_runs_the_real_arm_only_and_is_recorded() -> None:
    reg, runner = MemoryRegistry(), FakeRunner()
    res = funnel(CFG, reg, runner).run(control=False)
    assert {o.slot[2] for o in res.stages} == {"real"}
    row = reg.funnel(uuid.UUID(res.funnel_id))
    assert row["control"] is False and "--no-control" in row["notes"]


# -- resume (F-X.1's acceptance) -----------------------------------------------------------------
def test_F_X_1_interrupt_and_resume_gives_the_uninterrupted_result() -> None:
    clean_reg, clean = MemoryRegistry(), FakeRunner()
    want = funnel(CFG, clean_reg, clean).run()

    reg, runner = MemoryRegistry(), FakeRunner()
    runner.fail_on = ("1D", "s02_screen", "real")
    with pytest.raises(RuntimeError, match="injected"):
        funnel(CFG, reg, runner).run()
    (fid,) = reg.funnels
    assert reg.funnels[fid]["status"] == "failed"
    assert reg.rows[fid][("1D", "s02_screen", "real")].status == "failed"

    runner.fail_on = None
    before = list(runner.calls)
    got = funnel(CFG, reg, runner).run()
    assert got.resumed and got.funnel_id == str(fid)
    rerun = runner.calls[len(before) :]
    assert ("1D", "s01_edge", "real") not in rerun and ("1D", "s01_edge", "control") not in rerun
    assert rerun[0] == ("1D", "s02_screen", "real")  # the first unfinished stage
    # the same stage runs, with the same run ids, as the uninterrupted funnel
    assert [(o.slot, o.status, o.run_id) for o in got.stages] == [
        (o.slot, o.status, o.run_id) for o in want.stages
    ]
    assert reg.funnels[fid]["status"] == "done"


def test_F_X_1_a_finished_funnel_is_not_resumed_and_a_changed_config_is_a_new_run() -> None:
    reg, runner = MemoryRegistry(), FakeRunner()
    first = funnel(CFG, reg, runner).run()
    again = funnel(CFG, reg, runner).run()
    assert not again.resumed and again.funnel_id != first.funnel_id
    runner.fail_on = ("1D", "s01_edge", "control")
    with pytest.raises(RuntimeError):
        funnel(CFG, reg, runner).run()
    runner.fail_on = None
    other = HASHES.__class__(**{**HASHES.__dict__, "gates": "changed"})
    moved = funnel(CFG, reg, runner, hashes=other).run()
    assert not moved.resumed  # a different gate file is a different funnel key


def test_F_X_1_d663_a_dirty_tree_never_resumes() -> None:
    reg, runner = MemoryRegistry(), FakeRunner()
    dirty = HASHES.__class__(**{**HASHES.__dict__, "code_version": "f" * 40 + "-dirty"})
    runner.fail_on = ("1D", "s02_screen", "real")
    with pytest.raises(RuntimeError):
        funnel(CFG, reg, runner, hashes=dirty).run()
    runner.fail_on = None
    res = funnel(CFG, reg, runner, hashes=dirty).run()
    assert not res.resumed and len(reg.funnels) == 2


def test_F_X_1_fresh_forces_a_new_funnel_run() -> None:
    reg, runner = MemoryRegistry(), FakeRunner()
    runner.fail_on = ("1H", "s01_edge", "real")
    with pytest.raises(RuntimeError):
        funnel(CFG, reg, runner).run()
    runner.fail_on = None
    assert not funnel(CFG, reg, runner).run(fresh=True).resumed


# -- configs: the same stage runs as the hand-written T12-T14 configs ---------------------------
@pytest.mark.parametrize("tf", ["1d", "1h"])
def test_F_X_1_the_funnels_stage_configs_are_t12_t14s(tf: str) -> None:
    pipe = REPO / "configs" / "pipeline"
    TF = tf.upper()
    for arm, suffix in (("real", ""), ("control", "_control")):
        hand = load_pipeline_config(pipe / f"s01_broker_{tf}{suffix}.yaml")
        mine = stage_config(CFG, "s01_edge", TF, arm, None)
        assert config_hash(mine.canonical()) == config_hash(hand.canonical())
        downstream = (
            ("s02_screen", f"s02_screen_{tf}{suffix}.yaml", "s01_edge"),
            ("s03_entry", f"s03_entry_{tf}{suffix}.yaml", "s02_screen"),
        )
        for stage, file, upstream in downstream:
            hand = load_pipeline_config(pipe / file)
            run = hand.stage_inputs[upstream]
            mine = stage_config(CFG, stage, TF, arm, None, run, ("X",))
            assert config_hash(mine.canonical()) == config_hash(
                hand.model_copy(update={"symbols": ("X",)}).canonical()
            )


def test_F_X_1_d670_a_synthetic_source_is_in_every_stage_config() -> None:
    src = SourceRef(kind="null", seed=1, generator={"innovations": "gaussian"})
    reg, runner = MemoryRegistry(), FakeRunner()
    res = funnel(CFG, reg, runner, source=src).run()
    for o in res.stages:
        if o.run_id:
            assert runner.configs[o.run_id].source == src
    assert reg.funnel(uuid.UUID(res.funnel_id))["source"] == "real"  # the funnel config's kind


def test_F_X_2_the_shipped_funnel_configs_load() -> None:
    for name, kind in (("mvp", "real"), ("null", "null"), ("planted", "planted")):
        cfg = load_funnel_config(REPO / "configs" / "funnel" / f"{name}.yaml")
        assert cfg.source.kind == kind and cfg.timeframes == ("1D", "1H") and cfg.control


def test_F_X_2_a_funnel_runs_a_prefix_of_the_stages() -> None:
    assert FunnelConfig(timeframes=("1D",), stages=("s01_edge",)).stages == ("s01_edge",)
    with pytest.raises(ValueError, match="prefix"):
        FunnelConfig(timeframes=("1D",), stages=("s02_screen",))


# -- the real registry (D-663) --------------------------------------------------------------------
@pytest.mark.db
def test_F_X_1_d663_resume_on_the_real_registry(registry_engine: Any) -> None:
    """The same interrupt-and-resume on ``FunnelRegistry`` and its foreign keys."""
    from sqlalchemy.dialects.postgresql import insert

    from strategy_factory.registry.funnel import FunnelRegistry
    from strategy_factory.registry.tables import pipeline_runs

    class DbRunner(FakeRunner):
        def run(self, cfg: PipelineConfig, on_start: Callable[[str], None]) -> str:
            def start(run_id: str) -> None:
                with registry_engine.begin() as conn:
                    row = {"id": uuid.UUID(run_id), "config": {}, "config_hash": "h",
                           "code_version": "c", "seed": 1}  # fmt: skip
                    # the fake's run ids are deterministic, so a retried stage reuses its id
                    conn.execute(insert(pipeline_runs).values(**row).on_conflict_do_nothing())
                on_start(run_id)

            return super().run(cfg, start)

    reg = FunnelRegistry(registry_engine)
    runner = DbRunner()
    runner.fail_on = ("1D", "s03_entry", "real")
    with pytest.raises(RuntimeError):
        Funnel(CFG, reg, runner, HASHES, None).run()
    runner.fail_on = None
    runner.calls.clear()
    res = Funnel(CFG, reg, runner, HASHES, None).run()
    assert res.resumed
    assert runner.calls[0] == ("1D", "s03_entry", "real")
    rows = reg.stages(uuid.UUID(res.funnel_id))
    assert all(r.status in ("done", "empty") for r in rows.values())
    assert reg.funnel(uuid.UUID(res.funnel_id))["status"] == "done"


# -- reproduce (F-0.7.4) ---------------------------------------------------------------------------
class ArtifactRunner(FakeRunner):
    """Writes a summary per stage run that names its run, its upstream run and its config hash,
    as the real artifacts do; a fresh run gets fresh run ids."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def run(self, cfg: PipelineConfig, on_start: Callable[[str], None]) -> str:
        run_id = str(uuid.uuid4())
        on_start(run_id)
        self.configs[run_id] = cfg
        folder = self.root / run_id / cfg.stages[0]
        folder.mkdir(parents=True)
        body = {
            "run_id": run_id,
            "parent_run_id": next(iter(cfg.stage_inputs.values()), None),
            "config_hash": config_hash(cfg.canonical()),
            "candidates": [f"{cfg.stages[0]}:{s}:{cfg.control}" for s in cfg.symbols],
        }
        (folder / "summary.json").write_text(canonical_json(body), encoding="utf-8")
        return run_id


def _reproduce(
    reg: MemoryRegistry, runner: ArtifactRunner, fid: str, hashes: Hashes = HASHES
) -> Any:
    from strategy_factory.pipeline.funnel_reproduce import reproduce_funnel

    return reproduce_funnel(
        fid,
        registry=reg,  # type: ignore[arg-type]
        runner=runner,
        hashes=hashes,
        artifacts=runner.root,
        run_config=lambda rid: runner.configs[rid].canonical(),
    )


def test_F_0_7_4_funnel_reproduce_is_identical_after_normalising_the_run_ids(
    tmp_path: Path,
) -> None:
    reg, runner = MemoryRegistry(), ArtifactRunner(tmp_path)
    first = funnel(CFG, reg, runner).run()
    report, new = _reproduce(reg, runner, first.funnel_id)
    assert new.funnel_id != first.funnel_id and not new.resumed
    assert report.identical and report.compared_files == 10  # 10 stage runs ran, 2 were empty
    assert {o.run_id for o in new.stages} & {o.run_id for o in first.stages} == {None}


def test_F_0_7_4_funnel_reproduce_reports_a_changed_artifact(tmp_path: Path) -> None:
    reg, runner = MemoryRegistry(), ArtifactRunner(tmp_path)
    first = funnel(CFG, reg, runner).run()
    victim = tmp_path / str(first.run_of("1D", "s02_screen", "control")) / "s02_screen"
    text = (victim / "summary.json").read_text(encoding="utf-8")
    (victim / "summary.json").write_text(text.replace("MSFT", "MSFX"), encoding="utf-8")
    report, _ = _reproduce(reg, runner, first.funnel_id)
    assert not report.identical
    assert report.differences == ["('1D', 's02_screen', 'control'): differs: summary.json"]


def test_F_0_7_4_funnel_reproduce_refuses_other_or_dirty_code(tmp_path: Path) -> None:
    from strategy_factory.core.errors import ConfigError

    reg, runner = MemoryRegistry(), ArtifactRunner(tmp_path)
    first = funnel(CFG, reg, runner).run()
    other = Hashes(**{**HASHES.__dict__, "code_version": "e" * 40})
    with pytest.raises(ConfigError, match="check out the recorded commit"):
        _reproduce(reg, runner, first.funnel_id, other)
    dirty = Hashes(**{**HASHES.__dict__, "code_version": "f" * 40 + "-dirty"})
    run = funnel(CFG, reg, runner, hashes=dirty).run()
    with pytest.raises(ConfigError, match="not reproducible"):
        _reproduce(reg, runner, run.funnel_id, dirty)


# -- F-X.2: every MVP operation of stages 1-3 from the CLI -----------------------------------------
def test_F_X_2_the_command_tree_covers_the_mvp_operations() -> None:
    import typer.main
    from typer.testing import CliRunner

    from strategy_factory.cli import app

    root = typer.main.get_command(app)
    commands = root.commands  # type: ignore[attr-defined]
    assert {"run", "reproduce", "funnel"} <= set(commands)  # one stage; a trial; the funnel
    assert set(commands["funnel"].commands) == {"run", "status", "reproduce", "report"}
    runner = CliRunner()
    for args in (["funnel", "--help"], ["funnel", "run", "--help"], ["funnel", "report", "--help"]):
        res = runner.invoke(app, args)
        assert res.exit_code == 0, (args, res.output)
    assert "--no-control" in runner.invoke(app, ["funnel", "run", "--help"]).output


# -- D-654: the synthetic series never reach the store --------------------------------------------
def test_F_X_5_d654_the_synthetic_modules_cannot_write_the_store() -> None:
    """Static: nothing under `synthetic/` imports the store, the catalog's writers or the split
    manager, or opens a file for writing; the series live in memory (the truth is written by the
    orchestrator under the artifacts root)."""
    import ast

    for path in sorted((REPO / "src" / "strategy_factory" / "synthetic").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                banned = ("store", "catalog", "ingest")
                assert not any(mod == f"strategy_factory.data.{b}" for b in banned), mod
                names = {a.name for a in node.names}
                assert not names & {"SnapshotStore", "Catalog", "write_snapshot"}, (
                    path.name,
                    names,
                )
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in (
                "write_text",
                "write_bytes",
                "write_parquet",
                "write_csv",
                "mkdir",
            ):
                raise AssertionError(f"{path.name} writes a file")
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
                raise AssertionError(f"{path.name} opens a file")


def test_F_0_7_4_funnel_reproduce_names_a_moved_input(tmp_path: Path) -> None:
    """A recorded stage config that differs from the reproduction's (a reference snapshot moved,
    a cost input changed) is reported as that config key, not silently re-resolved."""
    reg, runner = MemoryRegistry(), ArtifactRunner(tmp_path)
    first = funnel(CFG, reg, runner).run()
    rid = str(first.run_of("1D", "s01_edge", "real"))
    runner.configs[rid] = runner.configs[rid].model_copy(update={"seed": 7})
    report, _ = _reproduce(reg, runner, first.funnel_id)
    assert "('1D', 's01_edge', 'real'): config seed differs" in report.differences
