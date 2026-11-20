"""Read recorded trials through the existing harness's validation and analysis."""

from dataclasses import asdict
from pathlib import Path
from typing import Any


def read_experiments(csv_path: Path) -> dict[str, Any]:
    """No experiment execution or fallback sample data."""
    if not csv_path.is_file():
        return {"available": False, "error": "No recorded benchmark CSV found", "summaries": []}
    try:
        from bench.analysis import calculate_stats, parse_csv_results

        runs, audit, caption = parse_csv_results(csv_path)
        return {
            "available": True,
            "source": "bench/results/experiments.csv",
            "caption": caption,
            "summaries": [asdict(summary) for summary in calculate_stats(runs)],
            "audit": audit,
        }
    except (ImportError, ValueError, OSError, KeyError, OverflowError) as exc:
        return {"available": False, "error": str(exc), "summaries": []}
