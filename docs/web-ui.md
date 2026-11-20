# Local web console

The four sections operate the existing engine: Dashboard, File Transfer, Peer
Network and Experiments. See [ADR 0009](adr/0009-local-web-console.md) for the
frontend exception and [DESIGN.md](../DESIGN.md) for the shared design system.

## Start

From the repository root with the existing environment, in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m p2p.cli tracker-start --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m p2p.web
```

Open `http://127.0.0.1:8080`. The tracker must include `GET /swarms` for complete
membership reporting. Console options are `--port` (8080), `--tracker-url`
(`http://127.0.0.1:8000`), and `--workspace` (`downloads/web-console`). The UI and
managed TCP peers bind only to loopback. Use one server worker per console.

A second independent console can join the same tracker:

```powershell
.\.venv\Scripts\python.exe -m p2p.web --port 8081 --workspace downloads/web-console-2
```

## Demonstration

1. In File Transfer, select a nonempty source file and choose **Import file and
   hash**. This copies the source into the workspace and creates its normal v1
   manifest. Choose **Seed source file**, set an optional upload cap in bytes/s,
   start the peer and wait for `seeding`. Save the manifest.
2. In the second console, import that manifest and start a **Download** peer.
   Alternatively start additional download peers using the first console's
   manifest selection. Every peer has an independent destination.
3. Observe verified chunk/byte progress, retries, payload totals and final SHA-256.
   **Save verified file** exports a completed artifact; swarm distribution uses TCP.
4. Inspect Peer Network for addresses, membership, local connections, advertised
   chunk counts, outstanding requests and actual verified bytes from each serving
   peer. Stop the origin, then start a later P2P downloader to demonstrate relay
   from a completed download peer.
5. To compare baseline behavior, stop previous P2P downloaders, keep one origin
   seed and enable **Download-only baseline** on every new client. Those clients
   advertise no chunks and upload zero payloads, including after completion.
6. Stop individual peers or stop the console with Ctrl+C. Shutdown cancels and
   awaits transfers, connections, heartbeats and best-effort tracker removal.

Upload caps apply to new peers; stop/start to change one. The shared token bucket
has an initial one-second burst. Very low caps relative to chunk size can trigger
the engine's existing 15-second request timeout. UI bounds are separate from CLI
bounds; see [ADR 0009](adr/0009-local-web-console.md).

## What the measurements mean

The repository already implements the networking features below. The console is
an adapter over them, with only read-only instrumentation added where noted.

| Existing capability | Existing exposure / console adapter |
|---|---|
| Framed v1 TCP, handshake, BITFIELD, REQUEST, PIECE, HAVE; malformed input and timeouts | Existing codec/connections; copied connection states and availability |
| Bounded listener, concurrent workers, seeded chunk scheduling, reservation, retries, failover and HAVE updates | Existing `PeerServer`/`SwarmDownloader`; copied live counters and per-source payload totals |
| Tracker registration, discovery, heartbeat, completion, departure and lazy expiry | Existing `/announce`, `/health`, `/swarms/{id}/peers`; added read-only `GET /swarms` |
| Strict manifests, chunk SHA-256, safe paths, `.part`, final SHA-256 and atomic publication | Existing builders/loader/storage; added read-only final integrity state |
| Seed verification, downloads, completed-peer serving and cancellation cleanup | Existing `SwarmPeer`; console owns its lifecycle tasks |
| Shared token-bucket upload caps and download-only mode | Existing constructor options; applied at peer creation |
| Payload, retries, chunk failures, duration and mean throughput | Existing downloader metrics; console snapshots them during and after transfers |
| N=1,2,4,8 sweeps, paired modes/seeds, warmups, repeated trials, raw CSV, trial audit, means/SD and four Matplotlib plots | Existing harness; shared pure analysis feeds the UI table and two SVG graphs |

No CPU/RAM metrics, global traffic rates, remote connection telemetry, per-peer
timeout/disconnect counters, resume or mid-download rediscovery are available.

- Membership comes from the tracker; transfer statistics belong only to peers
  managed by this console. Local totals include stopped peers in this process's
  history, not global traffic. Unavailable membership is distinct from zero.
- Progress is the exact manifest length of chunks accepted by storage. All chunks
  verified does not imply final-file verification. Final SHA-256 is `pending`,
  `verified`, or `failed` based on engine observations.
- Download mean throughput uses downloader monotonic elapsed time including its
  finalization interval, excluding console setup. It is not an instantaneous rate.
- Per-source counters retain verified payload contributions after a download
  connection closes. A connection by itself is not evidence of payload traffic.
- Tracker `is_seeder` means complete, including baseline clients. Locally known
  upload-disabled peers are labeled; remote upload capability and remote
  connection status remain unknown. Download discovery occurs at startup; the
  engine does not reconnect to peers that join later.
- Polling runs once per second without overlapping state requests. Fast transfers
  may finish between snapshots. Disconnected console data is labeled stale.
- Experiments reads `bench/results/experiments.csv` through `bench/analysis.py`,
  shared with the plotting script. It displays N=1,2,4,8 means/sample SD, counts,
  warmups and exclusions. Missing/invalid data produces an unavailable state.
  Display requires a source checkout, but does not import Matplotlib or execute
  trials. These recorded loopback/ASGI results do not establish LAN/WAN performance.

## HTTP and storage boundaries

All requests are same-origin. Mutations require `X-P2P-UI: 1`; a supplied Origin
must match the console origin. Host is restricted to loopback names. There is no
remote authentication or CORS access. HTTP bodies are raw files or JSON, without
a multipart dependency.

| Method / path | Purpose |
|---|---|
| `GET /api/state` | Tracker health/membership, asset metadata, transfer snapshots |
| `POST /api/assets?name=...&manifest_only=false` | Bounded source import and manifest generation |
| `POST /api/assets?name=...&manifest_only=true` | Bounded manifest import via existing strict loader |
| `GET /api/assets/{id}/manifest` | Export validated manifest |
| `POST /api/transfers` | Start with `asset_id`, `kind` (`seed`/`download`), optional `upload_rate_limit` and `download_only` |
| `POST /api/transfers/{id}/stop` | Idempotently cancel and await one peer |
| `GET /api/transfers/{id}/file` | Export verified output; 409 until available |
| `GET /api/experiments` | Validated trial summaries and exclusion audit |

Files stay in UUID directories inside the configured workspace. The API accepts
base names and catalog IDs, not arbitrary paths. Manifest imports preserve
duplicate-key, size, schema and filename validation. Downloads start fresh;
resume and catalog restoration are unavailable. Bounds return 429 or 413;
bad settings return 422. Restarting clears history without deleting files.

## Verification scope

API tests exercise real TCP, partial progress, capped uploads, output SHA-256,
relay, baseline, hash failure, validation, cancellation and cleanup. A separate
process E2E test starts one tracker and two consoles on ephemeral loopback HTTP
ports, checks TCP transfer and verifies tracker removal after console shutdown.
These are correctness checks, not new benchmark performance measurements.

Browser interaction and responsive visual inspection could not run in the
implementation session: Computer Use's native pipe was unavailable. Manually
verify file selection, navigation, keyboard focus and mobile table scrolling.
