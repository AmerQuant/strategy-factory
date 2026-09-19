"""Request budgeting and retries shared by the downloaders.

:class:`TokenBucket` guarantees that no window of ``window_seconds`` sees more than
``budget`` acquisitions: capacity ``burst`` and refill rate ``(budget - burst) / window``
bound any window by ``burst + (budget - burst) = budget``. Clock and sleep are injectable
so tests run on a simulated clock.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

_EPS = 1e-9
_MIN_SLEEP = 1e-3


class TokenBucket:
    def __init__(
        self,
        budget: int,
        burst: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < burst < budget:
            raise ValueError("need 0 < burst < budget")
        self.capacity = float(burst)
        self.rate = (budget - burst) / window_seconds
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
        self._last = now

    def acquire(self) -> None:
        """Block (via ``sleep``) until one token is available, then take it."""
        self._refill()
        # tolerance + minimum sleep: a float-rounding deficit must not spin forever
        while self._tokens < 1.0 - _EPS:
            self._sleep(max((1.0 - self._tokens) / self.rate, _MIN_SLEEP))
            self._refill()
        self._tokens = max(self._tokens - 1.0, 0.0)


class TransientError(Exception):
    """Retryable failure (HTTP 429, 5xx, connection reset, timeout)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class PermanentError(Exception):
    """Non-retryable request failure (e.g. HTTP 400/403/404)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class TLSVerificationError(Exception):
    """Certificate verification failed; downloads must stop (never bypass verification)."""


class GaveUpError(Exception):
    """A request still failed after the configured number of retries."""


def backoff_delay(attempt: int, base: float, cap: float, rng: random.Random) -> float:
    """Exponential backoff with full jitter in [0.5, 1.5) x base * 2**attempt, capped."""
    return float(min(cap, base * (2**attempt)) * (0.5 + rng.random()))


def call_with_retry[T](
    fn: Callable[[], T],
    max_retries: int,
    base: float,
    cap: float,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """Call ``fn``; retry :class:`TransientError` with backoff, give up after ``max_retries``.

    :class:`PermanentError` and :class:`TLSVerificationError` propagate immediately.
    """
    rng = rng or random.Random()
    attempt = 0
    while True:
        try:
            return fn()
        except TransientError as exc:
            if attempt >= max_retries:
                raise GaveUpError(f"gave up after {attempt} retries: {exc}") from exc
            delay = backoff_delay(attempt, base, cap, rng)
            if on_retry is not None:
                on_retry(attempt + 1, exc, delay)
            sleep(delay)
            attempt += 1
