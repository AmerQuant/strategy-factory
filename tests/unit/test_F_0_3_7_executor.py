"""F-0.3.7: executor (serial == parallel, order, seeds, thread budget, chunking, trials).

Decisions: D-012 (only the parent writes), D-331 (column chunks), D-334 (spawn, thread
budget, seeds from the unit key), F-0.7.1 (one trial per evaluated configuration).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest
import yaml
from fixtures.executor import (
    echo_key,
    fail_on_qqq,
    grid_job,
    numba_threads,
    run_unit,
    worker_flag,
    write_from_worker,
)
from sqlalchemy import Engine, func, select

from strategy_factory.core.errors import ConfigError, ExecutorError, RegistryError
from strategy_factory.pipeline.executor import (
    BYTES_PER_CELL,
    ExecutorConfig,
    LocalExecutor,
    SerialExecutor,
    WorkUnit,
    chunk_columns,
    grid_trial_rows,
    load_executor_config,
    make_executor,
    resolve_budget,
    run_grid,
    seeded,
    unit_seed,
    unit_seeds,
)

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = ("SPY", "QQQ", "AAPL", "EURUSD")


def units(stage: str = "s02_screen", **payload: object) -> list[WorkUnit]:
    return [WorkUnit(s, "1D", stage, dict(payload)) for s in SYMBOLS]


def without_pid(results: list[dict[str, object]]) -> list[dict[str, object]]:
    """Results without the worker pid, which is the only thing that may differ."""
    return [{k: v for k, v in r.items() if k != "pid"} for r in results]


# -- thread budget (D-334) -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("cfg", "cpu", "expected"),
    [
        ({}, 20, (4, 5)),  # both auto: floor(sqrt(20)) = 4 workers x 5 threads
        ({}, 1, (1, 1)),
        ({"workers": 4}, 20, (4, 5)),
        ({"numba_threads": 2}, 20, (10, 2)),
        ({"workers": 3, "numba_threads": 5}, 20, (3, 5)),
        ({"workers": 8}, 4, (8, 1)),  # explicit workers win; threads drop to 1
    ],
)
def test_F_0_3_7_thread_budget_never_exceeds_the_core_count(
    cfg: dict[str, object], cpu: int, expected: tuple[int, int]
) -> None:
    budget = resolve_budget(ExecutorConfig.model_validate(cfg), cpu)
    assert (budget.workers, budget.numba_threads) == expected
    assert budget.workers >= 1 and budget.numba_threads >= 1


def test_F_0_3_7_explicit_budget_over_the_core_count_is_refused() -> None:
    cfg = ExecutorConfig(workers=8, numba_threads=4)
    with pytest.raises(ConfigError, match="32 threads on 20 cores"):
        resolve_budget(cfg, 20)


def test_F_0_3_7_budget_uses_os_cpu_count_when_not_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("strategy_factory.pipeline.executor.os.cpu_count", lambda: 9)
    assert resolve_budget(ExecutorConfig()).cpu_count == 9


def test_F_0_3_7_executor_config_file_and_defaults(tmp_path: Path) -> None:
    assert load_executor_config(tmp_path / "missing.yaml") == ExecutorConfig()
    path = tmp_path / "executor.yaml"
    path.write_text(
        yaml.safe_dump({"workers": 2, "numba_threads": 3, "max_grid_bytes": 1024}),
        encoding="utf-8",
    )
    cfg = load_executor_config(path)
    assert (cfg.workers, cfg.numba_threads, cfg.max_grid_bytes) == (2, 3, 1024)
    path.write_text(yaml.safe_dump({"workers": 0}), encoding="utf-8")
    with pytest.raises(ConfigError, match="workers must be >= 1"):
        load_executor_config(path)
    path.write_text(yaml.safe_dump({"nope": 1}), encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid executor config"):
        load_executor_config(path)


def test_F_0_3_7_repo_executor_config_is_valid() -> None:
    cfg = load_executor_config(REPO / "configs" / "pipeline" / "executor.yaml")
    assert cfg.workers == "auto" and cfg.numba_threads == "auto"
    assert cfg.max_grid_bytes == 512 * 1024 * 1024  # D-331


def test_F_0_3_7_worker_gets_the_configured_numba_thread_count() -> None:
    ex = LocalExecutor(ExecutorConfig(workers=2, numba_threads=2), cpu_count=8)
    assert ex.map(numba_threads, units()[:2]) == [2, 2]


# -- seeds (D-334) -------------------------------------------------------------------------
def test_F_0_3_7_seeds_come_from_the_run_seed_and_the_unit_key() -> None:
    work = units()
    seeds = unit_seeds(42, work)
    assert set(seeds) == {u.key for u in work}
    assert len(set(seeds.values())) == len(work)  # distinct per unit
    assert seeds == unit_seeds(42, work)  # stable
    assert unit_seeds(43, work) != seeds  # depends on the run seed
    assert unit_seed(42, "SPY|1D|s02_screen") == seeds["SPY|1D|s02_screen"]
    assert all(0 <= s < 2**63 for s in seeds.values())


def test_F_0_3_7_seeded_units_carry_their_seed_into_the_worker() -> None:
    """The parent fills the seed; a worker never derives one from its process (D-334)."""
    work = seeded(42, units(n_bars=300, n_configs=4, run_seed=42))
    assert [u.seed for u in work] == [unit_seed(42, u.key) for u in work]
    assert [u.key for u in work] == [u.key for u in units()]  # nothing else changes
    ex = LocalExecutor(ExecutorConfig(workers=2, numba_threads=1), cpu_count=8)
    parallel = ex.map(run_unit, work)
    assert [r["seed"] for r in parallel] == [u.seed for u in work]
    assert without_pid(parallel) == without_pid(SerialExecutor().map(run_unit, work))
    assert [u.seed for u in seeded(43, work)] != [u.seed for u in work]


# -- order, identity, failures --------------------------------------------------------------
def test_F_0_3_7_results_are_in_input_order_serial_and_parallel() -> None:
    work = units()
    expected = [u.key for u in work]
    assert SerialExecutor().map(echo_key, work) == expected
    for workers in (2, 4):
        ex = LocalExecutor(ExecutorConfig(workers=workers, numba_threads=1), cpu_count=8)
        assert ex.map(echo_key, work) == expected
    assert SerialExecutor().map(echo_key, []) == []
    assert LocalExecutor(ExecutorConfig(workers=2, numba_threads=1), 8).map(echo_key, []) == []


def test_F_0_3_7_failing_unit_reports_its_key_and_keeps_the_finished_results() -> None:
    work = units()
    ex = LocalExecutor(ExecutorConfig(workers=2, numba_threads=1), cpu_count=8)
    with pytest.raises(ExecutorError) as err:
        ex.map(fail_on_qqq, work)
    assert "QQQ|1D|s02_screen" in str(err.value)
    assert list(err.value.failed) == ["QQQ|1D|s02_screen"]
    kept = [r for r in err.value.results if r is not None]
    assert kept == ["SPY|1D|s02_screen", "AAPL|1D|s02_screen", "EURUSD|1D|s02_screen"]
    with pytest.raises(ExecutorError) as serial_err:
        SerialExecutor().map(fail_on_qqq, work)
    # both executors run every unit and report the same failure (docstring: parallel == serial)
    assert str(serial_err.value) == str(err.value)
    assert serial_err.value.results == err.value.results
    assert list(serial_err.value.failed) == list(err.value.failed)


def test_F_0_3_7_d012_only_the_parent_writes_to_the_registry() -> None:
    """A worker that tries to open a registry writer is refused (D-012, D-334)."""
    from strategy_factory.core.env import in_executor_worker

    assert not in_executor_worker()  # the parent is not marked
    ex = LocalExecutor(ExecutorConfig(workers=2, numba_threads=1), cpu_count=8)
    assert ex.map(worker_flag, units()[:2]) == [True, True]
    with pytest.raises(ExecutorError) as err:
        ex.map(write_from_worker, units()[:1])
    assert "only the parent process writes to the registry" in str(err.value)
    assert isinstance(next(iter(err.value.failed.values())), RegistryError)
    assert not in_executor_worker()  # and the parent is still not marked afterwards


def test_F_0_3_7_make_executor_picks_serial_for_one_worker() -> None:
    assert isinstance(make_executor(ExecutorConfig(workers=1), 8), SerialExecutor)
    assert isinstance(make_executor(ExecutorConfig(workers=2, numba_threads=1), 8), LocalExecutor)


def test_F_0_3_7_parallel_equals_serial_on_a_grid_of_200_configurations() -> None:
    work = units(n_bars=400, n_configs=200, run_seed=42)  # 4 x 200 = 800 configurations
    serial = SerialExecutor().map(run_unit, work)
    assert len(serial[0]["metrics"]["n_trades"]) == 200
    assert [r["key"] for r in serial] == [u.key for u in work]
    for workers in (2, 4):
        ex = LocalExecutor(ExecutorConfig(workers=workers, numba_threads=1), cpu_count=8)
        parallel = ex.map(run_unit, work)
        # metrics, seeds and order are identical; only the worker pid differs
        assert without_pid(parallel) == without_pid(serial)
        assert {r["pid"] for r in parallel} != {r["pid"] for r in serial}


def test_F_0_3_7_engine_settings_travel_with_the_work_unit() -> None:
    """A non-default engine setting must reach the worker, not fall back to the default."""
    base = WorkUnit("SPY", "1D", "s02_screen", {"n_bars": 300, "n_configs": 6, "run_seed": 42})
    scaled = WorkUnit("SPY", "1D", "s02_screen", {**(base.payload or {}), "atr_scale": 2.5})
    ex = LocalExecutor(ExecutorConfig(workers=2, numba_threads=1), cpu_count=8)
    serial = SerialExecutor().map(run_unit, [base, scaled])
    assert without_pid(ex.map(run_unit, [base, scaled])) == without_pid(serial)
    assert serial[0]["metrics"] != serial[1]["metrics"]  # the setting really changes results


# -- grid chunking (D-331) -------------------------------------------------------------------
def test_F_0_3_7_chunk_size_respects_the_memory_budget() -> None:
    assert BYTES_PER_CELL == 16
    assert chunk_columns(1000, 500, 1000 * 16 * 10) == 10
    assert chunk_columns(1000, 5, 1000 * 16 * 10) == 5  # never more than the grid
    assert chunk_columns(1000, 500, 1) == 1  # never zero
    assert chunk_columns(2500, 2000, 512 * 1024 * 1024) == 2000
    with pytest.raises(ValueError, match="must be >= 1"):
        chunk_columns(0, 5, 1024)


def test_F_0_3_7_chunked_grid_equals_the_unchunked_grid() -> None:
    job = grid_job(400, 23)
    whole = run_grid(job, chunk_cols=23)
    for chunk in (1, 5, 8, 100):
        part = run_grid(job, chunk_cols=chunk)
        assert set(part) == set(whole)
        for name, values in whole.items():
            np.testing.assert_array_equal(part[name], values, err_msg=name)
        assert len(part["n_trades"]) == 23


def test_F_0_3_7_chunk_size_from_the_memory_budget(tmp_path: Path) -> None:
    job = grid_job(300, 12)
    tiny = run_grid(job, max_grid_bytes=300 * BYTES_PER_CELL * 2)  # two columns per chunk
    np.testing.assert_array_equal(tiny["n_trades"], run_grid(job, chunk_cols=12)["n_trades"])


# -- trials (F-0.7.1, D-012) -------------------------------------------------------------------
def test_F_0_3_7_one_trial_row_per_configuration() -> None:
    job = grid_job(300, 7)
    table = run_grid(job, chunk_cols=3)
    params = [{"sl_atr": float(x)} for x in job.sl_atr]
    rows = grid_trial_rows(uuid.uuid4(), "s02_screen", "fam", "a" * 64, params, table)
    assert len(rows) == 7
    assert [r.params["sl_atr"] for r in rows] == [float(x) for x in job.sl_atr]
    assert rows[0].n_trades == int(table["n_trades"][0])
    assert rows[0].exposure == pytest.approx(float(table["exposure"][0]))
    assert rows[0].extra == {"n_skipped_min_volume": int(table["n_skipped_min_volume"][0])}
    with pytest.raises(ExecutorError, match="values for 3 configurations"):
        grid_trial_rows(uuid.uuid4(), "s", "f", "a" * 64, params[:3], table)


@pytest.mark.db
def test_F_0_3_7_trial_count_equals_the_number_of_configurations(registry_engine: Engine) -> None:
    from fixtures.registry_db import RUN_CONFIG

    from strategy_factory.registry.tables import trials
    from strategy_factory.registry.writer import RegistryWriter

    job = grid_job(300, 25)
    table = run_grid(job, chunk_cols=4)
    params = [
        {"sl_atr": float(x), "tp_atr": float(y)}
        for x, y in zip(job.sl_atr, job.tp_atr, strict=True)
    ]
    with RegistryWriter(registry_engine, batch_size=10) as writer:
        run_id = writer.start_run(RUN_CONFIG, seed=42)
        writer.add_trials(grid_trial_rows(run_id, "s02_screen", "fam", "b" * 64, params, table))
    with registry_engine.connect() as conn:
        n = conn.execute(select(func.count()).select_from(trials)).scalar_one()
        first = conn.execute(select(trials).order_by(trials.c.id)).first()
    assert n == 25
    assert first is not None
    assert first._mapping["params"]["sl_atr"] == pytest.approx(float(job.sl_atr[0]))
    assert first._mapping["n_trades"] == int(table["n_trades"][0])
