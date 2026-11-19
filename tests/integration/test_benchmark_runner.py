"""Real loopback transfers verify benchmark plumbing without speed assertions."""

import asyncio
import csv
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bench.run_experiments import ExperimentConfig, get_system_metadata, run_experiments
from p2p.peer.client import SwarmPeer
from p2p.tracker.server import app


def tiny_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        "correctness-test",
        tmp_path / "results.csv",
        repetitions=1,
        file_size_bytes=4096,
        chunk_size_bytes=128,
        work_dir=tmp_path / "work",
    )


async def test_real_full_client_sweep_isolated_verified_and_clean(tmp_path: Path) -> None:
    before = set(asyncio.all_tasks())
    overrides = app.dependency_overrides.copy()
    config = tiny_config(tmp_path)
    async with asyncio.timeout(30):
        rows = await run_experiments(config)
    assert len(rows) == 60  # 2 modes * (1+2+4+8) clients * (warmup+1 measured)
    assert all(row["success"] == "true" for row in rows)
    assert all(row["bytes_downloaded"] == 4096 for row in rows)
    assert len({row["file_sha256"] for row in rows}) == 1
    assert len({row["run_id"] for row in rows}) == 16
    assert all(
        row["scheduler_seed"] == 42 + int(str(row["client_id"]).split("-")[1]) for row in rows
    )
    assert {row["is_warmup"] for row in rows} == {"true", "false"}
    for row in rows:
        if row["mode"] == "baseline":
            assert row["bytes_uploaded_leecher_peers"] == 0
            assert row["bytes_uploaded_origin_peer"] == 4096 * int(row["num_clients"])
    with config.output_path.open(newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == len(rows)
    assert app.dependency_overrides == overrides
    assert not list(config.work_dir.iterdir())  # type: ignore[union-attr]
    assert set(asyncio.all_tasks()) == before


@pytest.mark.parametrize("failure", ["download", "startup", "timeout"])
async def test_failed_trials_are_recorded_without_invented_hash_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    config = replace(tiny_config(tmp_path), modes=("baseline",), client_counts=(2,), warmup=False)
    if failure == "startup":
        monkeypatch.setattr(
            SwarmPeer, "start", AsyncMock(side_effect=RuntimeError("startup failure"))
        )
    elif failure == "download":
        monkeypatch.setattr(
            SwarmPeer, "download", AsyncMock(side_effect=OSError("transfer failure"))
        )
    else:

        async def stalled_download(peer: SwarmPeer) -> Path:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        monkeypatch.setattr(SwarmPeer, "download", stalled_download)
        config = replace(config, trial_timeout_s=0.1)
    before = set(asyncio.all_tasks())
    async with asyncio.timeout(5):
        rows = await run_experiments(config)
    assert len(rows) == 2
    assert all(row["success"] == "false" and row["failure_reason"] for row in rows)
    assert all(row["full_file_hash_failure_count"] == 0 for row in rows)
    assert not list(config.work_dir.iterdir())  # type: ignore[union-attr]
    assert set(asyncio.all_tasks()) == before


async def test_external_cancellation_closes_peers_and_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def blocked_download(peer: SwarmPeer) -> Path:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(SwarmPeer, "download", blocked_download)
    config = replace(tiny_config(tmp_path), client_counts=(1,), warmup=False)
    before = set(asyncio.all_tasks())
    async with asyncio.timeout(5):
        task = asyncio.create_task(run_experiments(config))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not config.output_path.exists()
    assert not list(config.work_dir.iterdir())  # type: ignore[union-attr]
    assert set(asyncio.all_tasks()) == before


async def test_independent_hash_mismatch_is_counted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("bench.run_experiments.file_hash", lambda path: "incorrect")
    config = replace(tiny_config(tmp_path), client_counts=(1,), modes=("baseline",), warmup=False)
    async with asyncio.timeout(5):
        rows = await run_experiments(config)
    assert rows[0]["success"] == "false"
    assert rows[0]["full_file_hash_failure_count"] == 1


def test_system_metadata_has_no_user_or_machine_name() -> None:
    metadata = get_system_metadata()
    assert "loopback" in str(metadata["network_profile"])
    assert "hostname" not in metadata and "username" not in metadata
