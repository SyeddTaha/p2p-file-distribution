# 0002. Wire Protocol Framing and Size Limits

- Status: Accepted
- Date: 2026-10-10

## Context
TCP provides an ordered byte stream without preserving message boundaries. One write call may arrive in multiple socket reads, or multiple message writes may arrive coalesced in a single read. We require a framing protocol that guarantees safe, non-blocking message parsing over TCP.

Furthermore, remote peer input is untrusted. Buffer allocation must be strictly bounded before reading frame bodies to prevent memory exhaustion attacks.

## Decision
1. **Framing Format:** Length-prefixed binary frames using a 4-byte big-endian unsigned integer (`uint32`) length prefix followed by a 1-byte message type identifier (`uint8`) and payload.
2. **Message Codes:** `0x01` HANDSHAKE, `0x02` BITFIELD, `0x03` REQUEST, `0x04` PIECE, `0x05` HAVE.
3. **Safety Bounds:**
   - Default chunk size: 256 KiB (`262,144` bytes).
   - Maximum allowed chunk size: 1 MiB (`1,048,576` bytes).
   - Maximum allowed frame body length: `1 + 4 + 1,048,576 = 1,048,581` bytes.
   - Handshake body maximum: `4,096` bytes.
4. **Validation Order:** The length prefix is read first via `StreamReader.readexactly(4)`. If `length > MAX_FRAME_SIZE` or `length < 1`, the connection is immediately closed without allocating or reading body bytes.

## Alternatives Considered
- **Delimiter-based framing (e.g. `\n` or `\0`):** Rejected because binary chunk payloads (`PIECE` messages) can contain arbitrary bytes matching delimiter characters.
- **Base64 Encoding Chunk Data:** Rejected due to ~33% bandwidth overhead and CPU overhead during chunk transfers.

## Consequences
- Requires strict integer packing/unpacking using standard `struct` module (`!I`).
- Framing codec can be thoroughly unit-tested using pure `bytes` without needing real network sockets.
