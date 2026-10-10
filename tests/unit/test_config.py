"""Unit tests for system configuration constants."""

from p2p.config import (
    DEFAULT_CHUNK_SIZE,
    MAX_CHUNK_SIZE,
    MAX_FRAME_SIZE,
    MAX_HANDSHAKE_BODY,
    PROTOCOL_VERSION,
)


def test_protocol_version() -> None:
    """Verify default protocol version."""
    assert PROTOCOL_VERSION == 1


def test_chunk_size_bounds() -> None:
    """Verify chunk size constants and bounds."""
    assert DEFAULT_CHUNK_SIZE <= MAX_CHUNK_SIZE
    assert DEFAULT_CHUNK_SIZE == 256 * 1024
    assert MAX_CHUNK_SIZE == 1024 * 1024


def test_frame_size_bound() -> None:
    """Verify maximum frame size includes type and length overhead."""
    assert MAX_FRAME_SIZE == 1 + 4 + MAX_CHUNK_SIZE
    assert MAX_HANDSHAKE_BODY == 4096
