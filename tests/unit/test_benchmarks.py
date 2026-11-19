"""Benchmark input validation and analysis arithmetic (synthetic fixtures only)."""

import csv
from dataclasses import replace
from pathlib import Path

import pytest

from bench.plot_results import calculate_stats, generate_all_plots, parse_csv_results
from bench.run_experiments import (
    CSV_FIELDNAMES,
    ExperimentConfig,
    Row,
    append_rows,
    parse_args,
    prepare_source,
)


@pytest.mark.parametrize(
    "args",
    [
        ["--clients", ""],
        ["--clients", "0"],
        ["--clients", "31"],
        ["--clients", "1,1"],
        ["--clients", "two"],
        ["--modes", "unknown"],
        ["--modes", "p2p,p2p"],
        ["--repetitions", "0"],
        ["--file-size", "0"],
        ["--chunk-size", "1048577"],
        ["--seeder-rate", "nan"],
        ["--leecher-rate", "inf"],
        ["--trial-timeout", "-1"],
    ],
)
def test_invalid_arguments_fail_before_running(args: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        parse_args(args)
    assert error.value.code == 2


def test_default_sweep_and_quick_mode() -> None:
    config = parse_args([])
    assert config.client_counts == (1, 2, 4, 8)
    assert config.modes == ("baseline", "p2p")
    assert config.repetitions == 5 and config.warmup
    assert config.file_size_bytes == 10 * 1024 * 1024
    quick = parse_args(["--quick"])
    assert quick.client_counts == config.client_counts
    assert quick.file_size_bytes == 1024 * 1024 and quick.repetitions == 2


def test_chunk_count_bound(tmp_path: Path) -> None:
    config = ExperimentConfig("test", tmp_path / "test.csv")
    with pytest.raises(ValueError, match="chunk count"):
        replace(config, chunk_size_bytes=1)


def synthetic_rows(run_id: str = "one", duration: float = 2.0) -> list[Row]:
    """Deliberately synthetic input for validating aggregation, never benchmark evidence."""
    rows: list[Row] = []
    for index in range(2):
        row: Row = dict.fromkeys(CSV_FIELDNAMES, "fixture")
        row.update(
            experiment_id="synthetic",
            run_id=run_id,
            mode="p2p",
            num_clients=2,
            client_id=f"client-{index}",
            repetition=1,
            is_warmup="false",
            success="true",
            completion_time_s=duration - 0.5 * index,
            run_makespan_s=duration,
            file_size_bytes=100,
            chunk_size_bytes=10,
            bytes_downloaded=100,
            bytes_uploaded_origin_peer=150,
            bytes_uploaded_leecher_peers=50,
            failure_reason="",
        )
        rows.append(row)
    return rows


def test_append_schema_and_reproducible_payload(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    append_rows(path, synthetic_rows())
    append_rows(path, synthetic_rows("two"))
    with path.open(newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 4
    before = path.read_bytes()
    other = tmp_path / "incompatible.csv"
    other.write_text("bad,header\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        append_rows(other, synthetic_rows())
    assert other.read_text() == "bad,header\n"
    assert path.read_bytes() == before
    left, right = tmp_path / "a.bin", tmp_path / "b.bin"
    prepare_source(left, 1024 * 1024 + 3, 42)
    prepare_source(right, 1024 * 1024 + 3, 42)
    assert left.read_bytes() == right.read_bytes()


def test_analysis_uses_whole_trials_and_counts_run_upload_totals_once(tmp_path: Path) -> None:
    rows = synthetic_rows() + synthetic_rows("two", 4.0)
    warmup = synthetic_rows("warmup", 999.0)
    for row in warmup:
        row["is_warmup"] = "true"
    failed = synthetic_rows("failed", 0.01)
    failed[1].update(success="false", failure_reason="test failure")
    path = tmp_path / "data.csv"
    append_rows(path, rows + warmup + failed + synthetic_rows("partial")[:1])
    runs, audit, _ = parse_csv_results(path)
    assert len(runs) == 2
    stats = calculate_stats(runs)[0]
    assert stats.count == 2
    assert stats.means["makespan_s"] == 3.0
    assert stats.stds["makespan_s"] == pytest.approx(2**0.5)
    assert stats.means["origin_upload_bytes"] == 150  # repeated across clients, not summed
    assert stats.means["peer_share_pct"] == 25
    assert stats.means["aggregate_throughput_bytes_per_s"] == 75  # mean(200/2, 200/4)
    assert len(audit) == 5
    assert sum(row["reason"] == "included" for row in audit) == 2
    paths = generate_all_plots(path, tmp_path / "plots")
    assert len(paths) == 4 and all(path.stat().st_size > 0 for path in paths)
    assert (tmp_path / "plots" / "trial_audit.csv").is_file()


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"experiment_id": "other"}, "exactly one experiment"),
        ({"file_sha256": "different"}, "mixed workloads"),
        ({"host_os": "different"}, "mixed workloads"),
    ],
)
def test_analysis_rejects_mixed_experiments_or_conditions(
    tmp_path: Path,
    mutation: dict[str, str],
    match: str,
) -> None:
    rows = synthetic_rows()
    rows[1].update(mutation)
    path = tmp_path / "data.csv"
    append_rows(path, rows)
    with pytest.raises(ValueError, match=match):
        parse_csv_results(path)


def test_analysis_rejects_duplicate_client_rows_and_invalid_numbers(tmp_path: Path) -> None:
    rows = synthetic_rows()
    path = tmp_path / "data.csv"
    append_rows(path, rows + rows)
    with pytest.raises(ValueError, match="duplicate client"):
        parse_csv_results(path)
    bad_path = tmp_path / "bad.csv"
    for row in rows:
        row["run_makespan_s"] = float("nan")
    append_rows(bad_path, rows)
    with pytest.raises(ValueError, match="invalid run_makespan"):
        parse_csv_results(bad_path)
