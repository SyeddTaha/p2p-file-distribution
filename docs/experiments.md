# Distribution experiments

## Research question and hypotheses

How do makespan, aggregate throughput and origin upload volume change when
N = 1, 2, 4, 8 clients download through the baseline and P2P modes?

Hypotheses, recorded before the sweep: a constrained origin makes baseline
completion time grow with N; verified chunk exchange lets P2P clients reduce
origin traffic and completion time. These are expectations, not measurements.

## Methodology

`bench/run_experiments.py` runs the same manifest, SHA-256 checks, TCP protocol,
downloader and disk path in both modes. Baseline clients use
`SwarmPeer(upload_enabled=False)`; only the origin serves payloads
([ADR 0006](adr/0006-download-only-baseline.md)). All P2P clients may upload
verified chunks and keep serving until every client finishes or fails.

| Control | Default |
|---|---|
| Clients | 1, 2, 4, 8 |
| Initial uploading seeds | 1 |
| File size | 10,485,760 bytes (10 MiB) |
| Chunk size | 262,144 bytes (256 KiB) |
| Origin upload cap | 1,048,576 bytes/s (1 MiB/s) in both modes |
| Client upload cap | 524,288 bytes/s (512 KiB/s); baseline uploads disabled |
| Repetitions | 5 measured plus 1 logged warmup per mode/N configuration |
| Workload / ordering RNG seed | 42 |
| Scheduler RNG seed | Workload seed + client index (42..49); paired between modes |
| Start pattern | All clients register, then release downloads together |
| Network | Real TCP on 127.0.0.1 with ephemeral ports |
| Tracker | Fresh FastAPI application/registry via in-process ASGI HTTP transport |

The source generator writes seeded `random.Random(seed).randbytes(...)` in
1 MiB blocks. All trials use identical source bytes; their SHA-256 is recorded.
Warmups run first; each repetition shuffles the mode/N configuration order
with a separate seeded RNG. Every trial has fresh directories, tracker state,
connections, tasks and token buckets. Peer teardown finishes before the next
trial; temporary files are removed. Global tracker overrides are never changed.

Token buckets apply to aggregate PIECE payload bytes per uploader, excluding
protocol overhead, and start full with a one-second burst allowance. They
model an upload bottleneck rather than a physical link. Peer limits and request
concurrency use the existing `p2p.config` defaults. Every client sees the same
registered swarm before download discovery, including baseline listeners.

The common `time.perf_counter()` start occurs after all clients register and
immediately before their download tasks start. A client's completion includes
discovery, connection/handshake, payload download, storage's whole-file check,
completed announcement and an independent streamed SHA-256 check in a worker
thread. Setup/source generation and teardown are excluded. Makespan is the
maximum completion interval from that common start. Successful aggregate
throughput is `N * file_size_bytes / makespan_s`; client throughput is
`file_size_bytes / completion_time_s`.

The per-trial deadline includes startup and is
`max(60, 4 * N * file_size_bytes / origin_rate + 30)` seconds unless overridden
with `--trial-timeout`. Timeouts and startup/download failures are recorded for
every affected client. Only observed final-file mismatches increment the
whole-file hash failure counter. Failed/cancelled transfers retain downloader
counters; external cancellation propagates after cleanup and leaves earlier
CSV trials intact. An interrupted trial is not appended. A suite containing a
failed trial exits nonzero after recording results.

## Commands and raw data

Run from the repository root with the existing development environment:

```powershell
# Tiny plumbing smoke, kept separate from measured experiments.
.\.venv\Scripts\python.exe -m bench.run_experiments --clients 1,2,4,8 --file-size 65536 --chunk-size 4096 --repetitions 1 --no-warmup --output bench/results/smoke-seeded.csv --experiment-id m8-smoke-seeded

# Full planned sweep: 48 trials, 180 client observations including warmups.
.\.venv\Scripts\python.exe -m bench.run_experiments --experiment-id m8-loopback-20261120
.\.venv\Scripts\python.exe -m bench.plot_results --experiment-id m8-loopback-20261120
```

`--quick` selects a 1 MiB workload and 2 measured repetitions, retaining all N
and default warmups. Such results are smoke evidence only. Flags also control
modes, rates, file/chunk sizes, seed, output and temporary workspace parent.
`--notes` records operator-known activity; no software is installed by scripts.

The append-only raw dataset is `bench/results/experiments.csv`; it is explicitly
allowed by `.gitignore`. The runner checks an existing file's header before any
trial, writes a single header and flushes completed trials individually. Use a
single runner per output file. Unique run IDs identify trials; experiment IDs
select a suite. Do not edit observations by hand or combine different conditions
into one curve. The Git revision and dirty-worktree flag describe the code used;
a dirty flag requires the associated source changes when reproducing the run.

`CSV_FIELDNAMES` in the runner defines the schema. Each row records a client,
mode/N/repetition, warmup flag, UTC timestamp, workload and scheduler seeds,
file/chunk sizes and source SHA-256, both caps, client completion/throughput and
verified payload volume, common run makespan, retries, chunk/final-file integrity
failures, success/failure reason, deadline, Git state, OS/Python/CPU/cores,
network profile and notes. `scheduler_seed_base` identifies the common seed
control, while `scheduler_seed` records the actual per-client seed. Rates use
bytes/s, times use seconds.

`bytes_uploaded_origin_peer` and `bytes_uploaded_leecher_peers` are **run totals
repeated on each client row**. Analysis takes each once per trial. Retry/hash
counters and `bytes_downloaded` are per client. Chunk integrity failures include
length and digest rejection; resource usage and RAM are not collected.

## Analysis and exclusions

`bench/plot_results.py` uses Matplotlib's Agg backend and produces four PNGs:
completion time, aggregate throughput, origin upload volume and peer upload
share versus N. Each point is a mean across successful complete trials, with
sample-standard-deviation error bars and the actual repetition count in the
caption. Single-repetition SD is shown as zero and is not evidence of stability.

The generated `bench/plots/summary.csv` contains derived means/SDs;
`trial_audit.csv` lists every trial as included, warmup, failed or incomplete.
Failed trials are warned about explicitly and excluded **as a whole**: their
successful client rows do not enter statistics. Raw failures remain in the
source dataset. Duplicate client records, invalid numbers, conflicting trial
totals, mixed experiments and mixed workloads/environments cause errors.
Select a suite with `--experiment-id` if an append-only CSV holds several.
Generated PNGs and derived CSVs are ignored; regenerate them from the raw data.

## Status and measured results

**Run (2026-11-20):** The full default command above exited zero and produced
[experiments.csv](../bench/results/experiments.csv): 48 complete trials and 180
verified client observations (150 measured, 30 warmup). Each mode/N combination
has five measured repetitions and one warmup. No failed/incomplete trials were
excluded; the audit contains 40 included trials and eight warmups. All retry,
chunk-integrity and whole-file-hash failure counters were zero. Each trial's
origin plus leecher payload totals equal `N * file_size_bytes`; baseline
leecher uploads were zero throughout.

Environment: Windows 11, Python 3.13.1, eight logical CPUs, reported processor
`Intel64 Family 6 Model 140 Stepping 1, GenuineIntel`, loopback TCP and
in-process ASGI tracker. Code was based on
`b926ada553d7e82c944cdf478064daa556f17a9b` with `git_dirty=true` at collection
time. The source changes and raw CSV are versioned together in the Milestone 8
commit on `feat/download-only-baseline`; the raw metadata preserves the actual
collection state.
The source SHA-256 was
`03ad677dc65a804d63e4bf5821bfc6c3e9ee302cd6b538a28d607ab882ba20b1` in every row.
RAM, resource usage and external activity were not collected.

The plotting command exited zero and generated all four figures plus
`bench/plots/summary.csv` and `trial_audit.csv`. Values below are calculated from
the measured trials only. Completion intervals are mean ± sample SD, seconds;
speedup is the ratio of baseline/P2P means, without an uncertainty estimate.

| N | Baseline makespan (s) | P2P makespan (s) | Ratio of means | Mean payload served by P2P leechers |
|---|---|---|---|---|
| 1 | 9.105 ± 0.074 | 9.073 ± 0.010 | 1.00x | 0.00% |
| 2 | 19.137 ± 0.124 | 11.329 ± 0.641 | 1.69x | 38.75% |
| 4 | 39.143 ± 0.022 | 15.414 ± 0.734 | 2.54x | 63.75% |
| 8 | 79.292 ± 0.070 | 23.518 ± 1.392 | 3.37x | 77.81% |

At N=8, mean aggregate throughput was 1.009 MiB/s for baseline and
3.411 MiB/s for P2P. These are means of per-trial aggregate throughputs, not
throughput recalculated from a mean duration. The initially full token bucket
explains throughput slightly above the configured sustained origin cap for
short trials.

## Interpretation

The measured baseline increases approximately with N under the origin cap.
P2P has a lower measured mean at N=2,4,8 and serves an increasing share of
payload through leechers, supporting the hypotheses under these controls.
P2P completion time still increases with N; this experiment does not show a
flat scaling curve. N=1 timings are close and their spread overlaps, so no
single-client advantage is established. Five repetitions on one host do not
establish statistical significance or performance on a real network.

## Limitations

All peers, the ASGI tracker and hashing share one Python process/event loop and
one host's CPU, disk/cache and memory. The tracker exercises HTTP handlers
without an HTTP socket or ASGI server. Loopback, initial bursts, a shared
laptop's background activity, sequential batches in the current downloader,
seeded scheduler choices and OS scheduling affect results. File caches are warm;
no cache flushing or process isolation is attempted. RAM, per-peer CPU/memory,
disconnect/timeout counts and external activity are not automatically captured.
These observations cannot establish WAN/LAN performance or statistical
significance. No Mininet, packet capture or multi-machine experiment is run.

## Local UI display

The [console](web-ui.md) reads the versioned CSV using `bench/analysis.py`, extracted
from the plotting script without changing trial-validation/aggregation rules. It
shows the N=1,2,4,8 table, makespan and throughput graphs with sample SD, repetition
counts, warmups and exclusions. It launches no trials and supplies no replacement
data when results are unavailable. UI smoke tests are correctness evidence, not
additional performance measurements. Existing plotting commands remain supported.
