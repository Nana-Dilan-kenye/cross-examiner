import unittest

from src.investigator import (
    ALLOWED_ACTIONS,
    CallBudget,
    challenge_claim,
    default_proposal,
    propose_actions,
)
from src.model_client import ModelInvalidResponse, ModelUnavailable


def finding():
    return {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2020",
        "measure_a": "WUENIC estimate",
        "value_a": 63.0,
        "measure_b": "Administrative coverage",
        "value_b": 74.0,
        "gap_percentage_points": 11.0,
        "sources": [
            {
                "name": "WUENIC 2025 revision",
                "url": "https://data.unicef.org/resources/dataset/immunization/",
            },
            {"name": "WHO", "url": "https://example.com/who.pdf"},
        ],
    }


def decision():
    return {
        "decision": "REVIEW",
        "reason": "The observed gap meets the review threshold.",
        "critic": {
            "passed": True,
            "issues": [],
            "source_checks": [
                {
                    "name": "WUENIC 2025 revision",
                    "url": "https://data.unicef.org/resources/dataset/immunization/",
                    "status": "NOT_VERIFIED",
                },
                {
                    "name": "WHO",
                    "url": "https://example.com/who.pdf",
                    "status": "CONTEXT_MATCHED",
                },
            ],
            "limitations": [],
        },
    }


class FakeClient:
    """Model stub that records calls and returns canned payloads."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []
        self.model = "test/model"

    def chat_json(self, messages, max_tokens=400, temperature=0.2):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.payload


class ProposeActionsTests(unittest.TestCase):
    def test_allowed_action_is_accepted(self):
        client = FakeClient({
            "actions": [{
                "year": "2020",
                "action": "FETCH_WUENIC_WORKBOOK",
                "target": None,
                "reason": "The estimate is still unverified.",
            }],
        })
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        proposal = result["proposals"][0]
        self.assertEqual(proposal["action"], "FETCH_WUENIC_WORKBOOK")
        self.assertEqual(proposal["source"], "model")
        self.assertTrue(proposal["accepted"])
        self.assertEqual(result["status"], "used")

    def test_invented_action_is_rejected_and_falls_back(self):
        client = FakeClient({
            "actions": [{
                "year": "2020",
                "action": "DELETE_ALL_EVIDENCE",
                "target": None,
                "reason": "Because.",
            }],
        })
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        proposal = result["proposals"][0]
        self.assertEqual(proposal["action"], "FETCH_WUENIC_WORKBOOK")
        self.assertEqual(proposal["source"], "model")
        self.assertFalse(proposal["accepted"])
        self.assertEqual(proposal["rejected_action"], "DELETE_ALL_EVIDENCE")
        self.assertEqual(proposal["fallback_reason"], "ACTION_NOT_ALLOWED")

    def test_invented_url_is_rejected(self):
        client = FakeClient({
            "actions": [{
                "year": "2020",
                "action": "FETCH_SOURCE_DOCUMENT",
                "target": "https://evil.example.com/data.csv",
                "reason": "Look elsewhere.",
            }],
        })
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        proposal = result["proposals"][0]
        self.assertFalse(proposal["accepted"])
        self.assertEqual(proposal["fallback_reason"], "TARGET_NOT_A_KNOWN_SOURCE")
        self.assertIsNone(proposal["target"])

    def test_known_source_url_is_resolved(self):
        client = FakeClient({
            "actions": [{
                "year": "2020",
                "action": "FETCH_SOURCE_DOCUMENT",
                "target": "https://example.com/who.pdf",
                "reason": "Check the table.",
            }],
        })
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        proposal = result["proposals"][0]
        self.assertTrue(proposal["accepted"])
        self.assertEqual(proposal["target"], "https://example.com/who.pdf")

    def test_proposal_for_unknown_year_is_ignored(self):
        client = FakeClient({
            "actions": [{
                "year": "1999",
                "action": "FETCH_WUENIC_WORKBOOK",
                "reason": "Wrong year.",
            }],
        })
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        proposal = result["proposals"][0]
        self.assertEqual(proposal["source"], "deterministic")

    def test_unavailable_runtime_falls_back_to_deterministic(self):
        client = FakeClient(error=ModelUnavailable("Cannot reach runtime"))
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        self.assertEqual(result["status"], "unavailable")
        proposal = result["proposals"][0]
        self.assertEqual(proposal["action"], "FETCH_WUENIC_WORKBOOK")
        self.assertEqual(proposal["source"], "deterministic")

    def test_invalid_json_falls_back_to_deterministic(self):
        client = FakeClient(error=ModelInvalidResponse("not json"))
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["proposals"][0]["source"], "deterministic")

    def test_no_client_uses_deterministic_proposals(self):
        result = propose_actions(
            None, "question", [finding()], {"2020": decision()}, max_calls=4
        )
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["proposals"][0]["source"], "deterministic")

    def test_budget_limits_calls(self):
        client = FakeClient({"actions": []})
        budget = CallBudget(0)
        result = propose_actions(
            client, "question", [finding()], {"2020": decision()}, budget=budget
        )
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(client.calls, [])

    def test_default_proposal_is_allowed(self):
        proposal = default_proposal(finding(), decision())
        self.assertIn(proposal["action"], ALLOWED_ACTIONS)


class ChallengeClaimTests(unittest.TestCase):
    def test_model_challenge_is_recorded(self):
        client = FakeClient({
            "challenges": ["The administrative figure has no independent source."],
            "missing_support": ["A second administrative data source."],
            "would_change_verdict": False,
            "summary": "The gap remains unexplained.",
        })
        result = challenge_claim(
            client, finding(), decision(), None, budget=CallBudget(4)
        )
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["status"], "used")
        self.assertEqual(
            result["challenges"][0],
            "The administrative figure has no independent source.",
        )

    def test_challenge_never_changes_the_decision(self):
        client = FakeClient({
            "challenges": ["I disagree with the threshold."],
            "missing_support": [],
            "would_change_verdict": True,
            "summary": "Should be ABSTAIN.",
        })
        original = decision()
        result = challenge_claim(
            client, finding(), original, None, budget=CallBudget(4)
        )
        self.assertTrue(result["would_change_verdict"])
        self.assertEqual(original["decision"], "REVIEW")
        self.assertNotIn("challenge", original)

    def test_invalid_challenges_fall_back(self):
        client = FakeClient({"challenges": "not a list"})
        result = challenge_claim(
            client, finding(), decision(), None, budget=CallBudget(4)
        )
        self.assertEqual(result["source"], "deterministic")
        self.assertEqual(
            result["fallback_reason"], "MODEL_RETURNED_INVALID_CHALLENGES"
        )

    def test_unavailable_runtime_falls_back(self):
        client = FakeClient(error=ModelUnavailable("runtime down"))
        result = challenge_claim(
            client, finding(), decision(), None, budget=CallBudget(4)
        )
        self.assertEqual(result["source"], "deterministic")
        self.assertIn("runtime down", result["fallback_reason"])

    def test_exhausted_budget_skips_the_call(self):
        client = FakeClient({"challenges": []})
        budget = CallBudget(0)
        result = challenge_claim(
            client, finding(), decision(), None, budget=budget
        )
        self.assertEqual(result["source"], "deterministic")
        self.assertEqual(result["fallback_reason"], "CALL_BUDGET_EXHAUSTED")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
