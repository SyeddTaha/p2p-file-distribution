"""Integration tests for PeerServer, loopback peer exchange, and fault handling."""

from __future__ import annotations

import asyncio

import pytest

from p2p.peer.connection import ConnectionState, PeerConnection
from p2p.peer.server import PeerServer
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Handshake,
    Have,
    Piece,
    ProtocolError,
    Request,
    read_message,
)

SAMPLE_SWARM_ID = "b1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890"


@pytest.mark.asyncio
async def test_peer_server_lifecycle_and_port_binding() -> None:
    bf = Bitfield.from_indices([0, 1], 4)
    server = PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="seeder-srv",
        chunk_count=4,
        local_bitfield=bf,
    )
    assert not server.is_running

    port = await server.start()
    assert server.is_running
    assert port > 0
    assert server.listen_port == port

    await server.stop()
    assert not server.is_running


@pytest.mark.asyncio
async def test_peer_server_async_context_manager() -> None:
    bf = Bitfield.from_indices([0], 2)
    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="server-1",
        chunk_count=2,
        local_bitfield=bf,
    ) as server:
        assert server.is_running
        assert server.listen_port > 0

    assert not server.is_running


@pytest.mark.asyncio
async def test_server_shutdown_closes_active_connections_and_handler_tasks() -> None:
    async def keep_open(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                await connection.receive_message()
        except (ConnectionClosed, ProtocolError):
            return

    server = PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="shutdown-server",
        chunk_count=1,
        local_bitfield=Bitfield.from_indices([0], 1),
        on_connection=keep_open,
    )
    await asyncio.wait_for(server.start(), timeout=1)
    client: PeerConnection | None = None
    try:
        client = await asyncio.wait_for(
            PeerConnection.connect(
                "127.0.0.1",
                server.listen_port,
                swarm_id=SAMPLE_SWARM_ID,
                my_peer_id="shutdown-client",
                my_listen_port=6881,
                chunk_count=1,
                local_bitfield=Bitfield.from_indices([], 1),
            ),
            timeout=2,
        )
        assert server.active_connection_count == 1
        await asyncio.wait_for(server.stop(), timeout=2)
        assert server.active_connection_count == 0
        assert not server._connection_tasks
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(client.receive_message(), timeout=1)
    finally:
        if client is not None:
            await asyncio.wait_for(client.close(), timeout=1)
        await asyncio.wait_for(server.stop(), timeout=1)


@pytest.mark.asyncio
async def test_full_loopback_peer_exchange() -> None:
    """Seeder serves chunks to a leecher over PeerServer and PeerConnection."""
    chunk_count = 4
    seeder_bf = Bitfield.from_indices([0, 1, 2, 3], chunk_count)
    leecher_bf = Bitfield.from_indices([], chunk_count)

    chunk_data_map = {
        0: b"ZERO_CHUNK_PAYLOAD_BYTES",
        1: b"ONE_CHUNK_PAYLOAD_BYTES",
    }

    async def seeder_worker(conn: PeerConnection) -> None:
        """Simple server worker loop handling requests."""
        try:
            while conn.is_connected:
                msg = await conn.receive_message()
                if isinstance(msg, Request):
                    data = chunk_data_map.get(msg.chunk_index, b"")
                    await conn.send_piece(msg.chunk_index, data)
                elif isinstance(msg, Have):
                    # Leecher verified and announced a chunk
                    pass
        except (ConnectionClosed, ProtocolError):
            pass

    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="seeder-node",
        chunk_count=chunk_count,
        local_bitfield=seeder_bf,
        on_connection=seeder_worker,
    ) as server:
        # Leecher connects to seeder
        client_conn = await PeerConnection.connect(
            "127.0.0.1",
            server.listen_port,
            swarm_id=SAMPLE_SWARM_ID,
            my_peer_id="leecher-node",
            my_listen_port=7888,
            chunk_count=chunk_count,
            local_bitfield=leecher_bf,
        )

        async with client_conn:
            assert client_conn.state == ConnectionState.STEADY_STATE
            assert client_conn.remote_peer_id == "seeder-node"
            assert client_conn.remote_bitfield is not None
            assert client_conn.remote_bitfield.to_indices(chunk_count) == {0, 1, 2, 3}

            # Leecher requests chunk 0
            await client_conn.send_request(0)
            piece_0 = await client_conn.receive_message()
            assert isinstance(piece_0, Piece)
            assert piece_0.chunk_index == 0
            assert piece_0.data == chunk_data_map[0]

            # Leecher announces HAVE(0)
            await client_conn.send_have(0)

            # Leecher requests chunk 1
            await client_conn.send_request(1)
            piece_1 = await client_conn.receive_message()
            assert isinstance(piece_1, Piece)
            assert piece_1.chunk_index == 1
            assert piece_1.data == chunk_data_map[1]


@pytest.mark.asyncio
async def test_peer_server_multiple_concurrent_connections() -> None:
    chunk_count = 4
    server_bf = Bitfield.from_indices([0, 1, 2, 3], chunk_count)

    connected_peers: list[str] = []
    connection_event = asyncio.Event()

    async def on_client(conn: PeerConnection) -> None:
        if conn.remote_peer_id is not None:
            connected_peers.append(conn.remote_peer_id)
        if len(connected_peers) == 3:
            connection_event.set()
        try:
            while conn.is_connected:
                await conn.receive_message()
        except (ConnectionClosed, ProtocolError):
            pass

    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="multi-server",
        chunk_count=chunk_count,
        local_bitfield=server_bf,
        on_connection=on_client,
    ) as server:
        clients: list[PeerConnection] = []
        for i in range(3):
            cli = await PeerConnection.connect(
                "127.0.0.1",
                server.listen_port,
                swarm_id=SAMPLE_SWARM_ID,
                my_peer_id=f"client-{i}",
                my_listen_port=8000 + i,
                chunk_count=chunk_count,
                local_bitfield=Bitfield.from_indices([], chunk_count),
            )
            clients.append(cli)

        await asyncio.wait_for(connection_event.wait(), timeout=3.0)
        assert len(connected_peers) == 3
        assert sorted(connected_peers) == ["client-0", "client-1", "client-2"]
        assert server.active_connection_count == 3

        for cli in clients:
            await cli.close()


@pytest.mark.asyncio
async def test_peer_server_handles_rogue_client_gracefully() -> None:
    """A rogue client connects and sends malformed garbage bytes; server survives."""
    server_bf = Bitfield.from_indices([0], 2)
    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="resilient-srv",
        chunk_count=2,
        local_bitfield=server_bf,
    ) as server:
        # Rogue client sends garbage
        reader, writer = await asyncio.open_connection("127.0.0.1", server.listen_port)
        writer.write(b"NOT_A_VALID_FRAME_AT_ALL_GARBAGE\x00\xff")
        await writer.drain()

        # Server should disconnect rogue client
        await asyncio.sleep(0.1)
        writer.close()
        await writer.wait_closed()

        # Server is still up and accepts legitimate peer
        legit_conn = await PeerConnection.connect(
            "127.0.0.1",
            server.listen_port,
            swarm_id=SAMPLE_SWARM_ID,
            my_peer_id="legit-peer",
            my_listen_port=9001,
            chunk_count=2,
            local_bitfield=Bitfield.from_indices([], 2),
        )
        assert legit_conn.is_connected
        await legit_conn.close()


@pytest.mark.asyncio
async def test_peer_server_rejects_connections_over_configured_limit() -> None:
    chunk_count = 1

    async def keep_open(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                await connection.receive_message()
        except (ConnectionClosed, ProtocolError):
            return

    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="limited-server",
        chunk_count=chunk_count,
        local_bitfield=Bitfield.from_indices([0], chunk_count),
        on_connection=keep_open,
        max_connections=1,
    ) as server:
        first = await asyncio.wait_for(
            PeerConnection.connect(
                "127.0.0.1",
                server.listen_port,
                swarm_id=SAMPLE_SWARM_ID,
                my_peer_id="first-client",
                my_listen_port=9001,
                chunk_count=chunk_count,
                local_bitfield=Bitfield.from_indices([], chunk_count),
            ),
            timeout=3,
        )
        try:
            with pytest.raises((ConnectionClosed, ProtocolError)):
                await asyncio.wait_for(
                    PeerConnection.connect(
                        "127.0.0.1",
                        server.listen_port,
                        swarm_id=SAMPLE_SWARM_ID,
                        my_peer_id="second-client",
                        my_listen_port=9002,
                        chunk_count=chunk_count,
                        local_bitfield=Bitfield.from_indices([], chunk_count),
                        handshake_timeout=1,
                    ),
                    timeout=3,
                )
            assert server.active_connection_count == 1
        finally:
            await asyncio.wait_for(first.close(), timeout=1)


@pytest.mark.asyncio
async def test_simultaneous_connections_respect_capacity_and_release_slots() -> None:
    handler_tasks: dict[str, asyncio.Task[None]] = {}
    handler_changed = asyncio.Event()

    async def keep_open(connection: PeerConnection) -> None:
        task = asyncio.current_task()
        assert task is not None
        assert connection.remote_peer_id is not None
        handler_tasks[connection.remote_peer_id] = task
        handler_changed.set()
        try:
            while connection.is_connected:
                await connection.receive_message()
        except (ConnectionClosed, ProtocolError):
            return

    chunk_count = 1
    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="simultaneous-server",
        chunk_count=chunk_count,
        local_bitfield=Bitfield.from_indices([0], chunk_count),
        on_connection=keep_open,
        max_connections=2,
    ) as server:

        async def connect(index: int) -> PeerConnection:
            return await PeerConnection.connect(
                "127.0.0.1",
                server.listen_port,
                swarm_id=SAMPLE_SWARM_ID,
                my_peer_id=f"simultaneous-client-{index}",
                my_listen_port=9000 + index,
                chunk_count=chunk_count,
                local_bitfield=Bitfield.from_indices([], chunk_count),
            )

        async def handler_for(peer_id: str) -> asyncio.Task[None]:
            while peer_id not in handler_tasks:
                handler_changed.clear()
                if peer_id in handler_tasks:
                    break
                await handler_changed.wait()
            return handler_tasks[peer_id]

        results = await asyncio.wait_for(
            asyncio.gather(
                *(connect(index) for index in range(3)),
                return_exceptions=True,
            ),
            timeout=5,
        )
        connected = [result for result in results if isinstance(result, PeerConnection)]
        rejected = [result for result in results if isinstance(result, Exception)]
        retried: PeerConnection | None = None
        try:
            assert len(results) == 3
            assert len(connected) == 2
            assert len(rejected) == 1
            assert server.active_connection_count == 2

            await asyncio.wait_for(connected[0].close(), timeout=1)
            handler_task = await asyncio.wait_for(
                handler_for(connected[0].my_peer_id),
                timeout=1,
            )
            await asyncio.wait_for(handler_task, timeout=1)
            assert server.active_connection_count == 1

            retried = await asyncio.wait_for(connect(3), timeout=3)
            assert retried.is_connected
            assert server.active_connection_count == 2
        finally:
            connections_to_close = [*connected]
            if retried is not None:
                connections_to_close.append(retried)
            close_results = await asyncio.wait_for(
                asyncio.gather(
                    *(connection.close() for connection in connections_to_close),
                    return_exceptions=True,
                ),
                timeout=2,
            )
            assert not any(isinstance(result, BaseException) for result in close_results)

        remaining_handlers = [
            await asyncio.wait_for(handler_for(connection.my_peer_id), timeout=1)
            for connection in connected[1:]
        ]
        if retried is not None:
            remaining_handlers.append(
                await asyncio.wait_for(handler_for(retried.my_peer_id), timeout=1)
            )
        await asyncio.wait_for(asyncio.gather(*remaining_handlers), timeout=2)
        assert server.active_connection_count == 0
        assert not server._connection_tasks


@pytest.mark.asyncio
async def test_failed_handshake_releases_capacity_and_handler_task() -> None:
    async def keep_open(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                await connection.receive_message()
        except (ConnectionClosed, ProtocolError):
            return

    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="failed-handshake-server",
        chunk_count=1,
        local_bitfield=Bitfield.from_indices([0], 1),
        handshake_timeout=1,
        on_connection=keep_open,
        max_connections=1,
    ) as server:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", server.listen_port),
            timeout=1,
        )
        assert isinstance(await asyncio.wait_for(read_message(reader), timeout=1), Handshake)
        writer.write(b"\x00\x00\x00\x01\xff")
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), timeout=1) == b""
        writer.close()
        await writer.wait_closed()
        tasks = tuple(server._connection_tasks)
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        assert server.active_connection_count == 0
        assert not server._connection_tasks

        connection = await asyncio.wait_for(
            PeerConnection.connect(
                "127.0.0.1",
                server.listen_port,
                swarm_id=SAMPLE_SWARM_ID,
                my_peer_id="after-failure-client",
                my_listen_port=9001,
                chunk_count=1,
                local_bitfield=Bitfield.from_indices([], 1),
            ),
            timeout=3,
        )
        try:
            assert connection.is_connected
            assert server.active_connection_count == 1
        finally:
            await asyncio.wait_for(connection.close(), timeout=1)


@pytest.mark.asyncio
async def test_server_reports_cleanup_errors_after_stopping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="cleanup-error-server",
        chunk_count=1,
        local_bitfield=Bitfield.from_indices([0], 1),
    )
    await asyncio.wait_for(server.start(), timeout=1)
    assert server._server is not None

    async def fail_wait_closed() -> None:
        raise OSError("listener wait failed")

    monkeypatch.setattr(server._server, "wait_closed", fail_wait_closed)
    with pytest.raises(ExceptionGroup, match="PeerServer cleanup failed") as exc_info:
        await asyncio.wait_for(server.stop(), timeout=1)

    assert any("listener wait failed" in str(error) for error in exc_info.value.exceptions)
    assert not server.is_running
    assert server._server is None


@pytest.mark.asyncio
async def test_bracketed_ipv6_addresses_are_normalized_for_sockets() -> None:
    probe = None
    try:
        probe = await asyncio.start_server(lambda _reader, _writer: None, "::1", 0)
    except OSError:
        pytest.skip("IPv6 loopback is unavailable")
    finally:
        if probe is not None:
            probe.close()
            await probe.wait_closed()

    async def keep_open(connection: PeerConnection) -> None:
        try:
            while connection.is_connected:
                await connection.receive_message()
        except (ConnectionClosed, ProtocolError):
            return

    server = PeerServer(
        host="[::1]",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="ipv6-server",
        chunk_count=1,
        local_bitfield=Bitfield.from_indices([0], 1),
        on_connection=keep_open,
    )
    await asyncio.wait_for(server.start(), timeout=1)
    connection: PeerConnection | None = None
    try:
        connection = await asyncio.wait_for(
            PeerConnection.connect(
                "[::1]",
                server.listen_port,
                swarm_id=SAMPLE_SWARM_ID,
                my_peer_id="ipv6-client",
                my_listen_port=6881,
                chunk_count=1,
                local_bitfield=Bitfield.from_indices([], 1),
            ),
            timeout=3,
        )
        assert connection.is_connected
        assert connection.remote_peer_id == "ipv6-server"
    finally:
        if connection is not None:
            await asyncio.wait_for(connection.close(), timeout=1)
        await asyncio.wait_for(server.stop(), timeout=2)


@pytest.mark.asyncio
async def test_peer_server_handles_hanging_client_timeout() -> None:
    """A hanging client connects but never handshakes; server cleans up via timeout."""
    server_bf = Bitfield.from_indices([0], 2)
    async with PeerServer(
        host="127.0.0.1",
        port=0,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="timeout-srv",
        chunk_count=2,
        local_bitfield=server_bf,
        handshake_timeout=0.1,
    ) as server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.listen_port)
        # Client never sends anything
        await asyncio.sleep(0.3)
        assert server.active_connection_count == 0

        writer.close()
        await writer.wait_closed()
