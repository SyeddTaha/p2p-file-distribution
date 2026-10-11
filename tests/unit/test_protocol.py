"""Comprehensive unit and stream tests for wire framing codec and protocol messages."""

import asyncio
import json
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from p2p.config import (
    MAX_CHUNK_SIZE,
    MAX_FRAME_SIZE,
    MAX_HANDSHAKE_BODY,
    PROTOCOL_VERSION,
)
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Handshake,
    Have,
    Message,
    MessageType,
    Piece,
    ProtocolError,
    Request,
    decode_body,
    decode_frame,
    encode_frame,
    encode_message,
    read_frame,
    read_message,
    write_frame,
    write_message,
)

SAMPLE_SWARM_ID = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890"


# ==============================================================================
# 1. Round-Trip Message Encoding and Decoding Tests
# ==============================================================================


def test_handshake_roundtrip() -> None:
    hs = Handshake(
        version=PROTOCOL_VERSION,
        peer_id="peer-test-123",
        swarm_id=SAMPLE_SWARM_ID,
        listen_port=6881,
    )
    frame = encode_message(hs)
    decoded = decode_frame(frame)
    assert isinstance(decoded, Handshake)
    assert decoded.version == hs.version
    assert decoded.peer_id == hs.peer_id
    assert decoded.swarm_id == hs.swarm_id
    assert decoded.listen_port == hs.listen_port


def test_bitfield_roundtrip() -> None:
    bf = Bitfield(bitfield=b"\xaa\x55\xff\x00")
    frame = encode_message(bf)
    decoded = decode_frame(frame)
    assert isinstance(decoded, Bitfield)
    assert decoded.bitfield == bf.bitfield


def test_request_roundtrip() -> None:
    req = Request(chunk_index=42)
    frame = encode_message(req)
    decoded = decode_frame(frame)
    assert isinstance(decoded, Request)
    assert decoded.chunk_index == 42


def test_piece_roundtrip() -> None:
    chunk_data = b"Arbitrary chunk binary payload \x00\xff\xfe\x01" * 10
    piece = Piece(chunk_index=7, data=chunk_data)
    frame = encode_message(piece)
    decoded = decode_frame(frame)
    assert isinstance(decoded, Piece)
    assert decoded.chunk_index == 7
    assert decoded.data == chunk_data


def test_have_roundtrip() -> None:
    have = Have(chunk_index=999)
    frame = encode_message(have)
    decoded = decode_frame(frame)
    assert isinstance(decoded, Have)
    assert decoded.chunk_index == 999


# ==============================================================================
# 2. Handshake Validation and Error Handling Tests
# ==============================================================================


def test_handshake_version_mismatch() -> None:
    hs = Handshake(
        version=99,
        peer_id="peer-1",
        swarm_id=SAMPLE_SWARM_ID,
        listen_port=6881,
    )
    with pytest.raises(ProtocolError, match="Unsupported protocol version"):
        encode_message(hs)


def test_handshake_boolean_version_rejected() -> None:
    # In Python, bool is a subclass of int (True == 1)
    hs = Handshake(
        version=True,
        peer_id="peer-1",
        swarm_id=SAMPLE_SWARM_ID,
        listen_port=6881,
    )
    with pytest.raises(ProtocolError, match="Handshake version must be int"):
        encode_message(hs)


def test_handshake_invalid_peer_id() -> None:
    with pytest.raises(ProtocolError, match="1..64 alphanumeric"):
        Handshake(
            version=1,
            peer_id="",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=6881,
        ).validate()

    with pytest.raises(ProtocolError, match="1..64 alphanumeric"):
        Handshake(
            version=1,
            peer_id="a" * 65,
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=6881,
        ).validate()

    # Reject whitespace and special characters
    with pytest.raises(ProtocolError, match="1..64 alphanumeric"):
        Handshake(
            version=1,
            peer_id="peer with spaces",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=6881,
        ).validate()

    with pytest.raises(ProtocolError, match="1..64 alphanumeric"):
        Handshake(
            version=1,
            peer_id="peer@name!",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=6881,
        ).validate()

    with pytest.raises(ProtocolError, match="must be str"):
        Handshake(
            version=1,
            peer_id=123,  # type: ignore[arg-type]
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=6881,
        ).validate()


def test_handshake_invalid_swarm_id() -> None:
    # Not 64 characters
    with pytest.raises(ProtocolError, match="64 lowercase hex"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id="abc123",
            listen_port=6881,
        ).validate()

    # Uppercase hex rejected
    with pytest.raises(ProtocolError, match="64 lowercase hex"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id=SAMPLE_SWARM_ID.upper(),
            listen_port=6881,
        ).validate()

    # Non-hex characters rejected
    with pytest.raises(ProtocolError, match="64 lowercase hex"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id="g" * 64,
            listen_port=6881,
        ).validate()

    with pytest.raises(ProtocolError, match="must be str"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id=123,  # type: ignore[arg-type]
            listen_port=6881,
        ).validate()


def test_handshake_invalid_port() -> None:
    with pytest.raises(ProtocolError, match="out of range"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=0,
        ).validate()

    with pytest.raises(ProtocolError, match="out of range"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=70000,
        ).validate()

    with pytest.raises(ProtocolError, match="must be int"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port=True,
        ).validate()

    with pytest.raises(ProtocolError, match="must be int"):
        Handshake(
            version=1,
            peer_id="peer-1",
            swarm_id=SAMPLE_SWARM_ID,
            listen_port="6881",  # type: ignore[arg-type]
        ).validate()


def test_handshake_malformed_json() -> None:
    with pytest.raises(ProtocolError, match="not valid JSON"):
        Handshake.from_json_bytes(b"{not: valid json}")


def test_handshake_non_utf8() -> None:
    with pytest.raises(ProtocolError, match="not valid UTF-8"):
        Handshake.from_json_bytes(b"\xff\xfe\x00")


def test_handshake_not_an_object() -> None:
    with pytest.raises(ProtocolError, match="must be an object"):
        Handshake.from_json_bytes(b"[1, 2, 3]")

    with pytest.raises(ProtocolError, match="must be an object"):
        Handshake.from_json_bytes(b"123")


def test_handshake_missing_fields() -> None:
    partial = json.dumps({"version": 1, "peer_id": "p"}).encode("utf-8")
    with pytest.raises(ProtocolError, match="missing required fields"):
        Handshake.from_json_bytes(partial)


def test_handshake_exceeds_max_body() -> None:
    oversized = json.dumps(
        {
            "version": 1,
            "peer_id": "p",
            "swarm_id": SAMPLE_SWARM_ID,
            "listen_port": 6881,
            "extra": "x" * (MAX_HANDSHAKE_BODY + 10),
        }
    ).encode("utf-8")
    with pytest.raises(ProtocolError, match="exceeds limit"):
        Handshake.from_json_bytes(oversized)


# ==============================================================================
# 3. Bitfield Logic and Spare Bit Validation Tests
# ==============================================================================


def test_bitfield_indices_and_queries() -> None:
    # 10 chunks: byte 0 has 8 bits, byte 1 has 2 bits + 6 spare bits
    # Chunks 0, 7, 8 set:
    # byte 0: bit 7 (0x80) and bit 0 (0x01) -> 0x81
    # byte 1: bit 7 (0x80) -> 0x80
    bf = Bitfield(bitfield=b"\x81\x80")
    bf.validate_for_swarm(10)

    assert bf.has_chunk(0) is True
    assert bf.has_chunk(1) is False
    assert bf.has_chunk(7) is True
    assert bf.has_chunk(8) is True
    assert bf.has_chunk(9) is False
    assert bf.has_chunk(10) is False  # out of bounds query is False

    assert bf.to_indices(10) == {0, 7, 8}


def test_bitfield_has_chunk_invalid_types() -> None:
    bf = Bitfield(bitfield=b"\x80")
    with pytest.raises(ProtocolError, match="chunk_index must be int"):
        bf.has_chunk(True)

    with pytest.raises(ProtocolError, match="Negative chunk index"):
        bf.has_chunk(-1)


def test_bitfield_with_chunk() -> None:
    bf = Bitfield(bitfield=b"\x00\x00")
    bf2 = bf.with_chunk(0)
    assert bf2.has_chunk(0) is True
    assert bf.has_chunk(0) is False  # original remains immutable

    bf3 = bf2.with_chunk(9)
    assert bf3.has_chunk(0) is True
    assert bf3.has_chunk(9) is True

    # Exceeding capacity raises ProtocolError
    with pytest.raises(ProtocolError, match="exceeds bitfield capacity"):
        bf3.with_chunk(16)

    with pytest.raises(ProtocolError, match="chunk_index must be int"):
        bf3.with_chunk(True)

    with pytest.raises(ProtocolError, match="Negative chunk index"):
        bf3.with_chunk(-1)


def test_bitfield_empty_rejected() -> None:
    bf = Bitfield(bitfield=b"")
    with pytest.raises(ProtocolError, match="cannot be empty"):
        bf.validate()

    bf_bad_type = Bitfield(bitfield="not bytes")  # type: ignore[arg-type]
    with pytest.raises(ProtocolError, match="must be bytes"):
        bf_bad_type.validate()


def test_bitfield_from_indices_roundtrip() -> None:
    indices = {1, 3, 5, 9, 11}
    bf = Bitfield.from_indices(indices, chunk_count=12)
    assert bf.to_indices(12) == indices


def test_bitfield_from_indices_invalid_inputs() -> None:
    with pytest.raises(ProtocolError, match="chunk_count must be int"):
        Bitfield.from_indices([0], True)

    with pytest.raises(ProtocolError, match="Chunk count must be positive"):
        Bitfield.from_indices([0], 0)

    with pytest.raises(ProtocolError, match="Chunk index must be int"):
        Bitfield.from_indices([True], 5)

    with pytest.raises(ProtocolError, match="out of range"):
        Bitfield.from_indices([5], 5)

    with pytest.raises(ProtocolError, match="out of range"):
        Bitfield.from_indices([-1], 5)


def test_bitfield_exact_multiples_of_eight() -> None:
    # 8 chunks -> 1 byte, 0 spare bits
    bf8 = Bitfield(bitfield=b"\xff")
    bf8.validate_for_swarm(8)
    assert bf8.to_indices(8) == set(range(8))

    # 16 chunks -> 2 bytes, 0 spare bits
    bf16 = Bitfield(bitfield=b"\xff\xff")
    bf16.validate_for_swarm(16)
    assert bf16.to_indices(16) == set(range(16))


def test_bitfield_rejects_nonzero_spare_bits() -> None:
    # 10 chunks -> 2 bytes. Last byte has bits for chunk 8 and 9.
    # Bits 5..0 are spare. If bit 0 is set (0x81), it must fail validation!
    bf = Bitfield(bitfield=b"\x00\x81")
    with pytest.raises(ProtocolError, match="non-zero spare bits"):
        bf.validate_for_swarm(10)


def test_bitfield_rejects_wrong_length_for_swarm() -> None:
    # 10 chunks expects 2 bytes
    bf_too_short = Bitfield(bitfield=b"\x00")
    with pytest.raises(ProtocolError, match="does not match expected"):
        bf_too_short.validate_for_swarm(10)

    bf_too_long = Bitfield(bitfield=b"\x00\x00\x00")
    with pytest.raises(ProtocolError, match="does not match expected"):
        bf_too_long.validate_for_swarm(10)

    with pytest.raises(ProtocolError, match="chunk_count must be int"):
        bf_too_short.validate_for_swarm(True)

    with pytest.raises(ProtocolError, match="Chunk count must be positive"):
        bf_too_short.validate_for_swarm(0)


def test_bitfield_to_indices_without_chunk_count() -> None:
    bf = Bitfield(bitfield=b"\x80")
    assert bf.to_indices() == {0}


# ==============================================================================
# 4. Request, Piece, and Have Boundary and Type Validation Tests
# ==============================================================================


def test_request_uint32_bounds() -> None:
    Request(chunk_index=0).validate()
    Request(chunk_index=0xFFFFFFFF).validate()

    with pytest.raises(ProtocolError, match="uint32 range"):
        Request(chunk_index=-1).validate()

    with pytest.raises(ProtocolError, match="uint32 range"):
        Request(chunk_index=0x100000000).validate()

    with pytest.raises(ProtocolError, match="must be int"):
        Request(chunk_index="0").validate()  # type: ignore[arg-type]

    with pytest.raises(ProtocolError, match="must be int"):
        Request(chunk_index=True).validate()


def test_piece_validation() -> None:
    Piece(chunk_index=0, data=b"data").validate()

    with pytest.raises(ProtocolError, match="cannot be empty"):
        Piece(chunk_index=0, data=b"").validate()

    with pytest.raises(ProtocolError, match="exceeds maximum"):
        Piece(chunk_index=0, data=b"x" * (MAX_CHUNK_SIZE + 1)).validate()

    with pytest.raises(ProtocolError, match="must be int"):
        Piece(chunk_index=True, data=b"data").validate()

    with pytest.raises(ProtocolError, match="uint32 range"):
        Piece(chunk_index=-1, data=b"data").validate()

    with pytest.raises(ProtocolError, match="must be bytes"):
        Piece(chunk_index=0, data="not bytes").validate()  # type: ignore[arg-type]


def test_have_uint32_bounds() -> None:
    Have(chunk_index=0).validate()
    Have(chunk_index=0xFFFFFFFF).validate()

    with pytest.raises(ProtocolError, match="uint32 range"):
        Have(chunk_index=-1).validate()

    with pytest.raises(ProtocolError, match="uint32 range"):
        Have(chunk_index=0x100000000).validate()

    with pytest.raises(ProtocolError, match="must be int"):
        Have(chunk_index=True).validate()


# ==============================================================================
# 5. Codec Malformed Input and Wire Bounds Tests
# ==============================================================================


def test_encode_frame_validations() -> None:
    with pytest.raises(ProtocolError, match="Invalid message type code"):
        encode_frame(256, b"")

    with pytest.raises(ProtocolError, match="Invalid message type code"):
        encode_frame(-1, b"")

    with pytest.raises(ProtocolError, match="Payload must be bytes"):
        encode_frame(1, "not bytes")  # type: ignore[arg-type]

    with pytest.raises(ProtocolError, match="exceeds maximum allowed"):
        encode_frame(1, b"x" * (MAX_FRAME_SIZE + 10))


def test_decode_body_empty() -> None:
    with pytest.raises(ProtocolError, match="Frame body is empty"):
        decode_body(b"")

    with pytest.raises(ProtocolError, match="Frame body must be bytes"):
        decode_body("not bytes")  # type: ignore[arg-type]


def test_decode_body_unknown_type() -> None:
    with pytest.raises(ProtocolError, match="Unknown message type"):
        decode_body(b"\x99payload")


def test_decode_body_empty_bitfield() -> None:
    with pytest.raises(ProtocolError, match="BITFIELD payload cannot be empty"):
        decode_body(bytes([MessageType.BITFIELD]))


def test_decode_body_wrong_payload_size() -> None:
    # REQUEST requires 4 payload bytes
    with pytest.raises(ProtocolError, match="REQUEST payload must be exactly 4 bytes"):
        decode_body(bytes([MessageType.REQUEST]) + b"\x00\x01")

    # HAVE requires 4 payload bytes
    with pytest.raises(ProtocolError, match="HAVE payload must be exactly 4 bytes"):
        decode_body(bytes([MessageType.HAVE]) + b"\x00\x01\x02")

    # PIECE requires > 4 bytes for chunk_index + chunk_data
    with pytest.raises(ProtocolError, match="PIECE payload must contain chunk index"):
        decode_body(bytes([MessageType.PIECE]) + b"\x00\x00\x00\x01")

    # PIECE with chunk data exceeding MAX_CHUNK_SIZE
    with pytest.raises(ProtocolError, match="exceeds maximum"):
        decode_body(bytes([MessageType.PIECE]) + b"\x00\x00\x00\x01" + b"x" * (MAX_CHUNK_SIZE + 1))


def test_decode_frame_length_mismatch() -> None:
    # Prefix says body is 10 bytes, but only 3 bytes provided
    frame = struct.pack("!I", 10) + bytes([MessageType.HAVE, 0x00, 0x01])
    with pytest.raises(ProtocolError, match="Frame length prefix mismatch"):
        decode_frame(frame)


def test_decode_frame_too_short() -> None:
    with pytest.raises(ProtocolError, match="Frame is too short"):
        decode_frame(b"\x00\x00\x00")

    with pytest.raises(ProtocolError, match="Frame must be bytes"):
        decode_frame("not bytes")  # type: ignore[arg-type]


def test_decode_frame_oversized() -> None:
    frame = struct.pack("!I", MAX_FRAME_SIZE + 1) + b"\x01" * 10
    with pytest.raises(ProtocolError, match="Invalid frame body length"):
        decode_frame(frame)


def test_encode_message_unsupported_type() -> None:
    with pytest.raises(ProtocolError, match="Cannot encode unsupported message type"):
        encode_message("unsupported")  # type: ignore[arg-type]


# ==============================================================================
# 6. Async Stream I/O Tests (Framing, Split/Merged Reads, Timeouts, Clean EOF)
# ==============================================================================


@pytest.mark.asyncio
async def test_stream_clean_eof() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()

    with pytest.raises(ConnectionClosed, match="cleanly"):
        await read_frame(reader, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_stream_truncated_length_prefix() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x00\x00")  # Only 2 of 4 bytes
    reader.feed_eof()

    with pytest.raises(ProtocolError, match="Truncated frame length prefix"):
        await read_frame(reader, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_stream_oversized_frame_bounds_check_before_read() -> None:
    reader = asyncio.StreamReader()
    # Claim body length is MAX_FRAME_SIZE + 1
    reader.feed_data(struct.pack("!I", MAX_FRAME_SIZE + 1))

    with pytest.raises(ProtocolError, match="Invalid frame body length"):
        await read_frame(reader, max_body=MAX_FRAME_SIZE, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_stream_zero_length_frame() -> None:
    reader = asyncio.StreamReader()
    # Length prefix of 0 is invalid because minimum body is 1 byte (type byte)
    reader.feed_data(struct.pack("!I", 0))

    with pytest.raises(ProtocolError, match="Invalid frame body length"):
        await read_frame(reader, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_stream_truncated_body() -> None:
    reader = asyncio.StreamReader()
    # Body length 5, but feed only 2 body bytes before EOF
    reader.feed_data(struct.pack("!I", 5) + b"\x01\x02")
    reader.feed_eof()

    with pytest.raises(ProtocolError, match="Truncated frame body"):
        await read_frame(reader, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_stream_header_timeout() -> None:
    reader = asyncio.StreamReader()
    # Nothing fed into reader
    with pytest.raises(ProtocolError, match="timeout"):
        await read_frame(reader, idle_timeout=0.05)


@pytest.mark.asyncio
async def test_stream_stall_timeout() -> None:
    reader = asyncio.StreamReader()
    # Feed 4-byte length prefix indicating body of 100 bytes, but no body data
    reader.feed_data(struct.pack("!I", 100))
    with pytest.raises(ProtocolError, match="stall timeout"):
        await read_frame(reader, idle_timeout=1.0, stall_timeout=0.05)


@pytest.mark.asyncio
async def test_stream_split_reads_one_byte_at_a_time() -> None:
    """Ensure framing handles TCP segment fragmentation down to single bytes."""
    req = Request(chunk_index=123)
    frame = encode_message(req)

    reader = asyncio.StreamReader()

    async def feeder() -> None:
        for b in frame:
            reader.feed_data(bytes([b]))
            await asyncio.sleep(0.001)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(feeder())
        msg = await read_message(reader, idle_timeout=1.0, stall_timeout=1.0)

    assert isinstance(msg, Request)
    assert msg.chunk_index == 123


@pytest.mark.asyncio
async def test_stream_merged_reads_multiple_frames() -> None:
    """Ensure framing parses multiple coalesced messages received in a single TCP read."""
    m1 = Have(chunk_index=1)
    m2 = Have(chunk_index=2)
    m3 = Request(chunk_index=99)

    f1 = encode_message(m1)
    f2 = encode_message(m2)
    f3 = encode_message(m3)

    reader = asyncio.StreamReader()
    reader.feed_data(f1 + f2 + f3)
    reader.feed_eof()

    r1 = await read_message(reader, idle_timeout=1.0)
    r2 = await read_message(reader, idle_timeout=1.0)
    r3 = await read_message(reader, idle_timeout=1.0)

    assert r1 == m1
    assert r2 == m2
    assert r3 == m3

    with pytest.raises(ConnectionClosed):
        await read_message(reader, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_write_frame_validations_and_failures() -> None:
    # Invalid short frame
    writer_mock = MagicMock()
    with pytest.raises(ProtocolError, match="Cannot write invalid frame"):
        await write_frame(writer_mock, b"\x00\x00")

    # Closed writer
    writer_mock.is_closing.return_value = True
    valid_frame = encode_message(Have(chunk_index=1))
    with pytest.raises(ConnectionClosed, match="Writer is closed"):
        await write_frame(writer_mock, valid_frame)

    # Connection reset during write
    writer_mock.is_closing.return_value = False
    writer_mock.drain = AsyncMock(side_effect=ConnectionResetError("Socket reset"))
    with pytest.raises(ConnectionClosed, match="Connection closed during write"):
        await write_frame(writer_mock, valid_frame)


@pytest.mark.asyncio
async def test_read_frame_connection_reset_during_header_or_body() -> None:
    # Mock stream raising ConnectionResetError on header
    reader_mock = AsyncMock(spec=asyncio.StreamReader)
    reader_mock.readexactly.side_effect = ConnectionResetError("Reset during header")
    with pytest.raises(ConnectionClosed, match="Connection closed by peer"):
        await read_frame(reader_mock, idle_timeout=1.0)

    # Mock stream succeeding on header but raising ConnectionResetError on body
    reader_mock = AsyncMock(spec=asyncio.StreamReader)
    reader_mock.readexactly.side_effect = [
        struct.pack("!I", 10),
        ConnectionResetError("Reset during body"),
    ]
    with pytest.raises(ConnectionClosed, match="Connection reset by peer mid-frame"):
        await read_frame(reader_mock, idle_timeout=1.0)


@pytest.mark.asyncio
async def test_loopback_socket_bidirectional_exchange() -> None:
    """Test full message exchange between client and server over real loopback TCP sockets."""
    received_on_server: list[Message] = []
    server_ready = asyncio.Event()

    async def server_handler(
        s_reader: asyncio.StreamReader, s_writer: asyncio.StreamWriter
    ) -> None:
        try:
            # Server reads Handshake, responds with Handshake and Bitfield
            hs = await read_message(s_reader, idle_timeout=2.0)
            received_on_server.append(hs)

            s_hs = Handshake(
                version=1,
                peer_id="server-peer",
                swarm_id=SAMPLE_SWARM_ID,
                listen_port=port,
            )
            write_lock = asyncio.Lock()
            await write_message(s_writer, s_hs, lock=write_lock)

            s_bf = Bitfield.from_indices({0, 2}, chunk_count=4)
            await write_message(s_writer, s_bf, lock=write_lock)

            # Read client's Request and send Piece
            req = await read_message(s_reader, idle_timeout=2.0)
            received_on_server.append(req)

            piece = Piece(chunk_index=0, data=b"CHUNK-0-DATA")
            await write_message(s_writer, piece, lock=write_lock)

        finally:
            s_writer.close()
            await s_writer.wait_closed()

    server = await asyncio.start_server(server_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server_ready.set()

    try:
        c_reader, c_writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            # Client sends Handshake
            c_hs = Handshake(
                version=1,
                peer_id="client-peer",
                swarm_id=SAMPLE_SWARM_ID,
                listen_port=6882,
            )
            await write_message(c_writer, c_hs)

            # Client receives Server Handshake & Bitfield
            srv_hs = await read_message(c_reader, idle_timeout=2.0)
            assert isinstance(srv_hs, Handshake)
            assert srv_hs.peer_id == "server-peer"

            srv_bf = await read_message(c_reader, idle_timeout=2.0)
            assert isinstance(srv_bf, Bitfield)
            assert srv_bf.to_indices(4) == {0, 2}

            # Client sends Request(0)
            await write_message(c_writer, Request(chunk_index=0))

            # Client receives Piece(0)
            srv_piece = await read_message(c_reader, idle_timeout=2.0)
            assert isinstance(srv_piece, Piece)
            assert srv_piece.chunk_index == 0
            assert srv_piece.data == b"CHUNK-0-DATA"

        finally:
            c_writer.close()
            await c_writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert len(received_on_server) == 2
    assert isinstance(received_on_server[0], Handshake)
    assert isinstance(received_on_server[1], Request)
