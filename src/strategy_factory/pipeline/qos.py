"""Keep ``sfac`` runs off the efficiency cores on Windows (D-804, P-103).

On a hybrid CPU, Windows 11 manages a process's power throttling (EcoQoS, "efficiency mode")
itself unless the process says otherwise, and it moves processes it treats as background onto
the **efficiency cores**. Measured on the development machine (T12 pilot §12-§13): one symbol
of stage 1 took 6.5 s on four performance cores and 21.1 s on the four efficiency cores; the
1D pilot 18 s and 67 s.

:func:`opt_out_of_efficiency_mode` marks **this process** as explicitly not throttled
(``SetProcessInformation(ProcessPowerThrottling)``: EXECUTION_SPEED controlled and off). It is
a **scheduling hint for our own process only**: it changes no system setting, no power plan and
no other process, and it cannot change a result (the executor is proven bit-identical, D-607).

* A no-op anywhere but Windows.
* **It can never stop a run:** if the call is unavailable or fails, it logs **once** and
  returns ``False``; the run continues as Windows schedules it.
* Controlled by ``efficiency_mode_opt_out`` in ``configs/pipeline/executor.yaml`` (default on),
  so a laptop on battery can leave Windows free to save power.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from strategy_factory.core.logging import get_logger

log = get_logger(__name__)

#: ``PROCESS_INFORMATION_CLASS.ProcessPowerThrottling``
PROCESS_POWER_THROTTLING = 4
#: ``PROCESS_POWER_THROTTLING_EXECUTION_SPEED``
EXECUTION_SPEED = 0x1

#: A setter takes ``(control_mask, state_mask)`` and applies them to the current process,
#: returning ``True`` on success; injectable so the call can be tested on any platform.
Setter = Callable[[int, int], bool]

_warned = False


def _windows_setter(control_mask: int, state_mask: int) -> bool:
    if sys.platform != "win32":  # mypy checks the Windows branch only where it exists
        raise OSError("ProcessPowerThrottling exists on Windows only")
    import ctypes
    import ctypes.wintypes as wt

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.SetProcessInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]

    class State(ctypes.Structure):
        _fields_ = [("Version", wt.ULONG), ("ControlMask", wt.ULONG), ("StateMask", wt.ULONG)]

    state = State(1, control_mask, state_mask)
    ok = k32.SetProcessInformation(
        k32.GetCurrentProcess(), PROCESS_POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state)
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "SetProcessInformation(ProcessPowerThrottling)")
    return True


def opt_out_of_efficiency_mode(
    enabled: bool = True,
    *,
    platform: str | None = None,
    setter: Setter | None = None,
) -> bool:
    """Mark this process "not power-throttled" on Windows; ``True`` if the hint was applied.

    Never raises: any failure is logged once per process and the caller carries on.
    """
    global _warned
    if not enabled or (platform or sys.platform) != "win32":
        return False
    try:
        # EXECUTION_SPEED: take control of it (ControlMask) and switch throttling off (StateMask)
        return bool((setter or _windows_setter)(EXECUTION_SPEED, 0))
    except Exception as exc:  # a scheduling hint must never be able to stop a run
        if not _warned:
            _warned = True
            log.warning(
                "could not opt out of Windows efficiency mode (%s); continuing, and Windows may "
                "schedule this run on the efficiency cores",
                exc,
            )
        return False
