import json
import tempfile
import unittest
from pathlib import Path

from experiment_tools.check_rosbag import main


def topic(name: str, field_check: bool = True) -> dict[str, object]:
    return {
        "name": name,
        "type": "synthetic/msg/Example",
        "message_count": 10,
        "start_time": 0,
        "end_time": 1,
        "average_frequency": 10,
        "max_gap": 0.2,
        "timestamp_valid": True,
        "field_check": field_check,
        "coverage_valid": True,
    }


def manifest(required: list[str], topics: list[dict[str, object]], not_applicable: list[str] | None = None, declared: bool = True) -> dict[str, object]:
    return {
        "bag_id": "synthetic-bag",
        "bag_path": "synthetic/bag",
        "bag_sha256": "0" * 64,
        "scenario_id": "synthetic",
        "required_topics": required,
        "not_applicable_topics": not_applicable or [],
        "not_applicable_declared_before_run": declared,
        "topics": topics,
        "dataset_label": "SYNTHETIC / TEST ONLY",
    }


class RosbagCheckerTests(unittest.TestCase):
    def run_manifest(self, value: dict[str, object]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            output = root / "out"
            manifest_path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(main(["--manifest", str(manifest_path), "--output", str(output)]), 0)
            return json.loads((output / "rosbag_check_report.json").read_text(encoding="utf-8"))

    def test_all_required_topics_pass_as_a(self) -> None:
        report = self.run_manifest(manifest(["/a", "/b"], [topic("/a"), topic("/b")]))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["overall_grade"], "A")

    def test_non_core_field_issue_is_b(self) -> None:
        report = self.run_manifest(manifest(["/a"], [topic("/a", field_check=False)]))
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["overall_grade"], "B")

    def test_required_missing_is_c(self) -> None:
        report = self.run_manifest(manifest(["/a", "/b"], [topic("/a")]))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["overall_grade"], "C")
        self.assertIn("/b", report["required_failures"])

    def test_predeclared_not_applicable_is_not_missing(self) -> None:
        report = self.run_manifest(manifest(["/a", "/b"], [topic("/a")], ["/b"], True))
        self.assertEqual(report["overall_grade"], "A")
        statuses = {item["name"]: item["status"] for item in report["topic_status"]}
        self.assertEqual(statuses["/b"], "NOT_APPLICABLE")

    def test_missing_topic_cannot_be_marked_not_applicable_afterwards(self) -> None:
        report = self.run_manifest(manifest(["/a", "/b"], [topic("/a")], ["/b"], False))
        self.assertEqual(report["overall_grade"], "C")
        self.assertIn("/b", report["required_failures"])
        self.assertIn("/b", report["undeclared_not_applicable_topics"])


if __name__ == "__main__":
    unittest.main()
