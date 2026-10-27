import unittest

from src.revision import revise_decision


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


def proposal(action, target=None, source="model"):
    return {
        "action": action,
        "target": target,
        "reason": "because",
        "source": source,
        "accepted": True,
    }


class ModelProposalTests(unittest.TestCase):
    def test_source_document_action_fetches_a_known_source(self):
        fetched = []

        def fetch_document(url):
            fetched.append(url)
            return {
                "status": "RETRIEVED",
                "content_type": "text/html",
                "bytes": 120,
                "text_excerpt": "Cameroon MCV1 immunization coverage",
                "mentions": {},
                "error": None,
            }

        updated, revision = revise_decision(
            finding(),
            decision(),
            fetch_document=fetch_document,
            proposal=proposal("FETCH_SOURCE_DOCUMENT", "https://example.com/who.pdf"),
        )

        self.assertEqual(fetched, ["https://example.com/who.pdf"])
        self.assertEqual(revision["action"], "FETCH_SOURCE_DOCUMENT")
        self.assertEqual(revision["outcome"], "EVIDENCE_RETRIEVED")
        self.assertEqual(revision["stop_reason"], "SOURCE_DOCUMENT_RETRIEVED")
        self.assertEqual(updated["decision"], "REVIEW")

        checks = updated["critic"]["source_checks"]
        who = next(c for c in checks if c["name"] == "WHO")
        self.assertEqual(who["status"], "SOURCE_DOCUMENT_RETRIEVED")
        self.assertEqual(who["verification_scope"], "DOCUMENT_PRESENCE")

    def test_source_document_action_rejects_unknown_target(self):
        def fetch_document(url):
            raise AssertionError("must not fetch an unknown target")

        updated, revision = revise_decision(
            finding(),
            decision(),
            fetch_document=fetch_document,
            proposal=proposal(
                "FETCH_SOURCE_DOCUMENT", "https://evil.example.com/x.csv"
            ),
        )

        self.assertEqual(revision["outcome"], "ADDITIONAL_EVIDENCE_UNAVAILABLE")
        self.assertEqual(revision["stop_reason"], "TARGET_NOT_A_KNOWN_SOURCE")
        self.assertEqual(updated["decision"], "REVIEW")

    def test_unknown_action_falls_back_to_the_deterministic_path(self):
        records = [{
            "country": "Cameroon",
            "antigen": "MCV1",
            "year": "2020",
            "measure": "WUENIC estimate",
            "value_percent": "63",
        }]

        updated, revision = revise_decision(
            finding(),
            decision(),
            fetch_records=lambda: records,
            proposal=proposal("DUMP_DATABASE"),
        )

        self.assertEqual(revision["action"], "FETCH_WUENIC")
        self.assertEqual(revision["outcome"], "REVISED_SOURCE_CHECK")
        self.assertEqual(updated["decision"], "REVIEW")

    def test_stop_action_leaves_the_decision_alone(self):
        updated, revision = revise_decision(
            finding(),
            decision(),
            proposal=proposal("STOP"),
        )

        self.assertEqual(revision["action"], "STOP")
        self.assertEqual(revision["outcome"], "STOPPED_BY_PROPOSAL")
        self.assertEqual(updated["decision"], "REVIEW")
        self.assertEqual(
            updated["critic"]["source_checks"][0]["status"], "NOT_VERIFIED"
        )

    def test_failed_document_fetch_keeps_the_decision(self):
        def fetch_document(url):
            return {
                "status": "NOT_RETRIEVED",
                "content_type": "",
                "bytes": 0,
                "text_excerpt": "",
                "mentions": {},
                "error": "URLError: connection refused",
            }

        updated, revision = revise_decision(
            finding(),
            decision(),
            fetch_document=fetch_document,
            proposal=proposal("FETCH_SOURCE_DOCUMENT", "https://example.com/who.pdf"),
        )

        self.assertEqual(revision["outcome"], "ADDITIONAL_EVIDENCE_UNAVAILABLE")
        self.assertEqual(updated["decision"], "REVIEW")
        self.assertTrue(
            any(
                "could not be retrieved" in limitation
                for limitation in updated["critic"]["limitations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
