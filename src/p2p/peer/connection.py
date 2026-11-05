"""Peer TCP connection management, state machine, and message exchange."""

from __future__ import annotations

import asyncio
import enum
import logging
from typing import Any, Final, Self

from p2p.config import (
    CONNECT_TIMEOUT_SEC,
    HANDSHAKE_TIMEOUT_SEC,
    IDLE_TIMEOUT_SEC,
    MAX_FRAME_SIZE,
    MAX_INFLIGHT_PER_PEER,
    PROTOCOL_VERSION,
    STALL_TIMEOUT_SEC,
)
from p2p.protocol import (
    Bitfield,
    ConnectionClosed,
    Handshake,
    Have,
    Message,
    Piece,
    ProtocolError,
    Request,
    read_message,
    write_message,
)

logger = logging.getLogger(__name__)


class ConnectionState(enum.Enum):
    """Lifecycle states for a peer TCP connection."""

    UNCONNECTED = "UNCONNECTED"
    AWAIT_HANDSHAKE = "AWAIT_HANDSHAKE"
    AWAIT_BITFIELD = "AWAIT_BITFIELD"
    STEADY_STATE = "STEADY_STATE"
    CLOSED = "CLOSED"


class PeerConnection:
    """Manages an individual peer TCP connection and its protocol state machine.

    Enforces the connection lifecycle:
    1. AWAIT_HANDSHAKE: Handshake exchange & validation (version, swarm ID, peer ID).
    2. AWAIT_BITFIELD: Initial bitfield exchange & validation.
    3. STEADY_STATE: Request/Piece data transfer, Have broadcasts, and state updates.
    4. CLOSED: Clean socket shutdown and resource cleanup.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader | None = None,
        writer: asyncio.StreamWriter | None = None,
        *,
        swarm_id: str,
        my_peer_id: str,
        my_listen_port: int,
        chunk_count: int,
        local_bitfield: Bitfield,
        handshake_timeout: float = HANDSHAKE_TIMEOUT_SEC,
        idle_timeout: float = IDLE_TIMEOUT_SEC,
        stall_timeout: float = STALL_TIMEOUT_SEC,
        max_inflight: int = MAX_INFLIGHT_PER_PEER,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._swarm_id: Final[str] = swarm_id
        self._my_peer_id: Final[str] = my_peer_id
        self._my_listen_port: Final[int] = my_listen_port
        self._chunk_count: Final[int] = chunk_count
        self._local_bitfield: Bitfield = local_bitfield

        self._handshake_timeout: Final[float] = handshake_timeout
        self._idle_timeout: Final[float] = idle_timeout
        self._stall_timeout: Final[float] = stall_timeout
        self._max_inflight: Final[int] = max_inflight

        self._state: ConnectionState = (
            ConnectionState.AWAIT_HANDSHAKE
            if (reader is not None and writer is not None)
            else ConnectionState.UNCONNECTED
        )

        self._remote_handshake: Handshake | None = None
        self._remote_peer_id: str | None = None
        self._remote_listen_port: int | None = None
        self._remote_bitfield: Bitfield | None = None

        self._pending_requests: set[int] = set()
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._is_closing: bool = False

    # --------------------------------------------------------------------------
    # Properties
    # --------------------------------------------------------------------------

    @property
    def state(self) -> ConnectionState:
        """Current lifecycle state of the connection."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """True if the connection has completed handshake and is in steady state."""
        return (
            self._state == ConnectionState.STEADY_STATE
            and self._writer is not None
            and not self._writer.is_closing()
        )

    @property
    def is_closed(self) -> bool:
        """True if the connection is closed."""
        return self._state == ConnectionState.CLOSED

    @property
    def remote_peer_id(self) -> str | None:
        """Peer ID of the remote peer once verified in handshake, or None."""
        return self._remote_peer_id

    @property
    def remote_listen_port(self) -> int | None:
        """Listening port of the remote peer once verified in handshake, or None."""
        return self._remote_listen_port

    @property
    def remote_handshake(self) -> Handshake | None:
        """Handshake payload received from the remote peer, or None."""
        return self._remote_handshake

    @property
    def remote_bitfield(self) -> Bitfield | None:
        """Bitfield of chunk availability for the remote peer, or None."""
        return self._remote_bitfield

    @property
    def my_peer_id(self) -> str:
        """Local peer identifier."""
        return self._my_peer_id

    @property
    def swarm_id(self) -> str:
        """Swarm identifier."""
        return self._swarm_id

    @property
    def chunk_count(self) -> int:
        """Total chunk count for this swarm."""
        return self._chunk_count

    @property
    def local_bitfield(self) -> Bitfield:
        """Local bitfield."""
        return self._local_bitfield

    @property
    def pending_requests(self) -> frozenset[int]:
        """Outstanding chunk request indices sent to this peer."""
        return frozenset(self._pending_requests)

    # --------------------------------------------------------------------------
    # Factory Methods
    # --------------------------------------------------------------------------

    @classmethod
    async def connect(
        cls,
        host: str,
        port: int,
        *,
        swarm_id: str,
        my_peer_id: str,
        my_listen_port: int,
        chunk_count: int,
        local_bitfield: Bitfield,
        connect_timeout: float = CONNECT_TIMEOUT_SEC,
        handshake_timeout: float = HANDSHAKE_TIMEOUT_SEC,
        idle_timeout: float = IDLE_TIMEOUT_SEC,
        stall_timeout: float = STALL_TIMEOUT_SEC,
        max_inflight: int = MAX_INFLIGHT_PER_PEER,
        auto_handshake: bool = True,
    ) -> Self:
        """Establish an outbound TCP connection to a peer and optionally perform handshake."""
        try:
            async with asyncio.timeout(connect_timeout):
                reader, writer = await asyncio.open_connection(host, port)
        except TimeoutError as exc:
            raise ConnectionError(
                f"Connection to {host}:{port} timed out after {connect_timeout}s"
            ) from exc
        except OSError as exc:
            raise ConnectionError(f"Failed to connect to {host}:{port}: {exc}") from exc

        conn = cls(
            reader=reader,
            writer=writer,
            swarm_id=swarm_id,
            my_peer_id=my_peer_id,
            my_listen_port=my_listen_port,
            chunk_count=chunk_count,
            local_bitfield=local_bitfield,
            handshake_timeout=handshake_timeout,
            idle_timeout=idle_timeout,
            stall_timeout=stall_timeout,
            max_inflight=max_inflight,
        )

        if auto_handshake:
            try:
                await conn.perform_handshake()
            except Exception:
                await conn.close()
                raise

        return conn

    @classmethod
    def accept(
        cls,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        swarm_id: str,
        my_peer_id: str,
        my_listen_port: int,
        chunk_count: int,
        local_bitfield: Bitfield,
        handshake_timeout: float = HANDSHAKE_TIMEOUT_SEC,
        idle_timeout: float = IDLE_TIMEOUT_SEC,
        stall_timeout: float = STALL_TIMEOUT_SEC,
        max_inflight: int = MAX_INFLIGHT_PER_PEER,
    ) -> Self:
        """Wrap an accepted inbound TCP connection ready for handshake."""
        return cls(
            reader=reader,
            writer=writer,
            swarm_id=swarm_id,
            my_peer_id=my_peer_id,
            my_listen_port=my_listen_port,
            chunk_count=chunk_count,
            local_bitfield=local_bitfield,
            handshake_timeout=handshake_timeout,
            idle_timeout=idle_timeout,
            stall_timeout=stall_timeout,
            max_inflight=max_inflight,
        )

    # --------------------------------------------------------------------------
    # Handshake State Machine
    # --------------------------------------------------------------------------

    async def perform_handshake(self) -> None:
        """Execute two-way handshake and bitfield exchange.

        Transitions:
        AWAIT_HANDSHAKE -> AWAIT_BITFIELD -> STEADY_STATE.

        Raises:
            ProtocolError: If peer violates protocol, mismatches version/swarm,
                is self-connection, or times out.
            ConnectionClosed: If peer disconnects during handshake.
        """
        if self._state != ConnectionState.AWAIT_HANDSHAKE:
            raise ProtocolError(f"Cannot perform handshake in state {self._state.value}")

        if self._reader is None or self._writer is None:
            raise ProtocolError("Cannot perform handshake on unestablished connection")

        try:
            async with asyncio.timeout(self._handshake_timeout):
                # 1. Send local Handshake
                local_hs = Handshake(
                    version=PROTOCOL_VERSION,
                    peer_id=self._my_peer_id,
                    swarm_id=self._swarm_id,
                    listen_port=self._my_listen_port,
                )
                await self._send_message(local_hs)

                # 2. Receive and validate remote Handshake
                remote_msg = await read_message(
                    self._reader,
                    max_body=MAX_FRAME_SIZE,
                    idle_timeout=self._handshake_timeout,
                    stall_timeout=self._stall_timeout,
                )
                if not isinstance(remote_msg, Handshake):
                    raise ProtocolError(
                        f"Expected HANDSHAKE message, received {type(remote_msg).__name__}"
                    )

                if remote_msg.version != PROTOCOL_VERSION:
                    raise ProtocolError(
                        f"Unsupported protocol version: {remote_msg.version} "
                        f"(expected {PROTOCOL_VERSION})"
                    )

                if remote_msg.swarm_id != self._swarm_id:
                    raise ProtocolError(
                        f"Swarm ID mismatch: expected {self._swarm_id}, got {remote_msg.swarm_id}"
                    )

                if remote_msg.peer_id == self._my_peer_id:
                    raise ProtocolError(
                        "Self-connection detected: remote peer_id matches local peer_id"
                    )

                self._remote_handshake = remote_msg
                self._remote_peer_id = remote_msg.peer_id
                self._remote_listen_port = remote_msg.listen_port
                self._state = ConnectionState.AWAIT_BITFIELD

                # 3. Send local Bitfield
                await self._send_message(self._local_bitfield)

                # 4. Receive and validate remote Bitfield
                remote_msg2 = await read_message(
                    self._reader,
                    max_body=MAX_FRAME_SIZE,
                    idle_timeout=self._handshake_timeout,
                    stall_timeout=self._stall_timeout,
                )
                if not isinstance(remote_msg2, Bitfield):
                    raise ProtocolError(
                        f"Expected BITFIELD message, received {type(remote_msg2).__name__}"
                    )

                remote_msg2.validate_for_swarm(self._chunk_count)
                self._remote_bitfield = remote_msg2
                self._state = ConnectionState.STEADY_STATE

        except TimeoutError as exc:
            await self.close()
            raise ProtocolError(
                f"Handshake exchange timed out after {self._handshake_timeout}s"
            ) from exc
        except (ProtocolError, ConnectionClosed):
            await self.close()
            raise
        except OSError as exc:
            await self.close()
            raise ConnectionClosed(f"Network error during handshake: {exc}") from exc
        except Exception:
            await self.close()
            raise

    # --------------------------------------------------------------------------
    # Steady State Messaging
    # --------------------------------------------------------------------------

    async def receive_message(self) -> Message:
        """Receive and process the next steady-state protocol message.

        Enforces steady-state rules:
        - Rejects unexpected HANDSHAKE or duplicate BITFIELD.
        - Validates chunk indices for REQUEST, PIECE, and HAVE.
        - Validates that received PIECE matches an outstanding request.
        - Automatically updates remote bitfield on received HAVE.

        Returns:
            The validated Message (Request, Piece, or Have).

        Raises:
            ProtocolError: On wire protocol violation or unexpected message.
            ConnectionClosed: If peer cleanly disconnects or socket breaks.
        """
        if self._state != ConnectionState.STEADY_STATE or self._reader is None:
            raise ProtocolError(f"Cannot receive message in state {self._state.value}")

        try:
            msg = await read_message(
                self._reader,
                max_body=MAX_FRAME_SIZE,
                idle_timeout=self._idle_timeout,
                stall_timeout=self._stall_timeout,
            )
        except ConnectionClosed:
            await self.close()
            raise
        except ProtocolError:
            await self.close()
            raise
        except TimeoutError as exc:
            await self.close()
            raise ProtocolError(f"Connection timed out waiting for message: {exc}") from exc
        except OSError as exc:
            await self.close()
            raise ConnectionClosed(f"Network error reading message: {exc}") from exc

        # Steady-state protocol validations
        if isinstance(msg, Handshake):
            await self.close()
            raise ProtocolError("Unexpected HANDSHAKE received in STEADY_STATE")

        if isinstance(msg, Bitfield):
            await self.close()
            raise ProtocolError("Duplicate BITFIELD received in STEADY_STATE")

        if isinstance(msg, Request):
            if msg.chunk_index >= self._chunk_count:
                await self.close()
                raise ProtocolError(
                    f"REQUEST chunk_index {msg.chunk_index} out of range "
                    f"(chunk_count={self._chunk_count})"
                )
            return msg

        if isinstance(msg, Piece):
            if msg.chunk_index >= self._chunk_count:
                await self.close()
                raise ProtocolError(
                    f"PIECE chunk_index {msg.chunk_index} out of range "
                    f"(chunk_count={self._chunk_count})"
                )
            if msg.chunk_index not in self._pending_requests:
                await self.close()
                raise ProtocolError(f"Received unsolicited PIECE for chunk_index {msg.chunk_index}")
            self._pending_requests.remove(msg.chunk_index)
            return msg

        if isinstance(msg, Have):
            if msg.chunk_index >= self._chunk_count:
                await self.close()
                raise ProtocolError(
                    f"HAVE chunk_index {msg.chunk_index} out of range "
                    f"(chunk_count={self._chunk_count})"
                )
            if self._remote_bitfield is not None:
                self._remote_bitfield = self._remote_bitfield.with_chunk(msg.chunk_index)
            return msg

        await self.close()
        raise ProtocolError(f"Unhandled message type in STEADY_STATE: {type(msg).__name__}")

    async def send_request(self, chunk_index: int) -> None:
        """Send a REQUEST message for a chunk index.

        Registers the chunk in pending_requests.

        Raises:
            ProtocolError: If state is not STEADY_STATE, chunk_index is invalid,
                already requested, or max in-flight limit is reached.
            ConnectionClosed: If the connection is closed.
        """
        if self._state != ConnectionState.STEADY_STATE:
            raise ProtocolError(f"Cannot send REQUEST in state {self._state.value}")
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ProtocolError(f"chunk_index must be int, got {type(chunk_index).__name__}")
        if chunk_index < 0 or chunk_index >= self._chunk_count:
            raise ProtocolError(
                f"REQUEST chunk_index {chunk_index} out of range (chunk_count={self._chunk_count})"
            )
        if chunk_index in self._pending_requests:
            raise ProtocolError(f"Chunk index {chunk_index} already has an outstanding request")
        if len(self._pending_requests) >= self._max_inflight:
            raise ProtocolError(
                f"Cannot send REQUEST: max in-flight requests ({self._max_inflight}) reached"
            )

        self._pending_requests.add(chunk_index)
        try:
            await self._send_message(Request(chunk_index=chunk_index))
        except Exception:
            self._pending_requests.discard(chunk_index)
            await self.close()
            raise

    async def send_piece(self, chunk_index: int, data: bytes) -> None:
        """Send a PIECE message delivering data for a chunk index.

        Raises:
            ProtocolError: If state is not STEADY_STATE or chunk_index is invalid.
            ConnectionClosed: If the connection is closed.
        """
        if self._state != ConnectionState.STEADY_STATE:
            raise ProtocolError(f"Cannot send PIECE in state {self._state.value}")
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ProtocolError(f"chunk_index must be int, got {type(chunk_index).__name__}")
        if chunk_index < 0 or chunk_index >= self._chunk_count:
            raise ProtocolError(
                f"PIECE chunk_index {chunk_index} out of range (chunk_count={self._chunk_count})"
            )
        try:
            await self._send_message(Piece(chunk_index=chunk_index, data=data))
        except Exception:
            await self.close()
            raise

    async def send_have(self, chunk_index: int) -> None:
        """Send a HAVE broadcast message announcing newly verified chunk availability.

        Raises:
            ProtocolError: If state is not STEADY_STATE or chunk_index is invalid.
            ConnectionClosed: If the connection is closed.
        """
        if self._state != ConnectionState.STEADY_STATE:
            raise ProtocolError(f"Cannot send HAVE in state {self._state.value}")
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ProtocolError(f"chunk_index must be int, got {type(chunk_index).__name__}")
        if chunk_index < 0 or chunk_index >= self._chunk_count:
            raise ProtocolError(
                f"HAVE chunk_index {chunk_index} out of range (chunk_count={self._chunk_count})"
            )
        try:
            await self._send_message(Have(chunk_index=chunk_index))
        except Exception:
            await self.close()
            raise

    def has_chunk(self, chunk_index: int) -> bool:
        """Check if remote peer has chunk_index according to remote bitfield."""
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ProtocolError(f"chunk_index must be int, got {type(chunk_index).__name__}")
        if chunk_index < 0 or chunk_index >= self._chunk_count:
            raise ProtocolError(
                f"chunk_index {chunk_index} out of range (chunk_count={self._chunk_count})"
            )
        if self._remote_bitfield is None:
            return False
        return self._remote_bitfield.has_chunk(chunk_index)

    def cancel_pending_request(self, chunk_index: int) -> bool:
        """Release a pending request reservation without network I/O.

        Returns True if the request was present and cancelled.
        """
        if chunk_index in self._pending_requests:
            self._pending_requests.remove(chunk_index)
            return True
        return False

    def update_local_bitfield(self, bitfield: Bitfield) -> None:
        """Update local bitfield representation."""
        bitfield.validate_for_swarm(self._chunk_count)
        self._local_bitfield = bitfield

    # --------------------------------------------------------------------------
    # Lifecycle & Cleanup
    # --------------------------------------------------------------------------

    async def close(self) -> None:
        """Close connection cleanly and release pending resources.

        Idempotent; safe to call multiple times.
        """
        if self._is_closing:
            return
        self._is_closing = True
        self._state = ConnectionState.CLOSED
        self._pending_requests.clear()

        writer = self._writer
        self._writer = None
        self._reader = None

        if writer is not None:
            try:
                if not writer.is_closing():
                    writer.close()
                await writer.wait_closed()
            except (OSError, ConnectionResetError, BrokenPipeError):
                pass
            except asyncio.CancelledError:
                # Always ensure cleanup completes on cancellation
                raise

    async def _send_message(self, msg: Message) -> None:
        """Serialize and send a message through the connection writer."""
        if self._writer is None or self._writer.is_closing():
            raise ConnectionClosed("Cannot send message: writer is closed")
        await write_message(self._writer, msg, lock=self._write_lock)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
