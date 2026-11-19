"""Metrics must survive failed or cancelled transfers for benchmark records."""

import asyncio
import random
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from p2p.peer.client import SwarmPeer
from p2p.peer.downloader import SwarmDownloader
from p2p.peer.scheduler import DownloadScheduler
from p2p.storage.manifest import build_manifest
from p2p.tracker.models import AnnounceResponse


@pytest.mark.parametrize("error", [RuntimeError("transfer failed"), asyncio.CancelledError()])
async def test_failed_download_retains_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"12345678")
    peer = SwarmPeer(
        build_manifest(source, 4), "http://tracker.test", tmp_path / "out", scheduler_seed=123
    )
    peer._started = True
    monkeypatch.setattr(peer, "_announce", AsyncMock(return_value=AnnounceResponse(interval=30)))
    monkeypatch.setattr(peer, "_connect_to_peers", AsyncMock(return_value=[object()]))
    scheduler_draws: list[float] = []

    def capture_scheduler(chunk_count: int, *, rng: random.Random) -> DownloadScheduler:
        scheduler_draws.append(rng.random())
        return DownloadScheduler(chunk_count, rng=rng)

    monkeypatch.setattr("p2p.peer.client.DownloadScheduler", capture_scheduler)

    def fake_init(downloader: SwarmDownloader, *args: object, **kwargs: object) -> None:
        downloader._workers = {}
        downloader._retired_bytes_downloaded = 4
        downloader._retired_retries = 2
        downloader._retired_hash_failures = 1
        downloader._start_time = 1.0
        downloader._end_time = 3.0

    monkeypatch.setattr(SwarmDownloader, "__init__", fake_init)
    monkeypatch.setattr(SwarmDownloader, "run", AsyncMock(side_effect=error))
    try:
        async with asyncio.timeout(5):
            with pytest.raises(type(error)):
                await peer.download()
        assert peer.bytes_downloaded == 4
        assert peer.total_retries == 2
        assert peer.chunk_hash_failures == 1
        assert peer.download_duration_seconds == 2.0
        assert peer.download_throughput_bytes_per_s == 2.0
        assert scheduler_draws == [random.Random(123).random()]
    finally:
        await peer.close()


@pytest.mark.parametrize("seed", [True, "42", 1.5])
def test_scheduler_seed_requires_integer(tmp_path: Path, seed: object) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"12345678")
    with pytest.raises(ValueError, match="scheduler_seed"):
        SwarmPeer(
            build_manifest(source, 4),
            "http://tracker.test",
            tmp_path / "out",
            scheduler_seed=seed,  # type: ignore[arg-type]
        )
