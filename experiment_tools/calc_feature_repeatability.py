"""Calculate a transparent nearest-neighbour feature repeatability reference metric."""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .common import (
        ToolError,
        ensure_output_dir,
        make_metadata,
        numeric_stats,
        parse_bool,
        parse_float,
        read_csv_rows,
        read_optional_config,
        required_text,
        write_csv,
        write_json,
    )
except ImportError:  # pragma: no cover
    from common import (  # type: ignore
        ToolError,
        ensure_output_dir,
        make_metadata,
        numeric_stats,
        parse_bool,
        parse_float,
        read_csv_rows,
        read_optional_config,
        required_text,
        write_csv,
        write_json,
    )


FEATURE_COLUMNS = ("frame_id", "timestamp", "feature_id", "x", "y", "valid")
PAIR_COLUMNS = ("frame_a", "frame_b", "scenario_id")
OUTPUT_COLUMNS = (
    "frame_a",
    "frame_b",
    "scenario_id",
    "valid_features_a",
    "valid_features_b",
    "matched_features",
    "repeat_rate",
    "distance_threshold",
    "status",
    "invalid_reason",
)


def load_features(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    rows = read_csv_rows(path, FEATURE_COLUMNS, "features CSV")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        frame_id = required_text(row, "frame_id", row_number, "features CSV")
        feature_id = required_text(row, "feature_id", row_number, "features CSV")
        key = (frame_id, feature_id)
        if key in seen:
            raise ToolError(f"features CSV row {row_number}: duplicate feature_id in frame", 2)
        seen.add(key)
        grouped[frame_id].append(
            {
                "frame_id": frame_id,
                "timestamp": parse_float(row["timestamp"], "timestamp", row_number, "features CSV"),
                "feature_id": feature_id,
                "x": parse_float(row["x"], "x", row_number, "features CSV"),
                "y": parse_float(row["y"], "y", row_number, "features CSV"),
                "valid": parse_bool(row["valid"], "valid", row_number, "features CSV"),
            }
        )
    if not grouped:
        raise ToolError("features CSV contains no data rows", 2)
    return dict(grouped)


def load_pairs(path: str | Path) -> list[dict[str, str]]:
    rows = read_csv_rows(path, PAIR_COLUMNS, "frame pairs CSV")
    pairs: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=2):
        pairs.append(
            {
                "frame_a": required_text(row, "frame_a", row_number, "frame pairs CSV"),
                "frame_b": required_text(row, "frame_b", row_number, "frame pairs CSV"),
                "scenario_id": required_text(row, "scenario_id", row_number, "frame pairs CSV"),
            }
        )
    if not pairs:
        raise ToolError("frame pairs CSV contains no data rows", 2)
    return pairs


def match_pair(features_a: list[dict[str, Any]], features_b: list[dict[str, Any]], threshold: float) -> int:
    valid_a = [feature for feature in features_a if feature["valid"]]
    valid_b = [feature for feature in features_b if feature["valid"]]
    used_b: set[str] = set()
    matched = 0
    for feature_a in sorted(valid_a, key=lambda item: item["feature_id"]):
        candidates: list[tuple[float, str]] = []
        for feature_b in valid_b:
            if feature_b["feature_id"] in used_b:
                continue
            distance = math.hypot(feature_a["x"] - feature_b["x"], feature_a["y"] - feature_b["y"])
            candidates.append((distance, feature_b["feature_id"]))
        if not candidates:
            continue
        distance, feature_id = min(candidates, key=lambda item: (item[0], item[1]))
        if distance <= threshold:
            used_b.add(feature_id)
            matched += 1
    return matched


def calculate(features: dict[str, list[dict[str, Any]]], pairs: list[dict[str, str]], threshold: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for pair in pairs:
        frame_a = features.get(pair["frame_a"])
        frame_b = features.get(pair["frame_b"])
        valid_a = sum(1 for feature in frame_a or [] if feature["valid"])
        valid_b = sum(1 for feature in frame_b or [] if feature["valid"])
        if frame_a is None or frame_b is None:
            missing = "frame_a not found" if frame_a is None else "frame_b not found"
            output.append({**pair, "valid_features_a": valid_a, "valid_features_b": valid_b, "matched_features": 0, "repeat_rate": "", "distance_threshold": threshold, "status": "INVALID", "invalid_reason": missing})
            continue
        if valid_a == 0:
            output.append({**pair, "valid_features_a": 0, "valid_features_b": valid_b, "matched_features": 0, "repeat_rate": "", "distance_threshold": threshold, "status": "INVALID", "invalid_reason": "valid_features_a is zero"})
            continue
        matched = match_pair(frame_a, frame_b, threshold)
        repeat_rate = matched / valid_a
        status = "PASS" if valid_b else "PARTIAL"
        reason = "" if valid_b else "valid_features_b is zero"
        output.append({**pair, "valid_features_a": valid_a, "valid_features_b": valid_b, "matched_features": matched, "repeat_rate": repeat_rate, "distance_threshold": threshold, "status": status, "invalid_reason": reason})
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate reference feature repeatability from feature and frame-pair CSV files.")
    parser.add_argument("--features", required=True, help="feature CSV")
    parser.add_argument("--pairs", required=True, help="adjacent frame-pair CSV")
    parser.add_argument("--output", required=True, help="output directory")
    parser.add_argument("--config", help="optional JSON config; its SHA-256 is recorded")
    parser.add_argument("--distance-threshold", type=float, help="match distance threshold")
    parser.add_argument("--match-policy", default="greedy_nearest_one_to_one", help="policy label to record")
    return parser


def run(args: argparse.Namespace) -> int:
    config, config_path = read_optional_config(args.config)
    threshold_value = args.distance_threshold
    if threshold_value is None:
        threshold_value = config.get("distance_threshold", 0.05)
    try:
        threshold = float(threshold_value)
    except (TypeError, ValueError) as exc:
        raise ToolError("distance threshold must be numeric", 2) from exc
    if not math.isfinite(threshold) or threshold < 0:
        raise ToolError("distance threshold must be a finite non-negative number", 2)
    features = load_features(args.features)
    pairs = load_pairs(args.pairs)
    samples = calculate(features, pairs, threshold)
    output_dir = ensure_output_dir(args.output)
    rates = [float(sample["repeat_rate"]) for sample in samples if sample["repeat_rate"] != ""]
    valid_pairs = sum(1 for sample in samples if sample["status"] != "INVALID")
    summary = {
        "status": "COMPLETE",
        "method": "greedy nearest-neighbour one-to-one reference matching",
        "match_policy": args.match_policy,
        "distance_threshold": threshold,
        "pair_count": len(samples),
        "valid_pair_count": valid_pairs,
        "invalid_pair_count": len(samples) - valid_pairs,
        "repeat_rate": numeric_stats(rates),
        "note": "Reference evaluation implementation only; not the competition feature definition or dynamic LiDAR algorithm.",
    }
    write_csv(output_dir / "feature_pair_samples.csv", OUTPUT_COLUMNS, samples)
    write_json(output_dir / "feature_summary.json", summary)
    write_json(
        output_dir / "run_metadata.json",
        make_metadata(
            {"features": args.features, "pairs": args.pairs},
            config_path,
            {"operation": "feature_repeatability", "output_files": ["feature_pair_samples.csv", "feature_summary.json"]},
        ),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
