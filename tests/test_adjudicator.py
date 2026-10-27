"""Tests for the evidence-based adjudicator."""

import unittest

from src.adjudicator import (
    MANDATORY_REVIEW_ITEMS,
    VERDICTS,
    apply_verdict,
    baseline_disposition,
    open_review_items,
    propose_verdict,
    validate_verdict,
)
from src.evidence_ledger import (
    REVIEW_ITEM_KIND,
    SCOPE_INDEPENDENT,
    SCOPE_SELF_CONSISTENCY,
    EvidenceLedger,
)
from src.investigator import CallBudget
from src.model_client import ModelInvalidResponse, ModelUnavailable

WHO_URL = "https://cdn.who.int/media/docs/default-source/country-profiles/immunization/cmr.pdf"


def finding(gap=11.0):
    return {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2020",
        "measure_a": "WUENIC estimate",
        "value_a": 63.0,
        "measure_b": "Administrative coverage",
        "value_b": 74.0,
        "gap_percentage_points": gap,
        "sources": [{"name": "WHO", "url": WHO_URL}],
    }


def decision(value="REVIEW"):
    return {
        "decision": value,
        "reason": "The observed gap meets the review threshold.",
        "critic": {"passed": True, "issues": [], "source_checks": []},
    }


def ledger_with_independent(both_confirmed=True, agree=False, closed_items=()):
    ledger = EvidenceLedger()
    ledger.register(
        kind="SOURCE_CHECK",
        name="WHO country profile",
        url=WHO_URL,
        status="CONTEXT_MATCHED",
        scope=SCOPE_INDEPENDENT,
        detail={
            "signals": {
                "both_values_confirmed": both_confirmed,
                "source_values_agree": agree,
            }
        },
    )
    for item in closed_items:
        ledger.register(
            kind=REVIEW_ITEM_KIND,
            name=f"Review item {item}",
            status="CLOSED",
            scope=SCOPE_INDEPENDENT,
            detail={"covers": [item]},
        )
    return ledger


class FakeClient:
    model = "test/model"

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def chat_json(self, messages, max_tokens=400, temperature=0.2):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.payload


class BaselineTests(unittest.TestCase):
    def test_arbiter_decisions_map_onto_dispositions(self):
        self.assertEqual(baseline_disposition(decision("ABSTAIN")), "ABSTAIN")
        self.assertEqual(baseline_disposition(decision("REVIEW")), "REVIEW")
        self.assertEqual(
            baseline_disposition(decision("REPORT_OBSERVATION")), "REJECT"
        )

    def test_unknown_decision_falls_back_to_review(self):
        self.assertEqual(baseline_disposition(decision("SOMETHING")), "REVIEW")


class ValidateVerdictTests(unittest.TestCase):
    def test_unknown_verdict_is_rejected(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "MAYBE", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "VERDICT_NOT_ALLOWED")

    def test_missing_reason_is_rejected(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "NO_REASON_SUPPLIED")

    def test_invented_citation_is_rejected(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-99"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "CITED_EVIDENCE_NOT_FOUND")

    def test_proposal_without_citation_is_rejected(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": []},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "NO_EVIDENCE_CITED")

    def test_accept_needs_independently_validated_evidence(self):
        ledger = EvidenceLedger()
        ledger.register(
            kind="SOURCE_CHECK",
            name="WUENIC 2025 revision",
            url="https://data.unicef.org/x",
            status="EXTRACT_CONSISTENT",
            scope=SCOPE_SELF_CONSISTENCY,
            detail={"signals": {"both_values_confirmed": True}},
        )
        for item in MANDATORY_REVIEW_ITEMS:
            ledger.register(
                kind=REVIEW_ITEM_KIND,
                name=f"Review item {item}",
                status="CLOSED",
                scope=SCOPE_INDEPENDENT,
                detail={"covers": [item]},
            )
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "NO_INDEPENDENTLY_VALIDATED_EVIDENCE")

    def test_accept_needs_the_mandatory_review_items_closed(self):
        """Leaving REVIEW needs the arbiter's review items discharged."""
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "MANDATORY_REVIEW_ITEMS_OPEN")

    def test_accept_is_allowed_once_the_review_items_are_closed(self):
        ledger = ledger_with_independent(
            closed_items=MANDATORY_REVIEW_ITEMS
        )
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertTrue(accepted)
        self.assertEqual(
            reason, "SUPPORTED_BY_INDEPENDENTLY_VALIDATED_EVIDENCE"
        )

    def test_open_review_items_are_reported(self):
        ledger = ledger_with_independent(
            closed_items=["measure_definitions", "denominators"]
        )
        self.assertEqual(
            open_review_items(ledger),
            ["reporting_quality", "estimation_methodology"],
        )

    def test_accept_needs_the_gap_to_meet_the_threshold(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            finding(gap=1.0), decision(), ledger, threshold=5,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "GAP_BELOW_THRESHOLD")

    def test_deterministic_abstention_cannot_be_overturned(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision("ABSTAIN"), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "DETERMINISTIC_ABSTENTION_STANDS")

    def test_accept_is_allowed_with_independent_evidence(self):
        ledger = ledger_with_independent(closed_items=MANDATORY_REVIEW_ITEMS)
        accepted, reason = validate_verdict(
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertTrue(accepted)
        self.assertEqual(
            reason, "SUPPORTED_BY_INDEPENDENTLY_VALIDATED_EVIDENCE"
        )

    def test_reject_needs_evidence_that_refutes_the_discrepancy(self):
        ledger = ledger_with_independent(both_confirmed=False, agree=True)
        accepted, reason = validate_verdict(
            {"verdict": "REJECT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertTrue(accepted)

    def test_reject_is_rejected_when_the_evidence_does_not_refute(self):
        ledger = ledger_with_independent()
        accepted, reason = validate_verdict(
            {"verdict": "REJECT", "reason": "because", "citations": ["ev-1"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "EVIDENCE_DOES_NOT_SUPPORT_REJECT")

    def test_abstain_is_always_permitted(self):
        ledger = EvidenceLedger()
        accepted, _ = validate_verdict(
            {"verdict": "ABSTAIN", "reason": "because", "citations": []},
            finding(), decision("ABSTAIN"), ledger,
        )
        self.assertTrue(accepted)

    def test_review_is_permitted_when_nothing_is_withheld(self):
        ledger = EvidenceLedger()
        accepted, reason = validate_verdict(
            {"verdict": "REVIEW", "reason": "because", "citations": []},
            finding(), decision("REVIEW"), ledger,
        )
        self.assertTrue(accepted)
        self.assertEqual(reason, "REVIEW_IS_A_PERMITTED_RESOLUTION")

    def test_review_cannot_soften_a_deterministic_abstention(self):
        ledger = EvidenceLedger()
        accepted, reason = validate_verdict(
            {"verdict": "REVIEW", "reason": "because", "citations": []},
            finding(), decision("ABSTAIN"), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "DETERMINISTIC_ABSTENTION_STANDS")

    def test_a_fabricated_citation_is_rejected_even_for_abstention(self):
        ledger = EvidenceLedger()
        accepted, reason = validate_verdict(
            {"verdict": "ABSTAIN", "reason": "because", "citations": ["ev-42"]},
            finding(), decision(), ledger,
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "CITED_EVIDENCE_NOT_FOUND")


class ProposeVerdictTests(unittest.TestCase):
    def test_model_proposal_is_recorded(self):
        client = FakeClient({
            "verdict": "accept",
            "reason": "The country profile confirms both figures.",
            "evidence": ["ev-1"],
        })
        ledger = ledger_with_independent()
        proposal = propose_verdict(
            client, finding(), decision(), ledger, budget=CallBudget(4)
        )
        self.assertEqual(proposal["verdict"], "ACCEPT")
        self.assertEqual(proposal["source"], "model")
        self.assertEqual(proposal["citations"], ["ev-1"])
        self.assertEqual(proposal["reason"], "The country profile confirms both figures.")

    def test_unavailable_runtime_degrades(self):
        client = FakeClient(error=ModelUnavailable("runtime down"))
        ledger = ledger_with_independent()
        proposal = propose_verdict(
            client, finding(), decision(), ledger, budget=CallBudget(4)
        )
        self.assertEqual(proposal["source"], "deterministic")
        self.assertIsNone(proposal["verdict"])
        self.assertIn("runtime down", proposal["rejected_reason"])

    def test_invalid_response_degrades(self):
        client = FakeClient(error=ModelInvalidResponse("not json"))
        ledger = ledger_with_independent()
        proposal = propose_verdict(
            client, finding(), decision(), ledger, budget=CallBudget(4)
        )
        self.assertEqual(proposal["source"], "deterministic")

    def test_no_client_proposes_nothing(self):
        ledger = ledger_with_independent()
        proposal = propose_verdict(
            None, finding(), decision(), ledger, budget=CallBudget(4)
        )
        self.assertEqual(proposal["rejected_reason"], "MODEL_NOT_REQUESTED")

    def test_exhausted_budget_skips_the_call(self):
        client = FakeClient({"verdict": "ACCEPT"})
        ledger = ledger_with_independent()
        proposal = propose_verdict(
            client, finding(), decision(), ledger, budget=CallBudget(0)
        )
        self.assertEqual(proposal["rejected_reason"], "CALL_BUDGET_EXHAUSTED")
        self.assertEqual(client.calls, [])


class ApplyVerdictTests(unittest.TestCase):
    def test_accepted_proposal_changes_the_disposition(self):
        base = decision()
        base["disposition"] = baseline_disposition(base)
        updated, record = apply_verdict(
            base,
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-1"]},
            True,
            "SUPPORTED_BY_INDEPENDENTLY_VALIDATED_EVIDENCE",
        )
        self.assertEqual(updated["disposition"], "ACCEPT")
        self.assertTrue(record["changed"])
        self.assertEqual(updated["decision"], "REVIEW")

    def test_rejected_proposal_keeps_the_baseline(self):
        base = decision()
        base["disposition"] = baseline_disposition(base)
        updated, record = apply_verdict(
            base,
            {"verdict": "ACCEPT", "reason": "because", "citations": ["ev-99"]},
            False,
            "CITED_EVIDENCE_NOT_FOUND",
        )
        self.assertEqual(updated["disposition"], "REVIEW")
        self.assertFalse(record["changed"])
        self.assertEqual(record["validation_reason"], "CITED_EVIDENCE_NOT_FOUND")

    def test_a_missing_proposal_leaves_the_disposition_alone(self):
        base = decision()
        base["disposition"] = "ACCEPT"
        updated, record = apply_verdict(
            base,
            {"verdict": None, "reason": "", "citations": []},
            False,
            "MODEL_NOT_REQUESTED",
        )
        self.assertEqual(updated["disposition"], "ACCEPT")
        self.assertFalse(record["changed"])

    def test_verdict_vocabulary(self):
        self.assertEqual(VERDICTS, ("ACCEPT", "REJECT", "REVIEW", "ABSTAIN"))


if __name__ == "__main__":
    unittest.main()
