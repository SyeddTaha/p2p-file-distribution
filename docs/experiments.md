# Experiment Methodology & Benchmarking Plan

## 1. Research Question & Hypotheses

### Primary Research Question
*How does P2P chunk-based file distribution compare against a traditional Client-Server architecture in total makespan and aggregate throughput as the number of downloading clients scales?*

### Hypotheses
1. **Hypothesis 1 (Scaling):** In Client-Server mode, total distribution makespan scales linearly with the number of downloading clients when the server's upload capacity is constrained.
2. **Hypothesis 2 (P2P Efficiency):** In P2P mode, as downloading leechers finish initial chunks and begin uploading to each other, total distribution makespan levels off and aggregate swarm throughput increases proportionally to peer count.

---

## 2. Experimental Methodology & Control Variables

To ensure fair comparison between Client-Server baseline and P2P distribution:
- **Identical Codebase (implemented):** Client-Server mode uses the same protocol,
  framing, chunking, downloader, and hashing logic. Every client sets
  `SwarmPeer(upload_enabled=False)` (CLI: `download-file --no-upload`); the single
  origin seed keeps uploading enabled. Clients advertise no chunks, emit no
  HAVE, and refuse uploads before and after completion. See
  [ADR 0006](adr/0006-download-only-baseline.md).
- **Controlled Rate Limits (planned):** Application-level token-bucket rate
  limiters will cap each uploader's aggregate payload bandwidth across all its
  connections, with the same origin cap in both modes. Loopback correctness
  tests currently have no bandwidth bottleneck and support no timing conclusion.
- **Fixed Workload Parameters:**
  - File Size: `10,485,760` bytes (10 MiB)
  - Chunk Size: `262,144` bytes (256 KiB)
  - Seeder Upload Cap: `1,048,576` bytes/sec (1 MiB/s)
  - Leecher Upload Cap: `524,288` bytes/sec (512 KiB/s)
- **Sweep Parameter (Independent Variable):** Number of downloading clients ($N \in \{1, 2, 4, 8, 16\}$).
- **Repetitions:** 5 runs per configuration (plus 1 uncounted warm-up run).

---

## 3. Collected Metrics

- **Completion Time (Makespan):** Measured via `time.perf_counter()` from initial announce to final whole-file SHA-256 verification.
- **Client Download Throughput:** `file_size_bytes / completion_time_seconds`.
- **Upload Contribution Ratio:** Ratio of bytes served by origin seeder vs. bytes served by peer leechers.
- **Integrity & Failure Rates:** Count of retried chunk requests and SHA-256 hash mismatches.

---

## 4. Dataset & CSV Schema

Milestone 8 is partially implemented; no dataset has been collected. When implemented, raw
benchmark data is intended for `bench/results/experiments.csv`. Keep units
explicit in field names: rates and throughput are bytes per second, not bits
per second. Record the runtime environment per observation so results from
different machines or software versions are not conflated.

```csv
experiment_id,run_id,mode,repetition,is_warmup,num_clients,client_id,file_size_bytes,chunk_size_bytes,host_os,host_os_version,python_version,cpu_model,logical_cpu_count,network_profile,seeder_upload_limit_bytes_per_s,leecher_upload_limit_bytes_per_s,completion_time_s,download_throughput_bytes_per_s,bytes_uploaded_origin_peer,bytes_uploaded_leecher_peers,total_retry_count,chunk_hash_failure_count,full_file_hash_failure_count,success,failure_reason,git_commit
```

`total_retry_count` counts repeated chunk requests, while the two hash-failure
columns separately record per-chunk and final-file integrity failures. No
benchmark command or measured result is claimed until the Milestone 8 runner
and dataset exist and have actually been run.

---

## 5. Status & Measurements

- **Status:** **Not run.** The download-only baseline control has correctness
  coverage; no performance experiment or benchmark smoke run has been executed.
  Per-peer upload limits, metric counters, workload/CSV runner, and plotting
  scripts remain planned. Next implement and test a shared per-uploader
  token bucket with deterministic clock-based tests and cancellation handling.
