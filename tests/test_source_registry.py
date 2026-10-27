"""Tests for the source registry: the lineage every number carries."""

import csv
import unittest
from pathlib import Path

from src import source_registry

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "data" / "coverage_evidence.csv"
SURVEY = ROOT / "data" / "survey_figures.csv"

WHO_URL = (
    "https://cdn.who.int/media/docs/default-source/country-profiles/"
    "immunization/2024-country-profiles/immunization-2024-cmr.pdf?download=true"
    "&sfvrsn=fb0d6c18_3"
)
UNICEF_URL = "https://data.unicef.org/resources/dataset/immunization/"
ETHIOPIA_URL = (
    "https://cdn.who.int/media/docs/default-source/country-profiles/"
    "immunization/2024-country-profiles/immunization-2024-eth.pdf"
)


def _rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class RegistryTests(unittest.TestCase):
    def test_every_source_in_the_evidence_file_is_registered(self):
        for row in _rows(EVIDENCE):
            source = {"name": row["source"], "url": row["source_url"]}
            self.assertIsNotNone(
                source_registry.entry_for(source),
                f"{row['source']} is not in the registry",
            )

    def test_every_source_in_the_compiled_survey_sheet_is_registered(self):
        for row in _rows(SURVEY):
            source = {"name": row["source_id"], "url": row["source_ref"]}
            self.assertIsNotNone(source_registry.entry_for(source))

    def test_the_estimate_and_the_country_profile_share_one_series(self):
        """The country profile republishes the WUENIC estimate.

        It publishes an earlier revision of it, so the two are the same
        series but not the same origin: a revision can neither confirm nor
        contradict the other.
        """
        workbook = {"name": "WUENIC 2025 revision", "url": UNICEF_URL}
        profile = {"name": "WUENIC country profile 2023 revision", "url": WHO_URL}

        self.assertEqual(
            source_registry.origin_for(workbook, "WUENIC estimate"),
            "wuenic_2025",
        )
        self.assertEqual(
            source_registry.origin_for(profile, "WUENIC estimate"),
            "wuenic_2023",
        )
        self.assertTrue(source_registry.same_series(
            "wuenic_2023", "wuenic_2025",
        ))

    def test_two_countries_have_separate_series(self):
        """One country's administrative reporting is not another's."""
        cameroon = {
            "name": "WUENIC country profile 2023 revision", "url": WHO_URL,
        }
        ethiopia = {
            "name": "WHO/UNICEF country profile for Ethiopia (2023 revision)",
            "url": ETHIOPIA_URL,
        }
        cameroon_origin = source_registry.origin_for(
            cameroon, "Administrative coverage",
        )
        ethiopia_origin = source_registry.origin_for(
            ethiopia, "Administrative coverage",
        )
        self.assertNotEqual(cameroon_origin, ethiopia_origin)
        self.assertFalse(source_registry.same_series(
            cameroon_origin, ethiopia_origin,
        ))

    def test_the_administrative_and_the_survey_rows_have_their_own_origins(self):
        profile = {"name": "WUENIC country profile 2023 revision", "url": WHO_URL}
        self.assertEqual(
            source_registry.origin_for(profile, "Administrative coverage"),
            "cameroon_admin_jrf",
        )
        self.assertEqual(
            source_registry.origin_for(profile, "Household survey coverage"),
            "cameroon_household_survey",
        )

    def test_a_derived_mirror_is_not_the_origin_of_the_series(self):
        """The World Bank republishes the estimate, so it is derived."""
        worldbank = {
            "name": "World Bank Indicators",
            "url": "https://api.worldbank.org/v2/country/CMR/indicator/SH.IMM.MEAS",
        }
        entry = source_registry.entry_for(worldbank)
        self.assertEqual(entry["source_id"], "worldbank_wdi")
        self.assertEqual(entry["derived_from"], "wuenic_workbook_2025")
        self.assertTrue(source_registry.is_derived(worldbank))
        self.assertEqual(
            source_registry.origin_for(worldbank, "WUENIC estimate"),
            "wuenic_2025",
        )

    def test_the_survey_report_is_the_own_publication_of_the_survey(self):
        survey = {
            "name": "Cameroon DHS 2018 survey report",
            "url": "https://dhsprogram.com/pubs/pdf/SR266/SR266.pdf",
        }
        origin = source_registry.origin_for(survey, "Household survey coverage")
        self.assertEqual(origin, "cameroon_household_survey")
        self.assertTrue(source_registry.is_own_publication(survey, origin))

    def test_the_country_profile_is_not_the_own_publication_of_the_survey(self):
        """It republishes the survey, so checking against it is not the
        survey's own published table."""
        profile = {"name": "WUENIC country profile 2023 revision", "url": WHO_URL}
        self.assertFalse(
            source_registry.is_own_publication(
                profile, "cameroon_household_survey"
            )
        )

    def test_only_a_household_survey_is_an_independent_measurement(self):
        profile = {"name": "WUENIC country profile 2023 revision", "url": WHO_URL}
        self.assertTrue(
            source_registry.is_independent_measurement(
                profile, "Household survey coverage"
            )
        )
        self.assertFalse(
            source_registry.is_independent_measurement(
                profile, "Administrative coverage"
            )
        )

    def test_the_lineage_does_not_depend_on_the_words_in_a_source_name(self):
        """Renaming a source must not change what it counts as.

        The old code guessed the upstream from the name, so renaming a
        source could turn a self-consistency check into an independent
        verification.
        """
        profile = {"name": "WUENIC country profile 2023 revision", "url": WHO_URL}
        renamed = {"name": "WHO country profile 2024", "url": WHO_URL}

        self.assertEqual(
            source_registry.origin_for(profile, "WUENIC estimate"),
            source_registry.origin_for(renamed, "WUENIC estimate"),
        )
        self.assertEqual(
            source_registry.lineage(profile, "WUENIC estimate")["origin"],
            source_registry.lineage(renamed, "WUENIC estimate")["origin"],
        )

    def test_the_registry_file_is_valid_and_complete(self):
        registry = source_registry.load_registry()
        self.assertIn("origins", registry)
        self.assertIn("sources", registry)
        for entry in registry["sources"]:
            self.assertIn("source_id", entry)
            self.assertIn("source_type", entry)
            for measure, origin in (entry.get("origin_of_measure") or {}).items():
                self.assertIn(
                    origin,
                    registry["origins"],
                    f"{entry['source_id']}: {measure} points at an unknown origin",
                )

    def test_the_synthetic_source_is_marked_synthetic(self):
        synthetic = {
            "name": "SYNTHETIC district programme reports",
            "url": "",
        }
        self.assertTrue(source_registry.is_synthetic(synthetic))
        entry = source_registry.entry_for(synthetic)
        self.assertTrue(entry["is_synthetic"])


if __name__ == "__main__":
    unittest.main()
