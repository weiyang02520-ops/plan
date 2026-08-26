"""Check a JSON bag-inspection manifest without requiring ROS2."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

try:
    from .common import ToolError, ensure_output_dir, make_metadata, read_json, required_text, write_json
except ImportError:  # pragma: no cover
    from common import ToolError, ensure_output_dir, make_metadata, read_json, required_text, write_json  # type: ignore


REQUIRED_MANIFEST_FIELDS = (
    "bag_id",
    "bag_path",
    "bag_sha256",
    "scenario_id",
    "required_topics",
    "not_applicable_topics",
    "topics",
)
REQUIRED_TOPIC_FIELDS = (
    "name",
    "type",
    "message_count",
    "start_time",
    "end_time",
    "average_frequency",
    "max_gap",
    "timestamp_valid",
    "field_check",
    "coverage_valid",
)


def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ToolError(f"manifest field {field} must be a list", 2)
    return value


def require_nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ToolError(f"manifest field {field} must be a non-negative number", 2)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"manifest field {field} must be a non-negative number", 2) from exc
    if not math.isfinite(number) or number < 0:
        raise ToolError(f"manifest field {field} must be a non-negative number", 2)
    return number


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ToolError("manifest must contain a JSON object", 2)
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in value]
    if missing:
        raise ToolError(f"manifest is missing fields {missing}", 2)
    bag_id = str(value["bag_id"]).strip()
    bag_path = str(value["bag_path"]).strip()
    bag_sha256 = str(value["bag_sha256"]).strip()
    scenario_id = str(value["scenario_id"]).strip()
    if not all((bag_id, bag_path, bag_sha256, scenario_id)):
        raise ToolError("bag_id, bag_path, bag_sha256 and scenario_id must be non-empty", 2)
    required = [str(item).strip() for item in require_list(value["required_topics"], "required_topics")]
    not_applicable = [str(item).strip() for item in require_list(value["not_applicable_topics"], "not_applicable_topics")]
    if any(not item for item in required + not_applicable) or len(set(required)) != len(required) or len(set(not_applicable)) != len(not_applicable):
        raise ToolError("required_topics and not_applicable_topics must contain unique non-empty names", 2)
    topics_value = require_list(value["topics"], "topics")
    topics: dict[str, dict[str, Any]] = {}
    for index, topic_value in enumerate(topics_value, start=1):
        if not isinstance(topic_value, dict):
            raise ToolError(f"topics item {index} must be an object", 2)
        missing_topic = [field for field in REQUIRED_TOPIC_FIELDS if field not in topic_value]
        if missing_topic:
            raise ToolError(f"topics item {index} is missing fields {missing_topic}", 2)
        name = str(topic_value["name"]).strip()
        if not name or name in topics:
            raise ToolError(f"topics item {index} has an empty or duplicate name", 2)
        message_count = topic_value["message_count"]
        if isinstance(message_count, bool) or not isinstance(message_count, int) or message_count < 0:
            raise ToolError(f"topics item {index} message_count must be a non-negative integer", 2)
        start_time = require_nonnegative_number(topic_value["start_time"], f"topics[{index}].start_time")
        end_time = require_nonnegative_number(topic_value["end_time"], f"topics[{index}].end_time")
        average_frequency = require_nonnegative_number(topic_value["average_frequency"], f"topics[{index}].average_frequency")
        max_gap = require_nonnegative_number(topic_value["max_gap"], f"topics[{index}].max_gap")
        if end_time < start_time:
            raise ToolError(f"topics item {index} end_time precedes start_time", 2)
        if not isinstance(topic_value["timestamp_valid"], bool) or not isinstance(topic_value["coverage_valid"], bool) or not isinstance(topic_value["field_check"], bool):
            raise ToolError(f"topics item {index} timestamp_valid, field_check and coverage_valid must be boolean", 2)
        topics[name] = {
            "name": name,
            "type": str(topic_value["type"]),
            "message_count": message_count,
            "start_time": start_time,
            "end_time": end_time,
            "average_frequency": average_frequency,
            "max_gap": max_gap,
            "timestamp_valid": topic_value["timestamp_valid"],
            "field_check": topic_value["field_check"],
            "coverage_valid": topic_value["coverage_valid"],
        }
    declared_before_run = value.get("not_applicable_declared_before_run", False)
    if not isinstance(declared_before_run, bool):
        raise ToolError("not_applicable_declared_before_run must be boolean when present", 2)
    return {
        "bag_id": bag_id,
        "bag_path": bag_path,
        "bag_sha256": bag_sha256,
        "scenario_id": scenario_id,
        "required_topics": required,
        "not_applicable_topics": not_applicable,
        "not_applicable_declared_before_run": declared_before_run,
        "topics": topics,
        "dataset_label": value.get("dataset_label", ""),
    }


def inspect(manifest: dict[str, Any]) -> dict[str, Any]:
    topics = manifest["topics"]
    declared_na = set(manifest["not_applicable_topics"]) if manifest["not_applicable_declared_before_run"] else set()
    required = set(manifest["required_topics"])
    active_required = required - declared_na
    topic_status: list[dict[str, Any]] = []
    required_failures: list[str] = []
    non_core_issues: list[str] = []
    for name in manifest["required_topics"]:
        if name in declared_na:
            topic_status.append({"name": name, "status": "NOT_APPLICABLE", "required": True, "reason": "declared before run"})
            continue
        topic = topics.get(name)
        if topic is None:
            topic_status.append({"name": name, "status": "FAIL", "required": True, "reason": "required topic missing"})
            required_failures.append(name)
            continue
        status, reason = assess_topic(topic)
        topic_status.append({"name": name, "status": status, "required": True, "reason": reason})
        if status == "FAIL":
            required_failures.append(name)
        elif status != "PASS":
            non_core_issues.append(name)
    for name, topic in topics.items():
        if name in required:
            continue
        status, reason = assess_topic(topic)
        topic_status.append({"name": name, "status": status, "required": False, "reason": reason})
        if status != "PASS":
            non_core_issues.append(name)
    undeclared_na = set(manifest["not_applicable_topics"]) - declared_na
    for name in sorted(undeclared_na):
        if name in active_required and name not in topics:
            # It remains a required missing topic; this records why it was not excluded.
            if name not in required_failures:
                required_failures.append(name)
    if required_failures:
        overall_status, grade = "FAIL", "C"
    elif non_core_issues:
        overall_status, grade = "PARTIAL", "B"
    elif not active_required:
        overall_status, grade = "NOT_APPLICABLE", "A"
    else:
        overall_status, grade = "PASS", "A"
    return {
        "status": overall_status,
        "overall_grade": grade,
        "bag_id": manifest["bag_id"],
        "scenario_id": manifest["scenario_id"],
        "required_topic_count": len(manifest["required_topics"]),
        "active_required_topic_count": len(active_required),
        "declared_not_applicable_topics": sorted(declared_na),
        "undeclared_not_applicable_topics": sorted(undeclared_na),
        "required_failures": sorted(set(required_failures)),
        "topic_status": topic_status,
        "rule": "A requires all active required topics complete; predeclared NOT_APPLICABLE topics are not counted as missing.",
        "note": "A missing topic is never converted to NOT_APPLICABLE after inspection.",
    }


def assess_topic(topic: dict[str, Any]) -> tuple[str, str]:
    if topic["message_count"] == 0 or not topic["timestamp_valid"] or not topic["coverage_valid"]:
        reasons = []
        if topic["message_count"] == 0:
            reasons.append("zero messages")
        if not topic["timestamp_valid"]:
            reasons.append("invalid timestamps")
        if not topic["coverage_valid"]:
            reasons.append("invalid coverage")
        return "FAIL", "; ".join(reasons)
    if not topic["field_check"]:
        return "PARTIAL", "field check failed"
    return "PASS", "all manifest checks passed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a JSON bag inspection manifest without requiring ROS2.")
    parser.add_argument("--manifest", required=True, help="JSON bag inspection manifest")
    parser.add_argument("--output", required=True, help="output directory")
    return parser


def run(args: argparse.Namespace) -> int:
    raw_manifest = read_json(args.manifest, "bag inspection manifest")
    manifest = validate_manifest(raw_manifest)
    report = inspect(manifest)
    output_dir = ensure_output_dir(args.output)
    write_json(output_dir / "rosbag_check_report.json", report)
    write_json(
        output_dir / "run_metadata.json",
        make_metadata(
            {"manifest": args.manifest},
            None,
            {"operation": "rosbag_manifest_check", "output_files": ["rosbag_check_report.json"]},
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
