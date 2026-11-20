"""Copied diagnostic snapshots; taking a snapshot never drives network work."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionSnapshot:
    peer_id: str | None
    direction: str
    state: str
    available_chunks: int | None
    pending_requests: int


@dataclass(frozen=True)
class PeerSnapshot:
    peer_id: str
    swarm_id: str
    host: str
    port: int
    online: bool
    upload_enabled: bool
    upload_rate_limit: float | None
    verified_chunks: int
    verified_bytes: int
    final_integrity: str
    bytes_uploaded: int
    bytes_downloaded: int
    retries: int
    chunk_hash_failures: int
    duration_seconds: float
    throughput_bytes_per_s: float
    downloaded_from: dict[str, int]
    connections: tuple[ConnectionSnapshot, ...]
