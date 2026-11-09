"""Loopback integration tests for bounded multi-peer downloading."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from p2p.peer.connection import PeerConnection
from p2p.peer.downloader import NoAvailablePeersError, SwarmDownloader
from p2p.peer.scheduler import ChunkState, DownloadScheduler
from p2p.peer.server import PeerServer
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Have,
    ProtocolError,
    Request,
)
from p2p.storage.manager import StorageManager
from p2p.storage.manifest import FileManifest, build_manifest

SWARM_ID = "b1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890"


def create_source(tmp_path: Path, contents: bytes) -> tuple[Path, FileManifest]:
    source = tmp_path / "source.bin"
    source.write_bytes(contents)
    return source, build_manifest(source, chunk_size=4)


async def connect_to_server(server: PeerServer, peer_id: str, chunk_count: int) -> PeerConnection:
    return await PeerConnection.connect(
        "127.0.0.1",
        server.listen_port,
        swarm_id=SWARM_ID,
        my_peer_id=peer_id,
        my_listen_port=0x1F91,
        chunk_count=chunk_count,
        local_bitfield=Bitfield.from_indices([], chunk_count),
    )


@pytest.mark.asyncio
async def test_swarm_downloader_fetches_in_parallel_and_broadcasts_have(
    tmp_path: Path,
) -> None:
    contents = b"aaaabbbbcccc"
    source, manifest = create_source(tmp_path, contents)
    chunks = [contents[index : index + 4] for index in range(0, len(contents), 4)]
    all_chunks = Bitfield.from_indices(range(manifest["chunk_count"]), manifest["chunk_count"])
    arrivals: set[tuple[str, int]] = set()
    have_updates: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
    both_peers_requested = asyncio.Event()

    def make_handler(peer_id: str) -> Callable[[PeerConnection], Coroutine[Any, Any, None]]:
        async def handler(connection: PeerConnection) -> None:
            try:
                while connection.is_connected:
                    message = await connection.receive_message()
                    if isinstance(message, Request):
                        arrivals.add((peer_id, message.chunk_index))
                        if len({peer for peer, _ in arrivals}) == 2:
                            both_peers_requested.set()
                        async with asyncio.timeout(3):
                            await both_peers_requested.wait()
                        await connection.send_piece(
                            message.chunk_index, chunks[message.chunk_index]
                        )
                    elif isinstance(message, Have):
                        await have_updates.put((peer_id, message.chunk_index))
            except (ConnectionClosed, ProtocolError):
                return

        return handler

    seeder_a = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="seeder-a",
        chunk_count=manifest["chunk_count"],
        local_bitfield=all_chunks,
        on_connection=make_handler("seeder-a"),
    )
    seeder_b = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="seeder-b",
        chunk_count=manifest["chunk_count"],
        local_bitfield=all_chunks,
        on_connection=make_handler("seeder-b"),
    )

    async with seeder_a, seeder_b:
        connections = [
            await connect_to_server(seeder_a, "leecher-a", manifest["chunk_count"]),
            await connect_to_server(seeder_b, "leecher-b", manifest["chunk_count"]),
        ]
        storage = StorageManager(manifest, tmp_path / "downloads")
        scheduler = DownloadScheduler(manifest["chunk_count"])
        downloader = SwarmDownloader(connections, scheduler, storage)

        async with asyncio.timeout(5):
            completed = await downloader.run()
            announced = {
                await have_updates.get(),
                await have_updates.get(),
                await have_updates.get(),
            }

    assert completed == {0, 1, 2}
    assert (tmp_path / "downloads" / source.name).read_bytes() == contents
    assert {chunk for _, chunk in arrivals} == {0, 1, 2}
    assert len(arrivals) == 3
    assert {chunk for _, chunk in announced} == {0, 1, 2}
    assert scheduler.is_complete


@pytest.mark.asyncio
async def test_swarm_downloader_retries_corrupt_peer_via_another_peer(
    tmp_path: Path,
) -> None:
    contents = b"aaaabbbbcccc"
    _, manifest = create_source(tmp_path, contents)
    chunks = [contents[index : index + 4] for index in range(0, len(contents), 4)]
    all_chunks = Bitfield.from_indices(range(manifest["chunk_count"]), manifest["chunk_count"])
    corrupt_requests: list[int] = []
    good_requests: list[int] = []

    async def corrupt_handler(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                message = await connection.receive_message()
                if isinstance(message, Request):
                    corrupt_requests.append(message.chunk_index)
                    await connection.send_piece(message.chunk_index, b"FAIL")
        except (ConnectionClosed, ProtocolError):
            return

    async def good_handler(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                message = await connection.receive_message()
                if isinstance(message, Request):
                    good_requests.append(message.chunk_index)
                    await connection.send_piece(message.chunk_index, chunks[message.chunk_index])
        except (ConnectionClosed, ProtocolError):
            return

    bad_peer = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="bad-seeder",
        chunk_count=manifest["chunk_count"],
        local_bitfield=all_chunks,
        on_connection=corrupt_handler,
    )
    good_peer = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="good-seeder",
        chunk_count=manifest["chunk_count"],
        local_bitfield=all_chunks,
        on_connection=good_handler,
    )

    async with bad_peer, good_peer:
        connections = [
            await connect_to_server(bad_peer, "leecher-bad", manifest["chunk_count"]),
            await connect_to_server(good_peer, "leecher-good", manifest["chunk_count"]),
        ]
        storage = StorageManager(manifest, tmp_path / "downloads")
        scheduler = DownloadScheduler(manifest["chunk_count"])
        downloader = SwarmDownloader(
            connections,
            scheduler,
            storage,
            max_retries=1,
            retry_delay=0,
        )

        async with asyncio.timeout(5):
            completed = await downloader.run()

    assert completed == {0, 1, 2}
    assert corrupt_requests
    assert set(good_requests) == {0, 1, 2}
    assert (tmp_path / "downloads" / "source.bin").read_bytes() == contents
    assert scheduler.is_complete


@pytest.mark.asyncio
async def test_swarm_downloader_reassigns_chunk_after_peer_disconnect(
    tmp_path: Path,
) -> None:
    contents = b"data"
    _, manifest = create_source(tmp_path, contents)
    all_chunks = Bitfield.from_indices([0], 1)
    disconnected = asyncio.Event()

    async def dropping_handler(connection: PeerConnection) -> None:
        try:
            await connection.receive_message()
            disconnected.set()
            await connection.close()
        except (ConnectionClosed, ProtocolError):
            disconnected.set()

    async def good_handler(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                message = await connection.receive_message()
                if isinstance(message, Request):
                    await connection.send_piece(message.chunk_index, contents)
        except (ConnectionClosed, ProtocolError):
            return

    dropping_peer = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="dropping-seeder",
        chunk_count=1,
        local_bitfield=all_chunks,
        on_connection=dropping_handler,
    )
    good_peer = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="recovery-seeder",
        chunk_count=1,
        local_bitfield=all_chunks,
        on_connection=good_handler,
    )

    async with dropping_peer, good_peer:
        connections = [
            await connect_to_server(dropping_peer, "leecher-drop", 1),
            await connect_to_server(good_peer, "leecher-recover", 1),
        ]
        scheduler = DownloadScheduler(1)
        downloader = SwarmDownloader(
            connections,
            scheduler,
            StorageManager(manifest, tmp_path / "downloads"),
            max_retries=2,
            retry_delay=0,
        )
        async with asyncio.timeout(5):
            completed = await downloader.run()
            await disconnected.wait()

    assert completed == {0}
    assert (tmp_path / "downloads" / "source.bin").read_bytes() == contents
    assert scheduler.state_for(0) == ChunkState.VERIFIED


@pytest.mark.asyncio
async def test_swarm_downloader_cancellation_releases_and_closes_peers(
    tmp_path: Path,
) -> None:
    contents = b"data"
    _, manifest = create_source(tmp_path, contents)
    request_received = asyncio.Event()
    never_release = asyncio.Event()

    async def stalled_handler(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                message = await connection.receive_message()
                if isinstance(message, Request):
                    request_received.set()
                    await never_release.wait()
        except (ConnectionClosed, ProtocolError):
            return

    seeder = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="stalled-seeder",
        chunk_count=manifest["chunk_count"],
        local_bitfield=Bitfield.from_indices([0], 1),
        on_connection=stalled_handler,
    )

    async with seeder:
        connection = await connect_to_server(seeder, "leecher-stalled", 1)
        scheduler = DownloadScheduler(1)
        downloader = SwarmDownloader(
            [connection],
            scheduler,
            StorageManager(manifest, tmp_path / "downloads"),
            max_retries=1,
        )
        task = asyncio.create_task(downloader.run())
        try:
            async with asyncio.timeout(3):
                await request_received.wait()
            task.cancel()
            async with asyncio.timeout(3):
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            never_release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    assert scheduler.inflight_chunks == frozenset()
    assert scheduler.state_for(0) == ChunkState.MISSING
    assert connection.is_closed


@pytest.mark.asyncio
async def test_swarm_downloader_reports_unavailable_chunks_and_closes_peer(
    tmp_path: Path,
) -> None:
    _, manifest = create_source(tmp_path, b"data")

    async def idle_handler(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                await connection.receive_message()
        except (ConnectionClosed, ProtocolError):
            return

    seeder = PeerServer(
        swarm_id=SWARM_ID,
        my_peer_id="empty-seeder",
        chunk_count=manifest["chunk_count"],
        local_bitfield=Bitfield.from_indices([], manifest["chunk_count"]),
        on_connection=idle_handler,
    )
    async with seeder:
        connection = await connect_to_server(seeder, "leecher-empty", manifest["chunk_count"])
        scheduler = DownloadScheduler(manifest["chunk_count"])
        downloader = SwarmDownloader(
            [connection],
            scheduler,
            StorageManager(manifest, tmp_path / "downloads"),
        )
        with pytest.raises(NoAvailablePeersError, match="missing chunks"):
            await downloader.run()

    assert connection.is_closed
