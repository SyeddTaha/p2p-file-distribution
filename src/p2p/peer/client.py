"""Tracker-connected peer lifecycle for seeding and downloading a swarm."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import random
import uuid
from pathlib import Path
from typing import Self

import httpx

from p2p.config import MAX_PEER_CONNECTIONS, STALL_TIMEOUT_SEC
from p2p.peer.connection import PeerConnection
from p2p.peer.downloader import NoAvailablePeersError, SwarmDownloader
from p2p.peer.rate_limiter import TokenBucketRateLimiter
from p2p.peer.scheduler import DownloadScheduler
from p2p.peer.server import PeerServer
from p2p.protocol import Bitfield, ConnectionClosed, Have, Piece, ProtocolError, Request
from p2p.storage.manager import StorageManager
from p2p.storage.manifest import (
    FileManifest,
    build_manifest,
    compute_swarm_id,
    validate_manifest,
)
from p2p.tracker.models import AnnounceEvent, AnnounceResponse, PeerInfo

logger = logging.getLogger(__name__)


class SwarmPeer:
    """Peer lifecycle joining tracker discovery, serving, and downloading.

    The instance owns its listener and HTTP client. For download peers, the
    ``StorageManager`` owns verified chunks and the listener serves only those
    chunks while the transfer is in progress and after it completes.
    With ``upload_enabled=False``, verified chunks remain local: BITFIELD is
    empty, HAVE is suppressed, and incoming chunk requests are refused.
    """

    def __init__(
        self,
        manifest: object,
        tracker_url: str,
        download_dir: Path,
        *,
        seed_file: Path | None = None,
        host: str = "127.0.0.1",
        listen_port: int = 0,
        peer_id: str | None = None,
        tracker_transport: httpx.AsyncBaseTransport | None = None,
        tracker_timeout: float = 10.0,
        upload_enabled: bool = True,
        upload_rate_limit: float | None = None,
        scheduler_seed: int = 0,
    ) -> None:
        self.manifest: FileManifest = validate_manifest(manifest)
        if not isinstance(upload_enabled, bool):
            raise ValueError("upload_enabled must be a boolean")
        if type(scheduler_seed) is not int:
            raise ValueError("scheduler_seed must be an integer")
        if not tracker_url.startswith(("http://", "https://")):
            raise ValueError("tracker_url must use http:// or https://")
        if not isinstance(listen_port, int) or isinstance(listen_port, bool):
            raise ValueError("listen_port must be an integer")
        if not 0 <= listen_port <= 65535:
            raise ValueError("listen_port must be in 0..65535")
        if not isinstance(host, str) or not host:
            raise ValueError("host must be a non-empty advertised address")
        if (
            not isinstance(tracker_timeout, (int, float))
            or isinstance(tracker_timeout, bool)
            or not math.isfinite(tracker_timeout)
            or tracker_timeout <= 0
        ):
            raise ValueError("tracker_timeout must be a positive finite number")
        if upload_rate_limit is not None and (
            not isinstance(upload_rate_limit, (int, float))
            or isinstance(upload_rate_limit, bool)
            or not math.isfinite(upload_rate_limit)
            or upload_rate_limit <= 0
        ):
            raise ValueError("upload_rate_limit must be a positive finite number or None")

        self.tracker_url = tracker_url.rstrip("/")
        self.host = host
        self.peer_id = peer_id or f"peer-{uuid.uuid4().hex}"
        self.swarm_id = compute_swarm_id(self.manifest)
        self.seed_file = seed_file
        self._upload_enabled = upload_enabled
        self._scheduler_seed = scheduler_seed
        self._rate_limiter: TokenBucketRateLimiter | None = (
            TokenBucketRateLimiter(upload_rate_limit) if upload_rate_limit is not None else None
        )
        self.storage = (
            None
            if seed_file is not None
            else StorageManager(
                self.manifest,
                download_dir,
            )
        )
        self._available_chunks: set[int] = (
            set(range(self.manifest["chunk_count"])) if seed_file is not None else set()
        )
        self._seed_path = seed_file
        self._listen_port = listen_port
        self._tracker_timeout = float(tracker_timeout)
        self._http = httpx.AsyncClient(
            transport=tracker_transport,
            timeout=httpx.Timeout(self._tracker_timeout),
        )
        self._server: PeerServer | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._heartbeat_interval = 30
        self._started = False
        self._closed = False
        self._stopped_event = asyncio.Event()
        self._outbound_connection_count = 0
        self._download_active = False
        self.received_haves: set[tuple[str, int]] = set()
        self.sent_haves: set[int] = set()
        self._known_peers: dict[str, PeerInfo] = {}
        self.bytes_uploaded: int = 0
        self.bytes_downloaded: int = 0
        self.total_retries: int = 0
        self.chunk_hash_failures: int = 0
        self.download_duration_seconds: float = 0.0
        self.download_throughput_bytes_per_s: float = 0.0

    @property
    def listen_port(self) -> int:
        """Return the listener's assigned port after start."""
        if self._server is None:
            raise RuntimeError("peer has not been started")
        return self._server.listen_port

    @property
    def is_seeder(self) -> bool:
        """Whether every manifest chunk is locally available."""
        return len(self._available_chunks) == self.manifest["chunk_count"]

    def _local_bitfield(self) -> Bitfield:
        advertised_chunks = self._available_chunks if self._upload_enabled else set()
        return Bitfield.from_indices(advertised_chunks, self.manifest["chunk_count"])

    async def start(self) -> int:
        """Start the peer listener, announce its presence, and launch heartbeats."""
        if self._closed:
            raise RuntimeError("a closed peer cannot be restarted")
        if self._started:
            return self.listen_port

        try:
            if self.seed_file is not None:
                actual_manifest = await asyncio.to_thread(
                    build_manifest,
                    self.seed_file,
                    self.manifest["chunk_size"],
                )
                if actual_manifest != self.manifest:
                    raise ValueError("seed file contents do not match the supplied manifest")

            self._server = PeerServer(
                self.host,
                self._listen_port,
                swarm_id=self.swarm_id,
                my_peer_id=self.peer_id,
                chunk_count=self.manifest["chunk_count"],
                local_bitfield=self._local_bitfield(),
                on_connection=self._serve_connection,
            )
            self._listen_port = await self._server.start()
            response = await self._announce(AnnounceEvent.STARTED)
        except BaseException as startup_error:
            cleanup_errors: list[BaseException] = []
            try:
                if self._server is not None:
                    await self._server.stop()
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
            finally:
                self._server = None
                try:
                    await self._http.aclose()
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
                finally:
                    self._closed = True
                    self._stopped_event.set()
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Peer startup failed and rollback encountered errors",
                    [startup_error, *cleanup_errors],
                ) from None
            raise

        self._started = True
        self._remember_peers(response.peers)
        self._heartbeat_interval = response.interval
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name=f"heartbeat-{self.peer_id}",
        )
        return self.listen_port

    async def _announce(self, event: AnnounceEvent) -> AnnounceResponse:
        payload = {
            "swarm_id": self.swarm_id,
            "peer_id": self.peer_id,
            "host": self.host,
            "port": self._listen_port,
            "event": event.value,
            "is_seeder": self.is_seeder,
        }
        async with asyncio.timeout(self._tracker_timeout):
            response = await self._http.post(f"{self.tracker_url}/announce", json=payload)
        response.raise_for_status()
        return AnnounceResponse.model_validate(response.json())

    def _remember_peers(self, peers: list[PeerInfo]) -> None:
        for peer in peers:
            if peer.peer_id != self.peer_id:
                self._known_peers[peer.peer_id] = peer

    async def heartbeat(self) -> None:
        """Refresh tracker registration and peer discovery immediately."""
        if not self._started or self._closed:
            raise RuntimeError("peer must be started before sending a heartbeat")
        response = await self._announce(AnnounceEvent.HEARTBEAT)
        self._remember_peers(response.peers)

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                try:
                    await self.heartbeat()
                except (httpx.HTTPError, TimeoutError, ValueError) as exc:
                    logger.warning("Tracker heartbeat failed for %s: %s", self.peer_id, exc)
        except asyncio.CancelledError:
            raise

    async def _read_chunk(self, index: int) -> bytes:
        if not self._upload_enabled:
            raise ProtocolError("chunk uploading is disabled")
        if index not in self._available_chunks:
            raise ProtocolError(f"peer does not have verified chunk {index}")
        source = self._seed_path
        if source is None:
            if self.storage is None:
                raise RuntimeError("download storage is unavailable")
            source = (
                self.storage.target_path
                if self.storage.target_path.exists()
                else self.storage.part_path
            )
        descriptor = self.manifest["chunks"][index]
        data = await asyncio.to_thread(
            self._read_and_verify_chunk,
            source,
            index * self.manifest["chunk_size"],
            descriptor["length"],
            descriptor["sha256"],
        )
        return data

    @staticmethod
    def _read_and_verify_chunk(path: Path, offset: int, length: int, expected_hash: str) -> bytes:
        with path.open("rb") as source:
            source.seek(offset)
            data = source.read(length)
        if len(data) != length or not hmac.compare_digest(
            hashlib.sha256(data).hexdigest(),
            expected_hash,
        ):
            raise OSError("local chunk no longer matches the manifest")
        return data

    async def _serve_connection(self, connection: PeerConnection) -> None:
        """Serve verified REQUESTs and record remote HAVE notifications."""
        try:
            initial_chunks = connection.local_bitfield.to_indices(self.manifest["chunk_count"])
            advertised_chunks = self._local_bitfield().to_indices(self.manifest["chunk_count"])
            for index in sorted(advertised_chunks - initial_chunks):
                await connection.send_have(index)
            while connection.is_connected:
                message = await connection.receive_message()
                if isinstance(message, Request):
                    data = await self._read_chunk(message.chunk_index)
                    if self._rate_limiter is not None:
                        await self._rate_limiter.acquire(len(data))
                    await connection.send_piece(message.chunk_index, data)
                    self.bytes_uploaded += len(data)
                elif isinstance(message, Have):
                    if connection.remote_peer_id is not None:
                        self.received_haves.add((connection.remote_peer_id, message.chunk_index))
                elif isinstance(message, Piece):
                    raise ProtocolError("unsolicited PIECE received by the serving peer")
        except (ConnectionClosed, ProtocolError, OSError) as exc:
            logger.debug("Serving connection to %s ended: %s", connection.remote_peer_id, exc)

    async def _on_chunk_verified(self, index: int) -> None:
        self._available_chunks.add(index)
        if not self._upload_enabled or self._server is None:
            return
        self._server.update_local_bitfield(self._local_bitfield())
        self.sent_haves.add(index)
        for connection in tuple(self._server.active_connections):
            if not connection.is_connected:
                continue
            try:
                async with asyncio.timeout(STALL_TIMEOUT_SEC):
                    await connection.send_have(index)
            except (ConnectionClosed, ProtocolError, TimeoutError, OSError) as exc:
                logger.debug("Unable to announce HAVE to %s: %s", connection.remote_peer_id, exc)
                await connection.close()

    async def _connect_to_peers(self, peers: list[PeerInfo]) -> list[PeerConnection]:
        connected_peer_ids: set[str] = set()
        if self._server is not None:
            connected_peer_ids = {
                connection.remote_peer_id
                for connection in self._server.active_connections
                if connection.remote_peer_id is not None
            }
        candidates: list[PeerInfo] = []
        seen = set(connected_peer_ids)
        for peer in peers:
            if peer.peer_id == self.peer_id or peer.peer_id in seen:
                continue
            seen.add(peer.peer_id)
            candidates.append(peer)

        async def connect(peer: PeerInfo) -> PeerConnection:
            return await PeerConnection.connect(
                peer.host,
                peer.port,
                swarm_id=self.swarm_id,
                my_peer_id=self.peer_id,
                my_listen_port=self.listen_port,
                chunk_count=self.manifest["chunk_count"],
                local_bitfield=self._local_bitfield(),
            )

        connections: list[PeerConnection] = []
        candidate_index = 0
        try:
            while candidate_index < len(candidates):
                current_inbound_count = (
                    self._server.active_connection_count if self._server is not None else 0
                )
                remaining_capacity = max(
                    0,
                    MAX_PEER_CONNECTIONS
                    - current_inbound_count
                    - self._outbound_connection_count
                    - len(connections),
                )
                if remaining_capacity == 0:
                    break

                batch = candidates[candidate_index : candidate_index + remaining_capacity]
                candidate_index += len(batch)
                if self._server is not None:
                    self._server.update_max_connections(
                        MAX_PEER_CONNECTIONS
                        - self._outbound_connection_count
                        - len(connections)
                        - len(batch)
                    )

                connection_tasks = [asyncio.create_task(connect(peer)) for peer in batch]
                try:
                    results = await asyncio.gather(*connection_tasks, return_exceptions=True)
                except asyncio.CancelledError:
                    for task in connection_tasks:
                        task.cancel()
                    results = await asyncio.gather(*connection_tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, PeerConnection):
                            await result.close()
                    raise

                for peer, result in zip(batch, results, strict=True):
                    if isinstance(result, BaseException):
                        if isinstance(result, asyncio.CancelledError):
                            raise result
                        if isinstance(result, Exception):
                            logger.warning(
                                "Unable to connect to peer %s: %s",
                                peer.peer_id,
                                result,
                            )
                            continue
                        raise result
                    connections.append(result)
        except asyncio.CancelledError:
            await asyncio.gather(*(connection.close() for connection in connections))
            if self._server is not None:
                self._server.update_max_connections(
                    MAX_PEER_CONNECTIONS - self._outbound_connection_count
                )
            raise

        self._outbound_connection_count = len(connections)
        if self._server is not None:
            self._server.update_max_connections(
                MAX_PEER_CONNECTIONS - self._outbound_connection_count
            )
        return connections

    async def download(self) -> Path:
        """Discover peers, download verified chunks, then announce completion."""
        if not self._started or self._closed:
            raise RuntimeError("peer must be started before downloading")
        if self.storage is None:
            raise RuntimeError("a seeder does not need to download its own file")
        if self._download_active:
            raise RuntimeError("this peer already has an active download")

        self._download_active = True
        try:
            response = await self._announce(AnnounceEvent.HEARTBEAT)
            self._remember_peers(response.peers)
            connections = await self._connect_to_peers(list(self._known_peers.values()))
            if not connections:
                raise NoAvailablePeersError("tracker returned no reachable peers")

            try:
                scheduler = DownloadScheduler(
                    self.manifest["chunk_count"], rng=random.Random(self._scheduler_seed)
                )
                downloader = SwarmDownloader(
                    connections,
                    scheduler,
                    self.storage,
                    on_chunk_verified=self._on_chunk_verified,
                    advertise_chunks=self._upload_enabled,
                )
                try:
                    await downloader.run()
                finally:
                    self.bytes_downloaded = downloader.bytes_downloaded
                    self.total_retries = downloader.total_retries
                    self.chunk_hash_failures = downloader.chunk_hash_failures
                    self.download_duration_seconds = downloader.duration_seconds
                    if self.download_duration_seconds > 0:
                        self.download_throughput_bytes_per_s = (
                            self.bytes_downloaded / self.download_duration_seconds
                        )
            finally:
                self._outbound_connection_count = 0
                if self._server is not None:
                    self._server.update_max_connections(MAX_PEER_CONNECTIONS)

            self._available_chunks.update(range(self.manifest["chunk_count"]))
            if self._server is not None:
                self._server.update_local_bitfield(self._local_bitfield())
            completed = await self._announce(AnnounceEvent.COMPLETED)
            self._remember_peers(completed.peers)
            return self.storage.target_path
        finally:
            self._download_active = False

    async def wait_until_stopped(self) -> None:
        """Keep serving as a seeder until the caller cancels or closes the peer."""
        await self._stopped_event.wait()

    async def close(self) -> None:
        """Stop serving, stop heartbeat, announce stopped, and release HTTP resources."""
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(
                self._close_resources(),
                name=f"close-{self.peer_id}",
            )
        await asyncio.shield(self._close_task)

    async def _close_resources(self) -> None:
        heartbeat = self._heartbeat_task
        self._heartbeat_task = None
        try:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            if self._server is not None:
                await self._server.stop()
                self._server = None
            if self._started:
                try:
                    async with asyncio.timeout(self._tracker_timeout):
                        await self._announce(AnnounceEvent.STOPPED)
                except (httpx.HTTPError, TimeoutError, ValueError) as exc:
                    logger.warning("Best-effort stopped announcement failed: %s", exc)
        finally:
            try:
                if self._server is not None:
                    await self._server.stop()
                    self._server = None
            finally:
                try:
                    await self._http.aclose()
                finally:
                    self._started = False
                    self._stopped_event.set()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
