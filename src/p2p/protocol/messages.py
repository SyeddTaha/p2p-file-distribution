"""Protocol message definitions, type codes, and exception types."""

from __future__ import annotations

import dataclasses
import enum
import json
import math
import re
from collections.abc import Iterable
from typing import Final, Self

from p2p.config import (
    MAX_CHUNK_SIZE,
    MAX_HANDSHAKE_BODY,
    PROTOCOL_VERSION,
)

HEX_64_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
PEER_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")


class ProtocolError(Exception):
    """Raised when a remote peer violates the wire protocol."""


class ConnectionClosed(Exception):
    """Raised when a connection is closed cleanly on a frame boundary."""


class MessageType(enum.IntEnum):
    """Application-layer message type codes."""

    HANDSHAKE = 0x01
    BITFIELD = 0x02
    REQUEST = 0x03
    PIECE = 0x04
    HAVE = 0x05


@dataclasses.dataclass(frozen=True, slots=True)
class Handshake:
    """Handshake payload exchanged upon connection establishment."""

    version: int
    peer_id: str
    swarm_id: str
    listen_port: int

    def validate(self) -> None:
        """Validate handshake fields against protocol requirements.

        Raises:
            ProtocolError: If any field violates protocol constraints.
        """
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise ProtocolError(f"Handshake version must be int, got {type(self.version).__name__}")
        if self.version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"Unsupported protocol version: {self.version} (expected {PROTOCOL_VERSION})"
            )

        if not isinstance(self.peer_id, str):
            raise ProtocolError(f"Handshake peer_id must be str, got {type(self.peer_id).__name__}")
        if not PEER_ID_PATTERN.match(self.peer_id):
            raise ProtocolError(
                f"Handshake peer_id must be 1..64 alphanumeric/hyphen/underscore/dot characters, "
                f"got {self.peer_id!r}"
            )

        if not isinstance(self.swarm_id, str):
            raise ProtocolError(
                f"Handshake swarm_id must be str, got {type(self.swarm_id).__name__}"
            )
        if not HEX_64_PATTERN.match(self.swarm_id):
            raise ProtocolError(
                f"Handshake swarm_id must be 64 lowercase hex chars, got {self.swarm_id!r}"
            )

        if not isinstance(self.listen_port, int) or isinstance(self.listen_port, bool):
            raise ProtocolError(
                f"Handshake listen_port must be int, got {type(self.listen_port).__name__}"
            )
        if self.listen_port < 1 or self.listen_port > 65535:
            raise ProtocolError(f"Handshake listen_port out of range 1..65535: {self.listen_port}")

    def to_json_bytes(self) -> bytes:
        """Serialize handshake to UTF-8 JSON bytes."""
        self.validate()
        payload = json.dumps(
            {
                "version": self.version,
                "peer_id": self.peer_id,
                "swarm_id": self.swarm_id,
                "listen_port": self.listen_port,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_HANDSHAKE_BODY:
            raise ProtocolError(
                f"Handshake payload length {len(payload)} exceeds maximum {MAX_HANDSHAKE_BODY}"
            )
        return payload

    @classmethod
    def from_json_bytes(cls, data: bytes) -> Self:
        """Parse and validate handshake from UTF-8 JSON bytes."""
        if len(data) > MAX_HANDSHAKE_BODY:
            raise ProtocolError(
                f"Handshake payload length {len(data)} exceeds limit {MAX_HANDSHAKE_BODY}"
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Handshake payload is not valid UTF-8") from exc

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProtocolError("Handshake payload is not valid JSON") from exc

        if not isinstance(parsed, dict):
            raise ProtocolError(
                f"Handshake payload JSON must be an object, got {type(parsed).__name__}"
            )

        required_keys = {"version", "peer_id", "swarm_id", "listen_port"}
        if not required_keys.issubset(parsed.keys()):
            missing = required_keys - set(parsed.keys())
            raise ProtocolError(f"Handshake missing required fields: {sorted(missing)}")

        handshake = cls(
            version=parsed["version"],
            peer_id=parsed["peer_id"],
            swarm_id=parsed["swarm_id"],
            listen_port=parsed["listen_port"],
        )
        handshake.validate()
        return handshake


@dataclasses.dataclass(frozen=True, slots=True)
class Bitfield:
    """Bitmask indicating chunk availability."""

    bitfield: bytes

    def validate(self) -> None:
        """Validate basic bitfield invariants."""
        if not isinstance(self.bitfield, bytes):
            raise ProtocolError(f"Bitfield data must be bytes, got {type(self.bitfield).__name__}")
        if len(self.bitfield) == 0:
            raise ProtocolError("Bitfield cannot be empty")

    def has_chunk(self, chunk_index: int) -> bool:
        """Check if chunk at chunk_index is indicated as available."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ProtocolError(f"chunk_index must be int, got {type(chunk_index).__name__}")
        if chunk_index < 0:
            raise ProtocolError(f"Negative chunk index: {chunk_index}")
        byte_index = chunk_index // 8
        if byte_index >= len(self.bitfield):
            return False
        bit_index = 7 - (chunk_index % 8)
        return bool(self.bitfield[byte_index] & (1 << bit_index))

    def with_chunk(self, chunk_index: int) -> Self:
        """Return a new Bitfield with chunk_index marked as present."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ProtocolError(f"chunk_index must be int, got {type(chunk_index).__name__}")
        if chunk_index < 0:
            raise ProtocolError(f"Negative chunk index: {chunk_index}")
        byte_index = chunk_index // 8
        if byte_index >= len(self.bitfield):
            capacity = len(self.bitfield) * 8
            raise ProtocolError(
                f"Chunk index {chunk_index} exceeds bitfield capacity ({capacity} bits)"
            )
        buf = bytearray(self.bitfield)
        bit_index = 7 - (chunk_index % 8)
        buf[byte_index] |= 1 << bit_index
        return type(self)(bitfield=bytes(buf))

    def validate_for_swarm(self, chunk_count: int) -> None:
        """Validate bitfield length and spare bits against expected chunk count.

        Args:
            chunk_count: Total number of chunks in the swarm.

        Raises:
            ProtocolError: If bitfield length does not match or spare bits are non-zero.
        """
        self.validate()
        if not isinstance(chunk_count, int) or isinstance(chunk_count, bool):
            raise ProtocolError(f"chunk_count must be int, got {type(chunk_count).__name__}")
        if chunk_count <= 0:
            raise ProtocolError(f"Chunk count must be positive, got {chunk_count}")

        expected_bytes = math.ceil(chunk_count / 8)
        if len(self.bitfield) != expected_bytes:
            raise ProtocolError(
                f"Bitfield length {len(self.bitfield)} does not match expected {expected_bytes} "
                f"for {chunk_count} chunks"
            )

        spare_bits = (expected_bytes * 8) - chunk_count
        if spare_bits > 0:
            last_byte = self.bitfield[-1]
            spare_mask = (1 << spare_bits) - 1
            if (last_byte & spare_mask) != 0:
                raise ProtocolError(
                    f"Bitfield has non-zero spare bits: 0x{last_byte:02x} "
                    f"has bits set in mask 0x{spare_mask:02x}"
                )

    def to_indices(self, chunk_count: int | None = None) -> set[int]:
        """Return the set of chunk indices marked present."""
        if chunk_count is not None:
            self.validate_for_swarm(chunk_count)
            total = chunk_count
        else:
            self.validate()
            total = len(self.bitfield) * 8

        result: set[int] = set()
        for idx in range(total):
            if self.has_chunk(idx):
                result.add(idx)
        return result

    @classmethod
    def from_indices(cls, indices: Iterable[int], chunk_count: int) -> Self:
        """Construct a Bitfield from an iterable of chunk indices for a known chunk count."""
        if not isinstance(chunk_count, int) or isinstance(chunk_count, bool):
            raise ProtocolError(f"chunk_count must be int, got {type(chunk_count).__name__}")
        if chunk_count <= 0:
            raise ProtocolError(f"Chunk count must be positive, got {chunk_count}")

        expected_bytes = math.ceil(chunk_count / 8)
        buf = bytearray(expected_bytes)
        for idx in indices:
            if not isinstance(idx, int) or isinstance(idx, bool):
                raise ProtocolError(f"Chunk index must be int, got {type(idx).__name__}")
            if idx < 0 or idx >= chunk_count:
                raise ProtocolError(f"Chunk index {idx} out of range for chunk_count {chunk_count}")
            byte_idx = idx // 8
            bit_idx = 7 - (idx % 8)
            buf[byte_idx] |= 1 << bit_idx
        return cls(bitfield=bytes(buf))


@dataclasses.dataclass(frozen=True, slots=True)
class Request:
    """Request for a specific chunk index."""

    chunk_index: int

    def validate(self) -> None:
        """Validate request fields."""
        if not isinstance(self.chunk_index, int) or isinstance(self.chunk_index, bool):
            raise ProtocolError(
                f"REQUEST chunk_index must be int, got {type(self.chunk_index).__name__}"
            )
        if self.chunk_index < 0 or self.chunk_index > 0xFFFFFFFF:
            raise ProtocolError(f"REQUEST chunk_index out of uint32 range: {self.chunk_index}")


@dataclasses.dataclass(frozen=True, slots=True)
class Piece:
    """Delivered chunk data for a specific chunk index."""

    chunk_index: int
    data: bytes

    def validate(self) -> None:
        """Validate piece fields."""
        if not isinstance(self.chunk_index, int) or isinstance(self.chunk_index, bool):
            raise ProtocolError(
                f"PIECE chunk_index must be int, got {type(self.chunk_index).__name__}"
            )
        if self.chunk_index < 0 or self.chunk_index > 0xFFFFFFFF:
            raise ProtocolError(f"PIECE chunk_index out of uint32 range: {self.chunk_index}")
        if not isinstance(self.data, bytes):
            raise ProtocolError(f"PIECE data must be bytes, got {type(self.data).__name__}")
        if len(self.data) == 0:
            raise ProtocolError("PIECE data cannot be empty")
        if len(self.data) > MAX_CHUNK_SIZE:
            raise ProtocolError(
                f"PIECE data length {len(self.data)} exceeds maximum {MAX_CHUNK_SIZE}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class Have:
    """Announcement that a verified chunk is now available."""

    chunk_index: int

    def validate(self) -> None:
        """Validate have fields."""
        if not isinstance(self.chunk_index, int) or isinstance(self.chunk_index, bool):
            raise ProtocolError(
                f"HAVE chunk_index must be int, got {type(self.chunk_index).__name__}"
            )
        if self.chunk_index < 0 or self.chunk_index > 0xFFFFFFFF:
            raise ProtocolError(f"HAVE chunk_index out of uint32 range: {self.chunk_index}")


Message = Handshake | Bitfield | Request | Piece | Have
