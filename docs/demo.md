# Course demonstration runbook

Target: an 8-10 minute presentation using the measured report and a short live
transfer. Run from the repository root on Windows PowerShell with the existing
`.venv`. No new package installation is required. The manual CLI sequence below
is prepared for presentation; it was not newly rehearsed end-to-end in four
interactive terminals during report preparation. Its underlying CLI and relay
behavior have automated coverage and the earlier Windows smoke in `testing.md`.
The five-test fallback, input/manifest preparation, tiny benchmark sweep and
plot regeneration were rehearsed successfully today.

## Presentation sequence

| Time | Show | Say / establish |
|---|---|---|
| 0:00-1:00 | Report overview and design | The tracker discovers peers; TCP peers carry chunks; SHA-256 gates acceptance. |
| 1:00-4:00 | First client completes; stop origin; second client downloads | A completed leecher can become the only source for another client. |
| 4:00-5:00 | Compare hashes and tracker entries | Completion means a verified file; graceful shutdown deregisters peers. |
| 5:00-6:00 | Selected automated cases | Baseline isolation, corrupt-peer retry and disconnect recovery have assertions. |
| 6:00-9:00 | Four measured plots and table | Five repetitions, error bars, upload caps and raw data support the comparison. |
| 9:00-10:00 | Limitations and conclusion | Shared-process loopback results are not real-network evidence. |

## Before presenting

Keep four terminals open at the repository root. Terminal 1 runs the tracker,
Terminal 2 the origin, Terminal 3 the first client, and Terminal 4 verification
and then the second client. Reserve loopback ports 8000, 9101, 9102 and 9103 for
this demo; if one is occupied, change its value consistently in the commands.
The live demo uses actual CLI OS processes and a real tracker HTTP socket.
The measured benchmark instead used a shared process and ASGI tracker transport.

Regenerate figures from committed data and open the report before the session:

```powershell
.\.venv\Scripts\python.exe -m bench.plot_results --experiment-id m8-loopback-20261120
.\.venv\Scripts\python.exe docs/build_course_report.py --pdf
Start-Process .\output\pdf\course-report.pdf
```

The PDF export uses an already installed Chrome; `--browser` can specify its
executable. The self-contained HTML is also available as
`output/course-report.html`. Neither command recollects the 20-minute sweep.

## Live transfer and origin-independent relay

### Prepare the small source and manifest (Terminal 4)

Generated demo files stay under the ignored `downloads/` directory. The source
is a deterministic 1 MiB file with 64 KiB chunks. The 256 KiB/s upload cap is
for visibility during the demonstration, not the report's experiment controls.

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import random; p=Path('downloads/course-demo/source'); p.mkdir(parents=True, exist_ok=True); (p/'payload.bin').write_bytes(random.Random(42).randbytes(1048576))"
.\.venv\Scripts\python.exe -m p2p.cli create-manifest downloads/course-demo/source/payload.bin --chunk-size 65536 --output downloads/course-demo/payload.manifest.json
```

### Start the tracker (Terminal 1)

```powershell
.\.venv\Scripts\python.exe -m p2p.cli tracker-start --host 127.0.0.1 --port 8000
```

Wait for the server startup message. From Terminal 4, check health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected fields: `status = ok`, `service = tracker`.

### Start the origin (Terminal 2)

```powershell
.\.venv\Scripts\python.exe -m p2p.cli seed-file downloads/course-demo/payload.manifest.json downloads/course-demo/source/payload.bin --tracker-url http://127.0.0.1:8000 --listen-port 9101 --upload-rate-limit 262144
```

Wait for the seeding message. Explain that the source is checked against its
manifest before it is offered to the swarm.

### Download and keep the first client online (Terminal 3)

```powershell
.\.venv\Scripts\python.exe -m p2p.cli download-file downloads/course-demo/payload.manifest.json --download-dir downloads/course-demo/first --tracker-url http://127.0.0.1:8000 --listen-port 9102 --upload-rate-limit 262144
```

Wait for `Downloaded and verified:` and leave this process running. Its
continuing listener is essential for the relay demonstration.

### Stop the origin and prove only the first client remains

Press Ctrl+C in Terminal 2 and wait for its prompt. In Terminal 4:

```powershell
$swarmId = .\.venv\Scripts\python.exe -c "from pathlib import Path; from p2p.storage.manifest import load_manifest, compute_swarm_id; print(compute_swarm_id(load_manifest(Path('downloads/course-demo/payload.manifest.json'))))"
$state = Invoke-RestMethod "http://127.0.0.1:8000/swarms/$swarmId/peers"
$state.peers | Select-Object peer_id, port, is_seeder
if (@($state.peers).Count -ne 1 -or $state.peers[0].port -ne 9102) {
    throw "Expected only the completed first client on port 9102."
}
```

Expected: exactly one peer on port 9102 with `is_seeder = True`. This establishes
that the original seed is absent before the second download begins.

### Download from the completed peer (Terminal 4)

```powershell
.\.venv\Scripts\python.exe -m p2p.cli download-file downloads/course-demo/payload.manifest.json --download-dir downloads/course-demo/second --tracker-url http://127.0.0.1:8000 --listen-port 9103
```

Wait for `Downloaded and verified:`. The tracker had no original seed to return;
the completed first client supplied the second file. This is a transfer demo,
not a measurement of swarm performance under mid-download origin failure.
The staged automated test additionally asserts nonzero PIECE bytes from the
completed leecher and verifies the reconstructed output.

### Verify all hashes and shut down cleanly

Press Ctrl+C in Terminal 4 after verification completes, then run:

```powershell
$paths = @(
    'downloads/course-demo/source/payload.bin',
    'downloads/course-demo/first/payload.bin',
    'downloads/course-demo/second/payload.bin'
)
$hashes = $paths | ForEach-Object { Get-FileHash -LiteralPath $_ -Algorithm SHA256 }
$hashes | Format-Table Hash, Path
if (@($hashes.Hash | Select-Object -Unique).Count -ne 1) {
    throw 'Source and downloaded hashes differ.'
}
```

Press Ctrl+C in Terminal 3, wait for its prompt, then check from Terminal 4:

```powershell
$state = Invoke-RestMethod "http://127.0.0.1:8000/swarms/$swarmId/peers"
if (@($state.peers).Count -ne 0) { throw 'Demo peers remain registered.' }
'All demo peers deregistered.'
```

Finally press Ctrl+C in Terminal 1. All four terminals should be at their
prompts. Demo files can remain in the ignored download directory for inspection;
no cleanup command deletes unrelated files. For a baseline demonstration on a
fresh run, keep the origin online and add `--no-upload` to every client. A
download-only client cannot act as the relay after the origin stops.

## Automated fallback and fault evidence (rehearsed)

If interactive setup consumes presentation time, run this exact short command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_full_transfer.py tests/integration/test_downloader_loopback.py::test_swarm_downloader_retries_corrupt_peer_via_another_peer tests/integration/test_downloader_loopback.py::test_swarm_downloader_reassigns_chunk_after_peer_disconnect -v -o addopts='--strict-markers'
```

Rehearsal result on 2026-11-20: **5 passed in 1.93s**. The output names these
cases: three concurrent P2P clients, three baseline clients, completed-leecher
relay after origin shutdown, corrupt-peer retry and disconnect reassignment.
Tests use real TCP, temporary files and an in-process ASGI tracker. Their pass
output is correctness evidence; their runtime is not benchmark evidence.

For a fresh, tiny benchmark plumbing demonstration, write to a separate file:

```powershell
.\.venv\Scripts\python.exe -m bench.run_experiments --clients 1,2 --file-size 65536 --chunk-size 4096 --repetitions 1 --no-warmup --output downloads/course-demo/smoke.csv --experiment-id course-demo-smoke
.\.venv\Scripts\python.exe -m bench.plot_results --csv downloads/course-demo/smoke.csv --experiment-id course-demo-smoke --output-dir bench/plots/course-demo
```

Use this smoke CSV only to show automation. Its one-repetition statistics do
not replace the measured five-repetition comparison. Rerunning appends more
unique trials; do not interpret the repetition count as a new independent study.
Rehearsal result on 2026-11-20: the runner exited zero and wrote six verified
client observations; plotting exited zero and generated four figures plus
summary/audit CSVs. The committed experiment CSV was unchanged.

## Results narration and likely questions

- Figure 1: at N=8, baseline 79.292 +/- 0.070 s; P2P 23.518 +/- 1.392 s.
  The 3.37x number is a ratio of means, without a confidence interval.
- Figure 2: aggregate throughput is N times file size divided by makespan,
  averaged per trial. It is not the mean client throughput or physical link speed.
- Figures 3-4: baseline origin uploads 80 MiB at N=8; P2P origin averages
  17.75 MiB and leechers serve a mean 77.81% of payload.
- Why use a baseline flag? It isolates peer uploading while keeping framing,
  hashing, downloader and origin rate cap the same.
- Why can throughput exceed an upload cap? Swarm throughput sums useful
  distribution to clients; multiple peers upload, and token buckets start full.
- What do error bars mean? Sample SD of five complete measured trials, not
  confidence intervals or 150 independent trials.
- What is not measured? Real LAN/WAN links, resource use, packet captures,
  fault-workload performance and multi-process benchmark scaling.
- Is this BitTorrent-compatible? No; it is an educational custom protocol.

Use [course-report.md](course-report.md) for the full narrative and
[experiments.md](experiments.md) for controls, provenance and limitations.
