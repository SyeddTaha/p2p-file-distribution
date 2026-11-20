# P2P viva quick revision

Study date: 20 November 2026. Code: `121b31f82b094ef68b3f512c83f4e8c33a6b5548` on `feat/local-web-console`. This is an independent revision sheet for the implemented project. [Full handbook](P2P_COMPLETE_PROJECT_HANDBOOK.md) includes 100 answered viva questions; [demo script](P2P_DEMO_SCRIPT.md) and [source map](P2P_SOURCE_CODE_MAP.md) supply commands and definitions.

## Contents

1. [Speak the project](#speak-the-project)
2. [Transfer sequence](#transfer-sequence)
3. [Protocol and constants](#protocol-and-constants)
4. [Algorithms and formulas](#algorithms-and-formulas)
5. [UI facts](#ui-facts)
6. [Measured evidence](#measured-evidence)
7. [Likely questions](#likely-questions)
8. [Limitations and checklist](#limitations-and-checklist)

## Speak the project

“We built a tracker-assisted, single-file P2P distribution system. The FastAPI tracker supplies peer addresses; asyncio TCP peers carry chunks directly. A manifest defines expected lengths and SHA-256 hashes. The scheduler reserves missing chunks before network waits, storage accepts only verified bytes, and the final on-disk file is hashed before atomic publication. Downloaders can contribute verified chunks and keep serving after completion. A local web console operates this engine, and controlled experiments compare it with upload-disabled clients.”

The tracker is a directory, not a file server. A peer can be client and server simultaneously. Seeder means complete; leecher means still downloading. A completed baseline client can still be labeled a seeder even though it uploads nothing. This custom protocol is inspired by BitTorrent; it is not BitTorrent-compatible.

## Transfer sequence

```mermaid
flowchart LR
    S[Source] -->|chunk and whole hashes| M[Manifest]
    M -->|canonical JSON SHA-256| I[Swarm ID]
    I -->|announce and discover| T[Tracker]
    T -->|addresses| C[TCP handshake and bitfields]
    C -->|reserve then request| P[PIECE bytes]
    P -->|length and SHA-256 then offset write| V[Verified chunks]
    V -->|whole-file hash and os.replace| O[Published output]
    O -->|completed announce and listener stays alive| R[Serve later peers]
```

Arrows show successive dependencies. Tracker output is addresses, not bytes; the PIECE arrow is direct peer TCP. A manifest is delivered out of band. The chunk-to-output arrow requires a separate final check; completion keeps the listener serving until Stop/Ctrl+C.

Call chain to remember: browser → `Console.start/_run` → `SwarmPeer.start/download` → `_connect_to_peers` → `PeerConnection.connect/perform_handshake` → `SwarmDownloader.run` → `DownloadWorker.fetch_next` → `DownloadScheduler.reserve_next` → REQUEST/PIECE → `StorageManager.write_chunk` → `finalize` → completed announce.

## Protocol and constants

```text
4-byte uint32 big-endian body length | 1-byte type | payload
body length excludes the 4-byte prefix
```

| Code | Message | Payload |
|---|---|---|
| 1 | HANDSHAKE | Compact UTF-8 JSON: version, peer_id, swarm_id, listen_port |
| 2 | BITFIELD | ceil(K/8) bytes, high bit first, spare bits zero |
| 3 | REQUEST | uint32 chunk_index |
| 4 | PIECE | uint32 index + raw nonempty bytes |
| 5 | HAVE | uint32 index, after verified acceptance |

REQUEST index 2 is `00 00 00 05 03 00 00 00 02`. Three complete chunks advertise `e0`; baseline advertises `00`. Unsolicited pieces, wrong state/type, invalid ranges and malformed messages close the connection.

| Item | Value |
|---|---|
| Protocol version | 1 |
| Default/max chunk | 256 KiB / 1 MiB |
| Max frame body/whole frame | 1,048,581 / 1,048,585 bytes |
| Handshake JSON cap | 4,096 bytes |
| Manifest cap/chunk count | 4 MiB / 30,000 |
| Connect/application handshake | 10s / 5s |
| Frame prefix/body/request deadlines | 60s / 15s / 15s |
| Heartbeat/expiry | 30s / strictly more than 90s; lazy cleanup |
| Peer connections/global requests | 30 shared inbound/outbound / ceiling 32 |
| Worker requests per peer | One; connection ceiling four is not pipelining |
| Worker attempts/backoff | Three attempts; 0.05s then 0.10s nominal delay |
| Console source/download cap | 128 MiB |

TCP supplies ordered reliable bytes, retransmissions and flow/congestion control. The application supplies message framing, lifecycle rules, chunk retries and SHA-256 verification. TCP handshake is not application HANDSHAKE; chunk index is not a TCP sequence number. Write/close helpers do not all have individual deadlines: avoid claiming universal per-await bounds.

## Algorithms and formulas

**Scheduler:** seeded random among sorted indices that a peer advertises and that remain missing. Synchronously mark IN_FLIGHT before any await. Keep ownership through retries; release on exhausted peer retirement/cancellation. Only storage-accepted data becomes VERIFIED. This is not rarest-first or endgame duplication.

**Concurrency:** one reader per outbound socket dispatches through a queue of maximum 32 entries. One worker request per peer; different peers overlap in a TaskGroup batch. The next batch waits for all tasks in the current batch. Large file work is threaded, but bounded chunk verification/write remains synchronous on the loop.

**Storage:** validate safe name/manifest, start fresh `.part`, validate index/length/hash, write at offset, flush and mark accepted. After all chunks: fsync, whole-file SHA-256, `os.replace`. Whole-file mismatch preserves part and gives failed final integrity. Stop does not supply resume.

**Token bucket:** one shared locked budget per uploader, payload bytes only, rate R, default burst B=R bytes and initially full. For R=65,536 B/s and a 256 KiB chunk: first nominal wait 3s, subsequent wait 4s without retained credit. Multiple sockets share the same budget. Queuing can exceed the 15s request deadline.

```text
K = (F+C-1)//C             offset(i) = i*C
length(i) = min(C,F-i*C)   swarm_id = SHA256(canonical_validated_manifest)
frame_body = 1+payload    full_frame = 4+frame_body
client throughput = F/t  makespan = max(common-start client times)
aggregate throughput = N*F/makespan
peer share = leechers/(origin+leechers)
refill = min(B,tokens+elapsed*R)
wait = max(0,requested_bytes-tokens)/R
```

F=file bytes; C=chunk bytes; K=chunks; N=clients; t=seconds; R=bytes/s; B=burst bytes. Example `F=10,C=4`: lengths 4,4,2 and offsets 0,4,8. Selection may cost O(K log K) per reservation; state/availability can use O(K+PK) space for P peers.

Theory only, ignoring bursts/overhead: `D_CS >= max(NF/u_s,F/d_min)`; `D_P2P >= max(F/u_s,F/d_min,NF/(u_s+sum(u_i)))`. Upload rates u and download bottleneck d use bytes/s. These are lower bounds, not measured runtime formulas.

## UI facts

Dashboard polls `/api/state` every 1000ms without overlapping pending state requests. It distinguishes tracker-wide membership from local managed-peer payload. Local totals retain stopped peers in the current process. Console HTTP failure labels the last snapshot stale; unavailable membership is not zero.

Source import creates a manifest in the same operation. Import does not start a seed. A manifest-only asset cannot seed without source bytes; it can download. Upload cap/baseline apply at peer creation. Completed P2P downloads continue serving. Stop cancels/joins; closing a browser tab does not stop server peers. Save verified file appears after output is returned successfully; final hash is separate from full chunk progress.

Peer Network shows tracker membership, local connections/availability/pending requests and positive verified source bytes. Remote upload capability and connection telemetry are unknown. Experiments reads recorded CSV; it does not execute benchmarks. Console HTTP ports and ephemeral peer TCP ports serve different purposes.

## Measured evidence

Committed `bench/results/experiments.csv`, experiment `m8-loopback-20261120`: 10 MiB file, 256 KiB chunks, origin 1 MiB/s, uploading clients 512 KiB/s, N=1,2,4,8. Five measured trials and one logged warmup per mode/N. 48 trials, 180 client rows: 40 included trials/150 measured client rows and eight warmups/30 rows. No failed/incomplete exclusions; recorded retry/integrity counters zero.

| N | Baseline makespan mean ± SD (s) | P2P makespan mean ± SD (s) | Ratio of means |
|---|---|---|---|
| 1 | 9.105 ± 0.074 | 9.073 ± 0.010 | 1.00× |
| 2 | 19.137 ± 0.124 | 11.329 ± 0.641 | 1.69× |
| 4 | 39.143 ± 0.022 | 15.414 ± 0.734 | 2.54× |
| 8 | 79.292 ± 0.070 | 23.518 ± 1.392 | 3.37× |

At N=8, P2P mean origin payload is 17.75 MiB versus baseline 80 MiB; clients serve 77.81% mean payload. Aggregate mean throughput: 3.411 versus 1.009 MiB/s. Means of trial throughputs are not throughput calculated from mean duration. Run-wide upload totals repeat on client rows and must be counted once per run ID.

Error bars are sample SD, not confidence intervals. The benchmark used one shared process/host and ASGI tracker, while peer TCP was real loopback. CPU/RAM, LAN/WAN, physical link shaping and packet captures were not measured. The N=1 timings do not establish a P2P advantage. Current correctness verification: full pytest 390 passed with one upstream warning; final browser/rehearsal qualifications are in the [coverage checklist](P2P_HANDBOOK_COVERAGE_CHECKLIST.md).

## Likely questions

| Question | Speakable answer |
|---|---|
| Why not HTTP transfers? | HTTP could work, but custom TCP exposes framing/state engineering for the course. HTTP remains discovery and local control. |
| Why TCP over UDP? | It supplies ordered reliable delivery and transport control, leaving chunk semantics to our application. |
| Why framing if TCP is reliable? | Reliability preserves stream bytes, not application message boundaries. |
| Why tracker outside payload? | Discovery and data movement are separate responsibilities; tracker bandwidth need not carry every file copy. |
| Is it decentralized? | Payload is direct P2P; discovery is centralized. |
| Can partial downloaders upload? | Yes, only verified chunks, unless baseline disables all uploads. |
| Corrupt piece? | Reject before accepting, count integrity failure, retry then retire/fail over to a connected source. |
| Two workers same chunk? | Synchronous reservation makes the second see in-flight, not missing. |
| Seeder disconnect? | Connected alternatives may supply missing chunks; unavailable information makes completion impossible. |
| Tracker offline? | Existing connections may continue; new discovery or completion reporting may fail; heartbeats can re-register after restart. |
| Hash proves authenticity? | No. Expected metadata must itself be trusted or authenticated. |
| P2P always faster? | No; peers need useful upload capacity/diverse available chunks, and overhead can dominate. |
| Why final hash? | It checks actual reconstruction/on-disk bytes independently of individual accepted chunk state. |
| Resume? | Not implemented; fresh construction truncates part and no verified-state restore exists. |
| 10,000 peers? | Not validated; discovery/resource limits, state structures and independent-host load testing need redesign/evaluation. |
| Biggest limitation? | Central discovery plus no active-download reconnection for resilience; shared-process loopback for generalizing results. |

## Limitations and checklist

No dynamic connection to later peers, resume, signed manifests, peer TLS/auth, NAT traversal, DHT, rarest-first or pipelining. Some waits lack individual deadlines; chunk disk acceptance can block the loop. Tracker list cap is 50 returned peers, not population. A renamed file changes manifest identity. CLI can target reachable lab IPs; web-managed peers remain loopback.

- Tracker 8000; console A 8090, B 8081, C 8092, each with distinct workspace.
- Same exported manifest in B/C; nonempty source; sensible cap; no unknown process terminated for a port.
- B completed/verified and online before stopping A; C source counters prove B supplied real bytes.
- Independent exported-file hashes equal source; chunk progress and final integrity distinguished.
- All previous uploaders stopped before baseline; every current client download-only.
- Means/SD/trial counts/units explained; benchmark scope honest.
- Stop peers, verify demo membership removal, then close consoles/tracker.
