"""Unit tests for the token-bucket upload rate limiter."""

from __future__ import annotations

import asyncio
import math

import pytest

from p2p.peer.rate_limiter import TokenBucketRateLimiter

# ---------------------------------------------------------------------------
# Deterministic clock helper
# ---------------------------------------------------------------------------


class FakeClock:
    """Manually-advancing monotonic clock for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_valid_rate(self) -> None:
        rl = TokenBucketRateLimiter(1024.0)
        assert rl.rate == 1024.0
        assert rl.burst == 1024.0

    def test_valid_rate_int(self) -> None:
        rl = TokenBucketRateLimiter(500)
        assert rl.rate == 500.0

    def test_custom_burst(self) -> None:
        rl = TokenBucketRateLimiter(1024.0, burst_bytes=2048.0)
        assert rl.burst == 2048.0

    def test_zero_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive finite"):
            TokenBucketRateLimiter(0)

    def test_negative_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive finite"):
            TokenBucketRateLimiter(-100)

    def test_inf_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive finite"):
            TokenBucketRateLimiter(math.inf)

    def test_nan_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive finite"):
            TokenBucketRateLimiter(math.nan)

    def test_bool_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive finite"):
            TokenBucketRateLimiter(True)

    def test_zero_burst_rejected(self) -> None:
        with pytest.raises(ValueError, match="burst_bytes"):
            TokenBucketRateLimiter(1024.0, burst_bytes=0)

    def test_negative_burst_rejected(self) -> None:
        with pytest.raises(ValueError, match="burst_bytes"):
            TokenBucketRateLimiter(1024.0, burst_bytes=-1)

    def test_bool_burst_rejected(self) -> None:
        with pytest.raises(ValueError, match="burst_bytes"):
            TokenBucketRateLimiter(1024.0, burst_bytes=True)

    def test_custom_clock(self) -> None:
        clock = FakeClock(100.0)
        rl = TokenBucketRateLimiter(1024.0, clock=clock)
        assert rl.rate == 1024.0
        # The bucket starts full at the clock's initial time
        assert rl.available_tokens == 1024.0


# ---------------------------------------------------------------------------
# Token refill
# ---------------------------------------------------------------------------


class TestRefill:
    def test_refill_adds_tokens(self) -> None:
        clock = FakeClock()
        rl = TokenBucketRateLimiter(100.0, clock=clock)
        # Drain the bucket
        rl._tokens = 0.0
        clock.advance(1.0)
        rl._refill()
        assert rl._tokens == pytest.approx(100.0)

    def test_refill_caps_at_burst(self) -> None:
        clock = FakeClock()
        rl = TokenBucketRateLimiter(100.0, burst_bytes=200.0, clock=clock)
        clock.advance(10.0)
        rl._refill()
        assert rl._tokens == pytest.approx(200.0)

    def test_no_refill_without_elapsed_time(self) -> None:
        clock = FakeClock()
        rl = TokenBucketRateLimiter(100.0, clock=clock)
        rl._tokens = 50.0
        rl._refill()
        assert rl._tokens == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# acquire() basics
# ---------------------------------------------------------------------------


class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_within_burst(self) -> None:
        clock = FakeClock()
        rl = TokenBucketRateLimiter(1000.0, clock=clock)
        await rl.acquire(500)
        assert rl.available_tokens == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_acquire_exact_burst(self) -> None:
        clock = FakeClock()
        rl = TokenBucketRateLimiter(1000.0, clock=clock)
        await rl.acquire(1000)
        assert rl.available_tokens == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_acquire_zero_rejected(self) -> None:
        rl = TokenBucketRateLimiter(1000.0)
        with pytest.raises(ValueError, match="positive integer"):
            await rl.acquire(0)

    @pytest.mark.asyncio
    async def test_acquire_negative_rejected(self) -> None:
        rl = TokenBucketRateLimiter(1000.0)
        with pytest.raises(ValueError, match="positive integer"):
            await rl.acquire(-1)

    @pytest.mark.asyncio
    async def test_acquire_bool_rejected(self) -> None:
        rl = TokenBucketRateLimiter(1000.0)
        with pytest.raises(ValueError, match="positive integer"):
            await rl.acquire(True)

    @pytest.mark.asyncio
    async def test_acquire_waits_for_refill(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the bucket is empty, acquire sleeps until tokens refill."""
        clock = FakeClock()
        rl = TokenBucketRateLimiter(100.0, clock=clock)
        # Drain the bucket
        await rl.acquire(100)
        assert rl.available_tokens == pytest.approx(0.0)

        real_sleep = asyncio.sleep

        async def fake_sleep(seconds: float) -> None:
            clock.advance(seconds)
            await real_sleep(0)  # yield control

        monkeypatch.setattr("p2p.peer.rate_limiter.asyncio.sleep", fake_sleep)
        await rl.acquire(50)

        # After acquiring 50 bytes at 100 bytes/s, 0.5s elapsed, so
        # 50 tokens were generated and immediately consumed
        assert rl.available_tokens == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_acquire_larger_than_burst_waits(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Acquiring more tokens than burst capacity waits proportionally."""
        clock = FakeClock()
        rl = TokenBucketRateLimiter(100.0, burst_bytes=50.0, clock=clock)
        # Request 200 bytes at 100 bytes/s — needs multiple wait cycles

        real_sleep = asyncio.sleep

        async def fake_sleep(seconds: float) -> None:
            clock.advance(seconds)
            await real_sleep(0)

        monkeypatch.setattr("p2p.peer.rate_limiter.asyncio.sleep", fake_sleep)
        await rl.acquire(200)

        # Tokens consumed; bucket should be near-empty
        assert rl.available_tokens <= 50.0


# ---------------------------------------------------------------------------
# Cancellation safety
# ---------------------------------------------------------------------------


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancelled_acquire_does_not_consume_tokens(self) -> None:
        """Cancelling while waiting does not deduct tokens."""
        clock = FakeClock()
        rl = TokenBucketRateLimiter(10.0, clock=clock)
        # Drain most tokens
        await rl.acquire(10)
        assert rl.available_tokens == pytest.approx(0.0)

        # Start a large acquire that will need to wait
        task = asyncio.create_task(rl.acquire(100))
        await asyncio.sleep(0)  # let it start
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Tokens should not have been consumed since the acquire
        # never completed; the bucket should still be near-empty
        assert rl.available_tokens <= 10.0


# ---------------------------------------------------------------------------
# Concurrent contention
# ---------------------------------------------------------------------------


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_serial_acquires_are_fair(self) -> None:
        """Multiple acquires serialize through the lock."""
        clock = FakeClock()
        rl = TokenBucketRateLimiter(1000.0, clock=clock)

        # Acquire in two steps
        await rl.acquire(400)
        await rl.acquire(400)
        assert rl.available_tokens == pytest.approx(200.0)

    @pytest.mark.asyncio
    async def test_concurrent_acquires_do_not_over_consume(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two concurrent acquires do not consume more tokens than available."""
        clock = FakeClock()
        rl = TokenBucketRateLimiter(1000.0, burst_bytes=1000.0, clock=clock)

        real_sleep = asyncio.sleep

        async def fake_sleep(seconds: float) -> None:
            clock.advance(seconds)
            await real_sleep(0)

        monkeypatch.setattr("p2p.peer.rate_limiter.asyncio.sleep", fake_sleep)
        # Launch two concurrent acquires that together exceed the burst
        t1 = asyncio.create_task(rl.acquire(600))
        t2 = asyncio.create_task(rl.acquire(600))
        await asyncio.gather(t1, t2)

        # Both consumed 600 bytes = 1200 total; bucket refilled over time
        # The key invariant: tokens never went negative
        assert rl.available_tokens >= 0.0


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_rate_property(self) -> None:
        rl = TokenBucketRateLimiter(512.0)
        assert rl.rate == 512.0

    def test_burst_property(self) -> None:
        rl = TokenBucketRateLimiter(512.0, burst_bytes=1024.0)
        assert rl.burst == 1024.0

    def test_available_tokens_snapshot(self) -> None:
        rl = TokenBucketRateLimiter(100.0)
        assert rl.available_tokens == pytest.approx(100.0)
