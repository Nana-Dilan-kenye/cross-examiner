"""Tests for the verification scope: what a source check may support."""

import unittest

from src.critic import detect_conflicts, value_scope, verification_scope
from src.evidence_ledger import (
    SCOPE_CONTEXT_ONLY,
    SCOPE_INDEPENDENT,
    SCOPE_SELF_CONSISTENCY,
)

WHO_URL = (
    "https://cdn.who.int/media/docs/default-source/country-profiles/"
    "immunization/2024-country-profiles/immunization-2024-cmr.pdf"
)
UNICEF_URL = "https://data.unicef.org/resources/dataset/immunization/"
DHS_URL = "https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf"
WORLD_BANK_URL = (
    "https://api.worldbank.org/v2/country/CMR/indicator/SH.IMM.MEAS"
)
SDMX_URL = "https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/UNICEF,IMMUNISATION,1.0/"


def _finding(**overrides):
    finding = {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2020",
        "measure_a": "WUENIC estimate",
        "value_a": 63.0,
        "measure_b": "Administrative coverage",
        "value_b": 74.0,
        "gap_percentage_points": 11.0,
        "sources": [
            {"name": "WUENIC 2025 revision", "url": UNICEF_URL},
            {"name": "WUENIC country profile 2023 revision", "url": WHO_URL},
        ],
        "measure_sources": {
            "value_a": {"name": "WUENIC 2025 revision", "url": UNICEF_URL},
            "value_b": {
                "name": "WUENIC country profile 2023 revision",
                "url": WHO_URL,
            },
        },
    }
    finding.update(overrides)
    return finding


def _matched(field, measure, found=True):
    return {
        "field": field,
        "measure": measure,
        "expected": 63.0,
        "table_value": "63",
        "found_in_expected_year_row": found,
    }


class ScopeTests(unittest.TestCase):
    def test_the_country_profile_is_not_independent_confirmation(self):
        """It republishes the WUENIC estimate, so it cannot confirm it."""
        finding = _finding()
        scope, note = verification_scope(
            finding,
            finding["sources"][1],
            "CONTEXT_MATCHED",
            [_matched("value_a", "WUENIC estimate")],
        )
        self.assertEqual(scope, SCOPE_SELF_CONSISTENCY)
        # The country profile publishes an earlier revision of the same
        # series, so it cannot confirm the workbook's figure.
        self.assertIn("revision", note)

    def test_a_source_publishing_an_earlier_revision_cannot_confirm(self):
        """A revision is not a second opinion."""
        finding = _finding()
        scope, note = verification_scope(
            finding,
            finding["sources"][1],
            "CONTEXT_MATCHED",
            [_matched("value_a", "WUENIC estimate")],
        )
        self.assertEqual(scope, SCOPE_SELF_CONSISTENCY)
        self.assertIn("earlier revision", note)

    def test_a_derived_mirror_is_not_independent_confirmation(self):
        """The World Bank and the UNICEF data warehouse republish the
        estimate, so they count once with it."""
        finding = _finding(
            sources=[
                {"name": "World Bank Indicators", "url": WORLD_BANK_URL},
                {"name": "UNICEF Data Warehouse SDMX", "url": SDMX_URL},
            ],
            measure_sources={
                "value_a": {
                    "name": "World Bank Indicators",
                    "url": WORLD_BANK_URL,
                },
                "value_b": {
                    "name": "UNICEF Data Warehouse SDMX",
                    "url": SDMX_URL,
                },
            },
        )
        scope, _ = verification_scope(
            finding,
            finding["sources"][1],
            "CONTEXT_MATCHED",
            [_matched("value_a", "WUENIC estimate")],
        )
        self.assertEqual(scope, SCOPE_SELF_CONSISTENCY)

    def test_the_survey_report_is_independent_confirmation_of_the_survey(self):
        """The survey's own report is where the survey is published.

        The country profile republishes the survey, so a value read out of
        the profile and checked against the survey report is a check
        against the origin's own published table.
        """
        finding = _finding(
            measure_a="Household survey coverage",
            measure_b="Administrative coverage",
            sources=[
                {"name": "WHO country profile", "url": WHO_URL},
                {"name": "Cameroon DHS 2018 survey report", "url": DHS_URL},
            ],
            measure_sources={
                "value_a": {"name": "WHO country profile", "url": WHO_URL},
                "value_b": {"name": "WHO country profile", "url": WHO_URL},
            },
        )
        scope, _ = verification_scope(
            finding,
            finding["sources"][1],
            "CONTEXT_MATCHED",
            [_matched("value_a", "Household survey coverage")],
        )
        self.assertEqual(scope, SCOPE_INDEPENDENT)

    def test_a_value_read_back_from_its_own_document_is_self_consistency(self):
        """Reading the survey out of the survey report proves the
        extraction worked, not that the survey is right."""
        finding = _finding(
            measure_a="Household survey coverage",
            measure_b="Administrative coverage",
            sources=[
                {"name": "Cameroon DHS 2018 survey report", "url": DHS_URL},
            ],
            measure_sources={
                "value_a": {
                    "name": "Cameroon DHS 2018 survey report",
                    "url": DHS_URL,
                },
                "value_b": {"name": "WHO country profile", "url": WHO_URL},
            },
        )
        scope, _ = verification_scope(
            finding,
            finding["sources"][0],
            "CONTEXT_MATCHED",
            [_matched("value_a", "Household survey coverage")],
        )
        self.assertEqual(scope, SCOPE_SELF_CONSISTENCY)

    def test_a_household_survey_against_an_administrative_line_is_a_measurement(self):
        """Different measurement process: independent evidence about the
        level, not a verification of the other number."""
        finding = _finding(
            measure_a="Household survey coverage",
            measure_b="Administrative coverage",
            sources=[
                {"name": "WHO country profile", "url": WHO_URL},
            ],
            measure_sources={
                "value_a": {"name": "WHO country profile", "url": WHO_URL},
                "value_b": {"name": "WHO country profile", "url": WHO_URL},
            },
        )
        scope, note = value_scope(
            finding,
            finding["sources"][0],
            "value_b",
            {"measure": "Administrative coverage"},
        )
        self.assertEqual(scope, SCOPE_SELF_CONSISTENCY)

    def test_an_unverified_source_is_context_only(self):
        finding = _finding()
        scope, _ = verification_scope(
            finding, finding["sources"][0], "NOT_VERIFIED", []
        )
        self.assertEqual(scope, SCOPE_CONTEXT_ONLY)

    def test_a_retrieved_document_is_document_presence(self):
        finding = _finding()
        scope, _ = verification_scope(
            finding, finding["sources"][1], "SOURCE_DOCUMENT_RETRIEVED", []
        )
        self.assertEqual(scope, "DOCUMENT_PRESENCE")


class RevisionTests(unittest.TestCase):
    """A revision of a series is not a conflict and not a confirmation."""

    ETHIOPIA_URL = (
        "https://cdn.who.int/media/docs/default-source/country-profiles/"
        "immunization/2024-country-profiles/immunization-2024-eth.pdf"
    )

    def _finding(self):
        from src.analyzer import analyze_records

        records = [
            {
                "country": "Ethiopia", "antigen": "MCV1", "year": "2017",
                "measure": "WUENIC estimate", "value_percent": "59",
                "source": "WUENIC 2025 revision",
                "source_url": UNICEF_URL, "notes": "",
            },
            {
                "country": "Ethiopia", "antigen": "MCV1", "year": "2017",
                "measure": "Administrative coverage", "value_percent": "92",
                "source": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
                "source_url": self.ETHIOPIA_URL, "notes": "",
            },
        ]
        return analyze_records(records)[0]

    def test_a_revision_difference_is_marked_as_such(self):
        from src.critic import _mark_revision_differences

        finding = self._finding()
        source = {
            "name": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
            "url": self.ETHIOPIA_URL,
        }
        marked = _mark_revision_differences(finding, source, [{
            "field": "value_a",
            "measure": "WUENIC estimate",
            "expected": 59.0,
            "table_value": "58",
            "found_in_expected_year_row": False,
        }])
        self.assertTrue(marked[0].get("revision_difference"))
        self.assertIn("revision", marked[0].get("revision_note", ""))

    def test_a_revision_difference_is_not_an_independent_measurement(self):
        finding = self._finding()
        source = {
            "name": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
            "url": self.ETHIOPIA_URL,
        }
        scope, note = value_scope(
            finding, source, "value_a",
            {"measure": "WUENIC estimate"},
        )
        self.assertEqual(scope, SCOPE_SELF_CONSISTENCY)
        self.assertIn("revision", note)

    def test_two_countries_do_not_share_a_series(self):
        from src import source_registry

        cameroon = {
            "name": "WUENIC country profile 2023 revision", "url": WHO_URL,
        }
        ethiopia = {
            "name": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
            "url": self.ETHIOPIA_URL,
        }
        self.assertFalse(source_registry.same_series(
            source_registry.origin_for(cameroon, "Administrative coverage"),
            source_registry.origin_for(ethiopia, "Administrative coverage"),
        ))


class ConflictTests(unittest.TestCase):
    def test_the_administrative_figure_against_the_survey_is_a_conflict(self):
        from src.analyzer import analyze_records

        records = [
            {
                "country": "Cameroon",
                "antigen": "MCV1",
                "year": "2020",
                "measure": "WUENIC estimate",
                "value_percent": "63",
                "source": "WUENIC 2025 revision",
                "source_url": UNICEF_URL,
                "notes": "",
            },
            {
                "country": "Cameroon",
                "antigen": "MCV1",
                "year": "2020",
                "measure": "Administrative coverage",
                "value_percent": "74",
                "source": "WUENIC country profile 2023 revision",
                "source_url": WHO_URL,
                "notes": "",
            },
            {
                "country": "Cameroon",
                "antigen": "MCV1",
                "year": "2020",
                "measure": "Household survey coverage",
                "value_percent": "54",
                "source": "WUENIC country profile 2023 revision",
                "source_url": WHO_URL,
                "notes": "",
            },
        ]
        finding = analyze_records(records)[0]
        conflicts = detect_conflicts(finding)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["code"], "CONFLICT_ADMIN_SURVEY")
        self.assertAlmostEqual(conflicts[0]["gap_percentage_points"], 20.0)
        self.assertIn("unverified", conflicts[0]["note"])
        self.assertNotIn("confirmed truth", conflicts[0]["note"])

    def test_two_publications_of_one_series_are_not_a_conflict(self):
        finding = _finding()
        self.assertEqual(detect_conflicts(finding), [])


if __name__ == "__main__":
    unittest.main()
