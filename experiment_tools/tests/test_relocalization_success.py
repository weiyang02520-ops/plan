import csv
import json
import tempfile
import unittest
from pathlib import Path

from experiment_tools.calc_relocalization_success import main


TRIAL_COLUMNS = [
    "trial_id", "scenario_id", "start_time", "end_time", "initial_pose_status", "success", "success_time",
    "position_error", "yaw_error", "timeout", "manual_takeover", "invalid", "invalid_reason", "bag_id",
]


def write_csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(TRIAL_COLUMNS)
        writer.writerows(rows)


class RelocalizationTests(unittest.TestCase):
    def test_denominator_and_failure_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "trials.csv", [
                ["success", "normal", 0, 5, "known-far", "true", 3, 0.1, 0.02, "false", "false", "false", "", "bag"],
                ["failure", "normal", 10, 15, "known-far", "false", "", 0.8, 0.4, "false", "false", "false", "", "bag"],
                ["timeout", "timeout", 20, 30, "known-far", "false", "", 1.5, 0.8, "true", "false", "false", "", "bag"],
                ["manual", "safety", 40, 45, "known-far", "false", "", 0.6, 0.5, "false", "true", "false", "", "bag"],
                ["invalid", "invalid", 50, 51, "not-recorded", "false", "", "", "", "false", "false", "true", "missing data", "bag"],
            ])
            output = root / "out"
            self.assertEqual(main(["--trials", str(root / "trials.csv"), "--output", str(output)]), 0)
            summary = json.loads((output / "relocalization_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["trial_count"], 5)
            self.assertEqual(summary["valid_trial_count"], 4)
            self.assertEqual(summary["successful_count"], 1)
            self.assertEqual(summary["failed_count"], 3)
            self.assertEqual(summary["timeout_count"], 1)
            self.assertEqual(summary["manual_takeover_count"], 1)
            self.assertEqual(summary["invalid_count"], 1)
            self.assertAlmostEqual(summary["success_rate"], 0.25)

    def test_all_invalid_returns_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "trials.csv", [["invalid", "x", 0, 1, "missing", "false", "", "", "", "false", "false", "true", "no bag", "bag"]])
            output = root / "out"
            self.assertEqual(main(["--trials", str(root / "trials.csv"), "--output", str(output)]), 4)
            summary = json.loads((output / "relocalization_summary.json").read_text(encoding="utf-8"))
            self.assertIsNone(summary["success_rate"])
            self.assertEqual(summary["valid_trial_count"], 0)


if __name__ == "__main__":
    unittest.main()
