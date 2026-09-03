#!/usr/bin/env python3
"""Validate and summarize structured AI-review records."""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
CATEGORIES = (
    "bug",
    "regression",
    "security",
    "missing_test",
    "documentation",
    "scope",
)
SEVERITIES = ("critical", "high", "medium", "low", "info")
OUTCOMES = ("clean", "findings", "inconclusive")
DISPOSITIONS = ("fixed", "accepted_risk", "not_reproduced")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TASK_PATTERN = re.compile(r"^TASK-\d{3}[A-Z]?$")
FINDING_PATTERN = re.compile(r"^F-\d{3}$")


class RecordValidationError(ValueError):
    """Raised when a record does not satisfy schema version 1."""


@dataclass(frozen=True)
class LoadedRecord:
    path: Path
    data: dict[str, Any]


def default_records_directory() -> Path:
    return Path(__file__).resolve().parent.parent / "docs" / "ai-reviews"


def fail(path: Path, message: str) -> None:
    raise RecordValidationError(f"{path}: {message}")


def require_exact_keys(
    value: dict[str, Any], required: set[str], path: Path, label: str
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required
    if missing:
        fail(path, f"{label} is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        fail(path, f"{label} has unknown field(s): {', '.join(sorted(unknown))}")


def require_nonempty_string(value: Any, path: Path, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(path, f"{label} must be a non-empty string")
    return value


def require_positive_integer(value: Any, path: Path, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        fail(path, f"{label} must be a positive integer")
    return value


def require_sha(value: Any, path: Path, label: str) -> str:
    value = require_nonempty_string(value, path, label)
    if not SHA_PATTERN.fullmatch(value):
        fail(path, f"{label} must be a lowercase 40-character Git SHA")
    return value


def require_utc_timestamp(value: Any, path: Path, label: str) -> str:
    value = require_nonempty_string(value, path, label)
    if not value.endswith("Z"):
        fail(path, f"{label} must use a UTC Z suffix")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(path, f"{label} must be an ISO 8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        fail(path, f"{label} must be in UTC")
    return value


def require_enum(value: Any, options: tuple[str, ...], path: Path, label: str) -> str:
    value = require_nonempty_string(value, path, label)
    if value not in options:
        fail(path, f"{label} must be one of: {', '.join(options)}")
    return value


def require_relative_path(value: Any, path: Path, label: str) -> str:
    value = require_nonempty_string(value, path, label)
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        fail(path, f"{label} must be a repository-relative path")
    return value


def read_records(records_directory: Path) -> list[LoadedRecord]:
    if not records_directory.is_dir():
        raise RecordValidationError(f"{records_directory}: records directory does not exist")

    records: list[LoadedRecord] = []
    for task_directory in sorted(records_directory.glob("TASK-*")):
        if not task_directory.is_dir():
            continue
        for path in sorted(task_directory.glob("review-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                fail(path, f"invalid JSON: {error.msg}")
            except OSError as error:
                fail(path, f"cannot read record: {error}")
            if not isinstance(data, dict):
                fail(path, "record root must be a JSON object")
            records.append(LoadedRecord(path=path, data=data))
    return records


def require_object(
    value: Any, path: Path, label: str, error_message: str | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(path, error_message or f"{label} must be an object")
    return value


def validate_task_identity(
    record: LoadedRecord, records_directory: Path, task: dict[str, Any], round_number: int
) -> str:
    path = record.path
    require_exact_keys(task, {"id", "path"}, path, "task")
    task_id = require_nonempty_string(task["id"], path, "task.id")
    if not TASK_PATTERN.fullmatch(task_id):
        fail(path, "task.id must match TASK-XXX or TASK-XXXA")
    require_relative_path(task["path"], path, "task.path")
    if record.path.parent.name != task_id:
        fail(path, "task directory must match task.id")
    expected_name = f"review-{round_number:03}.json"
    if record.path.name != expected_name:
        fail(path, f"filename must be {expected_name}")
    expected_record_id = f"{task_id}/review-{round_number:03}"
    if record.data["record_id"] != expected_record_id:
        fail(path, f"record_id must be {expected_record_id}")
    if record.path.parent.parent != records_directory:
        fail(path, "record must be directly inside docs/ai-reviews/TASK-XXX")
    return task_id


def validate_reviewer_and_pull_request(data: dict[str, Any], path: Path) -> None:
    reviewer = require_object(data["reviewer"], path, "reviewer")
    require_exact_keys(reviewer, {"label"}, path, "reviewer")
    require_nonempty_string(reviewer["label"], path, "reviewer.label")

    pull_request = data["pull_request"]
    if pull_request is None:
        return
    pull_request = require_object(
        pull_request,
        path,
        "pull_request",
        "pull_request must be null or an object",
    )
    require_exact_keys(pull_request, {"number", "url"}, path, "pull_request")
    require_positive_integer(pull_request["number"], path, "pull_request.number")
    url = require_nonempty_string(pull_request["url"], path, "pull_request.url")
    parsed_url = urlsplit(url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.netloc
        or parsed_url.query
        or parsed_url.fragment
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        fail(
            path,
            "pull_request.url must be an https URL without credentials, query or fragment",
        )


def validate_source(data: dict[str, Any], path: Path) -> str:
    source = require_object(data["source"], path, "source")
    require_exact_keys(
        source,
        {"base_sha", "head_sha", "comparison", "excluded_paths"},
        path,
        "source",
    )
    base_sha = require_sha(source["base_sha"], path, "source.base_sha")
    head_sha = require_sha(source["head_sha"], path, "source.head_sha")
    if source["comparison"] != f"{base_sha}...{head_sha}":
        fail(path, "source.comparison must equal source.base_sha...source.head_sha")
    excluded_paths = source["excluded_paths"]
    if not isinstance(excluded_paths, list) or not all(
        isinstance(item, str) for item in excluded_paths
    ):
        fail(path, "source.excluded_paths must be a string array")
    if "docs/ai-reviews/**" not in excluded_paths:
        fail(path, "source.excluded_paths must include docs/ai-reviews/**")
    return head_sha


def validate_locations(locations: Any, path: Path) -> None:
    if not isinstance(locations, list) or not locations:
        fail(path, "finding.locations must be a non-empty array")
    for location in locations:
        location = require_object(
            location,
            path,
            "finding.locations entry",
            "finding.locations entries must be objects",
        )
        if "path" not in location or location.keys() - {"path", "line"}:
            fail(path, "finding.location must contain path and optional line only")
        require_relative_path(location["path"], path, "finding.location.path")
        if "line" in location:
            require_positive_integer(location["line"], path, "finding.location.line")


def validate_findings(findings: list[Any], path: Path) -> None:
    finding_ids: set[str] = set()
    for finding in findings:
        finding = require_object(
            finding,
            path,
            "review.findings entry",
            "review.findings entries must be objects",
        )
        require_exact_keys(
            finding,
            {
                "id",
                "category",
                "severity",
                "summary",
                "rationale",
                "recommendation",
                "locations",
            },
            path,
            "finding",
        )
        finding_id = require_nonempty_string(finding["id"], path, "finding.id")
        if not FINDING_PATTERN.fullmatch(finding_id):
            fail(path, "finding.id must match F-001")
        if finding_id in finding_ids:
            fail(path, f"duplicate finding.id: {finding_id}")
        finding_ids.add(finding_id)
        require_enum(finding["category"], CATEGORIES, path, "finding.category")
        require_enum(finding["severity"], SEVERITIES, path, "finding.severity")
        for field in ("summary", "rationale", "recommendation"):
            require_nonempty_string(finding[field], path, f"finding.{field}")
        validate_locations(finding["locations"], path)


def validate_prior_dispositions(
    dispositions: Any, path: Path, record_id: str, head_sha: str
) -> None:
    if not isinstance(dispositions, list):
        fail(path, "review.prior_finding_dispositions must be an array")
    seen_dispositions: set[tuple[str, str]] = set()
    for disposition in dispositions:
        disposition = require_object(
            disposition,
            path,
            "prior finding disposition",
            "prior finding dispositions must be objects",
        )
        require_exact_keys(
            disposition,
            {"record_id", "finding_id", "disposition", "rationale", "validated_by"},
            path,
            "prior finding disposition",
        )
        previous_record_id = require_nonempty_string(
            disposition["record_id"], path, "prior finding disposition.record_id"
        )
        finding_id = require_nonempty_string(
            disposition["finding_id"], path, "prior finding disposition.finding_id"
        )
        pair = (previous_record_id, finding_id)
        if pair in seen_dispositions:
            fail(path, f"duplicate prior finding disposition: {previous_record_id} {finding_id}")
        seen_dispositions.add(pair)
        require_enum(
            disposition["disposition"],
            DISPOSITIONS,
            path,
            "prior finding disposition.disposition",
        )
        require_nonempty_string(
            disposition["rationale"], path, "prior finding disposition.rationale"
        )
        validated_by = require_object(
            disposition["validated_by"], path, "prior finding disposition.validated_by"
        )
        require_exact_keys(validated_by, {"review_id", "commit"}, path, "validated_by")
        if validated_by["review_id"] != record_id:
            fail(path, "validated_by.review_id must be the current record_id")
        if validated_by["commit"] != head_sha:
            fail(path, "validated_by.commit must equal source.head_sha")


def validate_review(data: dict[str, Any], path: Path, head_sha: str) -> None:
    review = require_object(data["review"], path, "review")
    require_exact_keys(
        review,
        {"outcome", "summary", "findings", "prior_finding_dispositions"},
        path,
        "review",
    )
    outcome = require_enum(review["outcome"], OUTCOMES, path, "review.outcome")
    require_nonempty_string(review["summary"], path, "review.summary")
    findings = review["findings"]
    if not isinstance(findings, list):
        fail(path, "review.findings must be an array")
    if outcome == "findings" and not findings:
        fail(path, "review.outcome findings requires at least one finding")
    if outcome == "clean" and findings:
        fail(path, "review.outcome clean cannot include findings")
    validate_findings(findings, path)
    validate_prior_dispositions(
        review["prior_finding_dispositions"], path, data["record_id"], head_sha
    )


def validate_record_shape(record: LoadedRecord, records_directory: Path) -> None:
    path = record.path
    data = record.data
    require_exact_keys(
        data,
        {
            "schema_version",
            "record_id",
            "task",
            "round",
            "reviewed_at",
            "reviewer",
            "pull_request",
            "source",
            "review",
        },
        path,
        "record",
    )
    if (
        isinstance(data["schema_version"], bool)
        or not isinstance(data["schema_version"], int)
        or data["schema_version"] != SCHEMA_VERSION
    ):
        fail(path, f"schema_version must be {SCHEMA_VERSION}")
    require_positive_integer(data["round"], path, "round")
    require_nonempty_string(data["record_id"], path, "record_id")
    require_utc_timestamp(data["reviewed_at"], path, "reviewed_at")
    task = require_object(data["task"], path, "task")
    validate_task_identity(record, records_directory, task, data["round"])
    validate_reviewer_and_pull_request(data, path)
    head_sha = validate_source(data, path)
    validate_review(data, path, head_sha)


def validate_records(records_directory: Path) -> list[LoadedRecord]:
    records = read_records(records_directory)
    record_id_paths: dict[str, Path] = {}
    for record in records:
        record_id = record.data.get("record_id")
        if isinstance(record_id, str) and record_id in record_id_paths:
            fail(record.path, f"duplicate record_id: {record_id}")
        if isinstance(record_id, str):
            record_id_paths[record_id] = record.path
    for record in records:
        validate_record_shape(record, records_directory)

    records_by_id: dict[str, LoadedRecord] = {}
    records_by_task: dict[str, list[LoadedRecord]] = defaultdict(list)
    findings: set[tuple[str, str]] = set()
    for record in records:
        record_id = record.data["record_id"]
        records_by_id[record_id] = record
        records_by_task[record.data["task"]["id"]].append(record)
        for finding in record.data["review"]["findings"]:
            findings.add((record_id, finding["id"]))

    for task_id, task_records in records_by_task.items():
        rounds = sorted(record.data["round"] for record in task_records)
        expected_rounds = list(range(1, len(rounds) + 1))
        if rounds != expected_rounds:
            first_path = sorted(task_records, key=lambda item: item.path)[0].path
            fail(first_path, f"{task_id} rounds must be sequential starting at 1")

    disposed_findings: set[tuple[str, str]] = set()
    for record in records:
        task_id = record.data["task"]["id"]
        round_number = record.data["round"]
        for disposition in record.data["review"]["prior_finding_dispositions"]:
            target = (disposition["record_id"], disposition["finding_id"])
            target_record = records_by_id.get(target[0])
            if target_record is None or target not in findings:
                fail(record.path, f"unknown prior finding reference: {target[0]} {target[1]}")
            if target_record.data["task"]["id"] != task_id:
                fail(record.path, "prior finding disposition must reference the same task")
            if target_record.data["round"] >= round_number:
                fail(record.path, "prior finding disposition must reference an earlier round")
            if target in disposed_findings:
                fail(record.path, f"prior finding already has a disposition: {target[0]} {target[1]}")
            disposed_findings.add(target)
    return records


def collect_findings(records: list[LoadedRecord]) -> dict[tuple[str, str], dict[str, Any]]:
    findings_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        record_id = record.data["record_id"]
        findings_by_key.update(
            {
                (record_id, finding["id"]): {
                    "record_id": record_id,
                    "finding_id": finding["id"],
                    "category": finding["category"],
                    "severity": finding["severity"],
                    "summary": finding["summary"],
                    "locations": finding["locations"],
                }
                for finding in record.data["review"]["findings"]
            }
        )
    return findings_by_key


def collect_dispositions(records: list[LoadedRecord]) -> dict[tuple[str, str], str]:
    dispositions_by_finding: dict[tuple[str, str], str] = {}
    for record in records:
        dispositions_by_finding.update(
            {
                (disposition["record_id"], disposition["finding_id"]): disposition[
                    "disposition"
                ]
                for disposition in record.data["review"]["prior_finding_dispositions"]
            }
        )
    return dispositions_by_finding


def add_recurrence_references(
    recurrence: dict[tuple[str, str], list[str]],
    key: tuple[str, str],
    finding: dict[str, Any],
) -> None:
    reference = f"{key[0]}:{key[1]}"
    location_paths = {location["path"] for location in finding["locations"]}
    for path in location_paths:
        recurrence[(finding["category"], path)].append(reference)


def build_summary(records: list[LoadedRecord]) -> dict[str, Any]:
    outcomes = Counter({outcome: 0 for outcome in OUTCOMES})
    categories = Counter({category: 0 for category in CATEGORIES})
    severities = Counter({severity: 0 for severity in SEVERITIES})
    disposition_counts = Counter({"open": 0, **{item: 0 for item in DISPOSITIONS}})
    recurrence: dict[tuple[str, str], list[str]] = defaultdict(list)
    findings_by_key = collect_findings(records)
    dispositions_by_finding = collect_dispositions(records)

    outcomes.update(record.data["review"]["outcome"] for record in records)
    categories.update(finding["category"] for finding in findings_by_key.values())
    severities.update(finding["severity"] for finding in findings_by_key.values())

    open_findings: list[dict[str, Any]] = []
    for key, finding in sorted(findings_by_key.items()):
        disposition = dispositions_by_finding.get(key, "open")
        disposition_counts[disposition] += 1
        add_recurrence_references(recurrence, key, finding)
        if disposition == "open":
            open_findings.append(finding)

    recurrence_candidates = [
        {
            "category": category,
            "path": path,
            "count": len(references),
            "finding_references": sorted(references),
        }
        for (category, path), references in sorted(recurrence.items())
        if len(references) > 1
    ]
    return {
        "record_count": len(records),
        "outcomes": dict(outcomes),
        "finding_counts": {
            "total": len(findings_by_key),
            "by_category": dict(categories),
            "by_severity": dict(severities),
            "by_disposition": dict(disposition_counts),
        },
        "open_findings": open_findings,
        "recurrence_candidates": recurrence_candidates,
    }


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = ["# AI Review Summary", "", f"Records: {summary['record_count']}", ""]
    lines.extend(["## Outcomes", ""])
    for outcome, count in summary["outcomes"].items():
        lines.append(f"- {outcome}: {count}")
    lines.extend(["", "## Findings", ""])
    for field, label in (
        ("by_category", "Category"),
        ("by_severity", "Severity"),
        ("by_disposition", "Disposition"),
    ):
        values = summary["finding_counts"][field]
        lines.append(f"### {label}")
        lines.append("")
        for item, count in values.items():
            lines.append(f"- {item}: {count}")
        lines.append("")
    lines.append("## Open Findings")
    lines.append("")
    if summary["open_findings"]:
        for finding in summary["open_findings"]:
            locations = ", ".join(
                f"{location['path']}:{location.get('line', '?')}"
                for location in finding["locations"]
            )
            lines.append(
                f"- {finding['record_id']}:{finding['finding_id']} "
                f"({finding['severity']} {finding['category']}): "
                f"{finding['summary']} — {locations}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Recurrence Candidates", ""])
    if summary["recurrence_candidates"]:
        for candidate in summary["recurrence_candidates"]:
            references = ", ".join(candidate["finding_references"])
            lines.append(
                f"- {candidate['category']} in {candidate['path']}: "
                f"{candidate['count']} finding(s) ({references})"
            )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "summarize"):
        subcommand = subcommands.add_parser(name)
        subcommand.add_argument(
            "--records-dir",
            type=Path,
            default=default_records_directory(),
            help="directory containing TASK-XXX/review-NNN.json records",
        )
        if name == "summarize":
            subcommand.add_argument(
                "--format", choices=("json", "markdown"), default="markdown"
            )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        records = validate_records(arguments.records_dir)
    except RecordValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if arguments.command == "validate":
        print(f"Validated {len(records)} AI-review record(s).")
        return 0

    summary = build_summary(records)
    if arguments.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(markdown_summary(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
