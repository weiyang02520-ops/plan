import csv
import json
import tempfile
import unittest
from pathlib import Path

from experiment_tools.calc_position_error import main


def write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


class PositionErrorTests(unittest.TestCase):
    def test_normal_matching_and_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            estimate = root / "estimate.csv"
            truth = root / "truth.csv"
            output = root / "out"
            columns = ["timestamp", "x", "y", "z"]
            write_csv(estimate, columns, [[0, 0, 0, 0], [1, 1, 0, 0.1], [2, 2, 0, 0.2]])
            write_csv(truth, columns, [[0, 0, 0, 0], [1.02, 1.02, 0, 0], [2, 2, 0, 0.2]])
            result = main(["--estimate", str(estimate), "--truth", str(truth), "--sync-tolerance", "0.05", "--output", str(output)])
            self.assertEqual(result, 0)
            summary = json.loads((output / "position_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["count"], 3)
            self.assertEqual(summary["valid_count"], 3)
            self.assertAlmostEqual(summary["plane_error"]["max"], 0.02)
            self.assertAlmostEqual(summary["elevation_abs_error"]["max"], 0.1)
            self.assertIsNotNone(summary["elevation_abs_error"]["p95"])
            self.assertTrue((output / "position_samples.csv").is_file())
            self.assertTrue((output / "run_metadata.json").is_file())

    def test_unmatched_samples_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_csv(root / "estimate.csv", ["timestamp", "x", "y", "z"], [[0, 0, 0, 0], [10, 1, 0, 0]])
            write_csv(root / "truth.csv", ["timestamp", "x", "y", "z"], [[0, 0, 0, 0]])
            output = root / "out"
            result = main(["--estimate", str(root / "estimate.csv"), "--truth", str(root / "truth.csv"), "--sync-tolerance", "0.01", "--output", str(output)])
            self.assertEqual(result, 0)
            with (output / "position_samples.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["status"], "UNMATCHED")
            self.assertEqual(rows[1]["valid"], "False")

    def test_missing_file_and_no_valid_samples_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(main(["--estimate", str(root / "missing.csv"), "--truth", str(root / "truth.csv"), "--output", str(root / "out")]), 2)
            write_csv(root / "estimate.csv", ["timestamp", "x", "y", "z"], [[0, 0, 0, 0]])
            write_csv(root / "truth.csv", ["timestamp", "x", "y", "z"], [[1, 0, 0, 0]])
            output = root / "out"
            self.assertEqual(main(["--estimate", str(root / "estimate.csv"), "--truth", str(root / "truth.csv"), "--sync-tolerance", "0.01", "--output", str(output)]), 4)
            summary = json.loads((output / "position_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "INCOMPLETE")
            self.assertEqual(summary["valid_count"], 0)


if __name__ == "__main__":
    unittest.main()
