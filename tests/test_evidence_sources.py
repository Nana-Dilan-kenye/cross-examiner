"""Tests for reading the evidence: the unified layer and the fallback."""

import unittest
from unittest.mock import patch

from src import evidence_sources


class _Result:
    def __init__(self, rows):
        self.rows = rows


class _Channel:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def run(self, sql, limit=100):
        self.queries.append(sql)
        return _Result(self._rows)

    def close(self):
        pass


VIEW = "cross_examiner.UNIFIED_EVIDENCE_TABLE"

# The columns of the semantic layer, in the order the USL declares them.
USL_ROW = [
    "obs-1", "Cameroon", "CMR", "MCV1", "2020", "Administrative coverage",
    "administrative", "administrative_reporting", "74.0", "percent",
    "Children 12-23 months", "Administrative coverage",
    "who_country_profile_2024", "pdf",
    "WUENIC country profile 2023 revision", "https://example.com/profile",
    "cameroon_admin_jrf", "Cameroon administrative reporting", "", "false",
    "false", "false", "SELF_CONSISTENCY", "verified_against_source_table",
    "Reported administrative figure",
]

VIEW_ROWS = [
    ["Cameroon", "MCV1", "2020", "Administrative coverage", "74.0",
     "WUENIC country profile 2023 revision", "https://example.com/profile", ""],
    ["Cameroon", "MCV1", "2020", "WUENIC estimate", "63.0",
     "WHO/UNICEF Estimates of National Immunization Coverage, 2025 revision",
     "https://example.com/wuenic", ""],
]


class ZetarisPathTests(unittest.TestCase):
    def test_the_semantic_layer_is_read_when_zetaris_is_reachable(self):
        """The application reads the USL, not the raw table or a view."""
        channel = _Channel([USL_ROW])
        with patch("src.zetaris_source._client", return_value=channel):
            rows, trace = evidence_sources.load_records(prefer_zetaris=True)

        self.assertEqual(trace[0]["origin"], "zetaris_usl")
        self.assertEqual(
            trace[0]["read_from"],
            "lightning.metastore.cross_examiner.coverage_observations"
            ".coverage_observation",
        )
        self.assertIn("coverage_observations", channel.queries[0])
        self.assertEqual(rows[0]["origin_id"], "cameroon_admin_jrf")
        self.assertEqual(rows[0]["source_id"], "who_country_profile_2024")

    def test_the_trace_names_the_source_ids_the_layer_returned(self):
        channel = _Channel([USL_ROW])
        with patch("src.zetaris_source._client", return_value=channel):
            _, trace = evidence_sources.load_records(prefer_zetaris=True)

        self.assertEqual(
            trace[0]["source_ids"], ["who_country_profile_2024"]
        )

    def test_the_layer_rows_carry_the_lineage(self):
        channel = _Channel([USL_ROW])
        with patch("src.zetaris_source._client", return_value=channel):
            rows, _ = evidence_sources.load_records(prefer_zetaris=True)

        row = rows[0]
        self.assertEqual(row["year"], "2020")
        self.assertEqual(row["measure"], "Administrative coverage")
        self.assertEqual(row["value_percent"], "74.0")
        self.assertEqual(row["source_url"], "https://example.com/profile")
        self.assertFalse(row["is_derived"])
        self.assertFalse(row["is_synthetic"])
        self.assertEqual(row["verification_scope"], "SELF_CONSISTENCY")

    def test_the_unified_view_is_read_when_it_is_asked_for(self):
        channel = _Channel(VIEW_ROWS)
        with patch("src.zetaris_source._client", return_value=channel):
            from src.zetaris_source import load_with_trace
            _, trace = load_with_trace(view=VIEW)

        self.assertEqual(trace["path"], "zetaris_view")
        self.assertEqual(trace["object"], VIEW)

    def test_the_fallback_is_used_when_zetaris_cannot_be_reached(self):
        def boom():
            raise FileNotFoundError("no Zetaris client here")

        with patch("src.zetaris_source._client", side_effect=boom):
            rows, trace = evidence_sources.load_records(prefer_zetaris=True)

        self.assertEqual(trace[0]["origin"], "local")
        self.assertIn("local files", trace[0]["read_from"])
        self.assertTrue(rows)
        self.assertTrue(
            any(row["measure"] == "Administrative coverage" for row in rows)
        )

    def test_the_fallback_is_used_when_the_view_is_empty(self):
        channel = _Channel([])
        with patch("src.zetaris_source._client", return_value=channel):
            rows, trace = evidence_sources.load_records(prefer_zetaris=True)

        self.assertEqual(trace[0]["origin"], "local")
        self.assertTrue(rows)

    def test_the_compiled_survey_sheet_is_always_included(self):
        rows, trace = evidence_sources.load_records(prefer_zetaris=False)
        measures = [row["measure"] for row in rows]
        self.assertIn("Household survey coverage", measures)
        self.assertTrue(
            any(entry["source_id"] == "compiled_survey_figures" for entry in trace)
        )

    def test_the_synthetic_rows_are_only_included_on_request(self):
        rows, _ = evidence_sources.load_records(
            prefer_zetaris=False, include_synthetic=False
        )
        self.assertFalse(
            any(row["country"] == "Meridia" for row in rows)
        )

        rows, trace = evidence_sources.load_records(
            prefer_zetaris=False, include_synthetic=True
        )
        self.assertTrue(any(row["country"] == "Meridia" for row in rows))
        self.assertTrue(
            any(entry["source_id"] == "synthetic_programme_reports" for entry in trace)
        )

    def test_the_synthetic_rows_carry_their_label(self):
        rows = evidence_sources.synthetic_rows()
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["is_synthetic"], "true")
            self.assertIn("SYNTHETIC", row["source"])


class SchemaAgreementTests(unittest.TestCase):
    def test_the_application_reads_exactly_the_columns_the_layer_declares(self):
        """The layer and the application must not drift apart.

        The column list the application asks for is the one the USL
        declares; if the model changes, this fails.
        """
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "generate_usl_sql",
            root / "scripts" / "generate_usl_sql.py",
        )
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)

        from src import zetaris_source

        declared = [name for name, _ in generator.COLUMNS]
        asked = [name for name, _ in zetaris_source.USL_COLUMNS]

        self.assertEqual(asked, declared)


if __name__ == "__main__":
    unittest.main()
