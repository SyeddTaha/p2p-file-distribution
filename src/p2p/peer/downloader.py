"""Async download worker for requesting and validating peer chunks."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Final

from p2p.config import MAX_GLOBAL_INFLIGHT, MAX_PEER_CONNECTIONS, STALL_TIMEOUT_SEC
from p2p.peer.connection import PeerConnection
from p2p.peer.scheduler import DownloadScheduler
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Have,
    Message,
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
        inbound_messages: asyncio.Queue[Message | Exception] | None = None,
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
        self._inbound_messages = inbound_messages
        self._completed: set[int] = set()
        self.last_error: Exception | None = None
        self.bytes_downloaded: int = 0
        self.retry_count: int = 0
        self.chunk_hash_failures: int = 0

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
                if self._inbound_messages is None:
                    msg = await self.connection.receive_message()
                else:
                    queued_message = await self._inbound_messages.get()
                    if isinstance(queued_message, Exception):
                        raise queued_message
                    msg = queued_message
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
                    self.bytes_downloaded += len(msg.data)
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
                if isinstance(exc, ChunkIntegrityError):
                    self.chunk_hash_failures += 1
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
                self.retry_count += 1
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
    ``advertise_chunks=False`` suppresses outbound HAVE broadcasts; verified
    chunk callbacks still run so the owning peer can track local completion.
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
        availability_timeout: float = STALL_TIMEOUT_SEC,
        on_chunk_verified: Callable[[int], Awaitable[None]] | None = None,
        advertise_chunks: bool = True,
    ) -> None:
        if not isinstance(advertise_chunks, bool):
            raise ValueError("advertise_chunks must be a boolean")
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
        if (
            not isinstance(availability_timeout, (int, float))
            or isinstance(availability_timeout, bool)
            or not math.isfinite(availability_timeout)
            or availability_timeout <= 0
        ):
            raise ValueError("availability_timeout must be a positive finite number")
        self.scheduler = scheduler
        self.storage = storage
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_global_inflight = max_global_inflight
        self.availability_timeout = availability_timeout
        self._on_chunk_verified = on_chunk_verified
        self._advertise_chunks = advertise_chunks
        self._workers: dict[str, DownloadWorker] = {}
        self._active: dict[str, PeerConnection] = {}
        self._inboxes: dict[str, asyncio.Queue[Message | Exception]] = {}
        self._reader_tasks: dict[str, asyncio.Task[None]] = {}
        self._worker_tasks: dict[str, asyncio.Task[int | None]] = {}
        self._reader_errors: dict[str, Exception] = {}
        self._availability_changed = asyncio.Event()
        self._retired_bytes_downloaded: int = 0
        self._retired_retries: int = 0
        self._retired_hash_failures: int = 0
        self._start_time: float | None = None
        self._end_time: float | None = None

    @property
    def bytes_downloaded(self) -> int:
        """Total verified payload bytes downloaded across all workers."""
        return (
            sum(w.bytes_downloaded for w in self._workers.values()) + self._retired_bytes_downloaded
        )

    @property
    def total_retries(self) -> int:
        """Total retry attempts made across all workers."""
        return sum(w.retry_count for w in self._workers.values()) + self._retired_retries

    @property
    def chunk_hash_failures(self) -> int:
        """Total chunk integrity/hash failures encountered."""
        return (
            sum(w.chunk_hash_failures for w in self._workers.values()) + self._retired_hash_failures
        )

    @property
    def duration_seconds(self) -> float:
        """Download duration in seconds measured via monotonic clock."""
        if self._start_time is None:
            return 0.0
        end = self._end_time if self._end_time is not None else time.perf_counter()
        return max(0.0, end - self._start_time)

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
            inbox: asyncio.Queue[Message | Exception] = asyncio.Queue(maxsize=32)
            self._inboxes[peer_id] = inbox
            self._workers[peer_id] = DownloadWorker(
                connection,
                self.scheduler,
                self.storage,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                inbound_messages=inbox,
            )

    async def _read_peer_messages(self, peer_id: str, connection: PeerConnection) -> None:
        """Own reads from a peer and dispatch updates to its download worker."""
        inbox = self._inboxes[peer_id]
        try:
            while connection.is_connected:
                message = await connection.receive_message()
                if isinstance(message, Have):
                    self.scheduler.update_peer_have(peer_id, message.chunk_index)
                    self._availability_changed.set()
                await inbox.put(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._reader_errors[peer_id] = exc
            self._availability_changed.set()
            await inbox.put(exc)

    def _start_readers(self) -> None:
        for peer_id, connection in self._active.items():
            self._reader_tasks[peer_id] = asyncio.create_task(
                self._read_peer_messages(peer_id, connection),
                name=f"peer-reader-{peer_id}",
            )

    async def _retire_peer(self, peer_id: str) -> None:
        self.scheduler.unregister_peer(peer_id)
        connection = self._active.pop(peer_id, None)
        worker = self._workers.pop(peer_id, None)
        if worker is not None:
            self._retired_bytes_downloaded += worker.bytes_downloaded
            self._retired_retries += worker.retry_count
            self._retired_hash_failures += worker.chunk_hash_failures
        self._inboxes.pop(peer_id, None)
        self._reader_errors.pop(peer_id, None)
        reader_task = self._reader_tasks.pop(peer_id, None)
        worker_task = self._worker_tasks.get(peer_id)
        if worker_task is not None and worker_task is not asyncio.current_task():
            worker_task.cancel()
        if reader_task is not None and reader_task is not asyncio.current_task():
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)
        if connection is not None:
            await connection.close()

    async def _broadcast_have(self, chunk_index: int, source_peer_id: str) -> None:
        failed: list[str] = []
        for peer_id, connection in tuple(self._active.items()):
            if peer_id == source_peer_id:
                continue
            try:
                async with asyncio.timeout(self.availability_timeout):
                    await connection.send_have(chunk_index)
            except (ConnectionClosed, ProtocolError, TimeoutError, OSError) as exc:
                logger.warning("Unable to broadcast HAVE to %s: %s", peer_id, exc)
                failed.append(peer_id)
        for peer_id in failed:
            await self._retire_peer(peer_id)

    async def _download_from_peer(self, peer_id: str) -> int | None:
        worker = self._workers[peer_id]
        chunk_index = await worker.fetch_next()
        if chunk_index is not None:
            if self._advertise_chunks:
                await self._broadcast_have(chunk_index, peer_id)
            if self._on_chunk_verified is not None:
                await self._on_chunk_verified(chunk_index)
        return chunk_index

    async def _wait_for_peer_update(self) -> None:
        self._availability_changed.clear()
        if self._reader_errors or any(
            self.scheduler.available_missing_for(peer_id) for peer_id in self._active
        ):
            return
        try:
            async with asyncio.timeout(self.availability_timeout):
                await self._availability_changed.wait()
        except TimeoutError as exc:
            missing = sorted(self.scheduler.missing_chunks)
            raise NoAvailablePeersError(
                f"no active peer can provide missing chunks: {missing}"
            ) from exc

    async def run(self) -> set[int]:
        """Download available chunks in parallel, finalize storage, and close peers."""
        self._start_time = time.perf_counter()
        try:
            self._register_connections()
            self._start_readers()
            while not self.scheduler.is_complete:
                for peer_id in tuple(self._reader_errors):
                    await self._retire_peer(peer_id)
                eligible = [
                    peer_id
                    for peer_id in self._active
                    if self.scheduler.available_missing_for(peer_id)
                ]
                if not eligible:
                    if not self._active:
                        missing = sorted(self.scheduler.missing_chunks)
                        raise NoAvailablePeersError(
                            f"no active peer can provide missing chunks: {missing}"
                        )
                    await self._wait_for_peer_update()
                    continue

                batch = eligible[: self.max_global_inflight]
                tasks: dict[str, asyncio.Task[int | None]] = {}
                async with asyncio.TaskGroup() as task_group:
                    for peer_id in batch:
                        tasks[peer_id] = task_group.create_task(
                            self._download_from_peer(peer_id),
                            name=f"download-from-{peer_id}",
                        )
                        self._worker_tasks[peer_id] = tasks[peer_id]

                progressed = False
                retired_peer = False
                for peer_id, task in tasks.items():
                    self._worker_tasks.pop(peer_id, None)
                    if task.cancelled():
                        retired_peer = True
                        continue
                    if task.result() is not None:
                        progressed = True
                    elif peer_id in self._workers and self._workers[peer_id].last_error is not None:
                        await self._retire_peer(peer_id)
                        retired_peer = True
                    elif peer_id not in self._active:
                        retired_peer = True

                if not progressed and not retired_peer and not self.scheduler.is_complete:
                    missing = sorted(self.scheduler.missing_chunks)
                    raise NoAvailablePeersError(
                        f"download made no progress for missing chunks: {missing}"
                    )

            await asyncio.to_thread(self.storage.finalize)
            self._end_time = time.perf_counter()
            return set(self.scheduler.verified_chunks)
        finally:
            if self._end_time is None:
                self._end_time = time.perf_counter()
            reader_tasks = tuple(self._reader_tasks.values())
            for task in reader_tasks:
                task.cancel()
            if reader_tasks:
                await asyncio.gather(*reader_tasks, return_exceptions=True)
            self._reader_tasks.clear()
            for peer_id in tuple(self._active):
                self.scheduler.unregister_peer(peer_id)
            for connection in self.connections:
                await connection.close()
