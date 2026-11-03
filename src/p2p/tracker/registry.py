"""In-memory swarm registry, peer management, and injectable clock for the tracker."""

from __future__ import annotations

import dataclasses
import random
import time
from typing import Final, Protocol

from p2p.config import (
    DEFAULT_HEARTBEAT_INTERVAL_SEC,
    MAX_PEERS_PER_ANNOUNCE,
    STALE_PEER_EXPIRY_MULTIPLIER,
)
from p2p.tracker.models import (
    AnnounceEvent,
    AnnounceRequest,
    AnnounceResponse,
    PeerInfo,
    SwarmPeerInfo,
)


class Clock(Protocol):
    """Protocol for monotonic time sources to enable deterministic clock injection."""

    def now(self) -> float:
        """Return the current timestamp in monotonic seconds."""
        ...


class MonotonicClock:
    """Default clock implementation using system monotonic time."""

    def now(self) -> float:
        """Return system monotonic time in seconds."""
        return time.monotonic()


@dataclasses.dataclass(slots=True)
class PeerRecord:
    """Internal tracker record representing an active peer in a swarm."""

    peer_id: str
    host: str
    port: int
    last_seen: float
    is_seeder: bool = False


class SwarmRegistry:
    """In-memory swarm registry tracking active peers, heartbeats, and stale expiry.

    Keeps state organized by swarm ID and peer ID. Completely decoupled from
    HTTP routing and ASGI frameworks.
    """

    def __init__(
        self,
        clock: Clock | None = None,
        *,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL_SEC,
        expiry_multiplier: int = STALE_PEER_EXPIRY_MULTIPLIER,
        max_peers_per_announce: int = MAX_PEERS_PER_ANNOUNCE,
        rng: random.Random | None = None,
    ) -> None:
        if (
            isinstance(heartbeat_interval, bool)
            or not isinstance(heartbeat_interval, int)
            or heartbeat_interval <= 0
        ):
            raise ValueError("heartbeat_interval must be a positive integer")
        if (
            isinstance(expiry_multiplier, bool)
            or not isinstance(expiry_multiplier, int)
            or expiry_multiplier <= 0
        ):
            raise ValueError("expiry_multiplier must be a positive integer")
        if (
            isinstance(max_peers_per_announce, bool)
            or not isinstance(max_peers_per_announce, int)
            or not 1 <= max_peers_per_announce <= MAX_PEERS_PER_ANNOUNCE
        ):
            raise ValueError(
                f"max_peers_per_announce must be an integer in 1..{MAX_PEERS_PER_ANNOUNCE}"
            )
        self._clock: Final[Clock] = clock if clock is not None else MonotonicClock()
        self._heartbeat_interval: Final[int] = heartbeat_interval
        self._expiry_multiplier: Final[int] = expiry_multiplier
        self._max_peers_per_announce: Final[int] = max_peers_per_announce
        self._rng: Final[random.Random] = rng if rng is not None else random.Random()
        # swarm_id -> {peer_id: PeerRecord}
        self._swarms: dict[str, dict[str, PeerRecord]] = {}

    @property
    def heartbeat_interval(self) -> int:
        """Interval in seconds peers should wait between regular announcements."""
        return self._heartbeat_interval

    @property
    def expiry_multiplier(self) -> int:
        """Multiplier applied to heartbeat_interval before evicting a stale peer."""
        return self._expiry_multiplier

    @property
    def expiry_timeout(self) -> float:
        """Duration in seconds after last_seen before a peer is considered stale."""
        return float(self._heartbeat_interval * self._expiry_multiplier)

    @property
    def max_peers_per_announce(self) -> int:
        """Maximum number of peer records returned in an announce response."""
        return self._max_peers_per_announce

    def announce(self, request: AnnounceRequest) -> AnnounceResponse:
        """Process a peer announcement and return an active peer list.

        Handles registration, heartbeats, seeder completion, and graceful departures.
        The announcing peer is strictly excluded from the returned peer list.
        """
        # Evict any stale peers in this swarm first
        self.evict_stale(request.swarm_id)

        swarm = self._swarms.setdefault(request.swarm_id, {})
        current_time = self._clock.now()

        if request.event == AnnounceEvent.STOPPED:
            swarm.pop(request.peer_id, None)
            if not swarm:
                self._swarms.pop(request.swarm_id, None)
            return AnnounceResponse(interval=self._heartbeat_interval, peers=[])

        # For started, heartbeat, and completed
        existing = swarm.get(request.peer_id)
        if existing is not None:
            existing.host = request.host
            existing.port = request.port
            existing.last_seen = current_time
            if request.event == AnnounceEvent.COMPLETED or request.is_seeder:
                existing.is_seeder = True
        else:
            is_seeder = (request.event == AnnounceEvent.COMPLETED) or request.is_seeder
            swarm[request.peer_id] = PeerRecord(
                peer_id=request.peer_id,
                host=request.host,
                port=request.port,
                last_seen=current_time,
                is_seeder=is_seeder,
            )

        # Collect candidate peers excluding the calling peer
        candidate_records = [record for pid, record in swarm.items() if pid != request.peer_id]

        # Sample if candidates exceed the maximum allowed
        if len(candidate_records) > self._max_peers_per_announce:
            selected_records = self._rng.sample(candidate_records, self._max_peers_per_announce)
        else:
            selected_records = candidate_records

        peers = [PeerInfo(peer_id=r.peer_id, host=r.host, port=r.port) for r in selected_records]
        return AnnounceResponse(interval=self._heartbeat_interval, peers=peers)

    def evict_stale(self, swarm_id: str | None = None) -> int:
        """Evict peers whose inactivity exceeds the expiry timeout.

        If swarm_id is provided, only inspects that swarm; otherwise inspects all swarms.
        Cleans up swarms that become empty. Returns the number of evicted peers.
        """
        now = self._clock.now()
        timeout = self.expiry_timeout
        evicted_count = 0

        target_swarms = [swarm_id] if swarm_id is not None else list(self._swarms.keys())

        for sid in target_swarms:
            swarm = self._swarms.get(sid)
            if swarm is None:
                continue

            stale_peer_ids = [
                pid for pid, record in swarm.items() if (now - record.last_seen) > timeout
            ]

            for pid in stale_peer_ids:
                del swarm[pid]
                evicted_count += 1

            if not swarm:
                self._swarms.pop(sid, None)

        return evicted_count

    def get_swarm_peers(self, swarm_id: str) -> list[SwarmPeerInfo]:
        """Return diagnostic descriptors for all active peers in a swarm.

        Evicts stale peers before returning the active list.
        """
        self.evict_stale(swarm_id)
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return []

        return [
            SwarmPeerInfo(
                peer_id=record.peer_id,
                host=record.host,
                port=record.port,
                last_seen=record.last_seen,
                is_seeder=record.is_seeder,
            )
            for record in swarm.values()
        ]

    def get_peer(self, swarm_id: str, peer_id: str) -> PeerRecord | None:
        """Look up an active peer record without modifying state."""
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return None
        return swarm.get(peer_id)

    def peer_count(self, swarm_id: str | None = None) -> int:
        """Return the count of active peers in a specific swarm or across all swarms."""
        if swarm_id is not None:
            swarm = self._swarms.get(swarm_id)
            return len(swarm) if swarm else 0
        return sum(len(swarm) for swarm in self._swarms.values())

    def active_swarms(self) -> list[str]:
        """Return a list of all currently tracked swarm IDs."""
        return list(self._swarms.keys())
