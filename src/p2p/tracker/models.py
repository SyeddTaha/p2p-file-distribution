"""Pydantic models and request/response schemas for the Tracker HTTP control plane."""

from __future__ import annotations

import enum
import ipaddress
import re
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from p2p.config import DEFAULT_HEARTBEAT_INTERVAL_SEC
from p2p.protocol.messages import HEX_64_PATTERN, PEER_ID_PATTERN

_HOSTNAME_LABEL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)


def _is_valid_ip(host: str) -> bool:
    """Check if host is a valid IPv4 or IPv6 address (including bracketed IPv6)."""
    clean_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(clean_host)
        return True
    except ValueError:
        return False


def _is_valid_rfc1123_hostname(host: str) -> bool:
    """Check if host conforms to RFC 1123 DNS hostname syntax."""
    if not host:
        return False
    # Allow single optional trailing dot
    normalized = host[:-1] if host.endswith(".") else host
    if not normalized or len(normalized) > 253:
        return False
    labels = normalized.split(".")
    if len(labels) == 1 and labels[0].isdigit():
        return False
    if len(labels) == 4 and all(label.isdigit() for label in labels):
        return False
    return all(_HOSTNAME_LABEL_PATTERN.match(label) is not None for label in labels)


class AnnounceEvent(enum.StrEnum):
    """Lifecycle events sent by peers in tracker announcements."""

    STARTED = "started"
    HEARTBEAT = "heartbeat"
    COMPLETED = "completed"
    STOPPED = "stopped"


class AnnounceRequest(BaseModel):
    """Peer announcement payload sent via POST /announce."""

    model_config = ConfigDict(extra="forbid")

    swarm_id: str
    peer_id: str
    host: str
    port: int
    event: AnnounceEvent
    is_seeder: bool = False

    @field_validator("swarm_id", mode="before")
    @classmethod
    def validate_swarm_id(cls, value: object) -> str:
        """Validate swarm ID as exactly 64 lowercase hexadecimal characters."""
        if not isinstance(value, str):
            raise ValueError("swarm_id must be a string")
        if not HEX_64_PATTERN.match(value):
            raise ValueError("swarm_id must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("peer_id", mode="before")
    @classmethod
    def validate_peer_id(cls, value: object) -> str:
        """Validate peer ID as 1..64 safe characters."""
        if not isinstance(value, str):
            raise ValueError("peer_id must be a string")
        if not PEER_ID_PATTERN.match(value):
            raise ValueError(
                "peer_id must be 1..64 alphanumeric, hyphen, underscore, or dot characters"
            )
        return value

    @field_validator("host", mode="before")
    @classmethod
    def validate_host(cls, value: object) -> str:
        """Validate advertised host as a valid IPv4, IPv6, or RFC 1123 hostname."""
        if not isinstance(value, str):
            raise ValueError("host must be a string")
        if not value or len(value) > 255:
            raise ValueError("host length must be between 1 and 255 characters")
        if any(char.isspace() for char in value) or "\x00" in value:
            raise ValueError("host cannot contain whitespace or NUL bytes")
        if not (_is_valid_ip(value) or _is_valid_rfc1123_hostname(value)):
            raise ValueError(f"host is not a valid IPv4, IPv6, or RFC 1123 hostname: {value!r}")
        return value

    @field_validator("port", mode="before")
    @classmethod
    def validate_port(cls, value: object) -> int:
        """Validate listening port is an integer in 1..65535."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("port must be an integer")
        if not (1 <= value <= 65535):
            raise ValueError(f"port out of range 1..65535: {value}")
        return value

    @field_validator("is_seeder", mode="before")
    @classmethod
    def validate_is_seeder(cls, value: object) -> bool:
        """Validate is_seeder is strictly a boolean."""
        if not isinstance(value, bool):
            raise ValueError("is_seeder must be a boolean")
        return value


class PeerInfo(BaseModel):
    """Peer connection descriptor returned in announcement responses."""

    peer_id: str
    host: str
    port: int


class AnnounceResponse(BaseModel):
    """Tracker response to a peer announcement."""

    interval: int = Field(default=DEFAULT_HEARTBEAT_INTERVAL_SEC)
    peers: list[PeerInfo] = Field(default_factory=list)


class SwarmPeerInfo(BaseModel):
    """Detailed peer descriptor returned by swarm inspection endpoints."""

    peer_id: str
    host: str
    port: int
    last_seen: float
    is_seeder: bool


class SwarmPeersResponse(BaseModel):
    """Response returned by GET /swarms/{swarm_id}/peers."""

    swarm_id: str
    peers: list[SwarmPeerInfo] = Field(default_factory=list)
