"""Calculate transparent position errors from estimate/truth CSV files."""

from __future__ import annotations

import argparse
import bisect
import math
import sys
from pathlib import Path
from typing import Any

try:  # Supports both package imports in tests and direct script execution.
    from .common import (
        ToolError,
        ensure_output_dir,
        make_metadata,
        numeric_stats,
        parse_float,
        read_csv_rows,
        read_optional_config,
        required_text,
        write_csv,
        write_json,
    )
except ImportError:  # pragma: no cover - exercised by the CLI smoke test.
    from common import (  # type: ignore
        ToolError,
        ensure_output_dir,
        make_metadata,
        numeric_stats,
        parse_float,
        read_csv_rows,
        read_optional_config,
        required_text,
        write_csv,
        write_json,
    )


REQUIRED_COLUMNS = ("timestamp", "x", "y", "z")
SAMPLE_COLUMNS = (
    "estimate_timestamp",
    "truth_timestamp",
    "x_est",
    "y_est",
    "z_est",
    "x_truth",
    "y_truth",
    "z_truth",
    "plane_error",
    "elevation_abs_error",
    "valid",
    "status",
    "reason",
)


def load_positions(path: str | Path, label: str) -> list[dict[str, float]]:
    rows = read_csv_rows(path, REQUIRED_COLUMNS, label)
    positions: list[dict[str, float]] = []
    for row_number, row in enumerate(rows, start=2):
        positions.append(
            {
                "timestamp": parse_float(row["timestamp"], "timestamp", row_number, label) or 0.0,
                "x": parse_float(row["x"], "x", row_number, label) or 0.0,
                "y": parse_float(row["y"], "y", row_number, label) or 0.0,
                "z": parse_float(row["z"], "z", row_number, label) or 0.0,
            }
        )
    if not positions:
        raise ToolError(f"{label} contains no data rows", 2)
    return positions


def nearest_truth(estimate: dict[str, float], truth: list[dict[str, float]], truth_times: list[float]) -> dict[str, float] | None:
    index = bisect.bisect_left(truth_times, estimate["timestamp"])
    candidates: list[dict[str, float]] = []
    if index < len(truth):
        candidates.append(truth[index])
    if index > 0:
        candidates.append(truth[index - 1])
    if not candidates:
        return None
    return min(candidates, key=lambda item: (abs(item["timestamp"] - estimate["timestamp"]), item["timestamp"]))


def calculate(estimate: list[dict[str, float]], truth: list[dict[str, float]], tolerance: float) -> list[dict[str, Any]]:
    truth_sorted = sorted(truth, key=lambda item: item["timestamp"])
    truth_times = [item["timestamp"] for item in truth_sorted]
    output: list[dict[str, Any]] = []
    for item in estimate:
        matched = nearest_truth(item, truth_sorted, truth_times)
        if matched is None or abs(matched["timestamp"] - item["timestamp"]) > tolerance:
            output.append(
                {
                    "estimate_timestamp": item["timestamp"],
                    "truth_timestamp": "",
                    "x_est": item["x"],
                    "y_est": item["y"],
                    "z_est": item["z"],
                    "x_truth": "",
                    "y_truth": "",
                    "z_truth": "",
                    "plane_error": "",
                    "elevation_abs_error": "",
                    "valid": False,
                    "status": "UNMATCHED",
                    "reason": "no truth timestamp within sync tolerance",
                }
            )
            continue
        plane_error = math.hypot(item["x"] - matched["x"], item["y"] - matched["y"])
        elevation_error = abs(item["z"] - matched["z"])
        output.append(
            {
                "estimate_timestamp": item["timestamp"],
                "truth_timestamp": matched["timestamp"],
                "x_est": item["x"],
                "y_est": item["y"],
                "z_est": item["z"],
                "x_truth": matched["x"],
                "y_truth": matched["y"],
                "z_truth": matched["z"],
                "plane_error": plane_error,
                "elevation_abs_error": elevation_error,
                "valid": True,
                "status": "MATCHED",
                "reason": "",
            }
        )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate position errors from estimate/truth CSV files.")
    parser.add_argument("--estimate", required=True, help="estimate CSV: timestamp,x,y,z")
    parser.add_argument("--truth", required=True, help="truth CSV: timestamp,x,y,z")
    parser.add_argument("--output", required=True, help="output directory")
    parser.add_argument("--config", help="optional JSON config; its SHA-256 is recorded")
    parser.add_argument("--estimate-topic", default="", help="source topic label to record")
    parser.add_argument("--truth-format", default="csv", help="truth format label to record")
    parser.add_argument("--frame", default="unspecified", help="coordinate frame label")
    parser.add_argument("--sync-tolerance", type=float, help="maximum timestamp difference in seconds")
    parser.add_argument("--statistic", choices=("all", "mean", "rmse", "max", "p95"), default="all")
    return parser


def run(args: argparse.Namespace) -> int:
    config, config_path = read_optional_config(args.config)
    tolerance_value = args.sync_tolerance
    if tolerance_value is None:
        tolerance_value = config.get("sync_tolerance", 0.1)
    try:
        tolerance = float(tolerance_value)
    except (TypeError, ValueError) as exc:
        raise ToolError("sync tolerance must be numeric", 2) from exc
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ToolError("sync tolerance must be a finite non-negative number", 2)

    estimate = load_positions(args.estimate, "estimate CSV")
    truth = load_positions(args.truth, "truth CSV")
    samples = calculate(estimate, truth, tolerance)
    output_dir = ensure_output_dir(args.output)
    valid_samples = [sample for sample in samples if sample["valid"]]
    plane_values = [float(sample["plane_error"]) for sample in valid_samples]
    elevation_values = [float(sample["elevation_abs_error"]) for sample in valid_samples]
    summary = {
        "status": "COMPLETE" if valid_samples else "INCOMPLETE",
        "method": "nearest timestamp; no interpolation",
        "statistic_requested": args.statistic,
        "count": len(samples),
        "valid_count": len(valid_samples),
        "unmatched_count": len(samples) - len(valid_samples),
        "sync_tolerance": tolerance,
        "frame": args.frame,
        "estimate_topic": args.estimate_topic,
        "truth_format": args.truth_format,
        "plane_error": numeric_stats(plane_values),
        "elevation_abs_error": numeric_stats(elevation_values),
        "note": "Statistics are provided for analysis; official 20 cm evaluation口径 remains unconfirmed.",
    }
    write_csv(output_dir / "position_samples.csv", SAMPLE_COLUMNS, samples)
    write_json(output_dir / "position_summary.json", summary)
    write_json(
        output_dir / "run_metadata.json",
        make_metadata(
            {"estimate": args.estimate, "truth": args.truth},
            config_path,
            {"operation": "position_error", "output_files": ["position_samples.csv", "position_summary.json"]},
        ),
    )
    return 0 if valid_samples else 4


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
