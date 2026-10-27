import io
import json
import sys
import unittest
from unittest.mock import patch

from src import analyzer
from src.model_client import ModelUnavailable


class FakeClient:
    """Model stub: proposes a workbook fetch and challenges the claim."""

    model = "test/model"

    def __init__(self):
        self.calls = 0

    def chat_json(self, messages, max_tokens=400, temperature=0.2):
        self.calls += 1
        if self.calls == 1:
            return {
                "actions": [{
                    "year": "2020",
                    "action": "FETCH_WUENIC_WORKBOOK",
                    "target": None,
                    "reason": "The estimate is still unverified.",
                }],
            }
        return {
            "challenges": ["The administrative figure has no independent source."],
            "missing_support": ["A second administrative data source."],
            "would_change_verdict": True,
            "summary": "The gap remains unexplained.",
        }


class BrokenClient:
    model = "test/model"

    def __init__(self):
        self.calls = 0

    def chat_json(self, messages, max_tokens=400, temperature=0.2):
        self.calls += 1
        raise ModelUnavailable("Cannot reach the runtime")


def pdf_verification(url, finding, **kwargs):
    return {
        "status": "CONTEXT_MATCHED",
        "table_page": 20,
        "matched_values": [
            {
                "measure": finding.get("measure_a"),
                "expected": finding.get("value_a"),
                "table_value": str(finding.get("value_a")),
                "found_in_expected_year_row": True,
            }
        ],
        "limitations": ["Text matching does not validate the underlying data."],
    }


def document_fetch(url):
    """Stub for the source-document retrieval, so the tests stay offline."""
    return {
        "status": "RETRIEVED",
        "content_type": "text/html",
        "bytes": 120,
        "text_excerpt": "Cameroon MCV1 immunization coverage",
        "mentions": {},
        "error": None,
    }


def zetaris_fetch():
    """Stub for the evidence store, so the tests stay offline."""
    return WORKBOOK_ROWS


WORKBOOK_ROWS = [
    {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2018",
        "measure": "WUENIC estimate",
        "value_percent": "61",
    },
    {
        "country": "Ethiopia",
        "antigen": "MCV1",
        "year": "2017",
        "measure": "WUENIC estimate",
        "value_percent": "59",
    },
    {
        "country": "Ethiopia",
        "antigen": "MCV1",
        "year": "2020",
        "measure": "WUENIC estimate",
        "value_percent": "67",
    },
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
        "year": "2021",
        "measure": "WUENIC estimate",
        "value_percent": "65",
    },
    {
        "country": "Cameroon",
        "antigen": "MCV1",
        "year": "2023",
        "measure": "WUENIC estimate",
        "value_percent": "71",
    },
]


class AnalyzerFlowTests(unittest.TestCase):
    def _run(self, client, extra_args=None):
        argv = [
            "analyzer",
            "--source", "csv",
            "--question", "Cameroon MCV1 coverage discrepancy 2023",
            "--model", "auto",
        ]
        argv.extend(extra_args or [])

        remembered = []

        def fake_remember(content, source, refs=None, tags=None, confidence=0.7):
            remembered.append({"content": content, "source": source, "tags": tags})
            return {"ok": True, "id": f"mem-{len(remembered)}"}

        stdout = sys.stdout

        def fake_build(mode="auto"):
            if mode == "off":
                return None, {
                    "status": "disabled",
                    "model": None,
                    "base_url": None,
                    "calls": 0,
                    "max_calls": 4,
                    "note": "MODEL_DISABLED_BY_FLAG",
                    "proposals": [],
                    "challenges": [],
                }
            return client, {
                "status": "enabled",
                "model": client.model,
                "base_url": "http://runtime.test/v1",
                "calls": 0,
                "max_calls": 4,
                "note": None,
                "proposals": [],
                "challenges": [],
            }

        try:
            with patch.object(sys, "argv", argv), \
                    patch("src.analyzer.build_model_client", fake_build), \
                    patch("src.source_verifier.verify_pdf_source", pdf_verification), \
                    patch("src.coordination.fetch_source_document", document_fetch), \
                    patch("src.zetaris_source.load_records", zetaris_fetch), \
                    patch("src.revision.fetch_wuenic_records", lambda: WORKBOOK_ROWS), \
                    patch("src.memory_bridge.query", lambda question: {
                        "memories": [{
                            "id": "mem-1",
                            "content": "Observed a 11.0 percentage-point gap.",
                            "confidence": 0.7,
                        }],
                        "available": True,
                        "error": None,
                    }), \
                    patch("src.memory_bridge.remember", fake_remember), \
                    patch.object(sys, "stdout", new=io.StringIO()):
                analyzer.main()
                output = sys.stdout.getvalue()
        finally:
            sys.stdout = stdout

        return json.loads(output), remembered

    def test_model_proposal_drives_the_revision(self):
        client = FakeClient()
        result, _ = self._run(client)

        self.assertEqual(result["model"]["status"], "used")
        proposals = result["model"]["proposals"]
        self.assertEqual(proposals[0]["action"], "FETCH_WUENIC_WORKBOOK")
        self.assertEqual(proposals[0]["source"], "model")

        revision = result["revisions"][0]
        self.assertEqual(revision["action"], "FETCH_WUENIC")
        self.assertEqual(revision["proposal_source"], "model")

    def test_model_cannot_change_the_decision(self):
        client = FakeClient()
        result, _ = self._run(client)

        for decision in result["decisions"]:
            self.assertIn(decision["decision"], ("REVIEW", "REPORT_OBSERVATION"))

        challenges = result["model"]["challenges"]
        self.assertTrue(any(c["would_change_verdict"] for c in challenges))

    def test_unavailable_runtime_falls_back_deterministically(self):
        client = BrokenClient()
        result, _ = self._run(client)

        self.assertEqual(result["model"]["status"], "unavailable")
        for proposal in result["model"]["proposals"]:
            self.assertEqual(proposal["source"], "deterministic")
        for challenge in result["model"]["challenges"]:
            self.assertEqual(challenge["source"], "deterministic")

    def test_challenge_is_written_to_memory(self):
        client = FakeClient()
        _, remembered = self._run(client, extra_args=["--remember"])

        sources = [item["source"] for item in remembered]
        self.assertTrue(
            any(source.startswith("cross-examiner:challenge:") for source in sources)
        )

    def test_model_off_uses_no_calls(self):
        client = FakeClient()
        result, _ = self._run(client, extra_args=["--model", "off"])

        self.assertEqual(result["model"]["status"], "disabled")
        self.assertEqual(client.calls, 0)


if __name__ == "__main__":
    unittest.main()
