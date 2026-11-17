"""Unit tests for peer lifecycle validation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

import p2p.peer.client as client_module
from p2p.peer.client import SwarmPeer
from p2p.peer.connection import PeerConnection
from p2p.peer.downloader import NoAvailablePeersError
from p2p.peer.server import PeerServer
from p2p.protocol import Bitfield, ConnectionClosed, Handshake, ProtocolError, read_message
from p2p.storage.manifest import build_manifest
from p2p.tracker.models import AnnounceResponse, PeerInfo
from p2p.tracker.server import app


@pytest.mark.asyncio
async def test_seeder_rejects_file_that_does_not_match_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    manifest = build_manifest(source, chunk_size=4)
    altered_source = tmp_path / "altered.bin"
    altered_source.write_bytes(b"different contents")
    peer = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path,
        seed_file=altered_source,
        tracker_transport=httpx.ASGITransport(app=app),
    )
    waiter = asyncio.create_task(peer.wait_until_stopped())
    await asyncio.sleep(0)

    with pytest.raises(ValueError, match="do not match"):
        await peer.start()

    await asyncio.wait_for(waiter, timeout=1)

    assert peer._server is None
    assert peer._http.is_closed


@pytest.mark.asyncio
async def test_tracker_failure_after_listener_start_cleans_up_peer(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    listener_started = False
    peer: SwarmPeer

    async def unavailable_tracker(_request: httpx.Request) -> httpx.Response:
        nonlocal listener_started
        listener_started = peer._server is not None and peer._server.is_running
        return httpx.Response(503, json={"detail": "tracker unavailable"})

    peer = SwarmPeer(
        build_manifest(source, chunk_size=4),
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.MockTransport(unavailable_tracker),
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await asyncio.wait_for(peer.start(), timeout=1)

        assert listener_started
        assert peer._server is None
        assert peer._http.is_closed
        await asyncio.wait_for(peer.wait_until_stopped(), timeout=1)
    finally:
        await asyncio.wait_for(peer.close(), timeout=1)


@pytest.mark.asyncio
async def test_start_rollback_closes_http_and_sets_stopped_when_server_stop_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    peer: SwarmPeer | None = None
    try:
        with monkeypatch.context() as patch:

            async def unavailable_tracker(_request: httpx.Request) -> httpx.Response:
                assert peer is not None
                server = peer._server
                assert server is not None and server.is_running
                original_stop = server.stop

                async def stop_then_fail() -> None:
                    await original_stop()
                    raise OSError("injected server stop failure")

                patch.setattr(server, "stop", stop_then_fail)
                return httpx.Response(503, json={"detail": "tracker unavailable"})

            peer = SwarmPeer(
                build_manifest(source, chunk_size=4),
                "http://tracker.test",
                tmp_path / "downloads",
                tracker_transport=httpx.MockTransport(unavailable_tracker),
            )
            with pytest.raises(BaseExceptionGroup) as exc_info:
                await asyncio.wait_for(peer.start(), timeout=1)

            assert any(
                isinstance(error, httpx.HTTPStatusError) for error in exc_info.value.exceptions
            )
            assert any(
                isinstance(error, OSError) and "injected server stop failure" in str(error)
                for error in exc_info.value.exceptions
            )
            assert peer._server is None
            assert peer._http.is_closed
            assert peer._stopped_event.is_set()
    finally:
        if peer is not None:
            await asyncio.wait_for(peer.close(), timeout=1)


@pytest.mark.asyncio
async def test_close_wakes_waiters_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    peer = SwarmPeer(
        build_manifest(source, chunk_size=4),
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
    )
    waiter = asyncio.create_task(peer.wait_until_stopped())
    await asyncio.sleep(0)
    assert not waiter.done()

    await asyncio.wait_for(peer.close(), timeout=1)
    await asyncio.wait_for(waiter, timeout=1)
    await asyncio.wait_for(peer.wait_until_stopped(), timeout=1)
    await asyncio.wait_for(peer.close(), timeout=1)


@pytest.mark.asyncio
async def test_concurrent_close_waits_for_shared_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    peer = SwarmPeer(
        build_manifest(source, chunk_size=4),
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
        peer_id="concurrent-close-peer",
    )
    await peer.start()
    assert peer._server is not None
    original_stop = peer._server.stop
    stop_started = asyncio.Event()
    allow_stop = asyncio.Event()
    second_close: asyncio.Task[None] | None = None

    async def delayed_stop() -> None:
        stop_started.set()
        await allow_stop.wait()
        await original_stop()

    monkeypatch.setattr(peer._server, "stop", delayed_stop)
    first_close = asyncio.create_task(peer.close())
    try:
        await asyncio.wait_for(stop_started.wait(), timeout=1)
        second_close = asyncio.create_task(peer.close())
        await asyncio.sleep(0)
        assert not second_close.done()
    finally:
        allow_stop.set()
        tasks = [first_close]
        if second_close is not None:
            tasks.append(second_close)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)

    assert peer._http.is_closed
    assert peer._server is None


async def _wait_for_connection(connection: PeerConnection) -> None:
    try:
        while connection.is_connected:
            await connection.receive_message()
    except (ConnectionClosed, ProtocolError):
        return


async def _start_peer_server(
    peer_id: str,
    swarm_id: str,
    chunk_count: int,
    *,
    on_connection: Callable[[PeerConnection], Coroutine[Any, Any, None]] | None = None,
) -> PeerServer:
    server = PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=swarm_id,
        my_peer_id=peer_id,
        chunk_count=chunk_count,
        local_bitfield=Bitfield.from_indices([], chunk_count),
        on_connection=on_connection,
    )
    await server.start()
    return server


@pytest.mark.asyncio
async def test_peer_discovery_tries_later_candidates_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest = build_manifest(source, chunk_size=4)
    peer = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
        peer_id="discovery-client",
    )
    peer._server = await _start_peer_server(
        peer.peer_id,
        peer.swarm_id,
        manifest["chunk_count"],
    )
    reachable_server = await _start_peer_server(
        "later-peer",
        peer.swarm_id,
        manifest["chunk_count"],
        on_connection=_wait_for_connection,
    )
    unused_server = await asyncio.start_server(lambda _reader, _writer: None, "127.0.0.1", 0)
    unreachable_port = unused_server.sockets[0].getsockname()[1]
    unused_server.close()
    await unused_server.wait_closed()
    monkeypatch.setattr(client_module, "MAX_PEER_CONNECTIONS", 1)

    candidates = [
        PeerInfo(peer_id="unreachable", host="127.0.0.1", port=unreachable_port),
        PeerInfo(peer_id="later-peer", host="127.0.0.1", port=reachable_server.listen_port),
    ]
    connections: list[PeerConnection] = []
    try:
        async with asyncio.timeout(3):
            connections = await peer._connect_to_peers(candidates)
        assert len(connections) == 1
        assert connections[0].remote_peer_id == "later-peer"
        assert len(connections) <= 1
    finally:
        await asyncio.gather(*(connection.close() for connection in connections))
        await peer.close()
        await reachable_server.stop()

    assert reachable_server.active_connection_count == 0
    assert not reachable_server._connection_tasks


@pytest.mark.asyncio
async def test_peer_discovery_cancellation_closes_attempts_and_restores_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest = build_manifest(source, chunk_size=4)
    peer = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
        peer_id="cancelled-discovery",
    )
    peer._server = await _start_peer_server(
        peer.peer_id,
        peer.swarm_id,
        manifest["chunk_count"],
        on_connection=_wait_for_connection,
    )
    existing_peer = await PeerConnection.connect(
        "127.0.0.1",
        peer.listen_port,
        swarm_id=peer.swarm_id,
        my_peer_id="existing-peer",
        my_listen_port=6881,
        chunk_count=manifest["chunk_count"],
        local_bitfield=Bitfield.from_indices([], manifest["chunk_count"]),
    )
    handshake_received = asyncio.Event()
    remote_disconnected = asyncio.Event()
    handler_tasks: set[asyncio.Task[None]] = set()
    accepted_writers: list[asyncio.StreamWriter] = []

    async def stalled_candidate(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            handler_tasks.add(task)
        accepted_writers.append(writer)
        try:
            message = await read_message(reader)
            if isinstance(message, Handshake):
                handshake_received.set()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            if task is not None:
                handler_tasks.discard(task)
            remote_disconnected.set()

    stalled_server = await asyncio.start_server(stalled_candidate, "127.0.0.1", 0)
    candidate_port = stalled_server.sockets[0].getsockname()[1]
    monkeypatch.setattr(client_module, "MAX_PEER_CONNECTIONS", 2)

    original_connect = PeerConnection.connect
    connector_tasks: list[asyncio.Task[Any]] = []

    async def tracked_connect(
        cls: type[PeerConnection],
        /,
        host: str,
        port: int,
        **kwargs: Any,
    ) -> PeerConnection:
        task = asyncio.current_task()
        if task is not None:
            connector_tasks.append(task)
        return await original_connect(host, port, **kwargs)

    monkeypatch.setattr(PeerConnection, "connect", classmethod(tracked_connect))
    discovery_task = asyncio.create_task(
        peer._connect_to_peers(
            [PeerInfo(peer_id="stalled-peer", host="127.0.0.1", port=candidate_port)]
        )
    )
    recovered_peer: PeerConnection | None = None
    try:
        await asyncio.wait_for(handshake_received.wait(), timeout=1)
        discovery_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(discovery_task, timeout=1)
        await asyncio.wait_for(remote_disconnected.wait(), timeout=1)

        assert discovery_task.cancelled()
        assert connector_tasks and all(task.done() for task in connector_tasks)
        assert not handler_tasks
        assert existing_peer.is_connected
        assert peer._server.active_connection_count == 1
        assert peer._server._max_connections == 2
        assert peer._outbound_connection_count == 0

        recovered_peer = await PeerConnection.connect(
            "127.0.0.1",
            peer.listen_port,
            swarm_id=peer.swarm_id,
            my_peer_id="recovery-peer",
            my_listen_port=6882,
            chunk_count=manifest["chunk_count"],
            local_bitfield=Bitfield.from_indices([], manifest["chunk_count"]),
        )
        assert peer._server.active_connection_count == 2
    finally:
        if not discovery_task.done():
            discovery_task.cancel()
            await asyncio.gather(discovery_task, return_exceptions=True)
        if recovered_peer is not None:
            await recovered_peer.close()
        await existing_peer.close()
        await peer.close()
        for writer in accepted_writers:
            writer.close()
        stalled_server.close()
        await asyncio.wait_for(stalled_server.wait_closed(), timeout=1)
        if handler_tasks:
            for task in handler_tasks:
                task.cancel()
            await asyncio.gather(*handler_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_empty_peer_discovery_fails_clearly(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    peer = SwarmPeer(
        build_manifest(source, chunk_size=4),
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
        peer_id="empty-discovery-peer",
    )
    try:
        await peer.start()
        with pytest.raises(NoAvailablePeersError, match="no reachable peers"):
            await peer.download()
    finally:
        await peer.close()


@pytest.mark.asyncio
async def test_peer_discovery_deduplicates_candidates_and_preserves_inbound_peer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest = build_manifest(source, chunk_size=4)
    peer = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
        peer_id="existing-client",
    )
    peer._server = await _start_peer_server(
        peer.peer_id,
        peer.swarm_id,
        manifest["chunk_count"],
        on_connection=_wait_for_connection,
    )
    existing_peer = await PeerConnection.connect(
        "127.0.0.1",
        peer.listen_port,
        swarm_id=peer.swarm_id,
        my_peer_id="existing-peer",
        my_listen_port=6881,
        chunk_count=manifest["chunk_count"],
        local_bitfield=Bitfield.from_indices([], manifest["chunk_count"]),
    )
    candidate_server = await _start_peer_server(
        "candidate-peer",
        peer.swarm_id,
        manifest["chunk_count"],
        on_connection=_wait_for_connection,
    )
    monkeypatch.setattr(client_module, "MAX_PEER_CONNECTIONS", 2)
    candidate = PeerInfo(
        peer_id="candidate-peer",
        host="127.0.0.1",
        port=candidate_server.listen_port,
    )
    connections: list[PeerConnection] = []
    try:
        connections = await peer._connect_to_peers([candidate, candidate])
        assert len(connections) == 1
        assert connections[0].remote_peer_id == "candidate-peer"
        assert existing_peer.is_connected
        assert peer._server.active_connection_count == 1
        assert peer._server.active_connection_count + len(connections) == 2
    finally:
        await asyncio.gather(*(connection.close() for connection in connections))
        await existing_peer.close()
        await peer.close()
        await candidate_server.stop()

    assert not candidate_server._connection_tasks
    assert peer._server is None


@pytest.mark.asyncio
async def test_heartbeat_requires_a_started_peer(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    peer = SwarmPeer(
        build_manifest(source, chunk_size=4),
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
    )
    try:
        with pytest.raises(RuntimeError, match="must be started"):
            await peer.heartbeat()
    finally:
        await peer.close()


@pytest.mark.asyncio
async def test_periodic_heartbeat_uses_tracker_interval_and_stops_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest contents")
    peer = SwarmPeer(
        build_manifest(source, chunk_size=4),
        "http://tracker.test",
        tmp_path / "downloads",
        tracker_transport=httpx.ASGITransport(app=app),
    )
    peer._started = True
    peer._heartbeat_interval = 30
    heartbeat_sent = asyncio.Event()
    sleep_calls = 0

    async def fake_sleep(delay: float) -> None:
        nonlocal sleep_calls
        assert delay == 30
        sleep_calls += 1
        if sleep_calls > 1:
            await asyncio.Event().wait()

    async def fake_heartbeat() -> None:
        heartbeat_sent.set()

    monkeypatch.setattr("p2p.peer.client.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(peer, "heartbeat", fake_heartbeat)
    peer._heartbeat_task = asyncio.create_task(peer._heartbeat_loop())

    await asyncio.wait_for(heartbeat_sent.wait(), timeout=1)
    await peer.close()

    assert peer._heartbeat_task is None


def test_tracker_response_rejects_invalid_peer_descriptors_and_interval() -> None:
    with pytest.raises(ValidationError):
        AnnounceResponse.model_validate({"interval": 0, "peers": []})
    with pytest.raises(ValidationError):
        AnnounceResponse.model_validate(
            {
                "interval": 30,
                "peers": [{"peer_id": "peer", "host": "not a host", "port": 70000}],
            }
        )
