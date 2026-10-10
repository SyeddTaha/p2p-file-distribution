---
name: network-benchmarking
description: Design, run, and report controlled experiments comparing a client-server baseline against P2P distribution, including workload parameters, repetitions, warm-up policy, fair comparison, metrics (completion time, throughput, upload contribution, retries, integrity failures, resource usage), CSV raw data, plotting scripts, and strict separation of measured results from theoretical expectations. Use when planning experiments, writing benchmark scripts, or presenting performance results. Never fabricate measurements. Not for correctness testing, protocol design, or scheduler implementation.
---

# Network Benchmarking

## When to use / when not to use

Use when you are:
- designing an experiment or workload;
- writing scripts that run the system and record results;
- turning raw data into tables/plots and writing conclusions.

Do **not** use for:
- correctness tests (pass/fail behavior) -> `network-testing-reliability`
- implementing scheduling or protocol changes -> `p2p-distributed-systems`, `tcp-protocol-engineering`
- structuring `docs/experiments.md` in general -> `engineering-documentation` (this skill supplies the methodology content)

## Non-negotiable honesty rules

1. **Never fabricate, estimate-and-present-as-measured, or "illustrate with typical numbers".** If an experiment has not been run, say it has not been run.
2. Every number in a report, plot, or doc must trace to a raw CSV row committed in the repo, produced by a script that is also in the repo.
3. Keep **measured** results and **theoretical expectations** in separate, clearly labeled sections. Theory (e.g. "client-server time grows roughly linearly with the number of clients when the server uplink is the bottleneck") is a hypothesis to compare against, never evidence.
4. Report failed runs, outliers, and anomalies; do not silently drop data. If a run is excluded, record why in a `notes` column or the methodology doc.
5. If you ran on loopback or a shared laptop, say so, and do not extrapolate to real networks.

## Research question and hypotheses

Main question: *How does P2P distribution compare with a client-server baseline as the number of downloading clients grows?* Write hypotheses *before* running (for example: P2P completion time grows more slowly than client-server as clients increase when the origin's upload capacity is the bottleneck). State them as hypotheses, then report whether the data supports them.

## Fair comparison design

- **Same code path where possible.** The client-server baseline should use the same manifest, chunk size, framing, hashing, and downloader, but with leechers *not* serving each other (only the single origin seeder uploads). That isolates the effect of peer-to-peer exchange. Document how this mode is switched on (a config flag, not a separate codebase).
- **Same workload:** identical file, chunk size, number of clients, start times, and limits across both modes.
- **Bottleneck must exist to be meaningful.** On loopback the OS can move data very fast and no real link constraint exists. Introduce a controlled limit and document it: an application-level token-bucket upload rate limit per peer (portable and deterministic), and/or Mininet link shaping if practical and available (Linux only; optional). Never imply loopback numbers represent a real WAN/LAN.
- **Controlled variables:** file size, chunk size, concurrency limits, seeder upload cap, leecher upload cap, number of seeders.
- **Independent variables (sweep one at a time):** number of clients (e.g. 1, 2, 4, 8, ...), file size, chunk size, number of initial seeders, upload cap.
- **Staggering:** decide whether clients start simultaneously (flash crowd) or staggered; document and keep identical between modes.
- **Randomness:** seed the scheduler RNG and workload generator; record the seed per run.

## Workload and run protocol

1. Generate the test file from a seeded RNG (deterministic bytes) so every machine uses the identical file; record its SHA-256.
2. **Warm-up:** run one discarded warm-up run per configuration (or document why not) to reduce cold-start effects (imports, file cache). Warm-up runs are logged with `is_warmup=true`, not mixed into statistics.
3. **Repetitions:** at least 5 per configuration (more if variance is high). Randomize or interleave configuration order to avoid time-of-day/thermal bias.
4. **Between runs:** fresh download directories, fresh tracker state, all processes/tasks terminated, ports released.
5. **Verification:** a run counts as *successful* only if every client's final file hash matches. Failed runs are recorded with `success=false`.
6. **Environment capture:** record OS, CPU model/cores, RAM, Python version, git commit hash, whether Wireshark or other tools were running, and network setup (loopback / Mininet / real LAN). Do not hard-code personal paths or machine names into committed scripts; take them as arguments or environment variables.

## Metrics

Collect where practical (mark any not collected as such):
- **Completion time** per client (monotonic clock: `time.perf_counter()`), and overall makespan.
- **Throughput** per client = `file_size / completion_time`; aggregate throughput.
- **Upload contribution:** bytes uploaded by the origin seeder vs. by leechers; fraction served by peers.
- **Retries and failures:** retried chunks, timeouts, disconnects.
- **Integrity failures:** hash mismatches detected.
- **Resource usage (optional):** CPU time and peak memory per process (e.g. via `resource`/`psutil` only if `psutil` is approved as a dependency; otherwise standard-library facilities).
- Measure time at well-defined points (start = first tracker announce or first connection; end = final file verified). Document the definition.

## Raw data format (CSV)

One row per client per run is recommended. Suggested columns:

`experiment_id, run_id, mode, repetition, is_warmup, seed, num_clients, client_id, file_size_bytes, chunk_size_bytes, seeder_count, seeder_upload_cap_bps, leecher_upload_cap_bps, start_offset_s, completion_time_s, throughput_bytes_per_s, bytes_uploaded_by_seeder, bytes_uploaded_by_leechers, bytes_downloaded, retries, integrity_failures, success, git_commit, python_version, os, cpu, notes`

Rules: write with the `csv` module; one header row; UTC ISO timestamps where used; units in column names; append-only per experiment; never hand-edit raw CSVs (derive cleaned data with scripts into separate files).

```python
import csv
from pathlib import Path

def append_row(path: Path, row: dict[str, object], fieldnames: list[str]) -> None:
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
```

## Analysis and plots

- Scripts live in `bench/` and read CSVs from `bench/results/`; plots are generated by script, never by hand.
- Use Matplotlib with a non-interactive backend (`matplotlib.use("Agg")`) so scripts run headless.
- Report central tendency **and** spread (mean and standard deviation, or median and min/max) over repetitions; show error bars. Do not claim a difference when ranges overlap heavily without saying so.
- Label axes with units, state `n` repetitions and the environment in the caption.
- Typical plots: completion time vs. number of clients (both modes); aggregate throughput vs. clients; origin upload bytes vs. clients; fraction served by peers.
- Statistics beyond mean/stdev are optional; do not over-claim significance with small samples.

## Workflow

1. Write the experiment plan in `docs/experiments.md` (question, hypotheses, variables, parameters, repetitions, metrics, environment, threats to validity) **before** running.
2. Implement or adjust the runner script in `bench/`; dry-run with a tiny workload to check plumbing (mark results as smoke tests, do not use in conclusions).
3. Run the real experiment; commit raw CSVs plus the exact command/parameters used.
4. Generate plots and tables with scripts.
5. Write results (measured) and discussion (interpretation, theory comparison, limitations) separately.
6. Update `docs/project-status.md` to reflect what was actually run.

## Common failure modes

- Comparing modes with different code paths, caps, or file sizes.
- No bottleneck on loopback, so the baseline looks as fast as P2P, then drawing wrong conclusions.
- A single run per configuration, or discarding bad runs silently.
- Measuring while Wireshark/other heavy processes run in one mode but not the other.
- Including warm-up runs in statistics.
- Leftover processes or ports from a previous run contaminating the next.
- Reporting averages without spread; reporting percentages without the base numbers.
- Stating theory as result, or describing an experiment as completed when only a smoke test ran.
- Time measured with `time.time()` (can jump) instead of `time.perf_counter()`.

## Checklist

- [ ] Plan with hypotheses written before running.
- [ ] Same code path/parameters for both modes except the variable under test.
- [ ] Warm-up and repetitions defined and followed.
- [ ] Raw CSV committed; every reported number traceable to it.
- [ ] Environment and git commit recorded.
- [ ] Plots generated by script; axes, units, `n`, and error bars present.
- [ ] Measured results and theoretical expectations in separate sections.
- [ ] Limitations stated (loopback, small scale, simulated caps).

## Expected deliverables and documentation updates

`bench/` runner and plot scripts; `bench/results/*.csv` raw data; generated plots; `docs/experiments.md` (methodology, parameters, environment, results, limitations); updated `docs/project-status.md` (benchmarks: planned / run, with dates and commit).
