"""Async TCP listener server for inbound peer connections."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Final, Self

from p2p.config import (
    HANDSHAKE_TIMEOUT_SEC,
    IDLE_TIMEOUT_SEC,
    MAX_INFLIGHT_PER_PEER,
    STALL_TIMEOUT_SEC,
)
from p2p.peer.connection import PeerConnection
from p2p.protocol import Bitfield, ConnectionClosed, ProtocolError

logger = logging.getLogger(__name__)

PeerConnectionHandler = Callable[[PeerConnection], Coroutine[Any, Any, None]]


class PeerServer:
    """Async TCP listener accepting incoming peer connections for a swarm."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        swarm_id: str,
        my_peer_id: str,
        chunk_count: int,
        local_bitfield: Bitfield,
        on_connection: PeerConnectionHandler | None = None,
        handshake_timeout: float = HANDSHAKE_TIMEOUT_SEC,
        idle_timeout: float = IDLE_TIMEOUT_SEC,
        stall_timeout: float = STALL_TIMEOUT_SEC,
        max_inflight: int = MAX_INFLIGHT_PER_PEER,
    ) -> None:
        self._host: Final[str] = host
        self._requested_port: Final[int] = port
        self._swarm_id: Final[str] = swarm_id
        self._my_peer_id: Final[str] = my_peer_id
        self._chunk_count: Final[int] = chunk_count
        self._local_bitfield: Bitfield = local_bitfield
        self._on_connection: Final[PeerConnectionHandler | None] = on_connection

        self._handshake_timeout: Final[float] = handshake_timeout
        self._idle_timeout: Final[float] = idle_timeout
        self._stall_timeout: Final[float] = stall_timeout
        self._max_inflight: Final[int] = max_inflight

        self._server: asyncio.Server | None = None
        self._listen_port: int | None = None
        self._active_connections: set[PeerConnection] = set()
        self._connection_tasks: set[asyncio.Task[None]] = set()
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        """True if the server is active and listening."""
        return self._is_running and self._server is not None and self._server.is_serving()

    @property
    def listen_port(self) -> int:
        """The actual bound port number."""
        if self._listen_port is None:
            raise RuntimeError("PeerServer is not running; port not yet bound")
        return self._listen_port

    @property
    def active_connections(self) -> frozenset[PeerConnection]:
        """Set of currently connected peers."""
        return frozenset(self._active_connections)

    @property
    def active_connection_count(self) -> int:
        """Count of currently active connections."""
        return len(self._active_connections)

    def update_local_bitfield(self, bitfield: Bitfield) -> None:
        """Update the bitfield advertised to future incoming connections."""
        bitfield.validate_for_swarm(self._chunk_count)
        self._local_bitfield = bitfield

    async def start(self) -> int:
        """Start the TCP listener server on host and port.

        Returns:
            The bound listen port.
        """
        if self._is_running:
            return self.listen_port

        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._requested_port,
        )

        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("Server started without any bound sockets")

        self._listen_port = sockets[0].getsockname()[1]
        self._is_running = True
        logger.info(
            "PeerServer started on %s:%d for swarm %s",
            self._host,
            self._listen_port,
            self._swarm_id[:8],
        )
        return self._listen_port

    async def stop(self) -> None:
        """Stop the listener server and close all active connections cleanly."""
        if not self._is_running and self._server is None:
            return

        self._is_running = False

        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

        # Cancel and wait for all connection handler tasks
        for task in list(self._connection_tasks):
            if not task.done():
                task.cancel()

        if self._connection_tasks:
            await asyncio.gather(*self._connection_tasks, return_exceptions=True)
            self._connection_tasks.clear()

        # Close all active PeerConnections
        for conn in list(self._active_connections):
            try:
                await conn.close()
            except Exception:
                pass
        self._active_connections.clear()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an accepted incoming TCP socket connection."""
        task = asyncio.current_task()
        if task is not None:
            self._connection_tasks.add(task)

        conn = PeerConnection.accept(
            reader=reader,
            writer=writer,
            swarm_id=self._swarm_id,
            my_peer_id=self._my_peer_id,
            my_listen_port=self.listen_port,
            chunk_count=self._chunk_count,
            local_bitfield=self._local_bitfield,
            handshake_timeout=self._handshake_timeout,
            idle_timeout=self._idle_timeout,
            stall_timeout=self._stall_timeout,
            max_inflight=self._max_inflight,
        )
        self._active_connections.add(conn)

        try:
            await conn.perform_handshake()
            if self._on_connection is not None:
                await self._on_connection(conn)
        except (ProtocolError, ConnectionClosed) as exc:
            logger.debug("Peer connection closed during handling: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Unexpected error handling peer connection: %s", exc)
        finally:
            self._active_connections.discard(conn)
            if task is not None:
                self._connection_tasks.discard(task)
            await conn.close()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.stop()
