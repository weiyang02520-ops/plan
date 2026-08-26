"""Summarise transparent relocalization trial outcomes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from .common import (
        ToolError,
        ensure_output_dir,
        make_metadata,
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
        parse_bool,
        parse_float,
        read_csv_rows,
        read_optional_config,
        required_text,
        write_csv,
        write_json,
    )


REQUIRED_COLUMNS = (
    "trial_id",
    "scenario_id",
    "start_time",
    "end_time",
    "initial_pose_status",
    "success",
    "success_time",
    "position_error",
    "yaw_error",
    "timeout",
    "manual_takeover",
    "invalid",
    "invalid_reason",
    "bag_id",
)
OUTPUT_COLUMNS = REQUIRED_COLUMNS + ("status", "included_in_denominator", "decision_reason")


def load_trials(path: str | Path) -> list[dict[str, Any]]:
    rows = read_csv_rows(path, REQUIRED_COLUMNS, "relocalization trials CSV")
    trials: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        success = parse_bool(row["success"], "success", row_number, "relocalization trials CSV")
        timeout = parse_bool(row["timeout"], "timeout", row_number, "relocalization trials CSV")
        manual = parse_bool(row["manual_takeover"], "manual_takeover", row_number, "relocalization trials CSV")
        invalid = parse_bool(row["invalid"], "invalid", row_number, "relocalization trials CSV")
        if success and (timeout or manual or invalid):
            raise ToolError(f"relocalization trials CSV row {row_number}: success conflicts with failure/invalid flags", 2)
        trials.append(
            {
                "trial_id": required_text(row, "trial_id", row_number, "relocalization trials CSV"),
                "scenario_id": required_text(row, "scenario_id", row_number, "relocalization trials CSV"),
                "start_time": parse_float(row["start_time"], "start_time", row_number, "relocalization trials CSV"),
                "end_time": parse_float(row["end_time"], "end_time", row_number, "relocalization trials CSV"),
                "initial_pose_status": required_text(row, "initial_pose_status", row_number, "relocalization trials CSV"),
                "success": success,
                "success_time": parse_float(row["success_time"], "success_time", row_number, "relocalization trials CSV", allow_blank=True),
                "position_error": parse_float(row["position_error"], "position_error", row_number, "relocalization trials CSV", allow_blank=True),
                "yaw_error": parse_float(row["yaw_error"], "yaw_error", row_number, "relocalization trials CSV", allow_blank=True),
                "timeout": timeout,
                "manual_takeover": manual,
                "invalid": invalid,
                "invalid_reason": row["invalid_reason"].strip(),
                "bag_id": required_text(row, "bag_id", row_number, "relocalization trials CSV"),
            }
        )
    if not trials:
        raise ToolError("relocalization trials CSV contains no data rows", 2)
    return trials


def classify(trial: dict[str, Any], timeout_counts_as_failure: bool, manual_counts_as_failure: bool) -> dict[str, Any]:
    if trial["invalid"]:
        status = "INVALID"
        included = False
        reason = trial["invalid_reason"] or "invalid=true"
    elif trial["timeout"] and timeout_counts_as_failure:
        status = "FAILURE_TIMEOUT"
        included = True
        reason = "timeout=true counts as failure"
    elif trial["manual_takeover"] and manual_counts_as_failure:
        status = "FAILURE_MANUAL_TAKEOVER"
        included = True
        reason = "manual_takeover=true counts as failure"
    elif trial["timeout"]:
        status = "TIMEOUT_EXCLUDED_BY_CONFIG"
        included = False
        reason = "timeout=true excluded by configuration"
    elif trial["manual_takeover"]:
        status = "MANUAL_TAKEOVER_EXCLUDED_BY_CONFIG"
        included = False
        reason = "manual_takeover=true excluded by configuration"
    elif trial["success"]:
        status = "SUCCESS"
        included = True
        reason = "success=true"
    else:
        status = "FAILURE"
        included = True
        reason = "success=false without invalid flag"
    return {**trial, "status": status, "included_in_denominator": included, "decision_reason": reason}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate relocalization success rate from trial CSV.")
    parser.add_argument("--trials", required=True, help="relocalization_trials.csv")
    parser.add_argument("--output", required=True, help="output directory")
    parser.add_argument("--config", help="optional JSON config; its SHA-256 is recorded")
    return parser


def run(args: argparse.Namespace) -> int:
    config, config_path = read_optional_config(args.config)
    timeout_counts = bool(config.get("timeout_counts_as_failure", True))
    manual_counts = bool(config.get("manual_takeover_counts_as_failure", True))
    trials = load_trials(args.trials)
    checked = [classify(trial, timeout_counts, manual_counts) for trial in trials]
    output_dir = ensure_output_dir(args.output)
    invalid_count = sum(1 for trial in checked if trial["invalid"])
    included = [trial for trial in checked if trial["included_in_denominator"]]
    success_count = sum(1 for trial in included if trial["status"] == "SUCCESS")
    failure_count = len(included) - success_count
    timeout_count = sum(1 for trial in checked if trial["timeout"])
    manual_count = sum(1 for trial in checked if trial["manual_takeover"])
    success_rate = success_count / len(included) if included else None
    summary = {
        "status": "COMPLETE" if included else "INCOMPLETE",
        "trial_count": len(checked),
        "valid_trial_count": len(included),
        "successful_count": success_count,
        "failed_count": failure_count,
        "timeout_count": timeout_count,
        "manual_takeover_count": manual_count,
        "invalid_count": invalid_count,
        "excluded_by_config_count": len(checked) - len(included) - invalid_count,
        "success_rate": success_rate,
        "rules": {
            "invalid_excluded_from_denominator": True,
            "timeout_counts_as_failure": timeout_counts,
            "manual_takeover_counts_as_failure": manual_counts,
        },
        "note": "Success criteria and official >95%口径 remain provisional until confirmed by the organiser.",
    }
    write_csv(output_dir / "relocalization_trials_checked.csv", OUTPUT_COLUMNS, checked)
    write_json(output_dir / "relocalization_summary.json", summary)
    write_json(
        output_dir / "run_metadata.json",
        make_metadata(
            {"trials": args.trials},
            config_path,
            {"operation": "relocalization_success", "output_files": ["relocalization_trials_checked.csv", "relocalization_summary.json"]},
        ),
    )
    return 0 if included else 4


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
