"""System configuration constants, default parameters, and network bounds."""

from typing import Final

# Protocol Version
PROTOCOL_VERSION: Final[int] = 1

# Chunk & Payload Boundaries
DEFAULT_CHUNK_SIZE: Final[int] = 256 * 1024  # 256 KiB
MAX_CHUNK_SIZE: Final[int] = 1024 * 1024  # 1 MiB
MAX_HANDSHAKE_BODY: Final[int] = 4096  # 4 KiB safety limit for handshake JSON
MAX_FRAME_SIZE: Final[int] = 1 + 4 + MAX_CHUNK_SIZE  # 1,048,581 bytes

# Network Timeouts (seconds)
CONNECT_TIMEOUT_SEC: Final[float] = 10.0
HANDSHAKE_TIMEOUT_SEC: Final[float] = 5.0
IDLE_TIMEOUT_SEC: Final[float] = 60.0
STALL_TIMEOUT_SEC: Final[float] = 15.0

# Tracker Default Parameters
DEFAULT_HEARTBEAT_INTERVAL_SEC: Final[int] = 30
STALE_PEER_EXPIRY_MULTIPLIER: Final[int] = 3
MAX_PEERS_PER_ANNOUNCE: Final[int] = 50

# Concurrency & Scheduling Limits
MAX_PEER_CONNECTIONS: Final[int] = 30
MAX_INFLIGHT_PER_PEER: Final[int] = 4
MAX_GLOBAL_INFLIGHT: Final[int] = 32

# Local web console bounds (independent of the existing CLI).
WEB_MAX_FILE_BYTES: Final[int] = 128 * 1024 * 1024
WEB_MAX_ASSETS: Final[int] = 64
WEB_MAX_TRANSFERS: Final[int] = 64
WEB_MAX_ACTIVE_TRANSFERS: Final[int] = 16
WEB_MAX_CONCURRENT_IMPORTS: Final[int] = 4
WEB_MAX_SETTINGS_BYTES: Final[int] = 8192
WEB_UPLOAD_TIMEOUT_SEC: Final[float] = 120.0
WEB_TRACKER_TIMEOUT_SEC: Final[float] = 3.0
WEB_MAX_TRACKER_RESPONSE_BYTES: Final[int] = 4 * 1024 * 1024
