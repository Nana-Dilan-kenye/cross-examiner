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
