"""The memory feature: what an earlier investigation changes.

These tests are deterministic. They use a fake memory store, never the
H-MEM engine, so they prove the *behaviour* - that a remembered finding
changes what the next investigation does - without depending on a
service. The live bridge is exercised by
``scripts/verify_journey.py``.
"""

import unittest
from unittest.mock import patch

from src.arbiter import arbitrate
from src.coordination import investigate
from src.investigator import CallBudget, default_proposal
from src.memory_policy import (
    CONFLICT_PREFIX,
    conflict_memory,
    question_memory,
    recall,
)
from src.tracing import Trace

WHO_URL = (
    "https://cdn.who.int/media/docs/default-source/country-profiles/"
    "immunization/2024-country-profiles/immunization-2024-cmr.pdf"
)
UNICEF_URL = "https://data.unicef.org/resources/dataset/immunization/"

CONFLICT_MEMORY = {
    "id": "mem-49",
    "source": f"{CONFLICT_PREFIX}Cameroon:MCV1:2020",
    "content": (
        "For Cameroon MCV1 in 2020, the administrative figure (74.0%) sits "
        "20.0 percentage points above an independent household-survey "
        "measurement (54.0%)."
    ),
    "confidence": 0.7,
    "refs": [WHO_URL],
}

DISPOSITION_MEMORY = {
    "id": "mem-40",
    "source": "cross-examiner:disposition:Cameroon:MCV1:2020",
    "content": "Final disposition for Cameroon MCV1 2020: REVIEW.",
    "confidence": 0.7,
    "refs": [],
}


def finding(year="2020"):
    return {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": year,
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
        "observations": [
            {
                "field": "value_a",
                "measure": "WUENIC estimate",
                "value": 63.0,
                "source": {"name": "WUENIC 2025 revision", "url": UNICEF_URL},
                "measurement_kind": "reconciled_estimate",
                "origin": "wuenic_2025",
            },
            {
                "field": "value_b",
                "measure": "Administrative coverage",
                "value": 74.0,
                "source": {
                    "name": "WUENIC country profile 2023 revision",
                    "url": WHO_URL,
                },
                "measurement_kind": "administrative_reporting",
                "origin": "cameroon_admin_jrf",
            },
            {
                "field": "value_c",
                "measure": "Household survey coverage",
                "value": 54.0,
                "source": {
                    "name": "WUENIC country profile 2023 revision",
                    "url": WHO_URL,
                },
                "measurement_kind": "household_survey",
                "origin": "cameroon_household_survey",
            },
        ],
    }


class RecallTests(unittest.TestCase):
    def test_a_remembered_conflict_is_recalled_for_the_same_topic(self):
        recalled = recall([CONFLICT_MEMORY], finding())
        self.assertTrue(recalled["has_prior_conflict"])
        self.assertEqual(recalled["memory_ids"], ["mem-49"])
        self.assertEqual(recalled["preferred_action"], "FETCH_SOURCE_DOCUMENT")
        self.assertEqual(recalled["preferred_target"], WHO_URL)
        self.assertIn("earlier investigation", recalled["effect"])

    def test_a_memory_about_another_year_is_not_recalled(self):
        recalled = recall([CONFLICT_MEMORY], finding(year="2023"))
        self.assertFalse(recalled["has_prior_conflict"])
        self.assertEqual(recalled["memory_ids"], [])

    def test_a_remembered_disposition_is_recalled_without_a_conflict(self):
        recalled = recall([DISPOSITION_MEMORY], finding())
        self.assertFalse(recalled["has_prior_conflict"])
        self.assertEqual(recalled["memory_ids"], ["mem-40"])
        self.assertIn("earlier investigation", recalled["effect"])

    def test_the_conflict_memory_text_names_the_two_numbers(self):
        text = conflict_memory(finding(), {
            "value_a": 74.0,
            "value_b": 54.0,
            "gap_percentage_points": 20.0,
        })
        self.assertIn("74.0", text)
        self.assertIn("54.0", text)
        self.assertIn("20.0 percentage points", text)
        self.assertIn("household-survey measurement", text)

    def test_the_question_memory_text_says_what_is_open(self):
        text = question_memory(finding(), ["The survey report could not be read."])
        self.assertIn("Still open", text)
        self.assertIn("survey report", text)


class BehaviourTests(unittest.TestCase):
    """The behavioural difference, proved deterministically."""

    def _decision(self, memories):
        context = {"memories": memories, "available": True}
        return arbitrate(finding(), 5, context)

    def test_without_a_memory_the_plan_starts_with_the_estimate(self):
        decision = self._decision([])
        proposal = default_proposal(finding(), decision)
        self.assertEqual(proposal["action"], "FETCH_WUENIC_WORKBOOK")
        self.assertEqual(proposal["source"], "deterministic")
        self.assertNotIn("memory_recall", decision)

    def test_with_a_remembered_conflict_the_plan_starts_with_the_survey(self):
        decision = self._decision([CONFLICT_MEMORY])
        proposal = default_proposal(finding(), decision)

        self.assertEqual(proposal["action"], "FETCH_SOURCE_DOCUMENT")
        self.assertEqual(proposal["source"], "memory")
        self.assertEqual(proposal["target"], WHO_URL)
        self.assertIn("earlier investigation", proposal["reason"])

    def test_the_recall_is_on_the_decision_and_in_its_reason(self):
        decision = self._decision([CONFLICT_MEMORY])
        self.assertIn("memory_recall", decision)
        self.assertTrue(decision["memory_recall"]["has_prior_conflict"])
        self.assertIn("earlier investigation", decision["reason"])

    def test_the_investigation_requests_the_survey_evidence_first(self):
        """The whole loop, not just the proposal."""
        decision = self._decision([CONFLICT_MEMORY])
        outcome = investigate(
            question="Cameroon MCV1 coverage discrepancy 2020",
            findings=[finding()],
            decisions=[decision],
            client=None,
            budget=CallBudget(0),
            threshold=5,
            max_iterations=1,
            fetch_records=lambda: [],
            fetch_document=lambda url: {
                "status": "RETRIEVED",
                "content_type": "application/pdf",
                "bytes": 10,
                "text_excerpt": "",
                "mentions": {},
                "error": None,
            },
        )
        executed = outcome["executed_actions"]
        self.assertTrue(executed)
        self.assertEqual(executed[0]["action"], "FETCH_SOURCE_DOCUMENT")

    def test_the_trace_records_what_was_recalled(self):
        import tempfile
        from pathlib import Path

        decision = self._decision([CONFLICT_MEMORY])
        with tempfile.TemporaryDirectory() as tmp:
            trace = Trace(run_id="test-run", directory=Path(tmp))
            investigate(
                question="Cameroon MCV1 coverage discrepancy 2020",
                findings=[finding()],
                decisions=[decision],
                client=None,
                budget=CallBudget(0),
                threshold=5,
                max_iterations=1,
                fetch_records=lambda: [],
                trace=trace,
            )
            trace.close()
            events = trace.read()

        recalled = [
            event for event in events
            if event["action"] == "recall.prior_findings"
        ]
        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0]["memory_ids"], ["mem-49"])
        self.assertTrue(recalled[0]["prior_conflict"])
        self.assertEqual(recalled[0]["changed_action"], "FETCH_SOURCE_DOCUMENT")
        self.assertEqual(recalled[0]["agent_name"], "memory")
        self.assertEqual(recalled[0]["target_agent"], "investigator")


if __name__ == "__main__":
    unittest.main()
