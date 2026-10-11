"""Wire framing codec, serialization, and stream I/O for the P2P protocol."""

from __future__ import annotations

import asyncio
import struct
from typing import Final

from p2p.config import (
    IDLE_TIMEOUT_SEC,
    MAX_CHUNK_SIZE,
    MAX_FRAME_SIZE,
    STALL_TIMEOUT_SEC,
)
from p2p.protocol.messages import (
    Bitfield,
    ConnectionClosed,
    Handshake,
    Have,
    Message,
    MessageType,
    Piece,
    ProtocolError,
    Request,
)

LENGTH_STRUCT: Final[struct.Struct] = struct.Struct("!I")
UINT32_STRUCT: Final[struct.Struct] = struct.Struct("!I")


def encode_frame(msg_type: int, payload: bytes) -> bytes:
    """Encode a wire frame from a message type and payload.

    Frame format:
    - 4 bytes uint32 big-endian: body length (1 + len(payload))
    - 1 byte uint8: message type code
    - N bytes: payload

    Raises:
        ProtocolError: If msg_type is out of range, payload is not bytes,
            or frame exceeds MAX_FRAME_SIZE.
    """
    if not isinstance(msg_type, int) or isinstance(msg_type, bool) or not (0 <= msg_type <= 255):
        raise ProtocolError(f"Invalid message type code: {msg_type}")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise ProtocolError(f"Payload must be bytes, got {type(payload).__name__}")

    raw_payload = bytes(payload)
    body_length = 1 + len(raw_payload)
    if body_length > MAX_FRAME_SIZE:
        raise ProtocolError(
            f"Frame body length {body_length} exceeds maximum allowed {MAX_FRAME_SIZE}"
        )

    return LENGTH_STRUCT.pack(body_length) + bytes([msg_type]) + raw_payload


def decode_body(body: bytes) -> Message:
    """Decode a message body (type byte + payload) into a typed Message.

    Raises:
        ProtocolError: If the message body is malformed or violates size bounds.
    """
    if not isinstance(body, (bytes, bytearray, memoryview)):
        raise ProtocolError(f"Frame body must be bytes, got {type(body).__name__}")

    raw_body = bytes(body)
    if len(raw_body) < 1:
        raise ProtocolError("Frame body is empty (must contain at least 1 type byte)")

    msg_type_code = raw_body[0]
    payload = raw_body[1:]

    try:
        msg_type = MessageType(msg_type_code)
    except ValueError as exc:
        raise ProtocolError(f"Unknown message type code: 0x{msg_type_code:02x}") from exc

    if msg_type == MessageType.HANDSHAKE:
        return Handshake.from_json_bytes(payload)

    if msg_type == MessageType.BITFIELD:
        if len(payload) == 0:
            raise ProtocolError("BITFIELD payload cannot be empty")
        bf = Bitfield(bitfield=payload)
        bf.validate()
        return bf

    if msg_type == MessageType.REQUEST:
        if len(payload) != UINT32_STRUCT.size:
            raise ProtocolError(
                f"REQUEST payload must be exactly {UINT32_STRUCT.size} bytes, got {len(payload)}"
            )
        (chunk_index,) = UINT32_STRUCT.unpack(payload)
        req = Request(chunk_index=chunk_index)
        req.validate()
        return req

    if msg_type == MessageType.PIECE:
        if len(payload) <= UINT32_STRUCT.size:
            raise ProtocolError(
                f"PIECE payload must contain chunk index and non-empty data "
                f"(> {UINT32_STRUCT.size} bytes), got {len(payload)}"
            )
        (chunk_index,) = UINT32_STRUCT.unpack(payload[: UINT32_STRUCT.size])
        piece_data = payload[UINT32_STRUCT.size :]
        if len(piece_data) > MAX_CHUNK_SIZE:
            raise ProtocolError(
                f"PIECE data length {len(piece_data)} exceeds maximum {MAX_CHUNK_SIZE}"
            )
        piece = Piece(chunk_index=chunk_index, data=piece_data)
        piece.validate()
        return piece

    if msg_type == MessageType.HAVE:
        if len(payload) != UINT32_STRUCT.size:
            raise ProtocolError(
                f"HAVE payload must be exactly {UINT32_STRUCT.size} bytes, got {len(payload)}"
            )
        (chunk_index,) = UINT32_STRUCT.unpack(payload)
        have = Have(chunk_index=chunk_index)
        have.validate()
        return have

    raise ProtocolError(f"Unhandled message type: {msg_type}")


def decode_frame(frame: bytes) -> Message:
    """Decode an entire wire frame (including 4-byte length prefix).

    Raises:
        ProtocolError: If the length prefix does not match the frame length or frame is malformed.
    """
    if not isinstance(frame, (bytes, bytearray, memoryview)):
        raise ProtocolError(f"Frame must be bytes, got {type(frame).__name__}")

    raw_frame = bytes(frame)
    if len(raw_frame) < LENGTH_STRUCT.size + 1:
        raise ProtocolError(
            f"Frame is too short: {len(raw_frame)} bytes (minimum {LENGTH_STRUCT.size + 1})"
        )

    (expected_body_len,) = LENGTH_STRUCT.unpack(raw_frame[: LENGTH_STRUCT.size])
    if expected_body_len < 1 or expected_body_len > MAX_FRAME_SIZE:
        raise ProtocolError(
            f"Invalid frame body length: {expected_body_len} bytes (allowed: 1..{MAX_FRAME_SIZE})"
        )

    actual_body_len = len(raw_frame) - LENGTH_STRUCT.size
    if expected_body_len != actual_body_len:
        raise ProtocolError(
            f"Frame length prefix mismatch: expected {expected_body_len} body bytes, "
            f"got {actual_body_len}"
        )
    return decode_body(raw_frame[LENGTH_STRUCT.size :])


def encode_message(msg: Message) -> bytes:
    """Serialize a high-level Message into a complete wire frame."""
    if isinstance(msg, Handshake):
        msg.validate()
        return encode_frame(MessageType.HANDSHAKE, msg.to_json_bytes())

    if isinstance(msg, Bitfield):
        msg.validate()
        return encode_frame(MessageType.BITFIELD, msg.bitfield)

    if isinstance(msg, Request):
        msg.validate()
        return encode_frame(MessageType.REQUEST, UINT32_STRUCT.pack(msg.chunk_index))

    if isinstance(msg, Piece):
        msg.validate()
        return encode_frame(MessageType.PIECE, UINT32_STRUCT.pack(msg.chunk_index) + msg.data)

    if isinstance(msg, Have):
        msg.validate()
        return encode_frame(MessageType.HAVE, UINT32_STRUCT.pack(msg.chunk_index))

    raise ProtocolError(f"Cannot encode unsupported message type: {type(msg).__name__}")


async def read_frame(
    reader: asyncio.StreamReader,
    *,
    max_body: int = MAX_FRAME_SIZE,
    idle_timeout: float = IDLE_TIMEOUT_SEC,
    stall_timeout: float = STALL_TIMEOUT_SEC,
) -> bytes:
    """Read a single length-prefixed frame body from an async stream.

    Validates frame length bounds *before* allocating or reading body bytes.

    Args:
        reader: The asyncio StreamReader to read from.
        max_body: Maximum permitted body length in bytes.
        idle_timeout: Timeout in seconds for waiting on the initial 4-byte header.
        stall_timeout: Timeout in seconds for completing body transfer.

    Returns:
        The frame body bytes (message type + payload).

    Raises:
        ConnectionClosed: If EOF is reached cleanly on a frame boundary or connection reset.
        ProtocolError: On truncated reads, length boundary violations, or timeouts.
    """
    try:
        async with asyncio.timeout(idle_timeout):
            try:
                header = await reader.readexactly(LENGTH_STRUCT.size)
            except asyncio.IncompleteReadError as exc:
                if not exc.partial:
                    raise ConnectionClosed("Peer closed connection cleanly") from exc
                raise ProtocolError(
                    f"Truncated frame length prefix: received {len(exc.partial)} bytes"
                ) from exc
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                raise ConnectionClosed("Connection closed by peer") from exc
    except TimeoutError as exc:
        raise ProtocolError(f"Frame header read timeout after {idle_timeout}s") from exc

    (length,) = LENGTH_STRUCT.unpack(header)

    # Check bounds BEFORE reading the body to protect against memory exhaustion attacks
    if length < 1 or length > max_body:
        raise ProtocolError(
            f"Invalid frame body length: {length} bytes (allowed range: 1..{max_body})"
        )

    try:
        async with asyncio.timeout(stall_timeout):
            try:
                body = await reader.readexactly(length)
            except asyncio.IncompleteReadError as exc:
                raise ProtocolError(
                    f"Truncated frame body: expected {length} bytes, received {len(exc.partial)}"
                ) from exc
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                raise ConnectionClosed("Connection reset by peer mid-frame") from exc
    except TimeoutError as exc:
        raise ProtocolError(f"Frame body read stall timeout after {stall_timeout}s") from exc

    return body


async def write_frame(
    writer: asyncio.StreamWriter,
    frame: bytes,
    *,
    lock: asyncio.Lock | None = None,
) -> None:
    """Write an encoded frame to an async stream and drain backpressure.

    Optionally serializes writes using a provided asyncio.Lock to prevent
    concurrent tasks from interleaving frame bytes.

    Raises:
        ConnectionClosed: If the writer is closed or peer reset the connection.
        ProtocolError: If frame format is invalid.
    """
    if len(frame) < LENGTH_STRUCT.size + 1:
        raise ProtocolError(f"Cannot write invalid frame of length {len(frame)}")

    if writer.is_closing():
        raise ConnectionClosed("Writer is closed")

    async def _do_write() -> None:
        try:
            writer.write(frame)
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as exc:
            raise ConnectionClosed("Connection closed during write") from exc

    if lock is not None:
        async with lock:
            await _do_write()
    else:
        await _do_write()


async def read_message(
    reader: asyncio.StreamReader,
    *,
    max_body: int = MAX_FRAME_SIZE,
    idle_timeout: float = IDLE_TIMEOUT_SEC,
    stall_timeout: float = STALL_TIMEOUT_SEC,
) -> Message:
    """Read and decode a complete message from an async stream."""
    body = await read_frame(
        reader, max_body=max_body, idle_timeout=idle_timeout, stall_timeout=stall_timeout
    )
    return decode_body(body)


async def write_message(
    writer: asyncio.StreamWriter,
    msg: Message,
    *,
    lock: asyncio.Lock | None = None,
) -> None:
    """Encode and write a Message to an async stream."""
    frame = encode_message(msg)
    await write_frame(writer, frame, lock=lock)
