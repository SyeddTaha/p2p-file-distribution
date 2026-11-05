"""Unit tests for PeerConnection state machine, message handling, and timeouts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from p2p.peer.connection import ConnectionState, PeerConnection
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Handshake,
    Have,
    Piece,
    ProtocolError,
    Request,
    read_message,
    write_message,
)
from p2p.protocol.codec import encode_frame, write_frame

SAMPLE_SWARM_ID = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890"


def get_stream_reader(conn: PeerConnection) -> asyncio.StreamReader:
    """Helper to get non-null StreamReader for testing."""
    assert conn._reader is not None
    return conn._reader


def get_stream_writer(conn: PeerConnection) -> asyncio.StreamWriter:
    """Helper to get non-null StreamWriter for testing."""
    assert conn._writer is not None
    return conn._writer


@asynccontextmanager
async def connected_peer_pair(
    *,
    swarm_id: str = SAMPLE_SWARM_ID,
    peer_a_id: str = "peer-alpha",
    peer_b_id: str = "peer-beta",
    chunk_count: int = 4,
    bf_a: Bitfield | None = None,
    bf_b: Bitfield | None = None,
    handshake_timeout: float = 2.0,
    idle_timeout: float = 2.0,
    stall_timeout: float = 2.0,
    max_inflight: int = 4,
) -> AsyncIterator[tuple[PeerConnection, PeerConnection]]:
    """Context manager yielding a connected loopback pair of PeerConnections."""
    if bf_a is None:
        bf_a = Bitfield.from_indices([0, 1], chunk_count)
    if bf_b is None:
        bf_b = Bitfield.from_indices([2, 3], chunk_count)

    server_conn_future: asyncio.Future[PeerConnection] = asyncio.get_running_loop().create_future()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn = PeerConnection.accept(
            reader=reader,
            writer=writer,
            swarm_id=swarm_id,
            my_peer_id=peer_b_id,
            my_listen_port=6882,
            chunk_count=chunk_count,
            local_bitfield=bf_b,
            handshake_timeout=handshake_timeout,
            idle_timeout=idle_timeout,
            stall_timeout=stall_timeout,
            max_inflight=max_inflight,
        )
        server_conn_future.set_result(conn)

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    conn_a = await PeerConnection.connect(
        "127.0.0.1",
        port,
        swarm_id=swarm_id,
        my_peer_id=peer_a_id,
        my_listen_port=6881,
        chunk_count=chunk_count,
        local_bitfield=bf_a,
        handshake_timeout=handshake_timeout,
        idle_timeout=idle_timeout,
        stall_timeout=stall_timeout,
        max_inflight=max_inflight,
        auto_handshake=False,
    )
    conn_b = await server_conn_future

    try:
        yield conn_a, conn_b
    finally:
        await conn_a.close()
        await conn_b.close()
        server.close()
        await server.wait_closed()


# ==============================================================================
# 1. Initialization and Initial States
# ==============================================================================


def test_peer_connection_initial_state() -> None:
    bf = Bitfield.from_indices([0], 4)
    conn = PeerConnection(
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="peer-1",
        my_listen_port=6881,
        chunk_count=4,
        local_bitfield=bf,
    )
    assert conn.state == ConnectionState.UNCONNECTED
    assert not conn.is_connected
    assert not conn.is_closed
    assert conn.my_peer_id == "peer-1"
    assert conn.swarm_id == SAMPLE_SWARM_ID
    assert conn.chunk_count == 4
    assert conn.local_bitfield == bf
    assert conn.remote_peer_id is None
    assert conn.remote_listen_port is None
    assert conn.remote_handshake is None
    assert conn.remote_bitfield is None
    assert len(conn.pending_requests) == 0


def test_peer_connection_accept_initial_state() -> None:
    bf = Bitfield.from_indices([0], 4)
    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    conn = PeerConnection.accept(
        reader=reader,
        writer=writer,
        swarm_id=SAMPLE_SWARM_ID,
        my_peer_id="peer-1",
        my_listen_port=6881,
        chunk_count=4,
        local_bitfield=bf,
    )
    assert conn.state == ConnectionState.AWAIT_HANDSHAKE
    assert not conn.is_connected
    assert not conn.is_closed


# ==============================================================================
# 2. Handshake and Bitfield Exchange
# ==============================================================================


@pytest.mark.asyncio
async def test_successful_two_way_handshake() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):
        await asyncio.gather(
            conn_a.perform_handshake(),
            conn_b.perform_handshake(),
        )

        assert conn_a.state == ConnectionState.STEADY_STATE
        assert conn_b.state == ConnectionState.STEADY_STATE
        assert conn_a.is_connected
        assert conn_b.is_connected

        assert conn_a.remote_peer_id == "peer-beta"
        assert conn_a.remote_listen_port == 6882
        assert conn_a.remote_bitfield is not None
        assert conn_a.remote_bitfield.to_indices(4) == {2, 3}

        assert conn_b.remote_peer_id == "peer-alpha"
        assert conn_b.remote_listen_port == 6881
        assert conn_b.remote_bitfield is not None
        assert conn_b.remote_bitfield.to_indices(4) == {0, 1}

        # has_chunk checks
        assert conn_a.has_chunk(2)
        assert conn_a.has_chunk(3)
        assert not conn_a.has_chunk(0)

        assert conn_b.has_chunk(0)
        assert conn_b.has_chunk(1)
        assert not conn_b.has_chunk(2)


@pytest.mark.asyncio
async def test_handshake_version_mismatch() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):

        async def rogue_server() -> None:
            reader = get_stream_reader(conn_b)
            writer = get_stream_writer(conn_b)
            msg = await read_message(reader)
            assert isinstance(msg, Handshake)
            raw_payload = (
                b'{"version":99,"peer_id":"rogue-peer","swarm_id":"'
                + SAMPLE_SWARM_ID.encode()
                + b'","listen_port":7000}'
            )
            await write_frame(writer, encode_frame(0x01, raw_payload))

        server_task = asyncio.create_task(rogue_server())

        with pytest.raises(ProtocolError, match="Unsupported protocol version"):
            await conn_a.perform_handshake()

        await server_task
        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_swarm_id_mismatch() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):

        async def rogue_server() -> None:
            reader = get_stream_reader(conn_b)
            writer = get_stream_writer(conn_b)
            msg = await read_message(reader)
            assert isinstance(msg, Handshake)
            bad_hs = Handshake(
                version=1,
                peer_id="other-swarm-peer",
                swarm_id="0000000000000000000000000000000000000000000000000000000000000000",
                listen_port=7000,
            )
            await write_message(writer, bad_hs)

        server_task = asyncio.create_task(rogue_server())

        with pytest.raises(ProtocolError, match="Swarm ID mismatch"):
            await conn_a.perform_handshake()

        await server_task
        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_self_connection_rejected() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):

        async def rogue_server() -> None:
            reader = get_stream_reader(conn_b)
            writer = get_stream_writer(conn_b)
            msg = await read_message(reader)
            assert isinstance(msg, Handshake)
            same_hs = Handshake(
                version=1,
                peer_id="peer-alpha",
                swarm_id=SAMPLE_SWARM_ID,
                listen_port=7000,
            )
            await write_message(writer, same_hs)

        server_task = asyncio.create_task(rogue_server())

        with pytest.raises(ProtocolError, match="Self-connection detected"):
            await conn_a.perform_handshake()

        await server_task
        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_non_handshake_first_message_rejected() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):

        async def rogue_server() -> None:
            writer = get_stream_writer(conn_b)
            await write_message(writer, Bitfield(bitfield=b"\xf0"))

        server_task = asyncio.create_task(rogue_server())

        with pytest.raises(ProtocolError, match="Expected HANDSHAKE message, received Bitfield"):
            await conn_a.perform_handshake()

        await server_task
        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_non_bitfield_second_message_rejected() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):

        async def rogue_server() -> None:
            reader = get_stream_reader(conn_b)
            writer = get_stream_writer(conn_b)
            msg = await read_message(reader)
            assert isinstance(msg, Handshake)
            hs = Handshake(
                version=1,
                peer_id="peer-beta",
                swarm_id=SAMPLE_SWARM_ID,
                listen_port=7000,
            )
            await write_message(writer, hs)
            await write_message(writer, Request(chunk_index=0))

        server_task = asyncio.create_task(rogue_server())

        with pytest.raises(ProtocolError, match="Expected BITFIELD message, received Request"):
            await conn_a.perform_handshake()

        await server_task
        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_bad_bitfield_spare_bits_rejected() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):

        async def rogue_server() -> None:
            reader = get_stream_reader(conn_b)
            writer = get_stream_writer(conn_b)
            msg = await read_message(reader)
            assert isinstance(msg, Handshake)
            hs = Handshake(
                version=1,
                peer_id="peer-beta",
                swarm_id=SAMPLE_SWARM_ID,
                listen_port=7000,
            )
            await write_message(writer, hs)
            # Spare bits in lower nibble: 0b11110001
            await write_message(writer, Bitfield(bitfield=b"\xf1"))

        server_task = asyncio.create_task(rogue_server())

        with pytest.raises(ProtocolError, match="non-zero spare bits"):
            await conn_a.perform_handshake()

        await server_task
        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_timeout() -> None:
    async with connected_peer_pair(handshake_timeout=0.1) as (conn_a, conn_b):
        with pytest.raises(ProtocolError, match="Handshake exchange timed out"):
            await conn_a.perform_handshake()

        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_handshake_clean_eof_raises_connection_closed() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):
        await conn_b.close()

        with pytest.raises(ConnectionClosed):
            await conn_a.perform_handshake()

        assert conn_a.state == ConnectionState.CLOSED


# ==============================================================================
# 3. Steady-State Request / Piece / Have Protocol Flow
# ==============================================================================


@pytest.mark.asyncio
async def test_steady_state_request_and_piece_flow() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        await conn_a.send_request(2)
        assert 2 in conn_a.pending_requests

        msg_b = await conn_b.receive_message()
        assert isinstance(msg_b, Request)
        assert msg_b.chunk_index == 2

        sample_data = b"PAYLOAD-CHUNK-2"
        await conn_b.send_piece(2, sample_data)

        msg_a = await conn_a.receive_message()
        assert isinstance(msg_a, Piece)
        assert msg_a.chunk_index == 2
        assert msg_a.data == sample_data
        assert 2 not in conn_a.pending_requests


@pytest.mark.asyncio
async def test_steady_state_have_broadcast_flow() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        assert not conn_b.has_chunk(3)

        await conn_a.send_have(3)

        msg = await conn_b.receive_message()
        assert isinstance(msg, Have)
        assert msg.chunk_index == 3

        assert conn_b.has_chunk(3)


@pytest.mark.asyncio
async def test_unsolicited_piece_rejected() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        await conn_b.send_piece(1, b"UNSOLICITED-DATA")

        with pytest.raises(ProtocolError, match="Received unsolicited PIECE"):
            await conn_a.receive_message()

        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_duplicate_bitfield_in_steady_state_rejected() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        writer = get_stream_writer(conn_b)
        await write_message(writer, Bitfield.from_indices([0], 4))

        with pytest.raises(ProtocolError, match="Duplicate BITFIELD received in STEADY_STATE"):
            await conn_a.receive_message()

        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_unexpected_handshake_in_steady_state_rejected() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        writer = get_stream_writer(conn_b)
        await write_message(
            writer,
            Handshake(version=1, peer_id="peer-beta", swarm_id=SAMPLE_SWARM_ID, listen_port=6882),
        )

        with pytest.raises(ProtocolError, match="Unexpected HANDSHAKE received in STEADY_STATE"):
            await conn_a.receive_message()

        assert conn_a.state == ConnectionState.CLOSED


# ==============================================================================
# 4. Out-of-Range Index Validations
# ==============================================================================


@pytest.mark.asyncio
async def test_out_of_range_send_request() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        with pytest.raises(ProtocolError, match="REQUEST chunk_index -1 out of range"):
            await conn_a.send_request(-1)

        with pytest.raises(ProtocolError, match="REQUEST chunk_index 4 out of range"):
            await conn_a.send_request(4)


@pytest.mark.asyncio
async def test_out_of_range_send_piece() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        with pytest.raises(ProtocolError, match="PIECE chunk_index 10 out of range"):
            await conn_a.send_piece(10, b"data")


@pytest.mark.asyncio
async def test_out_of_range_send_have() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        with pytest.raises(ProtocolError, match="HAVE chunk_index 99 out of range"):
            await conn_a.send_have(99)


@pytest.mark.asyncio
async def test_received_out_of_range_request_closes_connection() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        writer = get_stream_writer(conn_b)
        await write_message(writer, Request(chunk_index=10))

        with pytest.raises(ProtocolError, match="REQUEST chunk_index 10 out of range"):
            await conn_a.receive_message()

        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_received_out_of_range_have_closes_connection() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        writer = get_stream_writer(conn_b)
        await write_message(writer, Have(chunk_index=20))

        with pytest.raises(ProtocolError, match="HAVE chunk_index 20 out of range"):
            await conn_a.receive_message()

        assert conn_a.state == ConnectionState.CLOSED


# ==============================================================================
# 5. Concurrency, In-Flight Limits, and Cancellation
# ==============================================================================


@pytest.mark.asyncio
async def test_duplicate_pending_request_rejected() -> None:
    async with connected_peer_pair(chunk_count=4) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        await conn_a.send_request(0)
        with pytest.raises(ProtocolError, match="already has an outstanding request"):
            await conn_a.send_request(0)


@pytest.mark.asyncio
async def test_max_inflight_limit_enforced() -> None:
    async with connected_peer_pair(chunk_count=10, max_inflight=2) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        await conn_a.send_request(0)
        await conn_a.send_request(1)
        assert len(conn_a.pending_requests) == 2

        with pytest.raises(ProtocolError, match="max in-flight requests"):
            await conn_a.send_request(2)

        assert conn_a.cancel_pending_request(0)
        assert not conn_a.cancel_pending_request(0)
        await conn_a.send_request(2)
        assert conn_a.pending_requests == {1, 2}


@pytest.mark.asyncio
async def test_idle_timeout_in_receive_message() -> None:
    async with connected_peer_pair(idle_timeout=0.1) as (conn_a, conn_b):
        await asyncio.gather(conn_a.perform_handshake(), conn_b.perform_handshake())

        with pytest.raises(ProtocolError, match="Frame header read timeout after 0.1s"):
            await conn_a.receive_message()

        assert conn_a.state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_connect_to_unreachable_port_raises_connection_error() -> None:
    bf = Bitfield.from_indices([], 4)
    with pytest.raises(ConnectionError):
        await PeerConnection.connect(
            "127.0.0.1",
            1,
            swarm_id=SAMPLE_SWARM_ID,
            my_peer_id="peer-1",
            my_listen_port=6881,
            chunk_count=4,
            local_bitfield=bf,
            connect_timeout=0.2,
        )


@pytest.mark.asyncio
async def test_async_context_manager() -> None:
    async with connected_peer_pair() as (conn_a, conn_b):
        async with conn_a:
            assert conn_a.state == ConnectionState.AWAIT_HANDSHAKE
        assert conn_a.is_closed
