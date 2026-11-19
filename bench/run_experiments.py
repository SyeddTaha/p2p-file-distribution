"""Reproducible loopback sweeps: python -m bench.run_experiments."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import logging
import math
import os
import platform
import random
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI

from p2p.config import MAX_CHUNK_SIZE, MAX_PEER_CONNECTIONS
from p2p.peer.client import SwarmPeer
from p2p.storage.manager import FileIntegrityError
from p2p.storage.manifest import MAX_CHUNK_COUNT, build_manifest
from p2p.tracker.registry import SwarmRegistry
from p2p.tracker.server import app, get_registry

logger = logging.getLogger(__name__)
type Row = dict[str, str | int | float]
CSV_FIELDNAMES = [
    "experiment_id",
    "run_id",
    "mode",
    "repetition",
    "is_warmup",
    "num_clients",
    "client_id",
    "file_size_bytes",
    "chunk_size_bytes",
    "host_os",
    "host_os_version",
    "python_version",
    "cpu_model",
    "logical_cpu_count",
    "network_profile",
    "seeder_upload_limit_bytes_per_s",
    "leecher_upload_limit_bytes_per_s",
    "completion_time_s",
    "download_throughput_bytes_per_s",
    "bytes_uploaded_origin_peer",
    "bytes_uploaded_leecher_peers",
    "total_retry_count",
    "chunk_hash_failure_count",
    "full_file_hash_failure_count",
    "success",
    "failure_reason",
    "git_commit",
    "git_dirty",
    "seed",
    "scheduler_seed",
    "scheduler_seed_base",
    "file_sha256",
    "started_at_utc",
    "run_makespan_s",
    "bytes_downloaded",
    "trial_timeout_s",
    "notes",
]
DEFAULT_CLIENTS = (1, 2, 4, 8)
DEFAULT_MODES = ("baseline", "p2p")
DEFAULT_FILE_SIZE = 10 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 256 * 1024
DEFAULT_SEEDER_RATE = 1024 * 1024
DEFAULT_LEECHER_RATE = 512 * 1024
DEFAULT_REPETITIONS = 5
MAX_WORKLOAD_SIZE = 1024 * 1024 * 1024
MIN_TRIAL_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class ExperimentConfig:
    """Both modes use identical source bytes, chunk sizes and origin limits."""

    experiment_id: str
    output_path: Path
    modes: tuple[str, ...] = DEFAULT_MODES
    client_counts: tuple[int, ...] = DEFAULT_CLIENTS
    repetitions: int = DEFAULT_REPETITIONS
    warmup: bool = True
    file_size_bytes: int = DEFAULT_FILE_SIZE
    chunk_size_bytes: int = DEFAULT_CHUNK_SIZE
    seeder_upload_limit_bps: float = DEFAULT_SEEDER_RATE
    leecher_upload_limit_bps: float = DEFAULT_LEECHER_RATE
    seed: int = 42
    work_dir: Path | None = None
    trial_timeout_s: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must not be empty")
        if not self.modes or any(mode not in DEFAULT_MODES for mode in self.modes):
            raise ValueError("modes must contain baseline and/or p2p")
        if len(set(self.modes)) != len(self.modes):
            raise ValueError("duplicate modes are not allowed")
        if not self.client_counts or any(
            type(n) is not int or not 1 <= n <= MAX_PEER_CONNECTIONS for n in self.client_counts
        ):
            raise ValueError(f"clients must be integers in 1..{MAX_PEER_CONNECTIONS}")
        if len(set(self.client_counts)) != len(self.client_counts):
            raise ValueError("duplicate client counts are not allowed")
        if type(self.repetitions) is not int or self.repetitions < 1:
            raise ValueError("repetitions must be a positive integer")
        if (
            type(self.file_size_bytes) is not int
            or not 1 <= self.file_size_bytes <= MAX_WORKLOAD_SIZE
        ):
            raise ValueError("file size must be in 1..1073741824 bytes")
        if (
            type(self.chunk_size_bytes) is not int
            or not 1 <= self.chunk_size_bytes <= MAX_CHUNK_SIZE
        ):
            raise ValueError(f"chunk size must be in 1..{MAX_CHUNK_SIZE} bytes")
        if math.ceil(self.file_size_bytes / self.chunk_size_bytes) > MAX_CHUNK_COUNT:
            raise ValueError("workload exceeds the manifest chunk count limit")
        for rate in (self.seeder_upload_limit_bps, self.leecher_upload_limit_bps):
            if isinstance(rate, bool) or not math.isfinite(rate) or rate < 1:
                raise ValueError("upload rates must be finite and >= 1 byte/s")
        if self.trial_timeout_s is not None and (
            not math.isfinite(self.trial_timeout_s) or self.trial_timeout_s <= 0
        ):
            raise ValueError("trial timeout must be positive and finite")


def get_system_metadata() -> Row:
    """Capture environment without personal paths, usernames or hostnames."""
    metadata: Row = {
        "host_os": platform.system(),
        "host_os_version": platform.release(),
        "python_version": platform.python_version(),
        "cpu_model": platform.processor() or platform.machine(),
        "logical_cpu_count": os.cpu_count() or 1,
        "network_profile": "loopback-tcp/in-process-asgi-tracker",
        "git_commit": "unknown",
        "git_dirty": "unknown",
    }
    try:
        for key, arguments in (
            ("git_commit", ["rev-parse", "HEAD"]),
            ("git_dirty", ["status", "--porcelain"]),
        ):
            result = subprocess.run(
                ["git", *arguments],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            ).stdout.strip()
            metadata[key] = str(bool(result)).lower() if key == "git_dirty" else result
    except (OSError, subprocess.SubprocessError):
        pass
    return metadata


def validate_csv(csv_path: Path) -> None:
    if csv_path.exists() and csv_path.stat().st_size:
        with csv_path.open(newline="", encoding="utf-8") as stream:
            if next(csv.reader(stream)) != CSV_FIELDNAMES:
                raise ValueError(f"CSV schema mismatch: {csv_path}")


def append_rows(csv_path: Path, rows: list[Row]) -> None:
    """Append each completed trial, including failures, without overwriting prior rows."""
    validate_csv(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


def prepare_source(path: Path, size: int, seed: int) -> None:
    """Generate seeded bytes in bounded blocks outside the event loop."""
    rng = random.Random(seed)
    with path.open("wb") as stream:
        for offset in range(0, size, MAX_CHUNK_SIZE):
            stream.write(rng.randbytes(min(MAX_CHUNK_SIZE, size - offset)))


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


async def run_single_trial(
    config: ExperimentConfig,
    *,
    mode: str,
    num_clients: int,
    repetition: int,
    is_warmup: bool,
    system_meta: Row,
) -> list[Row]:
    """Fresh tracker, peers, ports and directories; one retained observation per client."""
    run_id = uuid.uuid4().hex
    started_at = datetime.now(UTC).isoformat()
    timeout = config.trial_timeout_s or max(
        MIN_TRIAL_TIMEOUT_S,
        4 * num_clients * config.file_size_bytes / config.seeder_upload_limit_bps + 30,
    )
    if config.work_dir is not None:
        config.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p2p-trial-", dir=config.work_dir) as directory:
        trial_dir = Path(directory)
        source = trial_dir / "source.bin"
        await asyncio.to_thread(prepare_source, source, config.file_size_bytes, config.seed)
        manifest = await asyncio.to_thread(build_manifest, source, config.chunk_size_bytes)
        tracker = FastAPI()
        tracker.include_router(app.router)
        registry = SwarmRegistry()
        tracker.dependency_overrides[get_registry] = lambda: registry
        peers: list[SwarmPeer] = []
        observations: dict[int, Row] = {}
        elapsed_start = time.perf_counter()
        download_start: float | None = None
        trial_failure = ""
        seeder: SwarmPeer | None = None

        async def download_client(index: int, peer: SwarmPeer) -> None:
            assert download_start is not None
            reason = ""
            hash_failures = 0
            try:
                target = await peer.download()
                if await asyncio.to_thread(file_hash, target) != manifest["file_sha256"]:
                    raise FileIntegrityError("independent final-file SHA-256 mismatch")
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                hash_failures = int(isinstance(exc, FileIntegrityError))
            observations[index] = {
                "completion_time_s": time.perf_counter() - download_start,
                "success": str(not reason).lower(),
                "failure_reason": reason,
                "full_file_hash_failure_count": hash_failures,
            }

        try:
            async with asyncio.timeout(timeout):
                seeder = SwarmPeer(
                    manifest,
                    "http://tracker.test",
                    trial_dir / "seed",
                    seed_file=source,
                    tracker_transport=httpx.ASGITransport(app=tracker),
                    peer_id="origin",
                    upload_rate_limit=config.seeder_upload_limit_bps,
                )
                peers.append(seeder)
                for index in range(num_clients):
                    peers.append(
                        SwarmPeer(
                            manifest,
                            "http://tracker.test",
                            trial_dir / f"client-{index}",
                            tracker_transport=httpx.ASGITransport(app=tracker),
                            peer_id=f"client-{index}",
                            upload_enabled=mode == "p2p",
                            upload_rate_limit=config.leecher_upload_limit_bps,
                            scheduler_seed=config.seed + index,
                        )
                    )
                await seeder.start()
                async with asyncio.TaskGroup() as group:
                    for peer in peers[1:]:
                        group.create_task(peer.start())
                # All clients are registered before the common flash-crowd release.
                download_start = time.perf_counter()
                async with asyncio.TaskGroup() as group:
                    for index, peer in enumerate(peers[1:]):
                        group.create_task(download_client(index, peer))
        except Exception as exc:
            trial_failure = f"{type(exc).__name__}: {exc}"
        finally:
            elapsed = time.perf_counter() - (download_start or elapsed_start)
            outcomes = await asyncio.gather(
                *(peer.close() for peer in peers), return_exceptions=True
            )
            cleanup_errors = [
                str(result) for result in outcomes if isinstance(result, BaseException)
            ]
            if cleanup_errors:
                trial_failure += f" cleanup failed: {'; '.join(cleanup_errors)}"

        origin_uploaded = seeder.bytes_uploaded if seeder is not None else 0
        leecher_uploaded = sum(peer.bytes_uploaded for peer in peers[1:])
        for index in range(num_clients):
            if index not in observations:
                observations[index] = {
                    "completion_time_s": elapsed,
                    "success": "false",
                    "failure_reason": trial_failure or "trial aborted",
                    "full_file_hash_failure_count": 0,
                }
        makespan = max(float(row["completion_time_s"]) for row in observations.values())
        rows: list[Row] = []
        for index, observation in sorted(observations.items()):
            client_peer = peers[index + 1] if index + 1 < len(peers) else None
            if cleanup_errors:
                observation.update(success="false", failure_reason=trial_failure)
            duration = float(observation["completion_time_s"])
            rows.append(
                {
                    **system_meta,
                    **observation,
                    "experiment_id": config.experiment_id,
                    "run_id": run_id,
                    "mode": mode,
                    "repetition": repetition,
                    "is_warmup": str(is_warmup).lower(),
                    "num_clients": num_clients,
                    "client_id": f"client-{index}",
                    "file_size_bytes": config.file_size_bytes,
                    "chunk_size_bytes": config.chunk_size_bytes,
                    "seeder_upload_limit_bytes_per_s": config.seeder_upload_limit_bps,
                    "leecher_upload_limit_bytes_per_s": config.leecher_upload_limit_bps,
                    "download_throughput_bytes_per_s": (
                        config.file_size_bytes / duration if observation["success"] == "true" else 0
                    ),
                    "bytes_uploaded_origin_peer": origin_uploaded,
                    "bytes_uploaded_leecher_peers": leecher_uploaded,
                    "total_retry_count": client_peer.total_retries if client_peer else 0,
                    "chunk_hash_failure_count": client_peer.chunk_hash_failures
                    if client_peer
                    else 0,
                    "bytes_downloaded": client_peer.bytes_downloaded if client_peer else 0,
                    "seed": config.seed,
                    "scheduler_seed": config.seed + index,
                    "scheduler_seed_base": config.seed,
                    "file_sha256": manifest["file_sha256"],
                    "started_at_utc": started_at,
                    "run_makespan_s": makespan,
                    "trial_timeout_s": timeout,
                    "notes": config.notes,
                }
            )
        return rows


async def run_experiments(config: ExperimentConfig) -> list[Row]:
    """Interleave configurations, flush each trial, and log warmups in the raw CSV."""
    validate_csv(config.output_path)
    metadata = await asyncio.to_thread(get_system_metadata)
    rng = random.Random(config.seed)
    all_rows: list[Row] = []
    for repetition in range(0 if config.warmup else 1, config.repetitions + 1):
        trials = [(mode, count) for count in config.client_counts for mode in config.modes]
        rng.shuffle(trials)
        for mode, count in trials:
            logger.info("Starting %s N=%d repetition=%d", mode, count, repetition)
            rows = await run_single_trial(
                config,
                mode=mode,
                num_clients=count,
                repetition=repetition,
                is_warmup=repetition == 0,
                system_meta=metadata,
            )
            await asyncio.to_thread(append_rows, config.output_path, rows)
            all_rows.extend(rows)
            logger.info(
                "Finished %s N=%d repetition=%d: %d/%d clients succeeded; makespan %.3fs",
                mode,
                count,
                repetition,
                sum(row["success"] == "true" for row in rows),
                count,
                float(rows[0]["run_makespan_s"]),
            )
    return all_rows


def parse_args(args: list[str] | None = None) -> ExperimentConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", default="1,2,4,8")
    parser.add_argument("--modes", default="baseline,p2p")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--file-size", type=int, default=DEFAULT_FILE_SIZE, help="bytes")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="bytes")
    parser.add_argument("--seeder-rate", type=float, default=DEFAULT_SEEDER_RATE, help="bytes/s")
    parser.add_argument("--leecher-rate", type=float, default=DEFAULT_LEECHER_RATE, help="bytes/s")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("bench/results/experiments.csv"))
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--trial-timeout", type=float, help="override per-trial deadline in seconds"
    )
    parser.add_argument(
        "--notes", default="RAM, resource usage and external activity not collected"
    )
    parser.add_argument("--experiment-id", default=f"exp-{datetime.now(UTC):%Y%m%dT%H%M%SZ}")
    parser.add_argument("--quick", action="store_true", help="smoke only: 1 MiB, 2 reps, all N")
    parsed = parser.parse_args(args)
    try:
        return ExperimentConfig(
            experiment_id=parsed.experiment_id,
            output_path=parsed.output,
            modes=tuple(value.strip().lower() for value in parsed.modes.split(",")),
            client_counts=tuple(int(value) for value in parsed.clients.split(",")),
            repetitions=2 if parsed.quick else parsed.repetitions,
            warmup=not parsed.no_warmup,
            file_size_bytes=1024 * 1024 if parsed.quick else parsed.file_size,
            chunk_size_bytes=parsed.chunk_size,
            seeder_upload_limit_bps=parsed.seeder_rate,
            leecher_upload_limit_bps=parsed.leecher_rate,
            seed=parsed.seed,
            work_dir=parsed.work_dir,
            trial_timeout_s=parsed.trial_timeout,
            notes=parsed.notes,
        )
    except ValueError as exc:
        parser.error(str(exc))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("p2p").setLevel(logging.WARNING)
    config = parse_args()
    try:
        rows = asyncio.run(run_experiments(config))
    except (OSError, ValueError) as exc:
        logger.error("Experiment failed: %s", exc)
        raise SystemExit(1) from exc
    logger.info("Wrote %d observations to %s", len(rows), config.output_path)
    if any(row["success"] != "true" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
