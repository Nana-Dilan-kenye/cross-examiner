"""Tests for the HTTP interface.

The API is exercised in sample mode: no network, no credentials, no
Zetaris. The live path is covered by ``scripts/verify_journey.py``.
"""

import json
import os
import unittest
from unittest.mock import patch

from src import app


class HealthTests(unittest.TestCase):
    def test_health_reports_the_mode_and_the_components(self):
        with patch.dict(os.environ, {"SAMPLE_MODE": "true"}):
            report = app.health()

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["mode"], "sample")
        self.assertTrue(report["sample_mode"])
        self.assertIn("zetaris_usl", report["components"])
        self.assertIn("memory", report["components"])
        self.assertIn("registry", report["components"])

    def test_health_names_the_semantic_layer(self):
        report = app.health()
        self.assertEqual(
            report["semantic_layer"],
            "lightning.metastore.cross_examiner.coverage_observations"
            ".coverage_observation",
        )


class RunTests(unittest.TestCase):
    def _run(self, **request):
        request.setdefault("source", "local")
        request.setdefault("model", "off")
        request.setdefault("use_memory", False)
        with patch.dict(os.environ, {"SAMPLE_MODE": "true"}):
            return app.run_payload(request)

    def test_a_run_returns_the_structured_result(self):
        payload = self._run(
            question="Which Cameroon MCV1 figure should we use for 2020?",
            country="Cameroon", antigen="MCV1", year="2020",
        )

        self.assertIn("run_id", payload)
        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["mode"], "sample")
        self.assertTrue(payload["trace"].endswith(".jsonl"))

        finding = payload["findings"][0]
        self.assertEqual(finding["country"], "Cameroon")
        self.assertEqual(finding["year"], "2020")
        self.assertEqual(finding["review_status"], "REVIEW")
        self.assertIn(finding["confidence"], ("high", "moderate", "low", "none"))
        self.assertTrue(finding["lineage"])
        self.assertTrue(finding["evidence"])
        self.assertEqual(finding["evidence"][0]["evidence_id"], "ev-1")

    def test_the_lineage_travels_with_the_finding(self):
        payload = self._run(
            question="Cameroon MCV1 2020", country="Cameroon",
            antigen="MCV1", year="2020",
        )
        lineage = payload["findings"][0]["lineage"]
        origins = {item["origin"] for item in lineage}

        self.assertIn("wuenic_2025", origins)
        self.assertIn("cameroon_admin_jrf", origins)
        self.assertIn("cameroon_household_survey", origins)

    def test_the_recommendation_is_returned(self):
        payload = self._run(
            question="Cameroon MCV1 2020", country="Cameroon",
            antigen="MCV1", year="2020",
        )
        recommendation = payload["findings"][0]["recommendation"]
        self.assertEqual(
            recommendation["recommended_measure"], "Household survey coverage"
        )
        self.assertEqual(recommendation["recommended_value"], 54.0)

    def test_a_year_without_an_independent_line_has_no_recommendation(self):
        payload = self._run(
            question="Cameroon MCV1 2023", country="Cameroon",
            antigen="MCV1", year="2023",
        )
        self.assertIsNone(payload["findings"][0]["recommendation"])

    def test_the_trace_file_is_written(self):
        payload = self._run(
            question="Cameroon MCV1 2020", country="Cameroon",
            antigen="MCV1", year="2020",
        )
        from src.tracing import read_trace
        events = read_trace(payload["run_id"])
        self.assertTrue(events)
        actions = {event["action"] for event in events}
        self.assertIn("run.started", actions)
        self.assertIn("investigation.started", actions)
        self.assertIn("run.finished", actions)

        # The log shape the technical guidance asks for.
        for event in events:
            for field in (
                "timestamp", "run_id", "agent_name", "action",
                "input_summary", "output_summary", "target_agent",
                "confidence", "retry_count", "status",
            ):
                self.assertIn(field, event)

        # More than one agent, and visible handovers between them.
        from src.tracing import agent_names, handoffs
        self.assertGreaterEqual(len(agent_names(events)), 2)
        self.assertTrue(handoffs(events))

    def test_the_sample_mode_marks_the_data_kind(self):
        payload = self._run(
            question="Cameroon MCV1 2020", country="Cameroon",
            antigen="MCV1", year="2020",
        )
        self.assertTrue(
            payload["findings"][0]["data_kind"].startswith("sample:")
        )

    def test_the_generated_records_are_checked_but_never_evidence(self):
        with patch.dict(os.environ, {"SAMPLE_MODE": "true"}):
            payload = app.run_payload({
                "question": "Meridia programme reports",
                "country": "Meridia",
                "source": "local",
                "model": "off",
                "use_memory": False,
                "include_synthetic": True,
            })
        # The generated records are checked by their own rules ...
        self.assertTrue(payload["programme_checks"])
        self.assertTrue(
            all(item["data_kind"] == "synthetic"
                for item in payload["programme_checks"])
        )
        # ... and they never become a finding about a real country.
        self.assertEqual(
            [finding for finding in payload["findings"]
             if finding["country"] != "Meridia"],
            [],
        )

    def test_the_generated_records_are_excluded_by_default(self):
        payload = self._run(
            question="Cameroon MCV1 2020", country="Cameroon",
            antigen="MCV1", year="2020",
        )
        self.assertEqual(payload["programme_checks"], [])
        self.assertFalse(
            any("Meridia" in finding["country"]
                for finding in payload["findings"])
        )


class ValidationTests(unittest.TestCase):
    def _expect_error(self, **request):
        with self.assertRaises(ValueError) as caught:
            app.run_payload(request)
        return str(caught.exception)

    def test_a_request_without_a_question_or_a_topic_is_refused(self):
        message = self._expect_error(source="local", model="off")
        self.assertIn("question", message)

    def test_a_question_that_is_not_a_string_is_refused(self):
        message = self._expect_error(question=42, source="local", model="off")
        self.assertIn("question", message)

    def test_an_unknown_source_is_refused(self):
        message = self._expect_error(
            question="Cameroon MCV1 2020", source="carrier-pigeon",
        )
        self.assertIn("source", message)

    def test_a_threshold_that_is_not_a_number_is_refused(self):
        message = self._expect_error(
            question="Cameroon MCV1 2020", source="local", threshold="high",
        )
        self.assertIn("threshold", message)

    def test_too_many_iterations_is_refused(self):
        message = self._expect_error(
            question="Cameroon MCV1 2020", source="local", max_iterations=99,
        )
        self.assertIn("max_iterations", message)


class TraceTests(unittest.TestCase):
    def test_the_trace_is_readable_by_run_id(self):
        from src.tracing import Trace, read_trace
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            trace = Trace(run_id="abc123", directory=Path(tmp))
            trace.event("test.event", value=1)
            trace.close()
            events = read_trace("abc123", directory=Path(tmp))

        self.assertIn("test.event", [event["action"] for event in events])

    def test_secrets_are_redacted(self):
        from src.tracing import redact

        redacted = redact({
            "api_key": "abc123",
            "note": "Authorization: Bearer sk-secret-value",
            "safe": "nothing to hide",
        })
        self.assertEqual(redacted["api_key"], "[redacted]")
        self.assertIn("[redacted]", redacted["note"])
        self.assertEqual(redacted["safe"], "nothing to hide")


if __name__ == "__main__":
    unittest.main()
