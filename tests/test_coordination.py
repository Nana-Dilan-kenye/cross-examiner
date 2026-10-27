"""Tests for the bounded, adaptive investigation coordinator."""

import unittest
from unittest.mock import patch

from src.adjudicator import MANDATORY_REVIEW_ITEMS
from src.arbiter import arbitrate
from src.coordination import investigate
from src.evidence_ledger import EvidenceLedger
from src.investigator import CallBudget
from src.model_client import ModelUnavailable

WHO_URL = (
    "https://cdn.who.int/media/docs/default-source/country-profiles/"
    "immunization/2024-country-profiles/immunization-2024-cmr.pdf"
)
UNICEF_URL = "https://data.unicef.org/resources/dataset/immunization/"
MINISTRY_URL = "https://www.camin-sante.cm/immunisation-bulletin.pdf"


def finding(year="2020", value_a=63.0, value_b=74.0):
    return {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": year,
        "measure_a": "WUENIC estimate",
        "value_a": value_a,
        "measure_b": "Administrative coverage",
        "value_b": value_b,
        "gap_percentage_points": abs(value_a - value_b),
        "sources": [
            {"name": "WUENIC 2025 revision", "url": UNICEF_URL},
            {"name": "WHO country profile", "url": WHO_URL},
        ],
    }


def finding_with_independent_source(year="2020", value_a=74.0, value_b=63.0):
    """A finding whose table was checked against a third, different source.

    Both figures are the ministry's own. The WHO/UNICEF country profile
    republishes them, so checking both against its table verifies the
    numbers against the origin's own published table rather than against
    the extract they were taken from.
    """
    claim = finding(year, value_a, value_b)
    claim["measure_a"] = "Administrative coverage"
    claim["measure_b"] = "Official (government) coverage"
    claim["sources"] = claim["sources"] + [
        {"name": "WHO country profile", "url": WHO_URL},
    ]
    claim["measure_sources"] = {
        "value_a": {
            "name": "Cameroon Ministry of Public Health",
            "url": MINISTRY_URL,
        },
        "value_b": {
            "name": "Cameroon Ministry of Public Health",
            "url": MINISTRY_URL,
        },
    }
    return claim


def pdf_matched(url, claim, **kwargs):
    """The source's own table confirms both published figures."""
    return {
        "status": "CONTEXT_MATCHED",
        "table_page": 20,
        "matched_values": [
            {
                "field": "value_a",
                "measure": claim.get("measure_a"),
                "expected": claim.get("value_a"),
                "table_value": str(claim.get("value_a")),
                "found_in_expected_year_row": True,
            },
            {
                "field": "value_b",
                "measure": claim.get("measure_b"),
                "expected": claim.get("value_b"),
                "table_value": str(claim.get("value_b")),
                "found_in_expected_year_row": True,
            },
        ],
        "limitations": [],
    }


def pdf_partial(url, claim, **kwargs):
    """Only one of the two published figures is confirmed."""
    return {
        "status": "PARTIAL_MATCH",
        "table_page": 20,
        "matched_values": [
            {
                "field": "value_a",
                "measure": claim.get("measure_a"),
                "expected": claim.get("value_a"),
                "table_value": str(claim.get("value_a")),
                "found_in_expected_year_row": True,
            },
            {
                "field": "value_b",
                "measure": claim.get("measure_b"),
                "expected": claim.get("value_b"),
                "table_value": str(claim.get("value_b")),
                "found_in_expected_year_row": False,
            },
        ],
        "limitations": [],
    }


def pdf_agreeing(url, claim, **kwargs):
    """The source's own table shows the same number for both measures."""
    return {
        "status": "CONTEXT_MATCHED",
        "table_page": 20,
        "matched_values": [
            {
                "field": "value_a",
                "measure": claim.get("measure_a"),
                "expected": claim.get("value_a"),
                "table_value": str(claim.get("value_b")),
                "found_in_expected_year_row": False,
            },
            {
                "field": "value_b",
                "measure": claim.get("measure_b"),
                "expected": claim.get("value_b"),
                "table_value": str(claim.get("value_b")),
                "found_in_expected_year_row": True,
            },
        ],
        "limitations": [],
    }


WORKBOOK_ROWS = [
    {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2020",
        "measure": "WUENIC estimate",
        "value_percent": "63",
    },
    {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2023",
        "measure": "WUENIC estimate",
        "value_percent": "71",
    },
]

CONFLICTING_ROWS = [
    {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2020",
        "measure": "WUENIC estimate",
        "value_percent": "55",
    },
]


class ScriptedClient:
    """Model stub that answers with scripted payloads in order."""

    model = "test/model"

    def __init__(self, payloads=()):
        self.payloads = list(payloads)
        self.calls = []
        self.prompts = []

    def chat_json(self, messages, max_tokens=400, temperature=0.2):
        self.calls.append(messages)
        self.prompts.append(messages[-1]["content"])
        if not self.payloads:
            return {}
        payload = self.payloads.pop(0)
        if callable(payload):
            payload = payload(messages[-1]["content"])
        if isinstance(payload, Exception):
            raise payload
        return payload


def verdict_citing_verified(
    value="ACCEPT",
    reason="An independent source confirms both figures.",
):
    """A verdict that cites the table-verified evidence listed in the prompt.

    This is how the real model works: it reads the evidence ids out of the
    prompt it was given.
    """
    def build(prompt):
        ids = []
        for line in prompt.splitlines():
            if "status=CONTEXT_MATCHED" in line or "status=PARTIAL_MATCH" in line:
                ids.append(line.strip().split(":")[0].strip())
        return {
            "verdict": value,
            "reason": reason,
            "evidence": ids[:1],
        }
    return build


def verdict_citing_independent(reason="An independent source confirms both figures."):
    return verdict_citing_verified("ACCEPT", reason)


def plan(action="FETCH_WUENIC_WORKBOOK", year="2020", target=None,
         country="Cameroon", antigen="MCV1"):
    return {
        "actions": [{
            "country": country,
            "antigen": antigen,
            "year": year,
            "action": action,
            "target": target,
            "reason": "The estimate is still unverified.",
        }],
    }


def challenge(would_change=True):
    return {
        "challenges": ["The administrative figure has no independent source."],
        "missing_support": ["A second administrative data source."],
        "would_change_verdict": would_change,
        "summary": "The gap remains unexplained.",
    }


def verdict(value="REVIEW", reason="Still unexplained.", evidence=None):
    return {
        "verdict": value,
        "reason": reason,
        "evidence": evidence if evidence is not None else [],
    }


class CoordinatorTestCase(unittest.TestCase):
    def setUp(self):
        patcher = patch(
            "src.source_verifier.verify_pdf_source", pdf_matched
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_investigation(self, client=None, findings=None, budget=None,
                          max_iterations=4, threshold=5, records=None,
                          document=None, zetaris=None, memory=None,
                          ledger=None):
        findings = findings if findings is not None else [finding()]
        decisions = [
            arbitrate(claim, threshold, None) for claim in findings
        ]
        budget = budget if budget is not None else CallBudget(20)
        outcome = investigate(
            question="Cameroon MCV1 coverage discrepancy",
            findings=findings,
            decisions=decisions,
            client=client,
            budget=budget,
            threshold=threshold,
            max_iterations=max_iterations,
            fetch_records=records if records is not None else (lambda: WORKBOOK_ROWS),
            fetch_document=document if document is not None else (
                lambda url: {
                    "status": "RETRIEVED",
                    "content_type": "text/html",
                    "bytes": 120,
                    "text_excerpt": "Cameroon MCV1 immunization coverage",
                    "mentions": {},
                    "error": None,
                }
            ),
            zetaris_fetcher=zetaris if zetaris is not None else (lambda: WORKBOOK_ROWS),
            memory_fetcher=memory if memory is not None else (
                lambda question: {"memories": [], "available": True, "error": None}
            ),
            ledger=ledger,
        )
        outcome["budget"] = budget
        return outcome


def closed_review_ledger():
    """A ledger that already holds evidence closing the mandatory items."""
    from src.evidence_ledger import REVIEW_ITEM_KIND, SCOPE_INDEPENDENT

    ledger = EvidenceLedger()
    for item in MANDATORY_REVIEW_ITEMS:
        ledger.register(
            kind=REVIEW_ITEM_KIND,
            name=f"Definitions and denominators for {item}",
            status="CLOSED",
            scope=SCOPE_INDEPENDENT,
            detail={"covers": [item]},
        )
    return ledger


class IterativeLoopTests(CoordinatorTestCase):
    def test_a_challenge_triggers_another_retrieval(self):
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
            # The model asks for the workbook again in the next iteration.
            plan("FETCH_WUENIC_WORKBOOK"),
        ])
        outcome = self.run_investigation(client=client)

        self.assertGreaterEqual(len(outcome["iterations"]), 2)

        executed = [
            action["action"]
            for record in outcome["iterations"]
            for action in record["executed"]
        ]
        self.assertIn("FETCH_WUENIC_WORKBOOK", executed)
        self.assertIn(
            "FETCH_SOURCE_DOCUMENT", executed,
            "the challenge should have triggered a further retrieval",
        )

        second = outcome["iterations"][1]
        steps = [step["action"] for step in second["next_steps"]]
        self.assertIn("FETCH_SOURCE_DOCUMENT", steps)

    def test_the_repeated_action_is_not_run_twice(self):
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
            plan("FETCH_WUENIC_WORKBOOK"),
        ])
        outcome = self.run_investigation(client=client)

        workbook_runs = [
            action for record in outcome["iterations"]
            for action in record["executed"]
            if action["action"] == "FETCH_WUENIC_WORKBOOK"
        ]
        self.assertEqual(len(workbook_runs), 1)

        rejected = [
            proposal
            for record in outcome["iterations"]
            for proposal in record["rejected_proposals"]
        ]
        self.assertTrue(rejected)

    def test_the_loop_stops_when_nothing_is_left_to_do(self):
        client = ScriptedClient([
            plan("STOP"),
        ])
        outcome = self.run_investigation(client=client, max_iterations=6)

        self.assertEqual(outcome["stop_reason"], "NO_USEFUL_NEXT_ACTION")
        self.assertEqual(len(outcome["iterations"]), 1)

    def test_the_iteration_budget_is_enforced(self):
        client = ScriptedClient()
        outcome = self.run_investigation(
            client=client, max_iterations=2
        )
        self.assertEqual(len(outcome["iterations"]), 2)
        self.assertEqual(outcome["stop_reason"], "ITERATION_BUDGET_EXHAUSTED")

    def test_the_model_call_budget_is_enforced(self):
        client = ScriptedClient()
        budget = CallBudget(0)
        outcome = self.run_investigation(client=client, budget=budget)

        self.assertEqual(len(client.calls), 0)
        self.assertEqual(budget.calls, 0)
        self.assertTrue(outcome["stop_reason"])

    def test_a_repeated_state_terminates_the_loop(self):
        """A model that keeps asking for the same thing must not loop."""
        class AlwaysStop:
            model = "test/model"

            def __init__(self):
                self.calls = 0

            def chat_json(self, messages, max_tokens=400, temperature=0.2):
                self.calls += 1
                if "investigator" in messages[-1]["content"]:
                    return plan("STOP")
                return challenge()

        client = AlwaysStop()
        outcome = self.run_investigation(client=client, max_iterations=8)

        self.assertLessEqual(len(outcome["iterations"]), 3)
        self.assertIn(
            outcome["stop_reason"],
            ("REPEATED_STATE", "NO_USEFUL_NEXT_ACTION", "EVIDENCE_SUFFICIENT"),
        )


class AdjudicationTests(CoordinatorTestCase):
    def test_a_table_match_with_open_review_items_does_not_resolve_a_finding(self):
        """A PDF table match is not enough to leave REVIEW.

        The arbiter sends a threshold-meeting gap to REVIEW to have the
        definitions, denominators, reporting quality and estimation methods
        looked at. A table match discharges none of them.
        """
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict("ACCEPT", "The country profile confirms both figures.", ["ev-2"]),
        ])
        outcome = self.run_investigation(client=client)

        decision = outcome["decisions"][0]
        self.assertEqual(decision["decision"], "REVIEW")
        self.assertEqual(decision["disposition"], "REVIEW")
        rejections = [
            record["validation_reason"]
            for record in decision.get("adjudications", [])
            if not record["accepted"]
        ]
        self.assertIn("MANDATORY_REVIEW_ITEMS_OPEN", rejections)

    def test_validated_evidence_changes_the_final_disposition(self):
        """With independent evidence and closed review items, ACCEPT is granted."""
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict_citing_independent(),
        ])
        outcome = self.run_investigation(
            client=client,
            findings=[finding_with_independent_source()],
            ledger=closed_review_ledger(),
        )

        decision = outcome["decisions"][0]
        self.assertEqual(decision["decision"], "REVIEW")
        self.assertEqual(decision["disposition"], "ACCEPT")
        self.assertTrue(decision["adjudication"]["changed"])

    def test_a_self_consistent_source_cannot_resolve_a_finding(self):
        """The document a value was taken from is not independent evidence."""
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict_citing_independent("The source confirms both figures."),
        ])
        outcome = self.run_investigation(
            client=client, ledger=closed_review_ledger()
        )

        decision = outcome["decisions"][0]
        self.assertEqual(decision["disposition"], "REVIEW")
        rejections = [
            record["validation_reason"]
            for record in decision.get("adjudications", [])
            if not record["accepted"]
        ]
        self.assertIn("NO_INDEPENDENTLY_VALIDATED_EVIDENCE", rejections)

    def test_a_verdict_contradicted_by_the_evidence_is_rejected(self):
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict_citing_independent("Trust me."),
        ])
        with patch(
            "src.source_verifier.verify_pdf_source", pdf_partial
        ):
            outcome = self.run_investigation(
                client=client,
                findings=[finding_with_independent_source()],
                ledger=closed_review_ledger(),
            )

        decision = outcome["decisions"][0]
        self.assertEqual(decision["disposition"], "REVIEW")
        rejections = [
            record["validation_reason"]
            for record in decision.get("adjudications", [])
            if not record["accepted"]
        ]
        self.assertIn("EVIDENCE_DOES_NOT_SUPPORT_ACCEPT", rejections)

    def test_an_invented_citation_is_rejected(self):
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict("ACCEPT", "A source I made up.", ["ev-99"]),
        ])
        outcome = self.run_investigation(client=client)

        decision = outcome["decisions"][0]
        self.assertEqual(decision["disposition"], "REVIEW")
        rejections = [
            record["validation_reason"]
            for record in decision.get("adjudications", [])
            if not record["accepted"]
        ]
        self.assertIn("CITED_EVIDENCE_NOT_FOUND", rejections)

    def test_a_numeric_conflict_still_abstains(self):
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict("ACCEPT", "The gap is real.", ["ev-2"]),
        ])
        outcome = self.run_investigation(
            client=client, records=lambda: CONFLICTING_ROWS
        )

        decision = outcome["decisions"][0]
        self.assertEqual(decision["decision"], "ABSTAIN")
        self.assertEqual(decision["disposition"], "ABSTAIN")

    def test_an_unresolved_conflict_keeps_the_review_disposition(self):
        """A conflict the new evidence does not resolve stays unresolved."""
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict("REVIEW", "The conflict is unresolved.", ["ev-2"]),
        ])
        outcome = self.run_investigation(
            client=client, records=lambda: CONFLICTING_ROWS
        )

        decision = outcome["decisions"][0]
        self.assertEqual(decision["disposition"], "ABSTAIN")
        self.assertIn(
            "EXTRACT_CONFLICT",
            [
                check["status"]
                for check in decision["critic"]["source_checks"]
            ],
        )

    def test_the_deterministic_decision_is_never_rewritten(self):
        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict("ACCEPT", "The country profile confirms both figures.", ["ev-2"]),
        ])
        outcome = self.run_investigation(client=client)

        decision = outcome["decisions"][0]
        self.assertEqual(decision["decision"], "REVIEW")
        self.assertEqual(decision["adjudication"]["baseline_decision"], "REVIEW")


class ProposalSafetyTests(CoordinatorTestCase):
    def test_an_invented_action_is_rejected(self):
        client = ScriptedClient([
            plan("DELETE_ALL_EVIDENCE"),
            challenge(),
            verdict(),
        ])
        outcome = self.run_investigation(client=client)

        rejected = [
            proposal
            for record in outcome["iterations"]
            for proposal in record["rejected_proposals"]
        ]
        self.assertTrue(
            any(
                proposal.get("rejected_action") == "DELETE_ALL_EVIDENCE"
                or proposal.get("fallback_reason") == "ACTION_NOT_ALLOWED"
                for proposal in rejected
            )
        )
        executed = [
            action["action"]
            for record in outcome["iterations"]
            for action in record["executed"]
        ]
        self.assertNotIn("DELETE_ALL_EVIDENCE", executed)

    def test_an_invented_url_is_rejected(self):
        client = ScriptedClient([
            plan("FETCH_SOURCE_DOCUMENT", target="https://evil.example.com/x.csv"),
            challenge(),
            verdict(),
        ])
        outcome = self.run_investigation(client=client)

        executed = [
            action["target"]
            for record in outcome["iterations"]
            for action in record["executed"]
            if action["action"] == "FETCH_SOURCE_DOCUMENT"
        ]
        self.assertNotIn("https://evil.example.com/x.csv", executed)

        rejected = [
            proposal
            for record in outcome["iterations"]
            for proposal in record["rejected_proposals"]
        ]
        self.assertTrue(
            any(
                proposal.get("fallback_reason") == "TARGET_NOT_A_KNOWN_SOURCE"
                for proposal in rejected
            )
        )


class FailureFallbackTests(CoordinatorTestCase):
    def test_an_unreachable_runtime_falls_back_safely(self):
        client = ScriptedClient([ModelUnavailable("runtime down")])
        outcome = self.run_investigation(client=client)

        self.assertTrue(outcome["stop_reason"])
        self.assertEqual(outcome["decisions"][0]["disposition"], "REVIEW")
        for record in outcome["iterations"]:
            for challenge_entry in record["challenges"]:
                self.assertEqual(challenge_entry["source"], "deterministic")

    def test_a_failed_workbook_fetch_keeps_the_decision(self):
        def boom():
            raise OSError("connection refused")

        client = ScriptedClient([plan("FETCH_WUENIC_WORKBOOK"), challenge(), verdict()])
        outcome = self.run_investigation(client=client, records=boom)

        decision = outcome["decisions"][0]
        self.assertEqual(decision["decision"], "REVIEW")
        self.assertEqual(decision["disposition"], "REVIEW")
        outcomes = [
            action["outcome"]
            for record in outcome["iterations"]
            for action in record["executed"]
        ]
        self.assertIn("ADDITIONAL_EVIDENCE_UNAVAILABLE", outcomes)

    def test_an_unavailable_memory_store_is_handled(self):
        def boom(question):
            raise RuntimeError("memory store down")

        def failing_document(url):
            return {
                "status": "NOT_RETRIEVED",
                "content_type": "",
                "bytes": 0,
                "text_excerpt": "",
                "mentions": {},
                "error": "HTTPError: HTTP Error 403: Forbidden",
            }

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
        ])
        outcome = self.run_investigation(
            client=client, memory=boom, document=failing_document
        )

        outcomes = [
            action["outcome"]
            for record in outcome["iterations"]
            for action in record["executed"]
        ]
        self.assertIn("ADDITIONAL_EVIDENCE_UNAVAILABLE", outcomes)
        self.assertTrue(outcome["stop_reason"])

    def test_an_unavailable_evidence_store_is_handled(self):
        def boom():
            raise RuntimeError("evidence store down")

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
        ])
        # Only one published figure is confirmed, so the store still has to
        # be queried for the other one.
        with patch(
            "src.source_verifier.verify_pdf_source", pdf_partial
        ):
            outcome = self.run_investigation(client=client, zetaris=boom)

        outcomes = [
            action["outcome"]
            for record in outcome["iterations"]
            for action in record["executed"]
        ]
        self.assertIn("ADDITIONAL_EVIDENCE_UNAVAILABLE", outcomes)
        self.assertTrue(outcome["stop_reason"])


class ReportTests(CoordinatorTestCase):
    def test_the_report_records_the_trace_and_the_stopping_reason(self):
        from src.reporter import render_report

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
        ])
        outcome = self.run_investigation(client=client)

        report = render_report({
            "question": "Cameroon MCV1 coverage discrepancy",
            "records_loaded": 4,
            "findings": [finding()],
            "decisions": outcome["decisions"],
            "revisions": outcome["revisions"],
            "iterations": outcome["iterations"],
            "evidence_ledger": outcome["ledger"],
            "stop_reason": outcome["stop_reason"],
            "stop_detail": outcome["stop_detail"],
            "uncertainties": outcome["uncertainties"],
        })

        self.assertIn("## Investigation trace", report)
        self.assertIn("## Evidence ledger", report)
        self.assertIn("## Stopping reason", report)
        self.assertIn("### Iteration 1", report)
        self.assertIn("FETCH_WUENIC_WORKBOOK", report)
        self.assertIn("### Unresolved uncertainty", report)
        self.assertIn(str(outcome["stop_reason"]), report)

    def test_the_report_shows_the_disposition_and_its_basis(self):
        from src.reporter import render_report

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict_citing_independent(),
        ])
        outcome = self.run_investigation(
            client=client,
            findings=[finding_with_independent_source()],
            ledger=closed_review_ledger(),
        )

        report = render_report({
            "findings": [finding()],
            "decisions": outcome["decisions"],
            "revisions": outcome["revisions"],
            "iterations": outcome["iterations"],
            "evidence_ledger": outcome["ledger"],
            "stop_reason": outcome["stop_reason"],
            "uncertainties": outcome["uncertainties"],
        })

        self.assertIn("**Final disposition:** ACCEPT", report)
        self.assertIn("**Deterministic decision:** REVIEW", report)
        self.assertIn("Proposal accepted", report)
        self.assertIn("ev-2", report)


class EvidenceLedgerTests(unittest.TestCase):
    def test_a_shared_source_backs_every_finding_that_uses_it(self):
        from src.evidence_ledger import EvidenceLedger, register_source_checks

        ledger = EvidenceLedger()
        check = {
            "name": "WHO country profile",
            "url": WHO_URL,
            "status": "CONTEXT_MATCHED",
            "matched_values": [
                {"field": "value_a", "found_in_expected_year_row": True},
                {"field": "value_b", "found_in_expected_year_row": True},
            ],
        }
        first = register_source_checks(
            ledger, {"critic": {"source_checks": [check]}}, ("Cameroon", "MCV1", "2020")
        )
        second = register_source_checks(
            ledger, {"critic": {"source_checks": [check]}}, ("Cameroon", "MCV1", "2023")
        )

        self.assertEqual(first, second)
        summary = ledger.summary()
        self.assertEqual(len(summary), 1)
        # Tuples in memory, lists once the result is serialised to JSON.
        self.assertEqual(
            [tuple(item) for item in summary[0]["findings"]],
            [("Cameroon", "MCV1", "2020"), ("Cameroon", "MCV1", "2023")],
        )

    def test_a_citation_must_name_a_registered_item(self):
        from src.evidence_ledger import EvidenceLedger

        ledger = EvidenceLedger()
        ledger.register(kind="SOURCE_CHECK", name="x", url="u")
        self.assertTrue(ledger.has("ev-1"))
        self.assertFalse(ledger.has("ev-2"))


class StoppingConditionTests(CoordinatorTestCase):
    """The end state of an investigation must match what the findings are."""

    def test_a_403_while_a_finding_is_unresolved_is_not_evidence_sufficient(self):
        def forbidden(url):
            return {
                "status": "NOT_RETRIEVED",
                "content_type": "",
                "bytes": 0,
                "text_excerpt": "",
                "mentions": {},
                "error": "HTTPError: HTTP Error 403: Forbidden",
            }

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
        ])
        outcome = self.run_investigation(
            client=client, document=forbidden, max_iterations=6
        )

        self.assertNotEqual(outcome["stop_reason"], "EVIDENCE_SUFFICIENT")
        self.assertEqual(outcome["stop_reason"], "SOURCES_UNAVAILABLE")
        self.assertEqual(outcome["decisions"][0]["disposition"], "REVIEW")
        self.assertEqual(
            outcome["closing"]["Cameroon MCV1 (2020)"]["cause"],
            "SOURCE_UNAVAILABLE",
        )
        self.assertIn("403", outcome["stop_detail"])

    def test_mixed_resolved_and_unresolved_findings(self):
        """One finding resolved, one still open: the run must say so."""
        def pdf_by_year(url, claim, **kwargs):
            if str(claim.get("year")) == "2023":
                return pdf_agreeing(url, claim, **kwargs)
            return pdf_matched(url, claim, **kwargs)

        class MixedClient:
            model = "test/model"

            def chat_json(self, messages, max_tokens=400, temperature=0.2):
                prompt = messages[-1]["content"]
                if "investigator" in prompt:
                    return plan("FETCH_WUENIC_WORKBOOK")
                if "skeptical reviewer" in prompt:
                    return challenge()
                if "adjudicating" in prompt:
                    if "(2023)" in prompt:
                        return verdict_citing_verified(
                            "REJECT",
                            "The source's table shows the same number.",
                        )(prompt)
                    return verdict("REVIEW", "Still unexplained.")
                return {}

        findings = [finding("2020", 63.0, 74.0), finding("2023", 71.0, 82.0)]
        with patch("src.source_verifier.verify_pdf_source", pdf_by_year):
            outcome = self.run_investigation(
                client=MixedClient(), findings=findings
            )

        self.assertEqual(outcome["decisions"][1]["disposition"], "REJECT")
        self.assertEqual(outcome["decisions"][0]["disposition"], "REVIEW")

        # One finding is still open, so the run cannot claim to be resolved.
        self.assertNotEqual(outcome["stop_reason"], "EVIDENCE_SUFFICIENT")
        self.assertIn(
            outcome["closing"]["Cameroon MCV1 (2023)"]["cause"], "RESOLVED"
        )
        self.assertIn("2020", outcome["stop_detail"])

        # The open finding must still carry its uncertainty.
        self.assertTrue(outcome["uncertainties"]["Cameroon MCV1 (2020)"])

    def test_all_findings_resolved_reports_evidence_sufficient(self):
        def pdf_agreeing_for_all(url, claim, **kwargs):
            return pdf_agreeing(url, claim, **kwargs)

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict_citing_verified(
                "REJECT", "The source's table shows the same number."
            ),
        ])
        with patch(
            "src.source_verifier.verify_pdf_source", pdf_agreeing_for_all
        ):
            outcome = self.run_investigation(client=client)

        self.assertEqual(outcome["decisions"][0]["disposition"], "REJECT")
        self.assertEqual(outcome["stop_reason"], "EVIDENCE_SUFFICIENT")

    def test_the_iteration_budget_is_reported_as_such(self):
        client = ScriptedClient([plan("FETCH_WUENIC_WORKBOOK")])
        outcome = self.run_investigation(client=client, max_iterations=1)

        self.assertEqual(outcome["stop_reason"], "ITERATION_BUDGET_EXHAUSTED")
        self.assertIn("2020", outcome["stop_detail"])

    def test_the_stop_reason_matches_the_per_finding_state(self):
        client = ScriptedClient([plan("FETCH_WUENIC_WORKBOOK")])
        outcome = self.run_investigation(client=client, max_iterations=2)

        unresolved = [
            label for label, item in outcome["closing"].items()
            if item["disposition"] not in ("ACCEPT", "REJECT")
        ]
        if outcome["stop_reason"] == "EVIDENCE_SUFFICIENT":
            self.assertEqual(unresolved, [])
        else:
            self.assertTrue(unresolved)

    def test_the_report_states_the_stop_reason_and_the_open_findings(self):
        from src.reporter import render_report

        def forbidden(url):
            return {
                "status": "NOT_RETRIEVED",
                "content_type": "",
                "bytes": 0,
                "text_excerpt": "",
                "mentions": {},
                "error": "HTTPError: HTTP Error 403: Forbidden",
            }

        client = ScriptedClient([
            plan("FETCH_WUENIC_WORKBOOK"),
            challenge(),
            verdict(),
        ])
        outcome = self.run_investigation(
            client=client, document=forbidden, max_iterations=6
        )

        report = render_report({
            "findings": [finding()],
            "decisions": outcome["decisions"],
            "revisions": outcome["revisions"],
            "iterations": outcome["iterations"],
            "evidence_ledger": outcome["ledger"],
            "closing": outcome["closing"],
            "stop_reason": outcome["stop_reason"],
            "stop_detail": outcome["stop_detail"],
            "uncertainties": outcome["uncertainties"],
        })

        self.assertIn("SOURCES_UNAVAILABLE", report)
        self.assertNotIn("**Final disposition:** ACCEPT", report)
        self.assertIn("**Final disposition:** REVIEW", report)


if __name__ == "__main__":
    unittest.main()
