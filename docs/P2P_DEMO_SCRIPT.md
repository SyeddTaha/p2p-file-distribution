# P2P complete live demonstration guide

Prepared 20 November 2026 against `121b31f82b094ef68b3f512c83f4e8c33a6b5548`, branch `feat/local-web-console`. This guide stands alone. Use the [handbook](P2P_COMPLETE_PROJECT_HANDBOOK.md) for explanations and [source map](P2P_SOURCE_CODE_MAP.md) for exact definitions.

This is a correctness/usability demonstration, not a performance measurement protocol. The recorded N=1,2,4,8 study is a separate experiment. Verification scope and unresolved browser timing issues are recorded at the end and in the [coverage checklist](P2P_HANDBOOK_COVERAGE_CHECKLIST.md).

## Contents

1. [Preparation](#preparation)
2. [Start four services](#start-four-services)
3. [Import, seed and download](#import-seed-and-download)
4. [Stop origin and prove redistribution](#stop-origin-and-prove-redistribution)
5. [Rate cap](#rate-cap)
6. [Baseline and P2P comparison](#baseline-and-p2p-comparison)
7. [Recorded experiments](#recorded-experiments)
8. [Presentation scripts](#presentation-scripts)
9. [Troubleshooting and cleanup](#troubleshooting-and-cleanup)
10. [Verification scope](#verification-scope)

## Preparation

Use the existing Python environment, browser and repository checkout. Run PowerShell commands from the repository root. No install is required by this guide; if the environment is absent, follow README setup separately. Reserve at least four terminals for foreground services and a preparation/verification prompt. Use one worker per console; do not add Uvicorn `--workers`.

| Service | HTTP port | Workspace | Browser address |
|---|---|---|---|
| Tracker | 8000 | In-memory membership only | `http://127.0.0.1:8000/health` |
| Console A | 8090 | `downloads/handbook-demo/A` | `http://127.0.0.1:8090` |
| Console B | 8081 | `downloads/handbook-demo/B` | `http://127.0.0.1:8081` |
| Console C | 8092 | `downloads/handbook-demo/C` | `http://127.0.0.1:8092` |

These console HTTP ports are not the file-chunk listening ports. Every Start peer creates a separate `SwarmPeer` with an OS-assigned TCP port, shown in Peer Network and tracker membership.

Read-only port check:

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in @(8000,8090,8081,8092) } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

If a port is occupied, identify whether it is your intended running instance. Do not kill an unknown process or overwrite its workspace. Stop your own old instance deliberately, reuse a known setup deliberately, or choose consistent alternate ports and tracker URLs. On the handbook preparation machine 8000, 8090 and 8081 were already occupied, so the new isolated rehearsal used free ports instead; this fixed-port launch sequence was not restarted over those services.

Prepare a deterministic nonempty 1 MiB source before occupying the service terminals:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import random; p=Path('downloads/handbook-demo/source'); p.mkdir(parents=True,exist_ok=True); f=p/'payload.bin'; f.open('xb').write(random.Random(42).randbytes(1048576))"
Get-FileHash -LiteralPath downloads/handbook-demo/source/payload.bin -Algorithm SHA256
```

Exclusive `xb` creation refuses to overwrite an existing payload. Keep/reuse that file knowingly, or choose a fresh source path. All generated data remains under ignored `downloads/`. Workspace paths must be distinct across processes. Downloads inside each console use their own UUID subdirectories; catalogs and history are in memory and disappear on restart even though files persist.

## Start four services

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m p2p.cli tracker-start --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe -m p2p.web --port 8090 --tracker-url http://127.0.0.1:8000 --workspace downloads/handbook-demo/A
```

Terminal 3:

```powershell
.\.venv\Scripts\python.exe -m p2p.web --port 8081 --tracker-url http://127.0.0.1:8000 --workspace downloads/handbook-demo/B
```

Terminal 4:

```powershell
.\.venv\Scripts\python.exe -m p2p.web --port 8092 --tracker-url http://127.0.0.1:8000 --workspace downloads/handbook-demo/C
```

Verification prompt:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8090/api/state | Select-Object tracker
```

Health must return `status=ok`, `service=tracker`. Open all three console URLs. The browser's console connection status and tracker status are separate; wait for current snapshots. Counts can initially be zero only when the tracker has no other participants. Do not assume a shared tracker belongs solely to this demo.

What to say: “These are independent local controllers with separate asset catalogs. They share one discovery service. Chunk traffic will go between their managed TCP peers.”

## Import, seed and download

### A: source import and manifest

1. Open A → **File Transfer**.
2. Choose `downloads/handbook-demo/source/payload.bin` in Source file.
3. Click **Import file and hash**; wait for imported feedback.
4. Inspect filename, 1 MiB size, four chunks, full swarm ID and expected SHA-256.
5. Click **Save manifest** and note the browser's actual saved path.

The source body is copied over local HTTP to A's UUID asset directory. `Console.import_asset` calls threaded `build_manifest` and `write_manifest`. This one UI action includes manifest generation; there is no separate Generate button. No peer is serving yet. Empty source, over-128-MiB source and unsafe names are rejected.

Say: “Chunk hashes let recipients verify and share a segment before the whole file arrives. The whole-file hash later checks reconstruction. The swarm ID hashes all validated manifest fields, including filename and chunk layout.”

### A: start the seed

1. Select the imported source under File manifest.
2. Set Operation to **Seed source file**.
3. In Advanced peer settings, set Upload limit to `262144` bytes/s.
4. Baseline is disabled for a seed; click **Start peer**.
5. Wait for **seeding**, final SHA-256 verified and a registered peer in Peer Network.

`Console._run` calls `SwarmPeer.start`. Startup rebuilds the source manifest, checks equality, binds an ephemeral TCP listener and announces started. It begins periodic heartbeats. A seed can show all bytes verified while downloaded payload is zero: it began with the file.

Say: “The tracker advertises this bound TCP endpoint. It does not store the file or transfer its chunks.”

### B: import metadata and download

1. Open B → File Transfer → Import a manifest.
2. Select A's saved manifest and click **Import manifest**.
3. Verify the swarm ID and expected SHA-256 equal A's.
4. Select the asset, keep Operation **Download**, baseline unchecked, cap blank.
5. Click **Start peer** and watch verified chunks/bytes.
6. Inspect Peer Network → local B peer → outbound connection and verified source bytes.
7. Wait for **completed** and final SHA-256 **verified**; leave the peer online.

Manifest-only assets cannot Seed source file. Metadata does not contain file bytes. Download startup refreshes tracker discovery, connects to A, exchanges HANDSHAKE/BITFIELD, reserves indices before requests, and checks each PIECE before writing it at its offset. The source's shared cap should make progress visible. Polling is once per second, so fast phases can be missed.

Say: “Progress counts exact lengths of accepted chunks. Full chunk progress is not the final-file verdict; that is shown separately.”

### Export and independently verify B

Click **Save verified file**. Save it to a path distinct from the source and other exports; the browser may rename duplicate downloads. Substitute its actual path below:

```powershell
$sourceHash = (Get-FileHash -LiteralPath downloads/handbook-demo/source/payload.bin -Algorithm SHA256).Hash
$exportedHash = (Get-FileHash -LiteralPath '<actual B export path>' -Algorithm SHA256).Hash
if ($sourceHash -ne $exportedHash) { throw 'B output hash differs from source' }
'B export SHA-256 matches source.'
```

The placeholder is intentional: browser download locations are user settings, not part of the backend. The export link appears only after the engine returns a verified output. HTTP export is a local artifact download after the P2P transfer.

## Stop origin and prove redistribution

1. In A's transfer card, click **Stop peer**; wait for stopped.
2. In Peer Network, confirm A's ID is absent from tracker membership.
3. Keep completed B online. Closing A's tab alone is insufficient.
4. In C, import the same saved manifest, choose Download with baseline unchecked and Start.
5. Wait for C completed/verified.
6. Inspect C's **Verified chunk sources**: B's peer ID must show positive bytes.
7. Inspect B's uploaded payload increase, then export/hash C independently.

If A and B were the only initial participants, B should be the sole remaining source before C starts. On an unshared healthy demo, C's source total from B should equal 1,048,576 bytes. If unrelated peers share the same swarm, inspect actual source contributions before making an exclusive-source claim.

Optional read-only tracker check with the displayed swarm ID:

```powershell
$demoSwarm = '<paste full 64-character lowercase swarm ID>'
$members = Invoke-RestMethod "http://127.0.0.1:8000/swarms/$demoSwarm/peers"
$members.peers | Select-Object peer_id,host,port,is_seeder
```

This proves completed-peer redistribution after origin shutdown. It does not prove the original may vanish before all necessary chunks exist elsewhere. C still relies on tracker discovery at startup.

Say: “B was originally a downloader. Its listener remained alive after verification, so C obtained real chunks from B after A left. Source-byte counters and final hashes establish this, not membership alone.”

## Rate cap

Preparation: stop B/C's uploading transfer records. Use one new A seed and one new B downloader for a visible single-source run.

1. In A, start a new seed of the same source with upload limit `65536` bytes/s.
2. In B, start a fresh normal Download using its imported manifest.
3. Observe progress/mean throughput, then final verification.
4. Stop both peers before changing scenario.

Default chunks are 262,144 bytes. The bucket initially contains 65,536 credits. First nominal admission wait is three seconds, later ones four seconds without idle credit. Four chunks require about fifteen seconds of admission time plus overhead. These are algorithm calculations, not a fresh benchmark claim. The per-request deadline is 15s, so one ordinary four-second request fits; several queued clients or much lower cap can exceed it.

Say: “The bucket is shared by all serving connections of one peer. Setting a cap on B controls B's uploads, not the rate at which A sends to B. The cap counts payload, and the initial burst can raise short-interval throughput.”

The UI applies caps only to new peers. Stop and create another peer to change it. There is no live settings API.

## Baseline and P2P comparison

### Origin-only baseline

Preparation is essential: stop every earlier upload-enabled client across B/C and any extra local transfers. Restart/keep exactly one uploading A origin with cap `262144` for visibility.

1. B: select manifest, Download, check **Download-only baseline**; Start.
2. C: same settings; Start while B is still active if demonstrating multiple clients.
3. Observe that cap input is disabled for baseline clients; the browser submits null.
4. Wait for both outputs verified.
5. Inspect both clients: upload capability disabled, uploaded payload zero, positive sources only from A.
6. Keep them online briefly to show completeness does not re-enable uploads; then Stop.

Internal enforcement: zero BITFIELD, suppressed HAVE from peer and coordinator, refusal of REQUEST without reading/sending a chunk, even after completion. Heartbeats/listeners/control traffic still exist. Tracker may call those complete clients seeders; that label is not an upload capability field.

Say: “Every client disables uploads while retaining the same framing, hashing, scheduler and storage. This isolates peer contribution. The flag does not forbid downloading from other uploaders, which is why we stopped earlier normal peers.”

### Normal P2P comparison

Use the same source/manifest/origin cap and create fresh B/C Download peers with baseline unchecked. Start overlapping downloads, inspect actual source bytes/uploads and verify outputs. A 1 MiB live run is small and normal consoles default to the same scheduler seed; clients may request similar chunks and provide little useful overlap. Do not promise a visible speedup or nonzero contribution in every short simultaneous run. The staged B→C relay is the reliable illustration of redistribution; the controlled benchmark uses per-client scheduler seeds and repeated trials.

Say: “P2P permits recipients to contribute; whether that reduces time depends on actual chunk availability, overlap and bottlenecks. Our recorded experiment is the evidence for performance under its controls.”

## Recorded experiments

Open Experiments → **Reload results**. It reads the committed `bench/results/experiments.csv`, not current demo traffic. Expect eight summaries, five measured trials per mode/N, 40 included trials and eight warmups. Explain the table and two charts: makespan/aggregate throughput means ± sample SD, plus peer share and exclusions.

| N | Baseline seconds, mean ± SD | P2P seconds, mean ± SD |
|---|---|---|
| 1 | 9.105 ± 0.074 | 9.073 ± 0.010 |
| 2 | 19.137 ± 0.124 | 11.329 ± 0.641 |
| 4 | 39.143 ± 0.022 | 15.414 ± 0.734 |
| 8 | 79.292 ± 0.070 | 23.518 ± 1.392 |

At N=8, ratio of means is 3.37×; P2P clients serve 77.81% mean payload. Recorded conditions are 10 MiB file, 256 KiB chunks, 1 MiB/s origin and 512 KiB/s client caps, one shared process/event loop/host, real loopback TCP and ASGI tracker. The live console demo uses independent processes and a smaller file; do not equate their durations.

Optional commands, using only existing tooling:

```powershell
# Regenerate recorded plots; does not collect new trials.
.\.venv\Scripts\python.exe -m bench.plot_results --experiment-id m8-loopback-20261120

# Optional tiny automation smoke; not a defensible performance study.
.\.venv\Scripts\python.exe -m bench.run_experiments --clients 1,2 --file-size 65536 --chunk-size 4096 --repetitions 1 --no-warmup --output downloads/handbook-demo/smoke.csv --experiment-id handbook-demo-smoke
.\.venv\Scripts\python.exe -m bench.plot_results --csv downloads/handbook-demo/smoke.csv --experiment-id handbook-demo-smoke --output-dir downloads/handbook-demo/smoke-plots
```

The runner appends; choose a fresh output/ID for a new rehearsal to avoid confusing repetitions. The optional smoke/full sweep were not run as new performance measurements for this handbook. Generated figures and derived summaries are ignored; raw recorded CSV remains unchanged.

Say: “A trial, not each client row, is our aggregation unit. SD measures variation, not a confidence interval. Shared-host loopback does not prove LAN or Internet performance, and no CPU/RAM or packet-capture evidence was collected.”

## Presentation scripts

### Three minutes

| Time | Action and words |
|---|---|
| 0:00–0:25 | “Tracker finds peers; TCP carries chunks; hashes gate acceptance.” Show prepared architecture/manifest. |
| 0:25–1:10 | A seed at 256 KiB/s; B imports same manifest and downloads; point out verified progress. |
| 1:10–1:35 | B complete/final hash verified; show independent exported hash. |
| 1:35–2:20 | Stop A, confirm absent; C downloads from completed B; show positive B source bytes. |
| 2:20–3:00 | Explain baseline toggle; show recorded N=8 result and loopback/no-resume/no-auth limitations. |

Have services/file/tabs ready before starting the clock. Include cleanup after the spoken portion.

### Five minutes

Use the three-minute sequence, then spend one minute distinguishing tracker membership, local connections and actual verified source bytes. Show baseline zero client uploads with one origin. Finish by explaining framing, reservation and sample SD. Prepare independent hash verification and the results tab in advance; do not count on observing every subsecond phase.

### Ten minutes

| Time | Action and explanation |
|---|---|
| 0–1 | Motivation, control/data planes and expected benefits |
| 1–3 | Import/source hashing, manifest exchange, seed/download, final hash/export |
| 3–4.5 | Stop A; prove completed B supplies C with actual payload |
| 4.5–6 | Shared upload cap and origin-only baseline; inspect zero uploads |
| 6–7 | Five messages, reservation, retry/failover tests |
| 7–9 | Recorded curves, raw-trial counts, means/SD, provenance and limits |
| 9–10 | Major limitations, stop peers, show deregistration, invite questions |

## Troubleshooting and cleanup

| Symptom | Check and response |
|---|---|
| Start disabled | Tracker health, selected asset, busy action and seed source eligibility; baseline seed is invalid |
| Manifest-only cannot seed | Correct: choose Download or import actual source into that console |
| No reachable peers | Start a source first, match canonical manifest, verify source online; start a new download after fixing discovery |
| New source joined but old transfer failed | No mid-download reconnect loop; a new transfer refreshes candidates |
| Tracker online but membership unavailable | `/health` may work while `/swarms` fails; inspect displayed error, do not assume zero |
| Dashboard seems one step behind | Poll is 1000ms, coalesced; wait for a fresh snapshot or use Refresh before comparing counters |
| Cap causes request failures | Compare chunk size/queue wait with 15s request timeout; raise cap, reduce clients or use smaller CLI-created chunks |
| Baseline client receives from old B | Stop old uploading peers; baseline disables local upload, not source selection |
| Complete remote peer sends no chunks | Completeness does not guarantee upload capability; actual bitfield/sources matter |
| All chunks but final hash failed | No verified output should be exported; show explicit error. Do not damage real files to stage faults. |
| Export has a different filename | Browser may append a duplicate suffix; hash the actual saved file |
| Experiment unavailable | Require source checkout with `bench/` and raw CSV; mixed/invalid data is rejected |
| Too many active/history entries | Completed serving peers count active; stop them. Restart clears catalog/history, not files; reimport metadata after restart |
| Closing tab leaves peer online | Use Stop peer or Ctrl+C console, because server task ownership is independent of the tab |

Stop each A/B/C peer; check the demo swarm no longer contains their IDs. Then Ctrl+C consoles, then tracker. With an isolated tracker, `/swarms` should be empty before stopping it. On shared services check only your demo peer IDs, never require unrelated memberships to disappear. Abrupt crashes can leave stale entries until >90s and a cleanup-triggering operation.

Automated viva fallback using unchanged tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_full_transfer.py tests/integration/test_downloader_loopback.py::test_swarm_downloader_retries_corrupt_peer_via_another_peer tests/integration/test_downloader_loopback.py::test_swarm_downloader_reassigns_chunk_after_peer_disconnect -v -o addopts='--strict-markers'
```

## Verification scope

Commands/flags were checked against CLI parsers and help. The current full pytest run passed 390 cases with one existing upstream warning. A fresh documentation-only API rehearsal uses one tracker and three independent consoles with temporary isolated workspaces: source/manifest import/export, capped transfer, B→C relay after A removal, two concurrent baseline clients, the 65,536 B/s setting, recorded experiment summaries and shutdown membership checks. Its final outcome is in the coverage checklist. It uses free ports because the requested fixed ports are partly occupied; it does not claim a new manual four-terminal fixed-port run.

The unchanged browser harness was also attempted twice. Each attempt passed its first four groups, then stopped at `tests/browser/console.mjs:270`: it expected rendered payload 2.00 MiB after API-observed completion while the DOM still held the prior 1.75 MiB poll. The harness waits for membership that is already present, not a new completed payload snapshot. This is a synchronization gap inferred from the assertion/DOM evidence; production and tests were left untouched. Later browser groups were not newly verified by those failed runs. Historical 13-group success remains historical evidence, not a current all-browser-pass claim.
