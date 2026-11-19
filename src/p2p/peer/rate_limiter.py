"""Async token-bucket rate limiter for upload bandwidth control.

The limiter is shared across all connections of a single peer so the
aggregate upload rate is capped regardless of how many leechers are
downloading simultaneously.  An injectable monotonic clock supports
deterministic unit tests.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from typing import Final


class TokenBucketRateLimiter:
    """Async token-bucket rate limiter.

    Parameters
    ----------
    rate_bytes_per_sec:
        Maximum sustained upload rate in bytes per second.  Must be a
        positive finite number.
    burst_bytes:
        Maximum bucket capacity (burst allowance) in bytes.  Defaults to
        ``rate_bytes_per_sec`` (one second of burst).  Must be >= 1.
    clock:
        Callable returning the current monotonic time in seconds.
        Defaults to ``time.monotonic``.  Inject a fake clock for
        deterministic tests.
    """

    def __init__(
        self,
        rate_bytes_per_sec: float,
        *,
        burst_bytes: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if (
            not isinstance(rate_bytes_per_sec, (int, float))
            or isinstance(rate_bytes_per_sec, bool)
            or not math.isfinite(rate_bytes_per_sec)
            or rate_bytes_per_sec <= 0
        ):
            raise ValueError("rate_bytes_per_sec must be a positive finite number")

        effective_burst = burst_bytes if burst_bytes is not None else rate_bytes_per_sec
        if (
            not isinstance(effective_burst, (int, float))
            or isinstance(effective_burst, bool)
            or not math.isfinite(effective_burst)
            or effective_burst < 1
        ):
            raise ValueError("burst_bytes must be a finite number >= 1")

        self._rate: Final[float] = float(rate_bytes_per_sec)
        self._burst: Final[float] = float(effective_burst)
        self._clock: Final[Callable[[], float]] = clock or time.monotonic
        self._tokens: float = self._burst
        self._last_refill: float = self._clock()
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def rate(self) -> float:
        """Sustained rate in bytes per second."""
        return self._rate

    @property
    def burst(self) -> float:
        """Maximum bucket capacity in bytes."""
        return self._burst

    def _refill(self) -> None:
        """Add tokens for elapsed time since the last refill."""
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

    async def acquire(self, num_bytes: int) -> None:
        """Wait until *num_bytes* tokens are available, then consume them.

        The method handles requests larger than the burst capacity by
        waiting proportionally.  Cancellation is safe: tokens are only
        consumed when the full amount is available.

        Raises
        ------
        ValueError
            If *num_bytes* is not a positive integer.
        asyncio.CancelledError
            If the caller is cancelled while waiting.
        """
        if not isinstance(num_bytes, int) or isinstance(num_bytes, bool) or num_bytes < 1:
            raise ValueError("num_bytes must be a positive integer")

        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= num_bytes:
                    self._tokens -= num_bytes
                    return
                deficit = num_bytes - self._tokens
                wait_seconds = deficit / self._rate
                await asyncio.sleep(wait_seconds)
                now = self._clock()
                elapsed = now - self._last_refill
                earned = elapsed * self._rate
                if self._tokens + earned >= num_bytes:
                    remaining = (self._tokens + earned) - num_bytes
                    self._tokens = min(self._burst, max(0.0, remaining))
                    self._last_refill = now
                    return
                # Partial sleep (e.g. clock jitter); update tokens and retry
                self._tokens = min(self._burst, self._tokens + earned)
                self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """Current token count (without refilling — a snapshot)."""
        return self._tokens
