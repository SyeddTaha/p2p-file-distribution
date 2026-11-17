# Testing Strategy & Guide

## 1. Overview & Principles

Testing network applications requires strict isolation, determinism, and clean resource cleanup.

- **No External Network Dependencies:** All network tests bind exclusively to loopback (`127.0.0.1`) on ephemeral port `0`.
- **Deterministic Experiments:** Random number generators are explicitly seeded. Time-dependent logic (stale peer expiry, heartbeats) uses an **injectable clock interface** rather than real-world wall clock sleeps.
- **Isolated Filesystem Work:** All file writes occur within pytest `tmp_path` temporary directories.
- **Strict Cleanup:** Every async test must close sockets, stop server instances, and await background tasks before finishing.

---

## 2. Test Pyramid & Conventions

```
                  / \
                 /   \
                / E2E \       <-- Full Tracker + Multi-Peer Loopback Swarms (Milestone 7)
               /-------\
              / Integr. \     <-- Socket Handshake, Bitfield Exchange, Tracker Endpoints
             /-----------\
            /  Unit Tests \   <-- Codec, Manifest Validation, Scheduler, Path Safety
           /---------------\
```

### Async Test Framework
- Test runner: `pytest` with `pytest-asyncio`.
- Configuration in `pyproject.toml`: `asyncio_mode = "auto"`.

---

## 3. Scenario Matrix

| Area | Component / Feature | Test Scenarios |
|---|---|---|
| **Protocol Codec** | Message Encoding / Decoding | Round-trip serialization for Handshake, Bitfield, Request, Piece, Have. |
| **Protocol Framing** | Stream Boundaries & Safety | Split frame delivery, merged frames in single read, oversized length prefix protection, truncated header/body. |
| **Manifest & Storage** | JSON Manifest Parsing | Build/load/write manifests and canonical Swarm ID; reject malformed fields/JSON, duplicate keys, empty files, invalid chunk counts/sizes, and invalid SHA-256 digests. |
| **Manifest & Storage** | Path Safety | `validate_safe_filename()` blocks traversal, absolute/drive paths, separators, NUL, overlong names, Windows reserved names, trailing dot/space, and symbolic-link destinations. |
| **Storage & Integrity** | Chunk Writing & Verification | Verify index/length/hash before write; ignore verified duplicates; cover one-byte, single-chunk, exact-multiple, and remainder sizes; reject incomplete/corrupted files; preserve `.part` on whole-file mismatch; atomically finalize valid files. |
| **Tracker Service** | Peer Announcements | `POST /announce` schema and event validation, unknown-field rejection, idempotency, peer exclusion, and the 50-peer response cap. |
| **Tracker Service** | Peer Names & Hosts | RFC 1123 label/hostname length edges, optional trailing dot, IPv4/IPv6, and invalid hostname syntax. |
| **Tracker Service** | Stale Peer Expiry | Fake-clock boundary at exactly 90 seconds and just beyond; eviction during announce/listing and empty-swarm cleanup. |
| **Tracker Service** | HTTP Peer Listing | `GET /swarms/{swarm_id}/peers` response fields, malformed ID rejection, unknown valid swarm response, and registry dependency isolation. |
| **Peer Connection** | TCP Handshake Engine | Valid handshake exchange, version/swarm rejection, malformed and unsolicited messages, IPv6 loopback when available, inbound cap, simultaneous connection pressure, capacity release, failed-handshake cleanup, and socket cleanup when cancelled during handshake. |
| **Download Scheduler** | Chunk Reservation | `IN_FLIGHT` reservation prevention of duplicate requests across tasks, peer failure release of chunks. |
| **Download Worker** | Async Fetch / Retry Flow | Unit tests cover storage-verified chunks, retries, retained reservations during retries, retry exhaustion, HAVE updates while awaiting PIECE, unexpected REQUEST, cancellation, and completion tracking. |
| **Swarm Downloader** | Multi-Peer Orchestration | Loopback tests cover concurrent peer requests, storage finalization, HAVE broadcasts, corrupt-peer and disconnect failover, no available chunks, and cancellation cleanup. |
| **SwarmPeer** | Tracker Lifecycle & Serving | Seeder file/manifest match, startup rollback when server shutdown fails, verified-only chunk serving, started/heartbeat/completed/stopped announcements, empty and partially unavailable discovery, later-candidate fallback, duplicate filtering, shared connection capacity, discovery cancellation cleanup, concurrent-close cleanup, and heartbeat cancellation. |
| **PeerServer** | Listener Shutdown | Active loopback connections and handler tasks are closed and awaited during shutdown. |
| **CLI** | Four Command Entry Point | Parser and dispatch for tracker-start, create-manifest, seed-file, and download-file; expected no-peer download failures exit nonzero with a useful message and no traceback; project script resolves to `p2p.cli:main`. |
| **End-to-End (Milestone 7)** | Tracker-Driven File Transfer | In-process FastAPI tracker, real loopback TCP, one seeder and three concurrent leechers; byte equality, whole-file SHA-256, HAVE exchange, tracker lifecycle, and cleanup. A staged relay test proves a completed leecher serves nonzero PIECE payload bytes to a later leecher after the original seeder is removed. |

---

## 4. Running the Tests

Execute the following commands from the repository root:

```bash
# Run full test suite
pytest

# Run with verbose output
pytest -v

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage report
pytest --cov=src/p2p

# Measure downloader module coverage across unit and loopback tests
pytest tests/unit/test_scheduler.py tests/integration/test_downloader_loopback.py --cov=p2p.peer.downloader --cov-report=term-missing -ra
```

### Milestone 6 verification

On 2026-11-09 the focused command above passed 20 tests and measured 90%
statement coverage for `src/p2p/peer/downloader.py`. Its unexecuted statements
are defensive validation branches and exceptional fallback paths; the
milestone's functional flows are additionally exercised over loopback. Full
tracker-driven E2E/CLI coverage belongs to Milestone 7.

The loopback downloader integration tests were run five consecutive times on
2026-11-09, with all five tests passing in every run. To repeat that stability
check in PowerShell:

```powershell
for ($i = 1; $i -le 5; $i++) {
    .\.venv\Scripts\python.exe -m pytest tests\integration\test_downloader_loopback.py -q
    if ($LASTEXITCODE -ne 0) { throw "Loopback test run $i failed" }
}
```

### Milestone 7 verification

Run the CLI, peer lifecycle, peer server, existing downloader, and E2E tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_cli.py tests\unit\test_peer_connection.py tests\unit\test_swarm_peer.py tests\integration\test_peer_loopback.py tests\integration\test_downloader_loopback.py tests\unit\test_scheduler.py tests\e2e\test_full_transfer.py -q
```

Run only the full swarm end-to-end transfer:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_full_transfer.py -q
```

The E2E tests use FastAPI `ASGITransport` for the tracker, ephemeral loopback
TCP ports for real peers, and a temporary directory for all files. The tracker
is in-process; these tests do not spawn separate OS processes. The final
interactive Windows smoke test below separately verified process startup,
transfer integrity, Ctrl+C shutdown, tracker deregistration, and process cleanup.
Tests for the no-available-chunks failure configure
`availability_timeout=0.01` so they exercise the bounded timeout without
waiting for the production default of 15 seconds.

### Milestone 7 interactive Windows smoke test

This manual test uses three PowerShell terminals for the tracker, seeder, and
leecher, plus a fourth PowerShell prompt for verification. Run from the
repository root. It creates a deterministic 1 MiB payload, seeds it, downloads
it into a separate directory, compares bytes and SHA-256, then checks shutdown
and tracker state. The recorded run on 2026-11-17 used swarm ID
`ef3fbb61b390ba263b2503a97cb07209033d88f6b2df69f94af3ec3ca3135385`.

In Terminal 1, create the payload and manifest, then start the tracker. Use
fresh paths; the guard below refuses to overwrite an existing payload.

```powershell
$testFile = ".\m7-smoke-payload.bin"
if (Test-Path -LiteralPath $testFile) {
    throw "Test file already exists. Refusing to overwrite it."
}
if (Test-Path -LiteralPath ".\m7-smoke-payload.manifest.json") {
    throw "Manifest already exists. Refusing to overwrite it."
}

$bytes = New-Object byte[] (1MB)
for ($i = 0; $i -lt $bytes.Length; $i++) {
    $bytes[$i] = [byte](($i * 31 + 17) % 256)
}

[System.IO.File]::WriteAllBytes(
    (Join-Path (Get-Location) "m7-smoke-payload.bin"),
    $bytes
)

.\.venv\Scripts\python.exe -m p2p.cli create-manifest .\m7-smoke-payload.bin --chunk-size 262144 --output .\m7-smoke-payload.manifest.json
.\.venv\Scripts\python.exe -m p2p.cli tracker-start --host 127.0.0.1 --port 8000
```

In Terminal 2, start the seeder:

```powershell
.\.venv\Scripts\python.exe -m p2p.cli seed-file .\m7-smoke-payload.manifest.json .\m7-smoke-payload.bin --tracker-url http://127.0.0.1:8000
```

In Terminal 3, use a new download directory and start the leecher:

```powershell
$downloadDir = ".\m7-smoke-downloads-20261117-1333"
if (Test-Path -LiteralPath $downloadDir) {
    throw "Download directory already exists. Choose a fresh name."
}

.\.venv\Scripts\python.exe -m p2p.cli download-file .\m7-smoke-payload.manifest.json --download-dir $downloadDir --tracker-url http://127.0.0.1:8000
```

If you choose another download directory name, use that same path in the
verification command below.

Wait for `Downloaded and verified` and `Continuing to seed`. While the leecher
is still running, compare the original and downloaded bytes and hashes from
Terminal 4 in the repository root:

```powershell
$src = Join-Path (Get-Location) "m7-smoke-payload.bin"
$dst = Join-Path (Get-Location) "m7-smoke-downloads-20261117-1333\m7-smoke-payload.bin"
$a = [System.IO.File]::ReadAllBytes($src)
$b = [System.IO.File]::ReadAllBytes($dst)

$bytesMatch = $a.Length -eq $b.Length
if ($bytesMatch) {
    for ($i = 0; $i -lt $a.Length; $i++) {
        if ($a[$i] -ne $b[$i]) {
            $bytesMatch = $false
            break
        }
    }
}

$sourceHash = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
$downloadHash = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
"Original bytes:   $($a.Length)"
"Downloaded bytes: $($b.Length)"
"Original SHA256:   $sourceHash"
"Downloaded SHA256: $downloadHash"
"Byte-for-byte match: $bytesMatch"

if (-not $bytesMatch -or $sourceHash -ne $downloadHash) {
    throw "Smoke-test file verification failed."
}
```

After verification, press Ctrl+C in Terminal 2 and Terminal 3, and wait for
both commands to return to their PowerShell prompts. While Terminal 1 is still
running, confirm the peer list is empty:

```powershell
$swarmId = "ef3fbb61b390ba263b2503a97cb07209033d88f6b2df69f94af3ec3ca3135385"
$state = Invoke-RestMethod -Uri "http://127.0.0.1:8000/swarms/$swarmId/peers"
$state | ConvertTo-Json -Depth 5
if (@($state.peers).Count -ne 0) {
    throw "Tracker still reports peers in this swarm."
}
```

Then press Ctrl+C in Terminal 1. Check that no Python process matching the
smoke-test commands remains:

```powershell
$leftovers = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @("python.exe", "pythonw.exe") -and
    $_.CommandLine -match "m7-smoke-payload|p2p\.cli tracker-start --host 127\.0\.0\.1 --port 8000"
}
if ($leftovers) {
    $leftovers | Select-Object ProcessId, Name, CommandLine
    throw "Smoke-test Python processes are still running."
}
"No smoke-test Python processes remain."
```

**Recorded result (2026-11-17):** 1,048,576 bytes downloaded; byte-for-byte
comparison passed; source and destination SHA-256 both equaled
`042D84D3772B8CC9080A8F388C428C11D88F8566E5A38FDA322FC8EA33492CFC`.
Seeder, leecher, and tracker returned cleanly after Ctrl+C; the tracker
returned an empty peer list; the process check found no leftover smoke-test
Python processes. The generated payload, manifest, and download directory are
test artifacts and should not be committed.
