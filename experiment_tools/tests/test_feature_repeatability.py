import csv
import json
import tempfile
import unittest
from pathlib import Path

from experiment_tools.calc_feature_repeatability import main


def write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


class FeatureRepeatabilityTests(unittest.TestCase):
    def test_normal_matching_threshold_and_one_to_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "features.csv", ["frame_id", "timestamp", "feature_id", "x", "y", "valid"], [
                ["a", 0, "a1", 0, 0, "true"], ["a", 0, "a2", 1, 0, "true"],
                ["b", 1, "b1", 0.05, 0, "true"], ["b", 1, "b2", 1.2, 0, "true"],
            ])
            write_csv(root / "pairs.csv", ["frame_a", "frame_b", "scenario_id"], [["a", "b", "boundary"]])
            output = root / "out"
            self.assertEqual(main(["--features", str(root / "features.csv"), "--pairs", str(root / "pairs.csv"), "--distance-threshold", "0.05", "--output", str(output)]), 0)
            with (output / "feature_pair_samples.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["matched_features"], "1")
            self.assertAlmostEqual(float(rows[0]["repeat_rate"]), 0.5)
            summary = json.loads((output / "feature_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["valid_pair_count"], 1)

    def test_zero_valid_feature_and_missing_frame_are_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "features.csv", ["frame_id", "timestamp", "feature_id", "x", "y", "valid"], [["empty", 0, "e", 0, 0, "false"], ["full", 0, "f", 0, 0, "true"]])
            write_csv(root / "pairs.csv", ["frame_a", "frame_b", "scenario_id"], [["empty", "full", "zero-a"], ["full", "missing", "missing-b"]])
            output = root / "out"
            self.assertEqual(main(["--features", str(root / "features.csv"), "--pairs", str(root / "pairs.csv"), "--output", str(output)]), 0)
            with (output / "feature_pair_samples.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["status"], "INVALID")
            self.assertIn("zero", rows[0]["invalid_reason"])
            self.assertEqual(rows[1]["status"], "INVALID")
            self.assertIn("not found", rows[1]["invalid_reason"])


if __name__ == "__main__":
    unittest.main()
