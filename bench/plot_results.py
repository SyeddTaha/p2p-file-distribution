"""Headless plots and derived summaries: python -m bench.plot_results."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

if __package__:
    from bench.analysis import METRICS
    from bench.analysis import calculate_stats as calculate_stats
    from bench.analysis import parse_csv_results as parse_csv_results
else:
    from analysis import METRICS, calculate_stats, parse_csv_results  # type: ignore[no-redef,import-not-found]

logger = logging.getLogger(__name__)


def generate_all_plots(
    csv_path: Path,
    output_dir: Path,
    experiment_id: str | None = None,
) -> list[Path]:
    runs, audit, caption = parse_csv_results(csv_path, experiment_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "trial_audit.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    if not runs:
        raise ValueError("no complete, successful measured trials; see trial_audit.csv")
    stats = calculate_stats(runs)
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["mode", "num_clients", "successful_trials"]
        fields += [f"{key}_{suffix}" for key in METRICS for suffix in ("mean", "std")]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in stats:
            writer.writerow(
                {
                    "mode": item.mode,
                    "num_clients": item.num_clients,
                    "successful_trials": item.count,
                    **{f"{key}_mean": item.means[key] for key in METRICS},
                    **{f"{key}_std": item.stds[key] for key in METRICS},
                }
            )
    counts = "; ".join(f"{item.mode} N={item.num_clients}: n={item.count}" for item in stats)
    failed_count = sum(row["reason"] not in ("included", "warmup") for row in audit)
    caption += (
        f"\n{counts}\nExcluded failed/incomplete trials: {failed_count} (see trial_audit.csv)"
    )
    specs = (
        (
            "makespan_s",
            "Total distribution completion time",
            "Makespan (s)",
            1,
            "completion_time_vs_clients.png",
        ),
        (
            "aggregate_throughput_bytes_per_s",
            "Aggregate distribution throughput",
            "Aggregate throughput (MiB/s)",
            1048576,
            "throughput_vs_clients.png",
        ),
        (
            "origin_upload_bytes",
            "Origin upload contribution",
            "Origin payload uploaded (MiB)",
            1048576,
            "upload_contribution_vs_clients.png",
        ),
        (
            "peer_share_pct",
            "Upload contribution from leechers",
            "Payload served by peers (%)",
            1,
            "peer_share_vs_clients.png",
        ),
    )
    paths = []
    for key, title, ylabel, divisor, name in specs:
        fig, ax = plt.subplots(figsize=(10, 6))
        for mode, color in (("baseline", "#2463A6"), ("p2p", "#20804A")):
            items = [item for item in stats if item.mode == mode]
            if items:
                ax.errorbar(
                    [item.num_clients for item in items],
                    [item.means[key] / divisor for item in items],
                    yerr=[item.stds[key] / divisor for item in items],
                    label=mode,
                    color=color,
                    marker="o",
                    capsize=4,
                )
        ax.set(title=title, xlabel="Downloading clients (N)", ylabel=ylabel)
        ax.set_xticks(sorted({item.num_clients for item in stats}))
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.25)
        ax.legend()
        fig.text(0.5, 0.02, caption, ha="center", fontsize=7)
        fig.tight_layout(rect=(0, 0.17, 1, 1))
        path = output_dir / name
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
        logger.info("Generated %s", path)
    return paths


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("bench/results/experiments.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("bench/plots"))
    parser.add_argument("--experiment-id")
    args = parser.parse_args()
    try:
        generate_all_plots(args.csv, args.output_dir, args.experiment_id)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Plotting failed: {exc}\n")


if __name__ == "__main__":
    main()
