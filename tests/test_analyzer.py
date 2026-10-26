import csv
import tempfile
import unittest
from pathlib import Path

from src.analyzer import analyze


class AnalyzerTests(unittest.TestCase):
    def test_detects_large_discrepancy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "country", "antigen", "year", "measure",
                    "value_percent", "source", "source_url", "notes"
                ])
                writer.writerow([
                    "Cameroon", "MCV1", 2020, "Estimate", 63,
                    "Source A", "https://example.com/a", ""
                ])
                writer.writerow([
                    "Cameroon", "MCV1", 2020, "Administrative", 74,
                    "Source B", "https://example.com/b", ""
                ])

            result = analyze(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["gap_percentage_points"], 11)
            self.assertEqual(result[0]["status"], "REVIEW")

    def test_ignores_single_measure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "country", "antigen", "year", "measure",
                    "value_percent", "source", "source_url", "notes"
                ])
                writer.writerow([
                    "Cameroon", "MCV1", 2020, "Estimate", 63,
                    "Source A", "https://example.com/a", ""
                ])

            self.assertEqual(analyze(path), [])


if __name__ == "__main__":
    unittest.main()


class CriticArbiterTests(unittest.TestCase):
    def setUp(self):
        self.finding = {
            "country": "Cameroon",
            "antigen": "MCV1",
            "year": "2020",
            "measure_a": "Administrative coverage",
            "value_a": 74.0,
            "measure_b": "WUENIC estimate",
            "value_b": 63.0,
            "gap_percentage_points": 11.0,
            "sources": [
                {"name": "Source A", "url": "https://example.com/a"},
                {"name": "Source B", "url": "https://example.com/b"},
            ],
        }

    def test_large_gap_goes_to_review_not_a_verdict(self):
        from src.arbiter import arbitrate
        result = arbitrate(self.finding)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertTrue(result["critic"]["passed"])

    def test_missing_source_url_causes_abstention(self):
        from src.arbiter import arbitrate
        finding = {**self.finding, "sources": [
            {"name": "Source A", "url": ""},
            {"name": "Source B", "url": "https://example.com/b"},
        ]}
        self.assertEqual(arbitrate(finding)["decision"], "ABSTAIN")

    def test_inconsistent_gap_causes_abstention(self):
        from src.arbiter import arbitrate
        finding = {**self.finding, "gap_percentage_points": 2.0}
        self.assertEqual(arbitrate(finding)["decision"], "ABSTAIN")


class ReporterTests(unittest.TestCase):
    def test_report_includes_decision_sources_and_caveat(self):
        from src.reporter import render_report

        results = {
            "records_loaded": 2,
            "findings": [{
                "country": "Cameroon",
                "antigen": "MCV1",
                "year": "2020",
                "measure_a": "Administrative coverage",
                "value_a": 74.0,
                "measure_b": "WUENIC estimate",
                "value_b": 63.0,
                "gap_percentage_points": 11.0,
                "sources": [{"name": "WHO", "url": "https://example.com/who"}],
            }],
            "decisions": [{
                "decision": "REVIEW",
                "reason": "Investigate the discrepancy.",
            }],
        }

        report = render_report(results)
        self.assertIn("REVIEW", report)
        self.assertIn("https://example.com/who", report)
        self.assertIn("does not, by itself, establish which source is correct", report)
        self.assertIn("11.0 percentage points", report)

    def test_empty_findings_produces_clear_report(self):
        from src.reporter import render_report

        report = render_report({"records_loaded": 3, "findings": [], "decisions": []})
        self.assertIn("No discrepancies met the configured threshold.", report)
