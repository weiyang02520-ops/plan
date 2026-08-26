"""Small standard-library helpers shared by the experiment tools."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TOOL_VERSION = "0.1.0"


class ToolError(Exception):
    """An expected input or processing error with a CLI exit code."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def require_file(path_value: str | Path, label: str = "input file") -> Path:
    path = Path(path_value)
    if not path.is_file():
        raise ToolError(f"{label} does not exist or is not a file: {path}", 2)
    return path


def read_json(path_value: str | Path, label: str = "JSON input") -> Any:
    path = require_file(path_value, label)
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read {label}: {path}: {exc}", 2) from exc


def read_optional_config(path_value: str | Path | None) -> tuple[dict[str, Any], Path | None]:
    if path_value is None:
        return {}, None
    value = read_json(path_value, "config")
    if not isinstance(value, dict):
        raise ToolError("config must contain a JSON object", 2)
    return value, Path(path_value)


def read_csv_rows(path_value: str | Path, required_columns: Sequence[str], label: str) -> list[dict[str, str]]:
    path = require_file(path_value, label)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ToolError(f"{label} has no header: {path}", 2)
            missing = [column for column in required_columns if column not in reader.fieldnames]
            if missing:
                raise ToolError(f"{label} is missing columns {missing}: {path}", 2)
            rows: list[dict[str, str]] = []
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise ToolError(f"{label} has extra CSV fields at row {row_number}", 2)
                rows.append({key: (value or "") for key, value in row.items() if key is not None})
            return rows
    except UnicodeDecodeError as exc:
        raise ToolError(f"{label} is not valid UTF-8: {path}", 2) from exc
    except OSError as exc:
        raise ToolError(f"cannot read {label}: {path}: {exc}", 2) from exc


def required_text(row: Mapping[str, str], field: str, row_number: int, label: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise ToolError(f"{label} row {row_number}: {field} is required", 2)
    return value


def parse_float(value: str, field: str, row_number: int, label: str, allow_blank: bool = False) -> float | None:
    text = value.strip()
    if not text and allow_blank:
        return None
    if not text:
        raise ToolError(f"{label} row {row_number}: {field} is required", 2)
    try:
        number = float(text)
    except ValueError as exc:
        raise ToolError(f"{label} row {row_number}: {field} is not numeric", 2) from exc
    if not math.isfinite(number):
        raise ToolError(f"{label} row {row_number}: {field} must be finite", 2)
    return number


def parse_bool(value: str, field: str, row_number: int, label: str) -> bool:
    text = value.strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ToolError(f"{label} row {row_number}: {field} must be true/false", 2)


def sha256_file(path_value: str | Path) -> str:
    path = require_file(path_value)
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ToolError(f"cannot hash file: {path}: {exc}", 2) from exc
    return digest.hexdigest()


def git_sha() -> str | None:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def ensure_output_dir(path_value: str | Path) -> Path:
    path = Path(path_value)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ToolError(f"cannot create output directory: {path}: {exc}", 2) from exc
    return path


def write_json(path_value: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path_value)
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except (OSError, TypeError, ValueError) as exc:
        raise ToolError(f"cannot write JSON output: {path}: {exc}", 2) from exc


def write_csv(path_value: str | Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path_value)
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
    except (OSError, csv.Error) as exc:
        raise ToolError(f"cannot write CSV output: {path}: {exc}", 2) from exc


def percentile(values: Sequence[float], fraction: float = 0.95) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def numeric_stats(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "valid_count": 0, "mean": None, "rmse": None, "max": None, "p95": None}
    count = len(values)
    return {
        "count": count,
        "valid_count": count,
        "mean": sum(values) / count,
        "rmse": math.sqrt(sum(value * value for value in values) / count),
        "max": max(values),
        "p95": percentile(values),
    }


def make_metadata(
    input_paths: Mapping[str, str | Path],
    config_path: str | Path | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "input_sha256": {name: sha256_file(path) for name, path in input_paths.items()},
        "input_files": {name: Path(path).name for name, path in input_paths.items()},
        "config_file": Path(config_path).name if config_path is not None else None,
        "config_sha256": sha256_file(config_path) if config_path is not None else None,
    }
    if extra:
        metadata.update(extra)
    return metadata
