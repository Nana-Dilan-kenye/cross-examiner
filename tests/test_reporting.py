"""Tests for what the report says, and for the recommendation it carries."""

import unittest

from src.analyzer import analyze_records
from src.arbiter import arbitrate
from src.reporter import render_report

WHO_URL = (
    "https://cdn.who.int/media/docs/default-source/country-profiles/"
    "immunization/2024-country-profiles/immunization-2024-cmr.pdf"
)
UNICEF_URL = "https://data.unicef.org/resources/dataset/immunization/"

EVIDENCE = [
    {
        "country": "Cameroon", "antigen": "MCV1", "year": "2020",
        "measure": "WUENIC estimate", "value_percent": "63",
        "source": "WUENIC 2025 revision", "source_url": UNICEF_URL,
        "notes": "Estimate",
    },
    {
        "country": "Cameroon", "antigen": "MCV1", "year": "2020",
        "measure": "Administrative coverage", "value_percent": "74",
        "source": "WUENIC country profile 2023 revision", "source_url": WHO_URL,
        "notes": "Reported administrative figure",
    },
    {
        "country": "Cameroon", "antigen": "MCV1", "year": "2020",
        "measure": "Household survey coverage", "value_percent": "54",
        "source": "WUENIC country profile 2023 revision", "source_url": WHO_URL,
        "notes": "Household survey row published in the country profile",
    },
]


class RecommendationTests(unittest.TestCase):
    def test_the_survey_line_produces_a_recommendation(self):
        finding = analyze_records(EVIDENCE)[0]
        decision = arbitrate(finding)

        recommendation = decision.get("recommendation")
        self.assertIsNotNone(recommendation)
        self.assertEqual(
            recommendation["recommended_measure"], "Household survey coverage"
        )
        self.assertEqual(recommendation["recommended_value"], 54.0)
        self.assertEqual(
            recommendation["not_recommended_measure"], "Administrative coverage"
        )
        self.assertAlmostEqual(
            recommendation["gap_percentage_points"], 20.0
        )
        self.assertTrue(recommendation["caveats"])

    def test_a_finding_without_a_survey_line_has_no_recommendation(self):
        decision = arbitrate(analyze_records(EVIDENCE[:2])[0])
        self.assertIsNone(decision.get("recommendation"))

    def test_the_recommendation_does_not_claim_a_figure_is_correct(self):
        finding = analyze_records(EVIDENCE)[0]
        decision = arbitrate(finding)
        caveats = " ".join(decision["recommendation"]["caveats"])
        self.assertIn("not a claim", caveats)


class SecondCountryTests(unittest.TestCase):
    def test_two_countries_are_analysed_and_kept_apart(self):
        from src.analyzer import analyze_records
        from src.critic import critique

        records = [
            {"country": "Cameroon", "antigen": "MCV1", "year": "2020",
             "measure": "WUENIC estimate", "value_percent": "63",
             "source": "WUENIC 2025 revision",
             "source_url": "https://data.unicef.org/resources/dataset/immunization/",
             "notes": ""},
            {"country": "Cameroon", "antigen": "MCV1", "year": "2020",
             "measure": "Administrative coverage", "value_percent": "74",
             "source": "WUENIC country profile 2023 revision",
             "source_url": "https://cdn.who.int/x/immunization-2024-cmr.pdf",
             "notes": ""},
            {"country": "Ethiopia", "antigen": "MCV1", "year": "2017",
             "measure": "WUENIC estimate", "value_percent": "59",
             "source": "WUENIC 2025 revision",
             "source_url": "https://data.unicef.org/resources/dataset/immunization/",
             "notes": ""},
            {"country": "Ethiopia", "antigen": "MCV1", "year": "2017",
             "measure": "Administrative coverage", "value_percent": "92",
             "source": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
             "source_url": "https://cdn.who.int/x/immunization-2024-eth.pdf",
             "notes": ""},
            {"country": "Ethiopia", "antigen": "MCV1", "year": "2017",
             "measure": "Household survey coverage", "value_percent": "58",
             "source": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
             "source_url": "https://cdn.who.int/x/immunization-2024-eth.pdf",
             "notes": ""},
        ]
        findings = analyze_records(records)
        self.assertEqual(len(findings), 2)

        countries = {finding["country"] for finding in findings}
        self.assertEqual(countries, {"Cameroon", "Ethiopia"})

        ethiopia = next(
            finding for finding in findings if finding["country"] == "Ethiopia"
        )
        origins = {
            observation.get("origin") for observation in ethiopia["observations"]
        }
        self.assertIn("ethiopia_admin_jrf", origins)
        self.assertIn("ethiopia_household_survey", origins)
        self.assertNotIn("cameroon_admin_jrf", origins)

        decision = critique(ethiopia)
        conflicts = decision["conflicts"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["code"], "CONFLICT_ADMIN_SURVEY")
        self.assertAlmostEqual(conflicts[0]["gap_percentage_points"], 34.0)


class ReportTests(unittest.TestCase):
    def _results(self, findings):
        decisions = [arbitrate(finding) for finding in findings]
        return {
            "records_loaded": len(findings) * 3,
            "findings": findings,
            "decisions": decisions,
            "evidence_trace": [
                {
                    "source_id": "published_coverage_figures",
                    "records": 10,
                    "read_from": "cameroon_mcv1_evidence.csv",
                    "origin": "local",
                    "reason": None,
                }
            ],
        }

    def test_the_report_shows_the_lineage_of_every_number(self):
        report = render_report(self._results(analyze_records(EVIDENCE)))
        self.assertIn("## Sources and their lineage", report)
        self.assertIn("wuenic_2025", report)
        self.assertIn("Republishes", report)

    def test_the_report_shows_where_the_evidence_came_from(self):
        report = render_report(self._results(analyze_records(EVIDENCE)))
        self.assertIn("## Where the evidence came from", report)
        self.assertIn("cameroon_mcv1_evidence.csv", report)

    def test_the_report_shows_the_recommendation(self):
        report = render_report(self._results(analyze_records(EVIDENCE)))
        self.assertIn("### Recommendation for the coverage level", report)
        self.assertIn("Household survey coverage", report)
        self.assertIn("Do not use as the coverage level", report)

    def test_the_report_shows_the_other_reported_numbers(self):
        report = render_report(self._results(analyze_records(EVIDENCE)))
        self.assertIn("### Other reported numbers", report)
        self.assertIn("54.0", report)

    def test_a_synthetic_finding_is_labelled(self):
        records = [dict(row) for row in EVIDENCE]
        for row in records:
            row["country"] = "Meridia"
            row["source"] = "SYNTHETIC district programme reports"
            row["source_url"] = "synthetic://meridian/district-returns"
        findings = analyze_records(records)
        self.assertTrue(findings[0]["synthetic"])

        report = render_report(self._results(findings))
        self.assertIn("## SYNTHETIC DATA", report)
        self.assertIn("SYNTHETIC RECORD", report)


if __name__ == "__main__":
    unittest.main()
