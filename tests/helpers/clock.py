"""Test clock helper for deterministic time simulation."""

from __future__ import annotations


class FakeClock:
    """Controllable clock implementation for deterministic testing."""

    def __init__(self, initial_time: float = 0.0) -> None:
        self._current_time: float = float(initial_time)

    def now(self) -> float:
        """Return the current simulated time."""
        return self._current_time

    def advance(self, seconds: float) -> None:
        """Advance the simulated time by a non-negative number of seconds."""
        if seconds < 0:
            raise ValueError(f"Cannot advance clock backwards: {seconds}")
        self._current_time += seconds

    def set(self, timestamp: float) -> None:
        """Explicitly set the current simulated time."""
        self._current_time = float(timestamp)
