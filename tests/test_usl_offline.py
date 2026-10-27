"""Offline verification of the semantic layer's rules.

**These tests do not prove the live instance works.** They use fixtures:
they prove that the checks in ``scripts/verify_usl.py`` and in the
application read the layer correctly, and that they fail when the layer
holds something it should not. The live half is
``scripts/verify_usl.py``, which asks the running instance.
"""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from src import zetaris_source

ROOT = Path(__file__).resolve().parent.parent

# A fixture of what the layer holds: the published figures, a derived
# copy of the estimate, the independent survey line and the generated
# records.
FIXTURE_ROWS = [
    # Cameroon MCV1 2020, the reconciled estimate from the workbook.
    ["obs-1", "Cameroon", "CMR", "MCV1", "2020", "WUENIC estimate", "wuenic",
     "reconciled_estimate", "63.0", "percent", "Children 12-23 months",
     "WHO UNICEF reconciled estimate", "wuenic_workbook_2025", "xlsx",
     "WUENIC 2025 revision", "https://data.unicef.org/resources/dataset/immunization/",
     "wuenic_2025", "WHO UNICEF estimates", "", "false", "false", "false",
     "SELF_CONSISTENCY", "verified_against_source_table", "Estimate"],
    # The World Bank's copy of the same series.
    ["obs-2", "Cameroon", "CMR", "MCV1", "2020", "WUENIC estimate", "wuenic",
     "reconciled_estimate", "63.0", "percent", "Children 12-23 months",
     "World Bank indicator", "worldbank_wdi", "rest_json",
     "World Bank Indicators",
     "https://api.worldbank.org/v2/country/CMR/indicator/SH.IMM.MEAS",
     "wuenic_2025", "WHO UNICEF estimates", "wuenic_workbook_2025", "true",
     "false", "false", "SELF_CONSISTENCY", "verified_against_source_table",
     "Indicator SH.IMM.MEAS"],
    # The administrative figure from the country profile.
    ["obs-3", "Cameroon", "CMR", "MCV1", "2020", "Administrative coverage",
     "administrative", "administrative_reporting", "74.0", "percent",
     "Children 12-23 months", "Country profile", "who_country_profile_2024",
     "pdf", "WUENIC country profile",
     "https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf",
     "cameroon_admin_jrf", "Cameroon administrative reporting", "", "false",
     "false", "false", "SELF_CONSISTENCY", "verified_against_source_table",
     "Reported administrative figure"],
    # The household survey, from the country profile.
    ["obs-4", "Cameroon", "CMR", "MCV1", "2020", "Household survey coverage",
     "survey", "household_survey", "54.0", "percent", "Children 12-23 months",
     "Country profile", "who_country_profile_2024", "pdf",
     "WUENIC country profile",
     "https://cdn.who.int/media/docs/default-source/country-profiles/immunization/2024-country-profiles/immunization-2024-cmr.pdf",
     "cameroon_household_survey", "Cameroon household survey coverage", "",
     "false", "false", "false", "INDEPENDENT_MEASUREMENT",
     "verified_against_source_table", "Household survey row"],
    # The same survey, from the survey's own report.
    ["obs-5", "Cameroon", "CMR", "MCV1", "2018", "Household survey coverage",
     "survey", "household_survey", "65.3", "percent", "Children 12-23 months",
     "DHS summary report", "dhs_cameroon_2018", "pdf",
     "Cameroon DHS 2018 survey report",
     "https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf",
     "cameroon_household_survey", "Cameroon household survey coverage", "",
     "false", "false", "true", "INDEPENDENT_MEASUREMENT",
     "transcribed_from_publication", "Measles MCV1"],
    # A generated district return.
    ["obs-6", "Meridia", "MER", "MCV1", "2019",
     "Programme report (synthetic)", "programme_report", "synthetic", "52.0",
     "percent", "1000", "District return", "synthetic_programme_reports",
     "csv", "SYNTHETIC district programme reports",
     "synthetic://meridian-immunisation-programme/district-returns",
     "synthetic_programme", "Synthetic district programme reports", "", "false",
     "true", "false", "CONTEXT_ONLY", "generated", ""],
]


class _Result:
    def __init__(self, rows):
        self.rows = rows


class _Channel:
    """A channel that answers the queries the verification script makes."""

    def __init__(self, rows=None, usl_rows=None):
        self.rows = rows or []
        self.usl_rows = usl_rows if usl_rows is not None else self.rows
        self.queries = []

    def run(self, sql, limit=100):
        self.queries.append(sql)
        if "SHOW NAMESPACES" in sql:
            return _Result([
                ["coverage_observations", "usl", "1118", "1", None],
                ["cross_examiner_evidence", "usl", "849", "1", None],
            ])
        if sql.startswith("LOAD USL"):
            # One row, one column: the model as a JSON string.
            return _Result([[json.dumps({
                "namespace": ["metastore", "cross_examiner"],
                "name": "coverage_observations",
                "tables": [{
                    "name": "coverage_observation",
                    "columnSpecs": [
                        {"name": name, "dataType": "\"varchar(100)\""}
                        for name, _ in zetaris_source.USL_COLUMNS
                    ],
                }],
            })]])
        if "coverage_observation" in sql:
            return _Result(self.usl_rows)
        return _Result(self.rows)

    def close(self):
        pass


import json  # noqa: E402  (used by the fixture channel)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_usl", ROOT / "scripts" / "verify_usl.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineRuleTests(unittest.TestCase):
    """The rules, checked against fixtures."""

    def setUp(self):
        self.verifier = _load_verifier()

    def _report(self, rows):
        channel = _Channel(usl_rows=rows)
        report = self.verifier.Report()
        with patch("src.zetaris_source._client", return_value=channel):
            self.verifier.verify(report)
        return report

    def test_a_healthy_layer_passes_every_check(self):
        report = self._report(FIXTURE_ROWS)
        failed = [check["name"] for check in report.failed]
        self.assertEqual(failed, [], f"failed: {failed}")

    def test_a_derived_copy_marked_independent_fails(self):
        rows = [list(row) for row in FIXTURE_ROWS]
        rows[1][21] = "true"          # independent_capable on the World Bank
        report = self._report(rows)
        self.assertIn(
            "no derived copy is marked independent",
            [check["name"] for check in report.failed],
        )

    def test_an_unmarked_synthetic_record_fails(self):
        rows = [list(row) for row in FIXTURE_ROWS]
        rows[5][20] = "false"          # is_synthetic on the district return
        report = self._report(rows)
        self.assertIn(
            "every synthetic record is marked synthetic",
            [check["name"] for check in report.failed],
        )

    def test_a_record_without_an_origin_fails(self):
        rows = [list(row) for row in FIXTURE_ROWS]
        rows[0][16] = ""              # origin_id
        report = self._report(rows)
        self.assertIn(
            "every record keeps its origin",
            [check["name"] for check in report.failed],
        )

    def test_a_missing_source_fails(self):
        rows = [row for row in FIXTURE_ROWS if row[12] != "worldbank_wdi"]
        report = self._report(rows)
        self.assertIn(
            "every registered source contributes records",
            [check["name"] for check in report.failed],
        )

    def test_the_layer_must_answer(self):
        report = self._report([])
        self.assertIn(
            "the layer answers a direct query",
            [check["name"] for check in report.failed],
        )


class OfflineApplicationTests(unittest.TestCase):
    """The application, reading a fixture of the layer's rows."""

    def test_the_application_reads_the_layer_rows(self):
        channel = _Channel(usl_rows=FIXTURE_ROWS)
        with patch("src.zetaris_source._client", return_value=channel):
            rows, trace = zetaris_source.load_with_trace()

        self.assertEqual(trace["path"], "zetaris_usl")
        self.assertEqual(len(rows), len(FIXTURE_ROWS))
        self.assertEqual(
            trace["source_ids"],
            [
                "dhs_cameroon_2018",
                "synthetic_programme_reports",
                "who_country_profile_2024",
                "worldbank_wdi",
                "wuenic_workbook_2025",
            ],
        )

    def test_the_lineage_survives_the_read(self):
        channel = _Channel(usl_rows=FIXTURE_ROWS)
        with patch("src.zetaris_source._client", return_value=channel):
            rows, _ = zetaris_source.load_with_trace()

        by_id = {row["source_id"]: row for row in rows}
        self.assertEqual(
            by_id["worldbank_wdi"]["origin_id"], "wuenic_2025"
        )
        self.assertTrue(by_id["worldbank_wdi"]["is_derived"])
        self.assertFalse(by_id["worldbank_wdi"]["independent_capable"])
        self.assertEqual(
            by_id["who_country_profile_2024"]["verification_scope"],
            "INDEPENDENT_MEASUREMENT",
        )
        self.assertTrue(
            by_id["synthetic_programme_reports"]["is_synthetic"]
        )

    def test_the_derived_copy_is_counted_once_with_its_series(self):
        """Three publications of the estimate are one line of evidence."""
        from src.analyzer import analyze_records

        channel = _Channel(usl_rows=FIXTURE_ROWS)
        with patch("src.zetaris_source._client", return_value=channel):
            rows, _ = zetaris_source.load_with_trace()

        findings = analyze_records(rows)
        self.assertEqual(len(findings), 1)
        observation = findings[0]["observations"]
        estimate_lines = [
            item for item in observation
            if item["measure"] == "WUENIC estimate"
        ]
        self.assertEqual(len(estimate_lines), 1)
        self.assertEqual(estimate_lines[0]["origin"], "wuenic_2025")


if __name__ == "__main__":
    unittest.main()
