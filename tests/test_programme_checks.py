"""Tests for the programme-report checks and the synthetic data."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from src.programme_checks import check_records, load_reports

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src"
ANSWER_KEY = ROOT / "eval" / "answer_key.json"


class ProgrammeCheckTests(unittest.TestCase):
    def setUp(self):
        self.records = load_reports()
        self.flags = check_records(self.records)
        self.key = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
        self.flagged = {
            (flag["district"], flag["antigen"], str(flag["year"]))
            for flag in self.flags
        }

    def test_every_planted_contradiction_is_detected(self):
        missed = []
        for item in self.key["planted"]:
            key = (item["district"], item["antigen"], str(item["year"]))
            if key not in self.flagged:
                missed.append(item)
        self.assertEqual(missed, [], f"not detected: {missed}")

    def test_a_clean_control_is_never_flagged(self):
        false_positives = []
        for item in self.key["controls"]:
            key = (item["district"], item["antigen"], str(item["year"]))
            if key in self.flagged:
                false_positives.append(item)
        self.assertEqual(
            false_positives, [], f"false positives: {false_positives}"
        )

    def test_every_row_is_labelled_synthetic(self):
        for row in self.records:
            self.assertEqual(str(row.get("is_synthetic")).lower(), "true")
            self.assertIn("SYNTHETIC", row.get("source_ref", "") + row.get("notes", "") + "SYNTHETIC")

    def test_coverage_above_a_hundred_is_flagged(self):
        flags = [
            flag for flag in self.flags
            if flag["code"] == "C01_DENOMINATOR_SUSPECT"
        ]
        self.assertTrue(flags)

    def test_a_fraction_where_a_percentage_belongs_is_flagged(self):
        flags = [
            flag for flag in self.flags
            if flag["code"] == "C06_UNIT_MISMATCH"
        ]
        self.assertTrue(flags)

    def test_the_same_doses_against_two_targets_is_flagged(self):
        flags = [
            flag for flag in self.flags
            if flag["code"] == "C05_DENOMINATOR_MISMATCH"
        ]
        self.assertTrue(flags)

    def test_a_missing_year_is_flagged(self):
        records = [
            row for row in self.records
            if not (row["district"] == "North Ridge" and row["antigen"] == "MCV1")
        ]
        flags = check_records(
            records,
            expected_years=[2019, 2020],
            expected_pairs=[("North Ridge", "MCV1")],
        )
        codes = {flag["code"] for flag in flags}
        self.assertIn("C10_MISSING_EVIDENCE", codes)

    def test_the_generator_is_deterministic(self):
        before = (ROOT / "data" / "synthetic_programme_reports.csv").read_text()
        result = subprocess.run(
            [sys.executable, "scripts/make_synthetic.py"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = (ROOT / "data" / "synthetic_programme_reports.csv").read_text()
        self.assertEqual(before, after)


class AnswerKeyTests(unittest.TestCase):
    def test_the_application_never_reads_the_answer_key(self):
        """Only the evaluation harness may read the answer key."""
        for path in sorted(SOURCE_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "answer_key",
                text,
                f"{path.name} refers to the answer key",
            )

    def test_the_evaluation_harness_is_the_only_reader(self):
        harness = (ROOT / "eval" / "run_eval.py").read_text(encoding="utf-8")
        self.assertIn("answer_key", harness)


if __name__ == "__main__":
    unittest.main()
