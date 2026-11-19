"""Unit tests for the chunk download scheduler and worker."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from p2p.config import MAX_GLOBAL_INFLIGHT, MAX_PEER_CONNECTIONS
from p2p.peer.connection import ConnectionState, PeerConnection
from p2p.peer.downloader import DownloadWorker, NoAvailablePeersError, SwarmDownloader
from p2p.peer.scheduler import IN_FLIGHT, ChunkState, DownloadScheduler
from p2p.protocol import Bitfield, Have, Piece, ProtocolError, Request
from p2p.storage.manager import StorageManager
from p2p.storage.manifest import build_manifest


def make_storage(tmp_path: Path, contents: bytes, chunk_size: int) -> StorageManager:
    """Create isolated verified storage for downloader tests."""
    source = tmp_path / "source.bin"
    source.write_bytes(contents)
    return StorageManager(build_manifest(source, chunk_size), tmp_path / "downloads")


def make_connected_peer_connection(peer_id: str = "peer-a", chunk_count: int = 4) -> PeerConnection:
    """Create a steady-state connection stub suitable for downloader tests."""
    conn = PeerConnection(
        swarm_id="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890",
        my_peer_id="peer-client",
        my_listen_port=6881,
        chunk_count=chunk_count,
        local_bitfield=Bitfield.from_indices([], chunk_count),
    )
    conn._state = ConnectionState.STEADY_STATE
    conn._writer = MagicMock()
    conn._writer.is_closing.return_value = False
    conn._writer.wait_closed = AsyncMock()
    conn._remote_peer_id = peer_id
    send_request = AsyncMock()
    receive_message = AsyncMock()
    cast(Any, conn).send_request = send_request
    cast(Any, conn).receive_message = receive_message
    return conn


def test_scheduler_reserves_unique_chunks() -> None:
    scheduler = DownloadScheduler(4)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0, 1, 3], 4))
    scheduler.register_peer("peer-b", Bitfield.from_indices([1, 2], 4))

    first = scheduler.reserve_next("peer-a")
    assert first in {0, 1, 3}
    assert scheduler.state_for(first) == ChunkState.IN_FLIGHT
    assert scheduler.inflight_chunks == {first}
    assert first in scheduler.available_chunks_for("peer-a")

    second = scheduler.reserve_next("peer-b")
    assert second in {1, 2}
    assert scheduler.state_for(second) == ChunkState.IN_FLIGHT
    assert scheduler.inflight_chunks == {first, second}

    scheduler.mark_verified(first, peer_id="peer-a")
    assert scheduler.state_for(first) == ChunkState.VERIFIED
    assert scheduler.verified_chunks == {first}

    assert scheduler.release(second, peer_id="peer-b") is True
    assert scheduler.state_for(second) == ChunkState.MISSING
    assert scheduler.inflight_chunks == frozenset()


def test_scheduler_tracks_haves_and_releases_failed_peer() -> None:
    scheduler = DownloadScheduler(6)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0, 2, 4], 6))
    scheduler.register_peer("peer-b", Bitfield.from_indices([1, 3, 5], 6))

    chunk = scheduler.reserve_next("peer-a")
    assert chunk is not None
    assert scheduler.state_for(chunk) == IN_FLIGHT

    scheduler.update_peer_have("peer-a", 5)
    assert scheduler.has_chunk("peer-a", 5)
    assert scheduler.release_all("peer-a") == [chunk]
    assert scheduler.state_for(chunk) == ChunkState.MISSING

    assert scheduler.is_complete is False


def test_scheduler_marks_missing_and_verifies_complete_download() -> None:
    scheduler = DownloadScheduler(3, verified_chunks=[0])
    scheduler.register_peer("peer-a", Bitfield.from_indices([0, 1, 2], 3))

    assert scheduler.missing_chunks == {1, 2}
    assert scheduler.reserve_next("peer-a") in {1, 2}
    scheduler.mark_verified(1, peer_id="peer-a")
    scheduler.mark_verified(2, peer_id="peer-a")
    assert scheduler.verified_chunks == {0, 1, 2}
    assert scheduler.is_complete is True


@pytest.mark.asyncio
async def test_download_worker_fetches_valid_chunk_and_marks_verified(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(4)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0], 4))
    conn = make_connected_peer_connection("peer-a")
    receive_message = AsyncMock(return_value=Piece(chunk_index=0, data=b"abcd"))
    cast(Any, conn).receive_message = receive_message
    storage = make_storage(tmp_path, b"abcd" * 4, 4)

    worker = DownloadWorker(conn, scheduler, storage, max_retries=2, retry_delay=0.0)

    async with asyncio.timeout(2):
        chunk_index = await worker.fetch_next()

    assert chunk_index == 0
    assert scheduler.state_for(chunk_index) == ChunkState.VERIFIED
    assert worker.completed == frozenset({chunk_index})
    cast(Any, conn).send_request.assert_awaited_once_with(chunk_index)
    receive_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_worker_retries_failed_chunk_before_success(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(3)
    scheduler.register_peer("peer-a", Bitfield.from_indices([2], 3))
    scheduler.register_peer("peer-b", Bitfield.from_indices([2], 3))
    conn = make_connected_peer_connection("peer-a")
    receive_started = asyncio.Event()

    async def receive_message() -> Piece:
        if not receive_started.is_set():
            receive_started.set()
            raise ProtocolError("transient response failure")
        return Piece(chunk_index=2, data=b"xyz")

    receive_message = AsyncMock(side_effect=receive_message)
    cast(Any, conn).receive_message = receive_message
    storage = make_storage(tmp_path, b"xyz" * 3, 3)

    worker = DownloadWorker(conn, scheduler, storage, max_retries=2, retry_delay=0.05)
    task = asyncio.create_task(worker.fetch_next())
    async with asyncio.timeout(2):
        await receive_started.wait()
        assert scheduler.state_for(2) == ChunkState.IN_FLIGHT
        assert scheduler.reserve_next("peer-b") is None
        chunk_index = await task

    assert chunk_index == 2
    assert scheduler.state_for(2) == ChunkState.VERIFIED
    assert cast(Any, conn).send_request.await_count == 2


@pytest.mark.asyncio
async def test_download_worker_releases_chunk_when_all_retries_fail(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(2)
    scheduler.register_peer("peer-a", Bitfield.from_indices([1], 2))
    conn = make_connected_peer_connection("peer-a")
    receive_message = AsyncMock(side_effect=ProtocolError("bad payload"))
    cast(Any, conn).receive_message = receive_message
    storage = make_storage(tmp_path, b"ab" * 2, 2)

    worker = DownloadWorker(conn, scheduler, storage, max_retries=2, retry_delay=0.0)

    async with asyncio.timeout(2):
        chunk_index = await worker.fetch_next()

    assert chunk_index is None
    assert scheduler.state_for(1) == ChunkState.MISSING
    assert scheduler.inflight_chunks == frozenset()
    assert worker.completed == frozenset()


@pytest.mark.asyncio
async def test_download_worker_finish_chunk_and_run_track_completion(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(2)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0], 2))
    conn = make_connected_peer_connection("peer-a")
    storage = make_storage(tmp_path, b"ab" * 2, 2)
    storage.write_chunk(0, b"ab")

    worker = DownloadWorker(conn, scheduler, storage=storage)
    async with asyncio.timeout(2):
        await worker.finish_chunk(0)

    assert scheduler.state_for(0) == ChunkState.VERIFIED
    assert worker.completed == frozenset({0})
    with pytest.raises(ValueError, match="has not been verified"):
        await worker.finish_chunk(1)

    conn._state = ConnectionState.CLOSED
    assert await worker.run() == set()


@pytest.mark.asyncio
async def test_download_worker_records_have_before_piece(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(4)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0], 4))
    conn = make_connected_peer_connection("peer-a")
    receive_message = AsyncMock(
        side_effect=[Have(chunk_index=2), Piece(chunk_index=0, data=b"data")]
    )
    cast(Any, conn).receive_message = receive_message
    storage = make_storage(tmp_path, b"data", 4)

    worker = DownloadWorker(conn, scheduler, storage, max_retries=1)
    async with asyncio.timeout(2):
        assert await worker.fetch_next() == 0

    assert scheduler.has_chunk("peer-a", 2)


@pytest.mark.asyncio
async def test_download_worker_rejects_unexpected_request(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(1)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0], 1))
    conn = make_connected_peer_connection("peer-a", chunk_count=1)
    cast(Any, conn).receive_message = AsyncMock(return_value=Request(chunk_index=0))
    storage = make_storage(tmp_path, b"data", 4)

    worker = DownloadWorker(conn, scheduler, storage, max_retries=1)
    assert await worker.fetch_next() is None
    assert isinstance(worker.last_error, ProtocolError)
    assert scheduler.state_for(0) == ChunkState.MISSING


def test_download_worker_validates_dependencies_and_retry_options(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(1)
    connection = make_connected_peer_connection("peer-a", chunk_count=1)
    storage = make_storage(tmp_path, b"data", 4)

    with pytest.raises(TypeError, match="connection"):
        DownloadWorker(cast(PeerConnection, object()), scheduler, storage)
    with pytest.raises(TypeError, match="scheduler"):
        DownloadWorker(connection, cast(DownloadScheduler, object()), storage)
    with pytest.raises(TypeError, match="storage"):
        DownloadWorker(connection, scheduler, cast(StorageManager, object()))
    with pytest.raises(ValueError, match="max_retries"):
        DownloadWorker(connection, scheduler, storage, max_retries=0)
    with pytest.raises(ValueError, match="retry_delay"):
        DownloadWorker(connection, scheduler, storage, retry_delay=-1)
    with pytest.raises(ValueError, match="retry_delay"):
        DownloadWorker(connection, scheduler, storage, retry_delay=math.nan)


@pytest.mark.asyncio
async def test_download_worker_run_fetches_all_chunks(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(2)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0, 1], 2))
    conn = make_connected_peer_connection("peer-a", chunk_count=2)
    requested: list[int] = []

    async def send_request(chunk_index: int) -> None:
        requested.append(chunk_index)

    async def receive_message() -> Piece:
        return Piece(chunk_index=requested[-1], data=b"ab")

    cast(Any, conn).send_request = send_request
    cast(Any, conn).receive_message = receive_message
    storage = make_storage(tmp_path, b"abab", 2)

    worker = DownloadWorker(conn, scheduler, storage, max_retries=1)
    async with asyncio.timeout(2):
        assert await worker.run() == {0, 1}

    assert scheduler.is_complete


@pytest.mark.asyncio
async def test_download_worker_cancellation_releases_reservation(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(1)
    scheduler.register_peer("peer-a", Bitfield.from_indices([0], 1))
    conn = make_connected_peer_connection("peer-a")
    receive_started = asyncio.Event()

    async def wait_for_piece() -> Piece:
        receive_started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    cast(Any, conn).receive_message = wait_for_piece
    storage = make_storage(tmp_path, b"data", 4)
    worker = DownloadWorker(conn, scheduler, storage)
    task = asyncio.create_task(worker.fetch_next())
    async with asyncio.timeout(2):
        await receive_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert scheduler.state_for(0) == ChunkState.MISSING
    assert scheduler.inflight_chunks == frozenset()
    assert conn.pending_requests == frozenset()


@pytest.mark.asyncio
async def test_swarm_downloader_reports_missing_peer_chunks(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(1)
    conn = make_connected_peer_connection("peer-a", chunk_count=1)
    conn._remote_bitfield = Bitfield.from_indices([], 1)
    storage = make_storage(tmp_path, b"data", 4)
    downloader = SwarmDownloader([conn], scheduler, storage, availability_timeout=0.01)

    with pytest.raises(NoAvailablePeersError, match="missing chunks"):
        await asyncio.wait_for(downloader.run(), timeout=0.5)

    assert conn.is_closed


@pytest.mark.asyncio
async def test_swarm_downloader_removes_peer_that_rejects_have(
    tmp_path: Path,
) -> None:
    scheduler = DownloadScheduler(1)
    source = make_connected_peer_connection("peer-a", chunk_count=1)
    other = make_connected_peer_connection("peer-b", chunk_count=1)
    source._remote_bitfield = Bitfield.from_indices([0], 1)
    other._remote_bitfield = Bitfield.from_indices([0], 1)
    storage = make_storage(tmp_path, b"data", 4)
    downloader = SwarmDownloader([source, other], scheduler, storage)
    downloader._register_connections()

    async def fail_broadcast(_chunk_index: int) -> None:
        raise ProtocolError("peer disconnected")

    cast(Any, other).send_have = fail_broadcast
    await downloader._broadcast_have(0, "peer-a")

    assert "peer-b" not in downloader._active
    assert not scheduler.available_chunks_for("peer-b")
    assert other.is_closed
    await source.close()


def test_swarm_downloader_enforces_configured_concurrency_limits(tmp_path: Path) -> None:
    scheduler = DownloadScheduler(1)
    connection = make_connected_peer_connection("peer-a", chunk_count=1)
    storage = make_storage(tmp_path, b"data", 4)

    with pytest.raises(ValueError, match="max_peer_connections cannot exceed"):
        SwarmDownloader(
            [connection],
            scheduler,
            storage,
            max_peer_connections=MAX_PEER_CONNECTIONS + 1,
        )
    with pytest.raises(ValueError, match="max_global_inflight cannot exceed"):
        SwarmDownloader(
            [connection],
            scheduler,
            storage,
            max_global_inflight=MAX_GLOBAL_INFLIGHT + 1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("advertise_chunks", [True, False])
async def test_downloader_controls_have_broadcasts_without_skipping_verified_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    advertise_chunks: bool,
) -> None:
    scheduler = DownloadScheduler(1)
    connection = make_connected_peer_connection("source", chunk_count=1)
    connection._remote_bitfield = Bitfield.from_indices([0], 1)
    storage = make_storage(tmp_path, b"data", 4)
    verified_callback = AsyncMock()
    downloader = SwarmDownloader(
        [connection],
        scheduler,
        storage,
        advertise_chunks=advertise_chunks,
        on_chunk_verified=verified_callback,
    )
    broadcast = AsyncMock()
    monkeypatch.setattr(downloader, "_broadcast_have", broadcast)
    downloader._register_connections()
    downloader._inboxes["source"].put_nowait(Piece(0, b"data"))
    try:
        async with asyncio.timeout(2):
            assert await downloader._download_from_peer("source") == 0
        assert storage.verified_chunks == {0}
        verified_callback.assert_awaited_once_with(0)
        if advertise_chunks:
            broadcast.assert_awaited_once_with(0, "source")
        else:
            broadcast.assert_not_awaited()
    finally:
        await connection.close()
