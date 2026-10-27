import unittest

from src.revision import revise_decision


def _decision(source_name="WUENIC 2025 revision", url="https://data.unicef.org/resources/dataset/immunization/"):
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
            {"name": source_name, "url": url},
            {"name": "WHO", "url": "https://example.com/who"},
        ],
    }
    decision = {
        "decision": "REVIEW",
        "reason": "The observed gap meets the review threshold.",
        "critic": {
            "passed": True,
            "issues": [],
            "source_checks": [
                {"name": source_name, "url": url, "status": "NOT_VERIFIED"},
                {"name": "WHO", "url": "https://example.com/who", "status": "CONTEXT_MATCHED"},
            ],
            "limitations": [],
        },
    }
    return finding, decision


class RevisionTests(unittest.TestCase):
    def test_skips_when_no_unverified_wuenic_source(self):
        finding, decision = _decision()
        decision["critic"]["source_checks"][0]["status"] = "CONTEXT_MATCHED"
        updated, revision = revise_decision(
            finding, decision, fetch_records=lambda: (_ for _ in ()).throw(AssertionError("should not fetch"))
        )
        self.assertEqual(revision["action"], "NO_ADDITIONAL_EVIDENCE")
        self.assertEqual(updated["decision"], "REVIEW")

    def test_matching_workbook_upgrades_source_check(self):
        finding, decision = _decision()
        records = [{
            "country": "Cameroon",
            "antigen": "MCV1",
            "year": "2020",
            "measure": "WUENIC estimate",
            "value_percent": "63",
        }]
        updated, revision = revise_decision(
            finding, decision, fetch_records=lambda: records
        )
        self.assertEqual(revision["action"], "FETCH_WUENIC")
        self.assertEqual(revision["outcome"], "REVISED_SOURCE_CHECK")
        self.assertEqual(updated["decision"], "REVIEW")
        self.assertEqual(
            updated["critic"]["source_checks"][0]["status"],
            "EXTRACT_CONSISTENT",
        )
        self.assertEqual(
            updated["critic"]["source_checks"][0]["verification_scope"],
            "SELF_CONSISTENCY",
        )

    def test_conflicting_workbook_value_abstains(self):
        finding, decision = _decision()
        records = [{
            "country": "Cameroon",
            "antigen": "MCV1",
            "year": "2020",
            "measure": "WUENIC estimate",
            "value_percent": "50",
        }]
        updated, revision = revise_decision(
            finding, decision, fetch_records=lambda: records
        )
        self.assertEqual(updated["decision"], "ABSTAIN")
        self.assertEqual(revision["stop_reason"], "EXTRACT_VALUE_CONFLICT")

    def test_failed_fetch_keeps_original_decision(self):
        finding, decision = _decision()

        def boom():
            raise OSError("connection refused")

        updated, revision = revise_decision(finding, decision, fetch_records=boom)
        self.assertEqual(updated["decision"], "REVIEW")
        self.assertEqual(revision["outcome"], "ADDITIONAL_EVIDENCE_UNAVAILABLE")


class RevisionReportTests(unittest.TestCase):
    def test_report_includes_revision_action(self):
        from src.reporter import render_report

        report = render_report({
            "findings": [{
                "country": "Cameroon",
                "antigen": "MCV1",
                "year": "2020",
                "measure_a": "WUENIC estimate",
                "value_a": 63.0,
                "measure_b": "Administrative coverage",
                "value_b": 74.0,
                "gap_percentage_points": 11.0,
                "sources": [{"name": "UNICEF", "url": "https://example.com/unicef"}],
            }],
            "decisions": [{
                "decision": "REVIEW",
                "reason": "Investigate.",
                "critic": {
                    "source_checks": [
                        {"name": "UNICEF", "status": "EXTRACT_CONSISTENT"}
                    ],
                },
                "revision": {
                    "action": "FETCH_WUENIC",
                    "outcome": "REVISED_SOURCE_CHECK",
                    "stop_reason": "WORKBOOK_VALUE_MATCHED",
                    "year": "2020",
                },
            }],
            "revisions": [{
                "action": "FETCH_WUENIC",
                "outcome": "REVISED_SOURCE_CHECK",
                "stop_reason": "WORKBOOK_VALUE_MATCHED",
                "year": "2020",
                "country": "Cameroon",
                "antigen": "MCV1",
            }],
        })
        self.assertIn("## Revision loop", report)
        self.assertIn("FETCH_WUENIC", report)
        self.assertIn("WORKBOOK_VALUE_MATCHED", report)
        self.assertIn("Verification status: EXTRACT_CONSISTENT", report)
        self.assertIn("not independent verification", report)
