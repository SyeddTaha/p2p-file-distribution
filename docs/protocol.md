# Wire Protocol Specification (v1)

## 1. Overview & Framing

The P2P peer-to-peer data plane communicates directly over TCP streams.

Because TCP is a stream-oriented protocol without message boundaries, all wire communications use explicit **length-prefixed framing**:

```
+-------------------+------------------+------------------------------+
| Length (4 bytes)  | Msg Type (1 byte)| Payload (Type-Specific)      |
| uint32 (big-endian)| uint8            | (Length - 1) bytes           |
+-------------------+------------------+------------------------------+
```

- **Length Field:** 32-bit unsigned integer (`uint32`, big-endian network byte order) representing the size of the message body (`Msg Type` byte + `Payload` length). Does **not** include the 4 length bytes themselves.
- **Minimum Frame Length:** `1` byte (contains only `Msg Type`).
- **Maximum Frame Length:** `1 + 4 + MAX_CHUNK_SIZE` bytes (1,048,581 bytes for a 1 MiB chunk PIECE message).

---

## 2. Message Types & Formats

| Code | Type | Payload Format | Description |
|---|---|---|---|
| `0x01` | **HANDSHAKE** | UTF-8 JSON object string | Initial handshake exchanging `version`, `peer_id`, `swarm_id`, and `listen_port`. |
| `0x02` | **BITFIELD** | `ceil(chunk_count / 8)` bytes | Bitmask of chunk availability. Bit `i` is bit `7 - (i % 8)` of byte `i // 8`. Trailing spare bits MUST be `0`. |
| `0x03` | **REQUEST** | `uint32 chunk_index` (4 bytes) | Requests chunk by zero-based index. |
| `0x04` | **PIECE** | `uint32 chunk_index` (4 bytes) + raw chunk bytes | Delivers payload bytes for the specified chunk index. |
| `0x05` | **HAVE** | `uint32 chunk_index` (4 bytes) | Broadcasts that a newly verified chunk has been written to local storage. |

---

## 3. Detailed Payload Specifications

### 3.1 HANDSHAKE (`0x01`)
Sent immediately upon connection establishment before any other message.

```json
{
  "version": 1,
  "peer_id": "peer-abc123xyz",
  "swarm_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890",
  "listen_port": 6881
}
```

- `version`: Protocol version integer (`1`).
- `peer_id`: String identifier for the peer (1 to 64 chars).
- `swarm_id`: 64 lowercase hexadecimal SHA-256 string representing the target swarm.
- `listen_port`: Integer port (1..65535) where the sender accepts incoming peer connections.

### 3.2 BITFIELD (`0x02`)
Sent strictly once per connection, immediately following a successful `HANDSHAKE`.

- Length in bytes: `ceil(chunk_count / 8)`.
- Bit `1` indicates chunk present and verified; `0` indicates missing.
- Unused spare bits at the end of the final byte **must** be set to `0`. If any spare bit is `1`, the connection MUST be closed with a protocol error.

### 3.3 REQUEST (`0x03`)
- Payload: `uint32` (4 bytes big-endian) representing `chunk_index`.
- Payload size MUST be exactly 4 bytes (total frame body length = 5 bytes).

### 3.4 PIECE (`0x04`)
- Payload: `uint32` (4 bytes big-endian) `chunk_index` followed by raw binary chunk data bytes.
- Total frame body length: `1 + 4 + chunk_length`.
- Unsolicited `PIECE` messages (not matching an outstanding request) MUST be rejected and the connection closed.

### 3.5 HAVE (`0x05`)
- Payload: `uint32` (4 bytes big-endian) `chunk_index`.
- Total frame body length: 5 bytes.

---

## 4. Connection State Machine

```
   +-------------------+
   |   UNCONNECTED     |
   +---------+---------+
             | Connect / Accept
             v
   +-------------------+
   |  AWAIT_HANDSHAKE  |
   +---------+---------+
             | Send & Recv HANDSHAKE (Validate version, swarm_id, peer_id)
             v
   +-------------------+
   |   AWAIT_BITFIELD  |
   +---------+---------+
             | Send & Recv BITFIELD (Validate bitfield length and spare bits)
             v
   +-------------------+
   |   STEADY_STATE    | <---> [ Exchange REQUEST / PIECE / HAVE ]
   +---------+---------+
             | Protocol Violation / Disconnect / Shutdown
             v
   +-------------------+
   |      CLOSED       |
   +-------------------+
```

### State Rules & Violations
- Any message received before `HANDSHAKE` triggers immediate connection termination.
- `BITFIELD` is allowed **only** immediately following `HANDSHAKE`. A second `BITFIELD` triggers immediate close.
- Unrequested `PIECE` messages cause immediate disconnection.
- Out-of-range `chunk_index` (`>= chunk_count`) causes immediate disconnection.

---

## 5. Protocol Constants & Safety Limits

| Constant Name | Value | Purpose |
|---|---|---|
| `PROTOCOL_VERSION` | `1` | Supported protocol version |
| `MAX_HANDSHAKE_BODY` | `4,096` bytes (4 KiB) | Safety ceiling for handshake JSON payload |
| `MAX_CHUNK_SIZE` | `1,048,576` bytes (1 MiB) | Maximum allowed chunk payload size |
| `MAX_FRAME_SIZE` | `1,048,581` bytes | `1 + 4 + MAX_CHUNK_SIZE` |
| `CONNECT_TIMEOUT_SEC` | `10.0` seconds | Timeout for socket connection setup |
| `HANDSHAKE_TIMEOUT_SEC` | `5.0` seconds | Timeout for initial handshake exchange |
| `IDLE_TIMEOUT_SEC` | `60.0` seconds | Idle connection timeout between frames |
| `STALL_TIMEOUT_SEC` | `15.0` seconds | Read timeout during mid-frame payload receipt |
