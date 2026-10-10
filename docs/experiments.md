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
- **Identical Codebase:** Client-Server mode uses the exact same protocol, framing, chunking, and hashing logic, but with leechers configured to disable piece uploading (only the origin seed uploads).
- **Controlled Rate Limits:** Application-level token-bucket rate limiters cap the origin seeder's upload bandwidth to isolate bottleneck behavior on loopback network interfaces.
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

Raw benchmark data will be saved to `bench/results/experiments.csv`:

```csv
experiment_id,run_id,mode,repetition,is_warmup,num_clients,client_id,file_size_bytes,chunk_size_bytes,seeder_upload_cap_bps,completion_time_s,throughput_bps,bytes_uploaded_seeder,bytes_uploaded_peers,success,git_commit
```

---

## 5. Status & Measurements

- **Status:** **Not run yet.** Workload scripts and baseline flags planned for Milestone 8.
