"""D-804 (P-103): ``sfac run`` and its workers opt out of Windows efficiency mode.

* the call is made with the right masks when enabled on Windows -- asserted through an injected
  setter, so it fails on any platform;
* it is skipped when disabled in config or off Windows;
* a failing or unavailable call never stops the process: it returns ``False`` and logs once;
* a real executor worker, and ``sfac run``'s parent, apply it (read back on Windows, which the
  ``windows-fast`` CI job runs).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from strategy_factory.pipeline import qos
from strategy_factory.pipeline.executor import (
    ExecutorConfig,
    LocalExecutor,
    _init_worker,
    load_executor_config,
)


@pytest.fixture(autouse=True)
def fresh_warning_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qos, "_warned", False)


def test_F_0_3_7_d804_the_call_is_made_on_windows() -> None:
    calls: list[tuple[int, int]] = []

    def setter(control: int, state: int) -> bool:
        calls.append((control, state))
        return True

    assert qos.opt_out_of_efficiency_mode(True, platform="win32", setter=setter) is True
    # EXECUTION_SPEED taken under control (ControlMask) and switched off (StateMask 0)
    assert calls == [(qos.EXECUTION_SPEED, 0)]


def test_F_0_3_7_d804_disabled_or_not_windows_makes_no_call() -> None:
    def setter(control: int, state: int) -> bool:
        raise AssertionError("must not be called")

    assert qos.opt_out_of_efficiency_mode(False, platform="win32", setter=setter) is False
    assert qos.opt_out_of_efficiency_mode(True, platform="linux", setter=setter) is False


def test_F_0_3_7_d804_a_failing_call_never_stops_the_run_and_logs_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(control: int, state: int) -> bool:
        raise OSError(87, "the parameter is incorrect")

    with caplog.at_level(logging.WARNING, logger="strategy_factory"):
        assert qos.opt_out_of_efficiency_mode(True, platform="win32", setter=broken) is False
        assert qos.opt_out_of_efficiency_mode(True, platform="win32", setter=broken) is False
    warnings = [r for r in caplog.records if "efficiency mode" in r.getMessage()]
    assert len(warnings) == 1  # once per process, not once per call


def test_F_0_3_7_d804_the_real_call_is_safe_on_this_platform() -> None:
    """On Windows the real call succeeds; anywhere else it is a quiet no-op."""
    result = qos.opt_out_of_efficiency_mode(True)
    assert result is (sys.platform == "win32")


def throttling_control_mask() -> int | None:
    """``ControlMask`` of this process's power-throttling state (Windows), else ``None``."""
    if sys.platform != "win32":
        return None
    import ctypes
    import ctypes.wintypes as wt

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.GetProcessInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]

    class State(ctypes.Structure):
        _fields_ = [("Version", wt.ULONG), ("ControlMask", wt.ULONG), ("StateMask", wt.ULONG)]

    st = State(1, 0, 0)
    assert k32.GetProcessInformation(
        k32.GetCurrentProcess(), qos.PROCESS_POWER_THROTTLING, ctypes.byref(st), ctypes.sizeof(st)
    )
    return int(st.ControlMask)


def worker_mask(_: int) -> int | None:
    return throttling_control_mask()


def test_F_0_3_7_d804_the_worker_initializer_applies_the_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-process, so the initializer's other effects are isolated: the D-012 worker marker would
    otherwise make every later registry test refuse to write, and the Numba thread count is
    restored."""
    import numba

    from strategy_factory.pipeline import executor

    seen: list[bool] = []
    monkeypatch.setattr(
        qos, "opt_out_of_efficiency_mode", lambda enabled=True: seen.append(enabled)
    )
    monkeypatch.setattr(executor, "mark_executor_worker", lambda: None)
    threads = numba.get_num_threads()
    try:
        _init_worker(1, True)
        _init_worker(1, False)
    finally:
        numba.set_num_threads(threads)
    assert seen == [True, False]


def test_F_0_3_7_d804_a_real_worker_is_opted_out() -> None:
    masks = LocalExecutor(ExecutorConfig(workers=2, numba_threads=1)).map(worker_mask, [0, 1])
    if sys.platform == "win32":
        assert all(m is not None and m & qos.EXECUTION_SPEED for m in masks)
    else:
        assert masks == [None, None]


def test_F_0_3_7_d804_the_config_default_is_on_and_documented() -> None:
    assert ExecutorConfig().efficiency_mode_opt_out is True
    assert load_executor_config().efficiency_mode_opt_out is True
    text = (
        Path(__file__).resolve().parents[2] / "configs" / "pipeline" / "executor.yaml"
    ).read_text(encoding="utf-8")
    assert "efficiency_mode_opt_out: true" in text
    assert "no system setting" in text


def test_F_0_3_7_d804_sfac_run_opts_out_its_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from strategy_factory.pipeline import stage_run

    seen: list[Any] = []

    class Stop(Exception):
        pass

    def store() -> Any:
        raise Stop

    monkeypatch.setattr(
        stage_run, "opt_out_of_efficiency_mode", lambda enabled=True: seen.append(enabled)
    )
    monkeypatch.setattr(stage_run, "SnapshotStore", store)
    cfg = tmp_path / "p.yaml"
    cfg.write_text("symbols: [AAPL]\ntimeframes: [1D]\nstages: [s01_edge]\n", encoding="utf-8")
    with pytest.raises(Stop):
        stage_run.run_stage1(cfg)
    assert seen == [True]  # applied before any data is read
