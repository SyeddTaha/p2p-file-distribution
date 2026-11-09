"""Chunk selection and reservation logic for peer downloads."""

from __future__ import annotations

import random
from collections.abc import Iterable
from enum import StrEnum

from p2p.protocol import Bitfield


class ChunkState(StrEnum):
    """Download lifecycle state for a chunk."""

    MISSING = "MISSING"
    IN_FLIGHT = "IN_FLIGHT"
    VERIFIED = "VERIFIED"


IN_FLIGHT = ChunkState.IN_FLIGHT


class DownloadScheduler:
    """Tracks which chunks are still needed, reserved, or already verified.

    Chunk selection uses a seeded random choice among chunks available from the
    selected peer. Reservation is marked synchronously before any await point.
    """

    def __init__(
        self,
        chunk_count: int,
        *,
        verified_chunks: Iterable[int] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if not isinstance(chunk_count, int) or isinstance(chunk_count, bool):
            raise ValueError("chunk_count must be an integer")
        if chunk_count <= 0:
            raise ValueError("chunk_count must be positive")

        self._chunk_count: int = chunk_count
        self._rng: random.Random = rng if rng is not None else random.Random(0)
        verified = set(verified_chunks or ())
        self._states: dict[int, ChunkState] = {
            index: ChunkState.VERIFIED if index in verified else ChunkState.MISSING
            for index in range(chunk_count)
        }
        self._inflight: dict[int, str] = {}
        self._peer_chunks: dict[str, set[int]] = {}

    @property
    def chunk_count(self) -> int:
        """Total chunk count for the swarm."""
        return self._chunk_count

    @property
    def missing_chunks(self) -> frozenset[int]:
        """Return the set of chunks still missing."""
        return frozenset(
            index for index, state in self._states.items() if state == ChunkState.MISSING
        )

    @property
    def inflight_chunks(self) -> frozenset[int]:
        """Return the set of chunks currently in flight."""
        return frozenset(self._inflight)

    @property
    def verified_chunks(self) -> frozenset[int]:
        """Return the set of chunks already verified."""
        return frozenset(
            index for index, state in self._states.items() if state == ChunkState.VERIFIED
        )

    @property
    def is_complete(self) -> bool:
        """True when every chunk has been verified."""
        return self.missing_chunks == frozenset() and self.inflight_chunks == frozenset()

    def state_for(self, chunk_index: int) -> ChunkState:
        """Return the current state for a single chunk."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ValueError("chunk_index must be an integer")
        if not 0 <= chunk_index < self._chunk_count:
            raise ValueError("chunk_index is outside the valid range")
        return self._states[chunk_index]

    def register_peer(self, peer_id: str, bitfield: Bitfield | None) -> None:
        """Register or refresh a peer's available chunk set."""
        if not peer_id:
            raise ValueError("peer_id must be a non-empty string")
        if bitfield is None:
            self._peer_chunks[peer_id] = set()
            return
        bitfield.validate_for_swarm(self._chunk_count)
        self._peer_chunks[peer_id] = set(bitfield.to_indices(self._chunk_count))

    def update_peer_bitfield(self, peer_id: str, bitfield: Bitfield | None) -> None:
        """Compatibility wrapper for peer-bitfield updates."""
        self.register_peer(peer_id, bitfield)

    def update_peer_have(self, peer_id: str, chunk_index: int) -> None:
        """Record a HAVE broadcast from a peer."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ValueError("chunk_index must be an integer")
        if not 0 <= chunk_index < self._chunk_count:
            raise ValueError("chunk_index is outside the valid range")
        self._peer_chunks.setdefault(peer_id, set()).add(chunk_index)

    def has_chunk(self, peer_id: str, chunk_index: int) -> bool:
        """Return whether the peer advertises the chunk."""
        if peer_id not in self._peer_chunks:
            return False
        return chunk_index in self._peer_chunks[peer_id]

    def available_chunks_for(self, peer_id: str) -> frozenset[int]:
        """Chunks this peer advertises as available."""
        return frozenset(self._peer_chunks.get(peer_id, set()))

    def available_missing_for(self, peer_id: str) -> frozenset[int]:
        """Missing chunks advertised by a peer and eligible for reservation."""
        return frozenset(
            chunk_index
            for chunk_index in self._peer_chunks.get(peer_id, set())
            if self._states[chunk_index] == ChunkState.MISSING
        )

    def reserve_next(self, peer_id: str) -> int | None:
        """Reserve the next missing chunk available from a peer and return it."""
        candidates = self._peer_chunks.get(peer_id, set())
        if not candidates:
            return None

        eligible = sorted(
            chunk
            for chunk in candidates
            if self._states.get(chunk, ChunkState.MISSING) == ChunkState.MISSING
        )
        if not eligible:
            return None

        if len(eligible) > 1:
            chunk_index = self._rng.choice(eligible)
        else:
            chunk_index = eligible[0]

        self._reserve(chunk_index, peer_id)
        return chunk_index

    def reserve(self, chunk_index: int, peer_id: str) -> bool:
        """Reserve a specific chunk for a peer if it is still eligible."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ValueError("chunk_index must be an integer")
        if not 0 <= chunk_index < self._chunk_count:
            raise ValueError("chunk_index is outside the valid range")
        if chunk_index not in self._peer_chunks.get(peer_id, set()):
            return False
        if self._states[chunk_index] != ChunkState.MISSING:
            return False
        self._reserve(chunk_index, peer_id)
        return True

    def _reserve(self, chunk_index: int, peer_id: str) -> None:
        """Internal helper that marks a chunk as in-flight."""
        self._states[chunk_index] = ChunkState.IN_FLIGHT
        self._inflight[chunk_index] = peer_id

    def release(
        self,
        chunk_index: int,
        peer_id: str | None = None,
        *,
        failed: bool = False,
    ) -> bool:
        """Release an in-flight chunk reservation.

        If the release follows a failed transfer, the chunk returns to MISSING so it
        can be retried; otherwise it remains in the same state it had before the
        reservation, which is typically MISSING while the download is still active.
        """
        if chunk_index not in self._inflight:
            return False
        if peer_id is not None and self._inflight[chunk_index] != peer_id:
            return False

        self._inflight.pop(chunk_index, None)
        if failed:
            self._states[chunk_index] = ChunkState.MISSING
        elif self._states.get(chunk_index) == ChunkState.IN_FLIGHT:
            self._states[chunk_index] = ChunkState.MISSING
        return True

    def release_all(self, peer_id: str) -> list[int]:
        """Release all in-flight chunks assigned to a peer."""
        released: list[int] = []
        for chunk_index in list(self._inflight):
            if self._inflight[chunk_index] == peer_id:
                self.release(chunk_index, peer_id=peer_id)
                released.append(chunk_index)
        return released

    def unregister_peer(self, peer_id: str) -> list[int]:
        """Forget a peer and release any chunks reserved to it."""
        self._peer_chunks.pop(peer_id, None)
        return self.release_all(peer_id)

    def mark_verified(self, chunk_index: int, *, peer_id: str | None = None) -> bool:
        """Mark a chunk as verified after a valid PIECE payload passes validation."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ValueError("chunk_index must be an integer")
        if not 0 <= chunk_index < self._chunk_count:
            raise ValueError("chunk_index is outside the valid range")

        if peer_id is not None and chunk_index in self._inflight:
            if self._inflight[chunk_index] != peer_id:
                return False
            self._inflight.pop(chunk_index, None)

        if chunk_index in self._inflight:
            self._inflight.pop(chunk_index, None)

        self._states[chunk_index] = ChunkState.VERIFIED
        if peer_id is not None:
            self._peer_chunks.setdefault(peer_id, set()).add(chunk_index)
        return True

    def mark_missing(self, chunk_index: int) -> None:
        """Reset a chunk to missing if validation or transfer fails."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ValueError("chunk_index must be an integer")
        if not 0 <= chunk_index < self._chunk_count:
            raise ValueError("chunk_index is outside the valid range")
        self._inflight.pop(chunk_index, None)
        self._states[chunk_index] = ChunkState.MISSING

    def complete_chunk(self, chunk_index: int, *, peer_id: str | None = None) -> bool:
        """Alias for mark_verified used by downloader workers."""
        return self.mark_verified(chunk_index, peer_id=peer_id)

    def __len__(self) -> int:
        return self._chunk_count
