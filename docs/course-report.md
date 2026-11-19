# BitTorrent-Style P2P File Distribution

Computer Networks course report | Evidence snapshot: 20 November 2026

Implementation and dataset revision: `886c014` | Experiment: `m8-loopback-20261120`

This report describes that committed evidence snapshot. Later working-tree
feature development is outside its scope.

## Abstract

This project implements a tracker-assisted, single-file peer-to-peer distribution
system in Python. A FastAPI tracker provides peer discovery; peers exchange
length-prefixed messages over TCP, download chunks concurrently and serve chunks
only after SHA-256 verification. A JSON manifest defines chunk boundaries and
digests. Verified chunks are stored in a temporary file; complete-file verification
precedes atomic publication. The implementation includes bounded connections,
timeouts, retries, peer-failure handling and cancellation cleanup.

A controlled experiment compares an origin-only client-server baseline with P2P
exchange using the same transfer implementation. The measured sweep uses
N = 1, 2, 4, 8 clients, a 10 MiB file, 256 KiB chunks and five measured repetitions
per configuration after one warmup. All 180 client observations, including warmups,
passed final verification. At N=8, mean makespan was 79.292 seconds for baseline
and 23.518 seconds for P2P: a 3.37x ratio of means. P2P leechers served a mean
77.81% of payload. These results apply to one shared-process loopback environment;
they do not establish performance on a LAN or WAN.

## Research question

How do completion time, aggregate throughput and origin upload volume change as
the number of clients increases, when clients can contribute verified chunks?

The pre-recorded hypotheses were that a constrained origin makes baseline
completion time increase with N, and that peer exchange reduces origin traffic
and completion time. Measurements and interpretation are presented separately.

## Scope and deliverables

- A working HTTP tracker, TCP peers, manifest/storage layer and command-line interface.
- Automated unit, integration and end-to-end correctness tests.
- A repeatable benchmark runner, versioned raw CSV, analysis and four plots.
- A rehearsable live demonstration and automated evidence fallback in `docs/demo.md`.

The system handles one file per manifest on a trusted lab network. It uses no
database, frontend, DHT, NAT traversal, encryption or incentive/choking policy.
It is inspired by BitTorrent's chunk exchange, but implements its own small
protocol rather than the public BitTorrent wire protocol. Resume is not implemented.

<!-- pagebreak -->

## 1. System design

The control plane is separate from the data plane. The tracker lists peers and
their endpoints; it never carries file payloads. Each peer can accept TCP
connections, discover other peers and request chunks while uploading verified
local chunks. A seeder has all chunks; a leecher is still downloading.

```text
                   Tracker: FastAPI / in-memory registry
                       ^ HTTP announce / discovery ^
                       |                           |
                   Origin seed -- TCP PIECE --> Client A
                       |                           |
                       +------ TCP PIECE ------> Client B
                                                   ^
                       Client A -- TCP PIECE --------+
```

The registry supports `started`, heartbeat, `completed` and `stopped` announcements.
It returns at most 50 peers, excludes the caller and expires records older than
90 seconds. State is in memory; after a restart, peers can re-register through
heartbeat announcements. The normal heartbeat interval is 30 seconds.

### Application protocol

TCP provides an ordered byte stream, not application message boundaries. Each
frame begins with a four-byte big-endian body length, then a one-byte type and
its payload. Reads use explicit framing and `readexactly`; writes await `drain`.
Lengths are checked before allocating a frame body. The maximum body is
1,048,581 bytes, including a maximum 1 MiB PIECE payload and its type/index.

| Message | Purpose |
|---|---|
| HANDSHAKE | Validate protocol version, swarm ID, peer ID and listening port. |
| BITFIELD | Describe chunks available for upload; validate length and spare bits. |
| REQUEST | Request a zero-based chunk index. |
| PIECE | Return that index and the raw chunk bytes; reject unsolicited pieces. |
| HAVE | Announce a newly verified chunk to connected peers. |

### Scheduling, storage and failure handling

The scheduler reserves a missing chunk synchronously before network I/O, preventing
duplicate work within a downloader. Chunk selection is seeded random, not rarest-first.
Connections are capped at 30 and global in-flight work at 32; the current worker
has one outstanding request per remote peer. Failed chunks have bounded retries
with exponential delay; exhausted peers are retired and work can move to another
connected peer. Discovery happens at download start; later arrivals are not
dynamically reconnected during that download.

The manifest contains the filename, sizes, chunk descriptors and SHA-256 digests.
Its canonical JSON hash identifies the swarm. Storage validates safe filenames,
chunk index, length and digest before accepting bytes into a `.part` file. The
whole file is checked before `os.replace` publishes it. Cancellation propagates
after owned tasks and sockets are cleaned up. Hash checks establish integrity
relative to the supplied manifest; they do not authenticate its publisher.

<!-- pagebreak -->

## 2. Experimental method

The baseline and P2P modes use the same framing, manifest, downloader, hashing,
storage and origin cap. Every baseline client disables uploads, advertises an
empty bitfield and suppresses HAVE. The origin alone sends baseline payloads.
P2P clients serve verified chunks while downloading and after completing.

| Control | Value |
|---|---|
| Number of clients | 1, 2, 4, 8; one initial origin in each trial |
| File and chunk size | 10,485,760 bytes / 262,144 bytes (40 chunks) |
| Origin upload cap | 1,048,576 bytes/s (1 MiB/s), both modes |
| Client upload cap | 524,288 bytes/s (512 KiB/s); disabled in baseline |
| Repetition policy | Five measured trials plus one logged warmup per mode/N |
| Start pattern | Register every client, then release download tasks together |
| RNG controls | Source/order seed 42; scheduler seed 42 + client index |
| Isolation | Fresh tracker state, directories, peers, ports and token buckets |
| Host | Windows 11; Python 3.13.1; eight logical CPUs |
| Reported processor | Intel64 Family 6 Model 140 Stepping 1, GenuineIntel |
| Transport | Real loopback TCP; tracker handlers through in-process ASGI |

Configuration order is shuffled reproducibly within each repetition. Source bytes
are identical across modes and trials. Upload token buckets are shared across a
peer's connections and start with a one-second burst allowance. The cap counts
PIECE payload bytes; it is not a physical network-link limit.

### Definitions and analysis unit

The common start is immediately before download-task release, after registration.
A client finishes after discovery, handshake, transfer, whole-file verification,
completed announcement and an independent streamed SHA-256 check. Source generation,
startup and teardown are excluded from successful download intervals.

- Makespan = maximum client completion interval from the common start.
- Client throughput = file size / that client's completion interval.
- Aggregate throughput = N x file size / trial makespan.
- Peer share = leecher upload bytes / (origin + leecher upload bytes).
- Reported spread = sample standard deviation across five complete measured trials.

The trial, rather than each client row, is the independent aggregation unit.
Run-wide upload totals repeat on client rows and are counted once. Warmups are
retained in the CSV and excluded from statistics. A failed or incomplete trial
is excluded as a whole and listed in the audit; failures remain in raw data.
No such measured trial was excluded in this dataset. Error bars are sample SD,
not confidence intervals; no statistical significance test was performed.

### Provenance

There are 48 trials and 180 client observations: 40 measured trials / 150 client
rows and eight warmups / 30 client rows. The versioned source is
`bench/results/experiments.csv`. Collection recorded base revision `b926ada`
with `git_dirty=true`; revision `886c014` subsequently captured that implementation
and dataset together. These original metadata fields have not been rewritten.
RAM, per-peer CPU/memory and external activity were not collected.

<!-- pagebreak -->

## 3. Measured completion time

![Completion time versus clients](../bench/plots/completion_time_vs_clients.png)

Figure 1. Mean makespan with sample-SD error bars; five measured trials per
mode/N. Both modes use the same origin cap. Warmups are excluded.

| Clients | Baseline mean +/- SD (s) | P2P mean +/- SD (s) | Ratio of means |
|---|---|---|---|
| 1 | 9.105 +/- 0.074 | 9.073 +/- 0.010 | 1.00x |
| 2 | 19.137 +/- 0.124 | 11.329 +/- 0.641 | 1.69x |
| 4 | 39.143 +/- 0.022 | 15.414 +/- 0.734 | 2.54x |
| 8 | 79.292 +/- 0.070 | 23.518 +/- 1.392 | 3.37x |

The ratio divides the baseline mean by the P2P mean; no uncertainty estimate
is attached to this derived ratio. At N=8, P2P has a lower measured makespan
in these trials. The N=1 timings are close and their spread overlaps, so the
data does not establish a single-client advantage.

### Interpretation against the hypotheses

Baseline makespan increases approximately with N under the constrained origin.
P2P also takes longer as N grows, but its measured mean increases more slowly
across this sweep. These observations support the hypotheses for this workload
and host. They do not show a flat P2P scaling curve or prove that P2P is always
faster. Upload availability, scheduling, protocol overhead and network topology
can change the result.

The roughly nine-second single-client result is consistent with a ten-MiB file,
a one-MiB/s sustained origin cap and an initially full one-second token bucket.
This is an explanation of the measured setup, not a separate measurement.

<!-- pagebreak -->

## 4. Throughput and origin contribution

![Aggregate throughput versus clients](../bench/plots/throughput_vs_clients.png)

Figure 2. Mean of per-trial aggregate throughputs, with sample SD. At N=8,
baseline reaches 1.009 MiB/s and P2P reaches 3.411 MiB/s. These are useful
payload rates across the swarm, not physical link rates or per-client rates.

![Origin upload volume versus clients](../bench/plots/upload_contribution_vs_clients.png)

Figure 3. Origin payload is counted once per trial. Baseline origin volume
equals N times the file size: 80 MiB at N=8. P2P origin volume at N=8 averages
17.75 MiB. The origin still supplies initial copies; peers distribute much
of the remaining payload. Both figures show five measured trials per point.

<!-- pagebreak -->

## 5. Peer contribution and correctness evidence

![Peer upload share versus clients](../bench/plots/peer_share_vs_clients.png)

Figure 4. Leecher share of payload uploads: mean +/- sample SD. Baseline
leecher uploads are zero. P2P peer shares average 0.00%, 38.75%, 63.75% and
77.81% for N=1,2,4,8 respectively. N=8's sample SD is 0.88 percentage points.

### Integrity and observed failures

All 180 client observations, including warmups, passed independent final-file
verification. Recorded retries, chunk-integrity failures and whole-file hash
failures were zero. Per-trial origin plus leecher upload totals equal
N times the file size. These successful runs establish integrity for the
observed transfers; they do not measure performance under faults.

### Automated reliability evidence

The recorded full suite at revision `886c014` passed 376 tests with one upstream
Starlette/httpx deprecation warning. Ruff, formatting and mypy checks passed.
Tests use deterministic input, temporary directories and ephemeral loopback ports.

| Concern | Evidence in the repository |
|---|---|
| Framing and validation | Split/coalesced reads, malformed messages, bounds and timeout tests. |
| Baseline isolation | Concurrent baseline clients receive origin payloads and send no PIECE/HAVE. |
| Peer independence | A completed leecher serves a later client after the origin stops. |
| Corruption and disconnect | Integration tests retry via another peer and reassign released chunks. |
| Cancellation and teardown | Reservations, sockets, readers and heartbeat tasks are cleaned up. |
| Benchmark accounting | Retained failure metrics, warmup exclusions and complete-trial aggregation. |

The demo's five selected E2E/fault cases were rehearsed on 20 November 2026:
all five passed in 1.93 seconds. Fault tests are correctness evidence, not a
measured fault-workload benchmark. A separate historical Windows CLI smoke also
verified file equality, Ctrl+C exit and tracker deregistration; see `docs/testing.md`.

<!-- pagebreak -->

## 6. Limitations and conclusion

All measured peers and the ASGI tracker share one Python process/event loop,
CPU, storage and memory. TCP payloads traverse loopback, while tracker calls
exercise HTTP handlers without a tracker HTTP socket or server process. Cache
state, background host activity, the burst allowance, seeded scheduling and
batch-based download coordination affect timings. No Mininet, WAN/LAN, packet
capture or multi-machine benchmark was run. The small sweep and five repetitions
cannot establish statistical significance or scaling beyond N=8.

The implementation has bounded failure handling but not dynamic reconnection to
late peers, persistent download resume or pipelined requests per worker. Empty
files are unsupported. The tracker trusts advertised endpoints on a lab network;
remote fields and payloads are validated, but there is no publisher authentication,
TLS, NAT traversal or hostile-network security claim. Resource usage and explicit
disconnect/timeout metrics were not collected in the performance dataset.

The project demonstrates a complete path from discovery through framed chunk
exchange to verified file publication. Under the measured upload bottleneck,
P2P reduced mean makespan and origin traffic at N=2,4,8. The N=8 comparison was
79.292 seconds versus 23.518 seconds, with peers serving a mean 77.81% of payload.
The conclusion is limited to this experiment and supported by versioned raw
observations rather than assumed scaling formulas.

## 7. Reproduction and demonstration

Run the following from the repository root with the existing development environment:

```powershell
# Regenerate the four figures and derived summary/audit; do not rerun the sweep.
.\.venv\Scripts\python.exe -m bench.plot_results --experiment-id m8-loopback-20261120

# Export this report as self-contained HTML and PDF with an installed Chrome.
.\.venv\Scripts\python.exe docs/build_course_report.py --pdf
```

The full collection command and controls are recorded in `docs/experiments.md`.
For a new collection, choose a separate CSV and experiment ID; appending another
sweep to the evidence dataset would change sample counts. The short live demo,
presenter narration, expected outputs, cleanup and automated fallback are in
`docs/demo.md`. Do not present its tiny smoke workload as the measured experiment.

## Evidence and technical references

1. [Raw observations](../bench/results/experiments.csv), experiment `m8-loopback-20261120`; versioned in `886c014`.
2. [Experiment methodology](experiments.md) and `bench/plot_results.py`; generated `summary.csv` and `trial_audit.csv`.
3. [Architecture](architecture.md), [wire protocol](protocol.md) and [manifest specification](manifest-format.md).
4. [Testing guide](testing.md), `tests/e2e/test_full_transfer.py` and `tests/integration/test_downloader_loopback.py`.
5. [Decision records](adr/0008-in-process-benchmark-runner.md), including baseline controls and upload-rate limiting in ADRs 0006-0007.

These are project-internal evidence sources. No external literature review or
claim of BitTorrent interoperability is included.
