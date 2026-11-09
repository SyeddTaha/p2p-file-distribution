"""Async download worker for requesting and validating peer chunks."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Iterable
from typing import Final

from p2p.config import MAX_GLOBAL_INFLIGHT, MAX_PEER_CONNECTIONS, STALL_TIMEOUT_SEC
from p2p.peer.connection import PeerConnection
from p2p.peer.scheduler import DownloadScheduler
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Have,
    Piece,
    ProtocolError,
    Request,
)
from p2p.storage.manager import ChunkIntegrityError, StorageManager

logger = logging.getLogger(__name__)

_TRANSFER_ERRORS: Final[tuple[type[Exception], ...]] = (
    ConnectionClosed,
    ProtocolError,
    TimeoutError,
    OSError,
    ValueError,
    ChunkIntegrityError,
)


class DownloadError(RuntimeError):
    """Base error for a swarm download that cannot complete."""


class NoAvailablePeersError(DownloadError):
    """Raised when missing chunks are not available from any active peer."""


class DownloadWorker:
    """Sequential chunk worker for one already-connected peer."""

    def __init__(
        self,
        connection: PeerConnection,
        scheduler: DownloadScheduler,
        storage: StorageManager,
        *,
        max_retries: int = 3,
        retry_delay: float = 0.05,
    ) -> None:
        if not isinstance(connection, PeerConnection):
            raise TypeError("connection must be a PeerConnection")
        if not isinstance(scheduler, DownloadScheduler):
            raise TypeError("scheduler must be a DownloadScheduler")
        if not isinstance(storage, StorageManager):
            raise TypeError("storage must be a StorageManager")
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 1:
            raise ValueError("max_retries must be a positive integer")
        if (
            not isinstance(retry_delay, (int, float))
            or isinstance(retry_delay, bool)
            or not math.isfinite(retry_delay)
            or retry_delay < 0
        ):
            raise ValueError("retry_delay must be a finite non-negative number")
        self.connection = connection
        self.scheduler = scheduler
        self.storage = storage
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._completed: set[int] = set()
        self.last_error: Exception | None = None

    @property
    def completed(self) -> frozenset[int]:
        """Chunks successfully downloaded by this worker."""
        return frozenset(self._completed)

    async def finish_chunk(self, chunk_index: int) -> None:
        """Mark a chunk complete only after StorageManager verified it."""
        if chunk_index not in self.storage.verified_chunks:
            raise ChunkIntegrityError(f"chunk {chunk_index} has not been verified by storage")

        if not self.scheduler.mark_verified(
            chunk_index,
            peer_id=self.connection.remote_peer_id,
        ):
            raise RuntimeError(f"chunk {chunk_index} reservation belongs to another peer")
        self._completed.add(chunk_index)

    async def _request_one(self, chunk_index: int) -> Piece:
        """Request a single chunk and return its received PIECE payload."""
        async with asyncio.timeout(STALL_TIMEOUT_SEC):
            await self.connection.send_request(chunk_index)
            while True:
                msg = await self.connection.receive_message()
                if isinstance(msg, Have):
                    peer_id = self.connection.remote_peer_id
                    if peer_id is not None:
                        self.scheduler.update_peer_have(peer_id, msg.chunk_index)
                    continue
                if isinstance(msg, Piece):
                    if msg.chunk_index != chunk_index:
                        raise ProtocolError(
                            f"Received PIECE for chunk {msg.chunk_index} instead of {chunk_index}"
                        )
                    self.storage.write_chunk(chunk_index, msg.data)
                    return msg
                if isinstance(msg, Request):
                    raise ProtocolError(
                        f"Unexpected REQUEST for chunk {msg.chunk_index} while downloading"
                    )
                raise ProtocolError(
                    f"Expected PIECE for chunk {chunk_index}, got {type(msg).__name__}"
                )

    async def fetch_next(self) -> int | None:
        """Reserve and download the next chunk from the connected peer."""
        peer_id = self.connection.remote_peer_id or "remote-peer"
        self.last_error = None
        chunk_index = self.scheduler.reserve_next(peer_id)
        if chunk_index is None:
            return None

        for attempt in range(self.max_retries):
            try:
                await self._request_one(chunk_index)
                if not self.scheduler.mark_verified(chunk_index, peer_id=peer_id):
                    raise RuntimeError(f"chunk {chunk_index} reservation was lost")
                self._completed.add(chunk_index)
                self.last_error = None
                return chunk_index
            except asyncio.CancelledError:
                self.connection.cancel_pending_request(chunk_index)
                self.scheduler.release(chunk_index, peer_id=peer_id, failed=True)
                raise
            except _TRANSFER_ERRORS as exc:
                self.last_error = exc
                self.connection.cancel_pending_request(chunk_index)
                if attempt + 1 >= self.max_retries or not self.connection.is_connected:
                    self.scheduler.release(chunk_index, peer_id=peer_id, failed=True)
                    logger.warning(
                        "Chunk %d failed after %d attempts from %s",
                        chunk_index,
                        attempt + 1,
                        peer_id,
                    )
                    return None
                await asyncio.sleep(self.retry_delay * (2**attempt))

        raise AssertionError("positive max_retries must execute at least one request")

    async def run(self) -> set[int]:
        """Download as many chunks as possible from the connected peer."""
        downloaded: set[int] = set()
        while True:
            if not self.connection.is_connected:
                break
            chunk_index = await self.fetch_next()
            if chunk_index is None:
                break
            downloaded.add(chunk_index)
        return downloaded


class SwarmDownloader:
    """Coordinate bounded parallel chunk downloads across connected peers.

    The downloader takes ownership of the supplied connections and closes them
    when the run finishes or is cancelled.
    """

    def __init__(
        self,
        connections: Iterable[PeerConnection],
        scheduler: DownloadScheduler,
        storage: StorageManager,
        *,
        max_retries: int = 3,
        retry_delay: float = 0.05,
        max_peer_connections: int = MAX_PEER_CONNECTIONS,
        max_global_inflight: int = MAX_GLOBAL_INFLIGHT,
    ) -> None:
        self.connections = tuple(connections)
        if not self.connections:
            raise ValueError("at least one peer connection is required")
        if any(not isinstance(connection, PeerConnection) for connection in self.connections):
            raise TypeError("all connections must be PeerConnection instances")
        if (
            not isinstance(max_peer_connections, int)
            or isinstance(max_peer_connections, bool)
            or max_peer_connections < 1
        ):
            raise ValueError("max_peer_connections must be a positive integer")
        if max_peer_connections > MAX_PEER_CONNECTIONS:
            raise ValueError(f"max_peer_connections cannot exceed {MAX_PEER_CONNECTIONS}")
        if len(self.connections) > max_peer_connections:
            raise ValueError(f"connections exceed max_peer_connections ({max_peer_connections})")
        if not isinstance(scheduler, DownloadScheduler):
            raise TypeError("scheduler must be a DownloadScheduler")
        if not isinstance(storage, StorageManager):
            raise TypeError("storage must be a StorageManager")
        if scheduler.chunk_count != storage.manifest["chunk_count"]:
            raise ValueError("scheduler and storage chunk counts must match")
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 1:
            raise ValueError("max_retries must be a positive integer")
        if (
            not isinstance(retry_delay, (int, float))
            or isinstance(retry_delay, bool)
            or not math.isfinite(retry_delay)
            or retry_delay < 0
        ):
            raise ValueError("retry_delay must be a finite non-negative number")
        if (
            not isinstance(max_global_inflight, int)
            or isinstance(max_global_inflight, bool)
            or max_global_inflight < 1
        ):
            raise ValueError("max_global_inflight must be a positive integer")
        if max_global_inflight > MAX_GLOBAL_INFLIGHT:
            raise ValueError(f"max_global_inflight cannot exceed {MAX_GLOBAL_INFLIGHT}")
        self.scheduler = scheduler
        self.storage = storage
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_global_inflight = max_global_inflight
        self._workers: dict[str, DownloadWorker] = {}
        self._active: dict[str, PeerConnection] = {}

    def _register_connections(self) -> None:
        for connection in self.connections:
            peer_id = connection.remote_peer_id
            bitfield: Bitfield | None = connection.remote_bitfield
            if not connection.is_connected or peer_id is None or bitfield is None:
                raise ValueError("all peer connections must be handshaken and connected")
            if peer_id in self._active:
                raise ValueError(f"duplicate peer connection for {peer_id!r}")
            self.scheduler.register_peer(peer_id, bitfield)
            self._active[peer_id] = connection
            self._workers[peer_id] = DownloadWorker(
                connection,
                self.scheduler,
                self.storage,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
            )

    async def _broadcast_have(self, chunk_index: int, source_peer_id: str) -> None:
        failed: list[str] = []
        for peer_id, connection in tuple(self._active.items()):
            if peer_id == source_peer_id:
                continue
            try:
                async with asyncio.timeout(STALL_TIMEOUT_SEC):
                    await connection.send_have(chunk_index)
            except (ConnectionClosed, ProtocolError, TimeoutError, OSError) as exc:
                logger.warning("Unable to broadcast HAVE to %s: %s", peer_id, exc)
                failed.append(peer_id)
        for peer_id in failed:
            self.scheduler.unregister_peer(peer_id)
            connection = self._active.pop(peer_id)
            self._workers.pop(peer_id, None)
            await connection.close()

    async def _download_from_peer(self, peer_id: str) -> int | None:
        worker = self._workers[peer_id]
        chunk_index = await worker.fetch_next()
        if chunk_index is not None:
            await self._broadcast_have(chunk_index, peer_id)
        return chunk_index

    async def run(self) -> set[int]:
        """Download available chunks in parallel, finalize storage, and close peers."""
        try:
            self._register_connections()
            while not self.scheduler.is_complete:
                eligible = [
                    peer_id
                    for peer_id in self._active
                    if self.scheduler.available_missing_for(peer_id)
                ]
                if not eligible:
                    missing = sorted(self.scheduler.missing_chunks)
                    raise NoAvailablePeersError(
                        f"no active peer can provide missing chunks: {missing}"
                    )

                batch = eligible[: self.max_global_inflight]
                tasks: dict[str, asyncio.Task[int | None]] = {}
                async with asyncio.TaskGroup() as task_group:
                    for peer_id in batch:
                        tasks[peer_id] = task_group.create_task(
                            self._download_from_peer(peer_id),
                            name=f"download-from-{peer_id}",
                        )

                progressed = False
                retired_peer = False
                for peer_id, task in tasks.items():
                    if task.result() is not None:
                        progressed = True
                    elif self._workers[peer_id].last_error is not None:
                        self.scheduler.unregister_peer(peer_id)
                        connection = self._active.pop(peer_id)
                        self._workers.pop(peer_id, None)
                        await connection.close()
                        retired_peer = True

                if not progressed and not retired_peer and not self.scheduler.is_complete:
                    missing = sorted(self.scheduler.missing_chunks)
                    raise NoAvailablePeersError(
                        f"download made no progress for missing chunks: {missing}"
                    )

            await asyncio.to_thread(self.storage.finalize)
            return set(self.scheduler.verified_chunks)
        finally:
            for peer_id in tuple(self._active):
                self.scheduler.unregister_peer(peer_id)
            for connection in self.connections:
                await connection.close()
