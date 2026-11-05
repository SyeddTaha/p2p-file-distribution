"""Integration tests for PeerServer, loopback peer exchange, and fault handling."""

from __future__ import annotations

import asyncio

import pytest

from p2p.peer.connection import ConnectionState, PeerConnection
from p2p.peer.server import PeerServer
from p2p.protocol import Bitfield, ConnectionClosed, Have, Piece, ProtocolError, Request

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
