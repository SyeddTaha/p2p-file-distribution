"""Pure benchmark trial validation and aggregation, shared by plots and web UI."""

from __future__ import annotations

import csv
import logging
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from bench.run_experiments import CSV_FIELDNAMES
else:
    from run_experiments import CSV_FIELDNAMES  # type: ignore[no-redef,import-not-found]

logger = logging.getLogger(__name__)
METRICS = (
    "makespan_s",
    "aggregate_throughput_bytes_per_s",
    "origin_upload_bytes",
    "peer_share_pct",
)
# Different workloads/environments must never silently share a curve.
CONTEXT_FIELDS = (
    "file_size_bytes",
    "chunk_size_bytes",
    "seeder_upload_limit_bytes_per_s",
    "leecher_upload_limit_bytes_per_s",
    "file_sha256",
    "seed",
    "scheduler_seed_base",
    "host_os",
    "host_os_version",
    "python_version",
    "cpu_model",
    "logical_cpu_count",
    "network_profile",
    "git_commit",
    "git_dirty",
    "notes",
)
RUN_FIELDS = (
    "mode",
    "num_clients",
    "repetition",
    "is_warmup",
    "run_makespan_s",
    "bytes_uploaded_origin_peer",
    "bytes_uploaded_leecher_peers",
    *CONTEXT_FIELDS,
)


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    mode: str
    num_clients: int
    values: dict[str, float]


@dataclass(frozen=True)
class ConfigSummary:
    mode: str
    num_clients: int
    count: int
    means: dict[str, float]
    stds: dict[str, float]


def positive_number(value: str, field: str, *, allow_zero: bool = False) -> float:
    number = float(value)
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"invalid {field}: {value!r}")
    return number


def parse_csv_results(
    csv_path: Path,
    experiment_id: str | None = None,
) -> tuple[list[RunSummary], list[dict[str, str]], str]:
    """Validate complete trials; retain exclusions in an explicit audit, never partial successes."""
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != CSV_FIELDNAMES:
            raise ValueError("CSV schema mismatch; use the experiment runner's current schema")
        rows = list(reader)
    if experiment_id is not None:
        rows = [row for row in rows if row["experiment_id"] == experiment_id]
    ids = {row["experiment_id"] for row in rows}
    if len(ids) != 1:
        raise ValueError("select exactly one experiment with --experiment-id (or CSV is empty)")
    contexts = {tuple(row[field] for field in CONTEXT_FIELDS) for row in rows}
    if len(contexts) != 1:
        raise ValueError("mixed workloads or environments; plot them in separate datasets")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["run_id"]].append(row)
    summaries: list[RunSummary] = []
    audit: list[dict[str, str]] = []
    for run_id, clients in grouped.items():
        first = clients[0]
        for field in RUN_FIELDS:
            if len({row[field] for row in clients}) != 1:
                raise ValueError(f"inconsistent {field} within run {run_id}")
        n_clients = int(first["num_clients"])
        if n_clients < 1 or first["mode"] not in ("baseline", "p2p"):
            raise ValueError(f"invalid configuration in run {run_id}")
        if any(row["success"] not in ("true", "false") for row in clients):
            raise ValueError(f"invalid success flag in run {run_id}")
        if first["is_warmup"] not in ("true", "false"):
            raise ValueError(f"invalid warmup flag in run {run_id}")
        client_ids = {row["client_id"] for row in clients}
        if len(client_ids) != len(clients):
            raise ValueError(f"duplicate client records in run {run_id}")
        reason = "included"
        if first["is_warmup"] == "true":
            reason = "warmup"
        elif len(clients) != n_clients:
            reason = f"incomplete trial: expected {n_clients} clients, found {len(clients)}"
        elif any(row["success"] != "true" for row in clients):
            reason = "failed trial: " + "; ".join(
                row["failure_reason"] or "unspecified"
                for row in clients
                if row["success"] != "true"
            )
        audit.append(
            {
                "run_id": run_id,
                "mode": first["mode"],
                "num_clients": str(n_clients),
                "repetition": first["repetition"],
                "reason": reason,
            }
        )
        if reason != "included":
            if reason != "warmup":
                logger.warning("Excluded run %s: %s", run_id, reason)
            continue
        makespan = positive_number(first["run_makespan_s"], "run_makespan_s")
        times = [positive_number(row["completion_time_s"], "completion_time_s") for row in clients]
        if not math.isclose(makespan, max(times), rel_tol=1e-8):
            raise ValueError(f"makespan differs from maximum client completion in run {run_id}")
        origin = positive_number(
            first["bytes_uploaded_origin_peer"], "origin bytes", allow_zero=True
        )
        leechers = positive_number(
            first["bytes_uploaded_leecher_peers"], "peer bytes", allow_zero=True
        )
        file_size = int(first["file_size_bytes"])
        if file_size < 1 or any(int(row["bytes_downloaded"]) != file_size for row in clients):
            raise ValueError(f"successful trial has incomplete payload counters in run {run_id}")
        if first["mode"] == "baseline" and leechers:
            raise ValueError(f"baseline trial has leecher uploads in run {run_id}")
        summaries.append(
            RunSummary(
                run_id,
                first["mode"],
                n_clients,
                {
                    "makespan_s": makespan,
                    "aggregate_throughput_bytes_per_s": file_size * n_clients / makespan,
                    "origin_upload_bytes": origin,
                    "peer_share_pct": 100 * leechers / (origin + leechers)
                    if origin + leechers
                    else 0,
                },
            )
        )
    first = rows[0]
    caption = (
        f"{next(iter(ids))}; {first['host_os']} / Python {first['python_version']}; "
        f"{first['network_profile']}\n"
        f"File {int(first['file_size_bytes']) / 1048576:g} MiB; "
        f"chunk {int(first['chunk_size_bytes']) / 1024:g} KiB; "
        "mean ± sample SD across successful trials; warmups excluded"
    )
    return summaries, audit, caption


def calculate_stats(runs: list[RunSummary]) -> list[ConfigSummary]:
    grouped: dict[tuple[str, int], list[RunSummary]] = defaultdict(list)
    for run in runs:
        grouped[run.mode, run.num_clients].append(run)
    summaries = []
    for (mode, num_clients), items in sorted(grouped.items()):
        values = {key: [item.values[key] for item in items] for key in METRICS}
        summaries.append(
            ConfigSummary(
                mode,
                num_clients,
                len(items),
                {key: statistics.mean(data) for key, data in values.items()},
                {
                    key: statistics.stdev(data) if len(data) > 1 else 0
                    for key, data in values.items()
                },
            )
        )
    return summaries
