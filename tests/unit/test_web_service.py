"""Cancellation must join pending file work without hiding cancellation."""

import asyncio

import pytest

from p2p.web.service import finish_disk_task


async def test_cancelled_file_work_preserves_cancellation_when_worker_fails() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def file_work() -> None:
        started.set()
        await release.wait()
        raise ValueError("file validation failed during cancellation")

    async with asyncio.timeout(5):
        worker = asyncio.create_task(file_work())
        waiter = asyncio.create_task(finish_disk_task(worker))
        try:
            await started.wait()
            waiter.cancel()
            await asyncio.sleep(0)  # Let the cancellation handler begin joining the worker.
            assert not waiter.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert worker.done()
        finally:
            release.set()
            await asyncio.gather(worker, waiter, return_exceptions=True)
