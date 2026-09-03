import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "ai_review_records.py"
FIXTURES = Path(__file__).parent / "fixtures" / "ai_review_records" / "valid"


class AiReviewRecordsTests(unittest.TestCase):
    def copy_valid_records(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary_directory = tempfile.TemporaryDirectory[str]()
        records_directory = Path(temporary_directory.name) / "records"
        shutil.copytree(FIXTURES, records_directory)
        return temporary_directory, records_directory

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_validate_and_summarize_valid_multi_round_records(self) -> None:
        temporary_directory, records_directory = self.copy_valid_records()
        with temporary_directory:
            validation = self.command("validate", "--records-dir", str(records_directory))
            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertIn("Validated 4 AI-review record(s).", validation.stdout)

            json_result = self.command(
                "summarize", "--records-dir", str(records_directory), "--format", "json"
            )
            self.assertEqual(json_result.returncode, 0, json_result.stderr)
            summary = json.loads(json_result.stdout)
            self.assertEqual(summary["outcomes"], {
                "clean": 1,
                "findings": 2,
                "inconclusive": 1,
            })
            self.assertEqual(summary["finding_counts"]["total"], 3)
            self.assertEqual(summary["finding_counts"]["by_disposition"]["fixed"], 2)
            self.assertEqual(
                summary["finding_counts"]["by_disposition"]["accepted_risk"], 1
            )
            self.assertEqual(summary["open_findings"], [])
            self.assertEqual(summary["recurrence_candidates"][0]["count"], 2)

            markdown_result = self.command(
                "summarize", "--records-dir", str(records_directory), "--format", "markdown"
            )
            self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
            self.assertIn("# AI Review Summary", markdown_result.stdout)
            self.assertIn("## Recurrence Candidates", markdown_result.stdout)

    def test_rejects_malformed_json(self) -> None:
        temporary_directory, records_directory = self.copy_valid_records()
        with temporary_directory:
            target = records_directory / "TASK-900" / "review-004.json"
            target.write_text("{", encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("review-004.json: invalid JSON", result.stderr)

    def test_rejects_missing_field_and_unknown_enum(self) -> None:
        temporary_directory, records_directory = self.copy_valid_records()
        with temporary_directory:
            target = records_directory / "TASK-900" / "review-001.json"
            data = json.loads(target.read_text(encoding="utf-8"))
            del data["reviewer"]
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("record is missing required field(s): reviewer", result.stderr)

            data = json.loads((FIXTURES / "TASK-900" / "review-001.json").read_text())
            data["review"]["findings"][0]["category"] = "unknown"
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("finding.category must be one of", result.stderr)

    def test_rejects_duplicate_finding_id(self) -> None:
        temporary_directory, records_directory = self.copy_valid_records()
        with temporary_directory:
            target = records_directory / "TASK-900" / "review-001.json"
            data = json.loads(target.read_text(encoding="utf-8"))
            duplicate = data["review"]["findings"][0].copy()
            data["review"]["findings"].append(duplicate)
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate finding.id: F-001", result.stderr)

    def test_rejects_booleans_for_integer_fields(self) -> None:
        temporary_directory, records_directory = self.copy_valid_records()
        with temporary_directory:
            target = records_directory / "TASK-900" / "review-001.json"

            data = json.loads(target.read_text(encoding="utf-8"))
            data["schema_version"] = True
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("schema_version must be 1", result.stderr)

            data = json.loads((FIXTURES / "TASK-900" / "review-001.json").read_text())
            data["round"] = True
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("round must be a positive integer", result.stderr)

            data = json.loads((FIXTURES / "TASK-900" / "review-001.json").read_text())
            data["pull_request"] = {"number": True, "url": "https://example.test/pr/1"}
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pull_request.number must be a positive integer", result.stderr)

            data = json.loads((FIXTURES / "TASK-900" / "review-001.json").read_text())
            data["review"]["findings"][0]["locations"][0]["line"] = True
            target.write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("finding.location.line must be a positive integer", result.stderr)

    def test_rejects_duplicate_record_id_round_gap_and_invalid_prior_reference(self) -> None:
        temporary_directory, records_directory = self.copy_valid_records()
        with temporary_directory:
            task_directory = records_directory / "TASK-900"
            duplicate = task_directory / "review-005.json"
            duplicate.write_text((task_directory / "review-001.json").read_text(), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate record_id: TASK-900/review-001", result.stderr)

            duplicate.unlink()
            (task_directory / "review-004.json").rename(task_directory / "review-005.json")
            data = json.loads((task_directory / "review-005.json").read_text())
            data["round"] = 5
            data["record_id"] = "TASK-900/review-005"
            (task_directory / "review-005.json").write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("rounds must be sequential starting at 1", result.stderr)

            (task_directory / "review-005.json").unlink()
            shutil.copy(FIXTURES / "TASK-900" / "review-004.json", task_directory / "review-004.json")
            data = json.loads((task_directory / "review-002.json").read_text())
            data["review"]["prior_finding_dispositions"][0]["finding_id"] = "F-999"
            (task_directory / "review-002.json").write_text(json.dumps(data), encoding="utf-8")
            result = self.command("validate", "--records-dir", str(records_directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown prior finding reference", result.stderr)


if __name__ == "__main__":
    unittest.main()
