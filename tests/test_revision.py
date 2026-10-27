import unittest
import unittest.mock

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


from unittest.mock import patch

from src.revision import fetch_source_document


class SourceDocumentFallbackTests(unittest.TestCase):
    def test_primary_url_success(self):
        with patch("src.source_registry.candidate_urls", return_value=["https://primary.example/doc.pdf", "https://alt.example/doc.pdf"]):
            with patch("src.revision.urlopen") as mocked:
                response = mocked.return_value.__enter__.return_value
                response.headers.get.return_value = "application/pdf"
                response.read.return_value = b"%PDF-1.4"
                result = fetch_source_document("https://primary.example/doc.pdf")
        self.assertEqual(result["status"], "RETRIEVED")
        self.assertEqual(result["url"], "https://primary.example/doc.pdf")
        self.assertEqual(result["requested_url"], "https://primary.example/doc.pdf")

    def test_fallback_success_after_primary_403(self):
        from urllib.error import HTTPError

        def side_effect(request, timeout=...):
            if "primary" in request.full_url:
                raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
            response = unittest.mock.MagicMock()
            response.headers.get.return_value = "application/pdf"
            response.read.return_value = b"%PDF-1.4"
            response.__enter__.return_value = response
            return response

        with patch("src.source_registry.candidate_urls", return_value=["https://primary.example/doc.pdf", "https://alt.example/doc.pdf"]):
            with patch("src.revision.urlopen", side_effect=side_effect):
                result = fetch_source_document("https://primary.example/doc.pdf")
        self.assertEqual(result["status"], "RETRIEVED")
        self.assertEqual(result["url"], "https://alt.example/doc.pdf")
        self.assertEqual(result["requested_url"], "https://primary.example/doc.pdf")
        self.assertEqual(result["attempted_urls"], ["https://primary.example/doc.pdf", "https://alt.example/doc.pdf"])

    def test_all_candidates_fail(self):
        from urllib.error import HTTPError

        def side_effect(request, timeout=...):
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

        with patch("src.source_registry.candidate_urls", return_value=["https://primary.example/doc.pdf", "https://alt.example/doc.pdf"]):
            with patch("src.revision.urlopen", side_effect=side_effect):
                result = fetch_source_document("https://primary.example/doc.pdf")
        self.assertEqual(result["status"], "NOT_RETRIEVED")
        self.assertIsNone(result["url"])
        self.assertIn("403", result["error"])
        self.assertEqual(result["attempted_urls"], ["https://primary.example/doc.pdf", "https://alt.example/doc.pdf"])

    def test_provenance_records_failed_and_successful_urls(self):
        from urllib.error import HTTPError

        def side_effect(request, timeout=...):
            if "primary" in request.full_url:
                raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
            response = unittest.mock.MagicMock()
            response.headers.get.return_value = "application/pdf"
            response.read.return_value = b"%PDF-1.4"
            response.__enter__.return_value = response
            return response

        with patch("src.source_registry.candidate_urls", return_value=["https://primary.example/doc.pdf", "https://alt.example/doc.pdf"]):
            with patch("src.revision.urlopen", side_effect=side_effect):
                result = fetch_source_document("https://primary.example/doc.pdf")
        self.assertEqual(result["failed_attempts"][0]["url"], "https://primary.example/doc.pdf")
        self.assertEqual(result["failed_attempts"][0]["status"], "NOT_RETRIEVED")


class SourceDocumentIdentityTests(unittest.TestCase):
    def test_unrelated_document_is_rejected(self):
        catalog_body = b"<html><title>Publication Catalog</title></html>"

        def side_effect(request, timeout=...):
            response = unittest.mock.MagicMock()
            response.headers.get.return_value = "text/html"
            response.read.return_value = catalog_body
            response.__enter__.return_value = response
            return response

        with patch("src.source_registry.candidate_urls", return_value=["https://primary.example/doc.pdf", "https://catalog.example/search"]):
            with patch("src.revision.urlopen", side_effect=side_effect):
                result = fetch_source_document("https://primary.example/doc.pdf")
        self.assertEqual(result["status"], "NOT_RETRIEVED")
        self.assertIsNone(result["url"])
        self.assertEqual(result["failed_attempts"][0]["status"], "REJECTED_NOT_SAME_DOCUMENT")

    def test_candidate_urls_exclude_catalog_origin(self):
        with patch("src.source_registry.load_registry", return_value={
            "sources": [{
                "source_urls": [
                    "https://example.com/a.pdf",
                    "https://example.com/b.pdf",
                ],
                "origin_url": "https://example.com/catalog",
            }]
        }):
            from src.source_registry import candidate_urls, reset_registry
            reset_registry()
            urls = candidate_urls("https://example.com/a.pdf")
        self.assertEqual(urls, ["https://example.com/a.pdf", "https://example.com/b.pdf"])
        self.assertNotIn("https://example.com/catalog", urls)
