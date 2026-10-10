---
name: tcp-protocol-engineering
description: Design, implement, and review the application-layer wire protocol over TCP for the P2P system, covering message framing, the HANDSHAKE, BITFIELD, REQUEST, PIECE, and HAVE messages, serialization, partial reads/writes, size limits, validation of malformed input, timeouts, connection lifecycle, and protocol versioning. Use when touching code that reads or writes bytes on a peer socket or when editing docs/protocol.md. Not for tracker HTTP semantics, chunk scheduling, disk storage, or hashing policy.
---

# TCP Protocol Engineering

## When to use / when not to use

Use when you are:
- defining or changing message formats, type codes, or limits;
- writing or reviewing the encoder/decoder, `StreamReader`/`StreamWriter` handling, or the peer connection state machine;
- handling malformed, truncated, oversized, or out-of-order messages;
- bumping the protocol version.

Do **not** use for (see the owning skill instead):
- tracker registration, heartbeats, peer discovery, chunk scheduling, retries across peers -> `p2p-distributed-systems`
- manifest layout, hashing, disk writes, path safety -> `chunk-storage-integrity`
- test design and fault injection strategy -> `network-testing-reliability`
- structuring `docs/protocol.md` -> `engineering-documentation` (this skill supplies the technical content)

## Core principle

TCP delivers an ordered **byte stream**. It preserves no message boundaries. One `write` may arrive as many reads; many writes may arrive as one read. Therefore:
- Never assume one `recv()`/`read()` returns one complete message.
- Always use explicit framing and `StreamReader.readexactly(n)`.

## Reference wire format (v1)

Update `docs/protocol.md` whenever this changes. All integers are **big-endian** (network order).

Frame = `length` + `body`
- `length`: `uint32` = number of bytes in `body` (does not include the 4 length bytes themselves).
- `body`: `type` (`uint8`) followed by `payload` (type-specific bytes).
- A valid `length` is at least 1 (the type byte) and at most the per-type maximum below.

| Code | Type | Payload |
|---|---|---|
| 0x01 | HANDSHAKE | UTF-8 JSON object: `{"version": 1, "peer_id": "<string>", "swarm_id": "<64 hex>", "listen_port": <int>}` |
| 0x02 | BITFIELD | `ceil(chunk_count/8)` bytes; bit for chunk `i` is bit `7 - (i % 8)` of byte `i // 8`; spare trailing bits MUST be 0 |
| 0x03 | REQUEST | `uint32 chunk_index` |
| 0x04 | PIECE | `uint32 chunk_index` + raw chunk bytes (data length implied by frame length) |
| 0x05 | HAVE | `uint32 chunk_index` |

Rationale for the mix: JSON is used only for the one-time HANDSHAKE (easy to extend and debug); binary is used for hot-path messages to avoid encoding overhead for chunk data. Do not base64 chunk data.

Suggested limits (define as named constants in one config module):
- `MAX_HANDSHAKE_BODY = 4 KiB`
- `MAX_CHUNK_SIZE = 1 MiB` (the manifest's chunk size must be <= this)
- `MAX_PIECE_BODY = 1 + 4 + MAX_CHUNK_SIZE`
- REQUEST and HAVE bodies must be exactly 5 bytes (type + uint32).
- BITFIELD body length must equal `1 + ceil(chunk_count/8)` for the swarm's manifest.
- PIECE data length must equal the manifest length for that chunk index (validated with `chunk-storage-integrity`).

## Connection lifecycle

1. Connect (with timeout) -> both sides send HANDSHAKE first. Each side validates `version`, `swarm_id`, and `peer_id` (not self, not a duplicate connection).
2. After a valid handshake, each side sends one BITFIELD (may be all zeros).
3. Steady state: REQUEST -> PIECE; HAVE announcements when a newly verified chunk is stored.
4. Close: orderly (`close()` then `await wait_closed()`), or abort on protocol violation.

State rules (reject and close on violation): no non-HANDSHAKE message before HANDSHAKE; BITFIELD only once, directly after HANDSHAKE; PIECE only in answer to an outstanding REQUEST; chunk indices must be `< chunk_count`.

## Engineering workflow

1. **Pure codec first.** `encode_message(msg) -> bytes` and `decode_body(body: bytes) -> Message` as pure functions with no sockets. Unit-test exhaustively.
2. **Frame I/O layer.** `read_frame(reader, ...)` and `write_frame(writer, ...)` built on `readexactly` and `drain()`.
3. **Connection state machine.** Enforces the lifecycle rules above; kept separate from scheduling logic.
4. **Validation.** Reject, never "repair", bad input.
5. **Version handling.** Reject unsupported protocol versions in HANDSHAKE with a defined outcome before closing.
6. **Docs + tests** in the same change.

## Reference example: reading and writing a frame

```python
import asyncio
import struct

LENGTH = struct.Struct("!I")


class ProtocolError(Exception):
    """Peer violated the protocol; close the connection."""


class ConnectionClosed(Exception):
    """Peer closed cleanly between frames."""


async def read_frame(
    reader: asyncio.StreamReader, *, max_body: int, timeout: float
) -> bytes:
    try:
        async with asyncio.timeout(timeout):
            try:
                header = await reader.readexactly(LENGTH.size)
            except asyncio.IncompleteReadError as exc:
                if not exc.partial:
                    raise ConnectionClosed from exc  # clean EOF on a frame boundary
                raise ProtocolError("truncated length prefix") from exc
            (length,) = LENGTH.unpack(header)
            if length < 1 or length > max_body:  # check BEFORE reading the body
                raise ProtocolError(f"invalid frame length {length}")
            try:
                return await reader.readexactly(length)
            except asyncio.IncompleteReadError as exc:
                raise ProtocolError("truncated frame body") from exc
    except TimeoutError as exc:
        raise ProtocolError("read timeout") from exc


def encode_frame(msg_type: int, payload: bytes) -> bytes:
    return LENGTH.pack(1 + len(payload)) + bytes([msg_type]) + payload


async def write_frame(writer: asyncio.StreamWriter, frame: bytes) -> None:
    writer.write(frame)
    await writer.drain()  # applies backpressure and surfaces connection errors
```

Notes:
- `asyncio.timeout()` needs Python 3.11+ (fine for 3.12+).
- `StreamReader` has its own buffer limit for `readline`/`readuntil`, not for `readexactly`; the frame limit is what protects memory, so always check `length` first.
- Apply the per-type maximum after reading the type byte; `max_body` above is the outer safety bound.
- Decide in an ADR whether an idle connection waiting for the *next* frame uses a longer "idle timeout" than a mid-frame "stall timeout" (recommended: yes).

## Design constraints

- Concurrent writers on one connection must not interleave frames: serialize writes with a per-connection `asyncio.Lock`, or use a single writer task fed by a bounded queue.
- Keep chunks bounded (<= `MAX_CHUNK_SIZE`) so large PIECE writes do not starve control messages.
- Outbound queues are bounded; a peer that cannot keep up is disconnected, not buffered indefinitely.
- Timeouts exist for: connect, handshake, mid-frame stall, outstanding request. Values are named constants documented in `docs/protocol.md`.
- Decoders return typed messages or raise `ProtocolError`; they never leak bare `struct.error`/`IndexError`/`UnicodeDecodeError`/`JSONDecodeError`.
- No `pickle`, `eval`, or allocation driven by an unvalidated length field.

## Common failure modes (check each in review)

- Treating `reader.read(n)` as "exactly n bytes" (it returns *up to* n).
- Allocating or reading `length` bytes before checking it against a maximum.
- Forgetting `drain()`, or not handling `ConnectionResetError`/`BrokenPipeError`.
- Endianness mismatch (`<I` vs `!I`).
- Not distinguishing clean EOF from truncation.
- BITFIELD with wrong length or non-zero spare bits accepted silently.
- Accepting unsolicited PIECE messages (memory/disk abuse).
- Interleaved writes from multiple tasks.
- HANDSHAKE JSON that is not an object, has wrong field types, or missing fields.
- Closing without `wait_closed()`, leaking sockets in tests.

## Checklist

- [ ] Message table in `docs/protocol.md` matches the code exactly (codes, field order, limits).
- [ ] Every message type has an encode/decode round-trip test.
- [ ] Malformed cases tested: zero length, oversize length, truncated header/body, unknown type, wrong fixed length, bad JSON, bad BITFIELD length/spare bits, out-of-range chunk index.
- [ ] Split-delivery test: a frame delivered one byte at a time decodes correctly; two frames in one write decode as two messages.
- [ ] Every blocking network await has a timeout.
- [ ] Version mismatch produces a defined, tested outcome.

## Validation requirements

Coordinate with `network-testing-reliability` for test structure. Minimum for this skill: codec unit tests; split/merged delivery tests using a real loopback connection or a fed `StreamReader`; malformed-input tests that assert the connection is closed and resources are released.

## Expected deliverables and documentation updates

- Code: codec, frame I/O, connection state machine.
- Docs: `docs/protocol.md` (message table, state machine, limits, timeouts, error handling, version policy); an ADR for any change to framing or versioning; `docs/project-status.md` updated with the real state.
