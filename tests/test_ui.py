"""Tests for the investigation page and its contract with the API.

The page is static files under ``ui/``, served by the same server as the
API. The server tests start the real HTTP server on a free local port in
sample mode, so they need no credentials and no network. The page's logic
is exercised with Node when it is installed.
"""

import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from src import app

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
NODE = shutil.which("node")

TITLE = "<title>Cross-Examiner — Evidence-Based Investigation</title>"
SECTIONS = [
    "Investigation input",
    "Evidence comparison",
    "Investigation trace",
    "Conclusion and review status",
    "Run details",
]


def header(headers, name):
    lowered = {key.lower(): value for key, value in headers.items()}
    return lowered.get(name.lower(), "")


class LiveServerTestCase(unittest.TestCase):
    """The real HTTP server, on a free local port, in sample mode."""

    @classmethod
    def setUpClass(cls):
        cls._env = patch.dict(os.environ, {"SAMPLE_MODE": "true"})
        cls._env.start()
        cls._quiet = patch.object(
            app.Handler, "log_message", lambda self, *args: None
        )
        cls._quiet.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._quiet.stop()
        cls._env.stop()

    def request(self, method, path, body=None, headers=None):
        """One request with the path sent exactly as written."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post_run(self, raw):
        return self.request(
            "POST", "/run", body=raw,
            headers={"Content-Type": "application/json"},
        )


class PageServingTests(LiveServerTestCase):
    def test_the_page_is_served_at_ui(self):
        status, headers, body = self.request("GET", "/ui/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", header(headers, "Content-Type"))

        page = body.decode("utf-8")
        self.assertIn(TITLE, page)
        for section in SECTIONS:
            self.assertIn(section, page)
        self.assertIn('id="investigate-form"', page)
        self.assertIn('id="investigate-button"', page)

    def test_ui_without_the_slash_redirects_to_ui_with_it(self):
        # The page's asset links are relative. Served at /ui (no slash),
        # the browser would look for them at the root and 404. The server
        # sends the browser the canonical spelling instead.
        status, headers, body = self.request("GET", "/ui")
        self.assertEqual(status, 301)
        self.assertEqual(header(headers, "Location"), "/ui/")
        self.assertEqual(body, b"")

    def test_the_redirect_carries_the_query_string(self):
        status, headers, _ = self.request(
            "GET", "/ui?question=Which+figure%3F&country=Cameroon"
        )
        self.assertEqual(status, 301)
        self.assertEqual(
            header(headers, "Location"),
            "/ui/?question=Which+figure%3F&country=Cameroon",
        )

    def test_following_the_redirect_lands_on_the_page(self):
        # The loop guard: /ui must redirect once, to a page that does not
        # redirect back.
        _, headers, _ = self.request("GET", "/ui")
        status, headers, body = self.request("GET", header(headers, "Location"))
        self.assertEqual(status, 200)
        self.assertIn("text/html", header(headers, "Content-Type"))
        self.assertIn(TITLE, body.decode("utf-8"))

    def test_the_assets_have_their_content_types_and_are_not_cached(self):
        status, headers, _ = self.request("GET", "/ui/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", header(headers, "Content-Type"))
        self.assertEqual(header(headers, "Cache-Control"), "no-cache")

        status, headers, _ = self.request("GET", "/ui/styles.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", header(headers, "Content-Type"))

    def test_every_page_response_carries_the_content_policy(self):
        status, headers, _ = self.request("GET", "/ui/")
        self.assertEqual(status, 200)
        policy = header(headers, "Content-Security-Policy")
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertEqual(header(headers, "X-Content-Type-Options"), "nosniff")

    def test_nothing_outside_the_ui_directory_is_served(self):
        for path in (
            "/ui/../src/app.py",
            "/ui/%2e%2e/%2e%2e/run.py",
            "/ui/..%2F..%2Frun.py",
            "/ui//etc/passwd",
            "/ui/%00",
            "/ui/missing.html",
        ):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 404, path)
            self.assertIn("application/json", header(headers, "Content-Type"), path)
            self.assertNotIn(b"def ", body, path)

    def test_the_api_routes_that_existed_are_unchanged(self):
        status, headers, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        report = json.loads(body)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["ui"], "/ui/")

        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("application/json", header(headers, "Content-Type"))
        self.assertEqual(json.loads(body)["status"], "ok")


class ApiContractTests(LiveServerTestCase):
    """The API answers the page's requests with the fields it renders."""

    def _sample_request(self):
        path = ROOT / "input_examples" / "example_3_sample_mode.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_a_sample_run_has_every_field_the_page_renders(self):
        status, headers, body = self.post_run(
            json.dumps(self._sample_request()).encode("utf-8")
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)

        for key in (
            "run_id", "status", "mode", "sample_mode", "findings",
            "semantic_layer", "executed_actions", "memory", "stop_reason",
            "stop_detail", "model", "trace_id", "log_file", "agents",
            "execution_time_seconds",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["mode"], "sample")

        finding = payload["findings"][0]
        for key in (
            "country", "antigen", "year", "data_kind", "review_status",
            "confidence", "decision", "reason", "measures",
            "gap_percentage_points", "recommendation", "conflicts",
            "lineage", "evidence", "uncertainties",
        ):
            self.assertIn(key, finding)
        self.assertTrue(finding["data_kind"].startswith("sample:"))

        for item in finding["lineage"]:
            for key in (
                "measure", "value", "origin", "source_id", "source_name",
                "source_ref", "is_derived", "verification_scope",
            ):
                self.assertIn(key, item)
        for item in finding["evidence"]:
            for key in ("evidence_id", "kind", "name", "status", "scope"):
                self.assertIn(key, item)

    def test_a_year_without_an_independent_line_comes_back_without_a_recommendation(self):
        request = json.loads(
            (ROOT / "input_examples" / "example_2_cameroon_mcv1_2023.json")
            .read_text(encoding="utf-8")
        )
        request["use_memory"] = False
        status, _, body = self.post_run(json.dumps(request).encode("utf-8"))
        self.assertEqual(status, 200)
        finding = json.loads(body)["findings"][0]
        self.assertIsNone(finding["recommendation"])
        self.assertTrue(finding["uncertainties"])

    def test_the_trace_of_the_run_is_served_for_the_timeline(self):
        status, _, body = self.post_run(
            json.dumps(self._sample_request()).encode("utf-8")
        )
        run_id = json.loads(body)["run_id"]

        status, headers, body = self.request("GET", f"/traces/{run_id}")
        self.assertEqual(status, 200)
        events = json.loads(body)["events"]
        self.assertTrue(events)
        for event in events:
            for key in (
                "timestamp", "agent_name", "action", "target_agent",
                "status", "retry_count",
            ):
                self.assertIn(key, event)
        self.assertEqual(events[0]["action"], "run.started")
        self.assertEqual(events[-1]["action"], "run.finished")

    def test_an_unknown_run_is_a_json_404(self):
        status, headers, body = self.request("GET", "/traces/no-such-run")
        self.assertEqual(status, 404)
        self.assertIn("application/json", header(headers, "Content-Type"))
        self.assertIn("error", json.loads(body))

    def test_requests_the_api_refuses_come_back_as_json_400s(self):
        cases = [
            (b"not json", "not valid JSON"),
            (b"[1, 2]", "must be a JSON object"),
            (json.dumps({"question": "x", "source": "pigeon"}).encode(), "'source'"),
            (json.dumps({"question": "x", "threshold": "high"}).encode(), "'threshold'"),
            (json.dumps({}).encode(), "question"),
        ]
        for raw, expected in cases:
            status, headers, body = self.post_run(raw)
            self.assertEqual(status, 400, raw)
            self.assertIn("application/json", header(headers, "Content-Type"), raw)
            self.assertIn(expected, json.loads(body)["error"], raw)

    def test_the_example_requests_are_listed_for_the_shortcuts(self):
        status, _, body = self.request("GET", "/examples")
        self.assertEqual(status, 200)
        items = json.loads(body)["requests"]
        self.assertTrue(items)
        self.assertTrue(
            any(item["request"].get("country") == "Cameroon" for item in items)
        )
        for item in items:
            self.assertTrue(item["file"].startswith("input_examples/"))
            self.assertIn("question", item["request"])


class PageSourceTests(unittest.TestCase):
    """What the page is made of, read from its files."""

    def setUp(self):
        self.html = (UI / "index.html").read_text(encoding="utf-8")
        self.script = (UI / "app.js").read_text(encoding="utf-8")

    def test_every_form_control_has_a_label(self):
        controls = re.findall(r'<(?:input|textarea)\b[^>]*\bid="([^"]+)"', self.html)
        self.assertTrue(controls)
        for control in controls:
            self.assertIn(f'for="{control}"', self.html, control)

    def test_the_page_has_no_inline_script_style_or_handler(self):
        self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", self.html), [])
        self.assertNotIn("<style", self.html)
        self.assertEqual(re.findall(r"\son[a-z]+\s*=", self.html), [])
        self.assertNotIn(' style="', self.html)

    def test_the_page_declares_its_icon_so_the_browser_stops_asking_for_one(self):
        # Without it the browser asks for /favicon.ico on every load and
        # the console shows a 404 the page cannot answer.
        self.assertIn('rel="icon"', self.html)
        self.assertIn('href="data:,"', self.html)

    def test_the_script_writes_api_text_as_text_only(self):
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(sink, self.script, sink)

    def test_the_script_calls_only_the_documented_endpoints(self):
        paths = set(re.findall(r'["\'](/[a-z][^"\']*)["\']', self.script))
        self.assertTrue(paths)
        for path in paths:
            self.assertTrue(
                path in ("/health", "/examples", "/run") or path.startswith("/traces/"),
                path,
            )

    def test_the_script_holds_no_figure_from_an_example_result(self):
        # Results come from POST /run. The page must not carry them.
        for name in ("Household survey coverage", "Administrative coverage", "WUENIC estimate"):
            self.assertNotIn(name, self.script)


@unittest.skipUnless(NODE, "Node is not installed, so the page logic is not run")
class PageLogicTests(unittest.TestCase):
    """The page's decisions, run in Node on the real script."""

    def _evaluate(self, expressions):
        lines = [f"const ui = require({json.dumps(str(UI / 'app.js'))});",
                 "const out = {};"]
        for name, expression in expressions.items():
            lines.append(f"out[{json.dumps(name)}] = ({expression});")
        lines.append("console.log(JSON.stringify(out));")
        result = subprocess.run(
            [NODE, "-e", "\n".join(lines)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_a_figure_is_classified_by_its_own_fields(self):
        result = self._evaluate({
            "independent": 'ui.classifyFigure({is_derived: false, verification_scope: "INDEPENDENT_MEASUREMENT"})',
            "republished": 'ui.classifyFigure({is_derived: true, verification_scope: "SELF_CONSISTENCY"})',
            "published": 'ui.classifyFigure({is_derived: false, verification_scope: "SELF_CONSISTENCY"})',
            "missing": "ui.classifyFigure({})",
        })
        self.assertEqual(result["independent"]["tone"], "independent")
        self.assertEqual(result["republished"]["tone"], "derived")
        self.assertEqual(result["published"]["tone"], "published")
        self.assertEqual(result["missing"]["tone"], "unknown")

    def test_a_real_sample_output_is_classified_row_by_row(self):
        path = json.dumps(str(ROOT / "output_examples" / "example_3_sample_mode_output.json"))
        result = self._evaluate({
            "tones": (
                f'JSON.parse(require("fs").readFileSync({path}, "utf8"))'
                ".findings[0].lineage.map(function (row) { return ui.classifyFigure(row).tone; })"
            ),
        })
        self.assertEqual(result["tones"], ["published", "published", "independent"])

    def test_the_data_kind_is_named_as_sample_or_synthetic(self):
        result = self._evaluate({
            "sample": 'ui.describeDataKind("sample:observed")',
            "synthetic": 'ui.describeDataKind("synthetic")',
            "observed": 'ui.describeDataKind("observed")',
        })
        self.assertEqual(result["sample"]["tone"], "sample")
        self.assertIn("Sample", result["sample"]["label"])
        self.assertEqual(result["synthetic"]["tone"], "synthetic")
        self.assertEqual(result["observed"]["tone"], "published")

    def test_review_is_shown_whenever_the_api_returns_it(self):
        result = self._evaluate({
            "run": 'ui.verdictFor({status: "review", findings: []}).label',
            "finding": 'ui.verdictFor({status: "abstained", findings: [{review_status: "REVIEW"}]}).label',
            "resolved": 'ui.verdictFor({status: "resolved", findings: []}).label',
            "empty": 'ui.verdictFor({status: "no_findings", findings: []}).label',
            "unknown": 'ui.verdictFor({status: "surprising", findings: []}).label',
        })
        self.assertEqual(result["run"], "REVIEW")
        self.assertEqual(result["finding"], "REVIEW")
        self.assertEqual(result["resolved"], "RESOLVED")
        self.assertEqual(result["empty"], "NO FINDINGS")
        self.assertEqual(result["unknown"], "SURPRISING")

    def test_trace_events_are_told_apart_by_the_agent_that_wrote_them(self):
        result = self._evaluate({
            "memory": 'ui.eventKind({agent_name: "memory", action: "recall.prior_findings"})',
            "memoryEvent": 'ui.eventKind({agent_name: "orchestrator", action: "memory.stored"})',
            "critic": 'ui.eventKind({agent_name: "critic", action: "verify.sources"})',
            "arbiter": 'ui.eventKind({agent_name: "arbiter", action: "decide"})',
            "investigator": 'ui.eventKind({agent_name: "investigator", action: "plan.fetch"})',
            "lifecycle": 'ui.eventKind({agent_name: "orchestrator", action: "run.started"})',
        })
        self.assertEqual(result["memory"], "memory")
        self.assertEqual(result["memoryEvent"], "memory")
        self.assertEqual(result["critic"], "critique")
        self.assertEqual(result["arbiter"], "arbitration")
        self.assertEqual(result["investigator"], "investigation")
        self.assertEqual(result["lifecycle"], "lifecycle")

    def test_retries_and_verdict_changes_are_badged_only_when_recorded(self):
        result = self._evaluate({
            "retry": "ui.eventBadges({agent_name: \"investigator\", retry_count: 2}).map(function (b) { return b.label; })",
            "none": "ui.eventBadges({agent_name: \"critic\", retry_count: 0})",
            "verdict": "ui.eventBadges({agent_name: \"critic\", would_change_verdict: true}).map(function (b) { return b.label; })",
        })
        self.assertEqual(result["retry"], ["Retry 2"])
        self.assertEqual(result["none"], [])
        self.assertEqual(result["verdict"], ["Would change the verdict"])

    def test_missing_values_are_reported_as_missing(self):
        result = self._evaluate({
            "whole": "ui.formatValue(63.0)",
            "fraction": "ui.formatValue(63.5)",
            "absent": "ui.formatValue(undefined)",
            "flag": "ui.formatValue(true)",
        })
        self.assertEqual(result["whole"], "63")
        self.assertEqual(result["fraction"], "63.5")
        self.assertEqual(result["absent"], "not reported")
        self.assertEqual(result["flag"], "yes")

    def test_only_http_links_are_followed(self):
        result = self._evaluate({
            "https": 'ui.safeHref("https://example.org/x")',
            "script": 'ui.safeHref("javascript:alert(1)")',
            "data": 'ui.safeHref("data:text/html,x")',
        })
        self.assertEqual(result["https"], "https://example.org/x")
        self.assertIsNone(result["script"])
        self.assertIsNone(result["data"])

    def test_the_request_leaves_out_blank_scope_fields(self):
        result = self._evaluate({
            "request": 'ui.buildRequest({question: "  Q  ", country: "", antigen: "MCV1", year: "2020", remember: false})',
            "problem": 'ui.requestProblem({question: "", country: "", antigen: "", year: ""})',
            "scopeOnly": 'ui.requestProblem({question: "", country: "Cameroon", antigen: "MCV1", year: "2020"})',
        })
        self.assertEqual(result["request"], {
            "question": "Q",
            "antigen": "MCV1",
            "year": "2020",
            "use_memory": True,
            "remember": False,
        })
        self.assertIn("Type a question", result["problem"])
        self.assertIsNone(result["scopeOnly"])

    def test_the_trace_summary_counts_handovers_and_retries(self):
        result = self._evaluate({
            "summary": (
                '(function () { var s = ui.traceSummary(['
                '{agent_name: "investigator", target_agent: "critic"},'
                '{agent_name: "critic", target_agent: "arbiter", retry_count: 1}'
                ']); return s; })()'
            ),
        })
        self.assertEqual(result["summary"]["events"], 2)
        self.assertEqual(result["summary"]["handovers"], 2)
        self.assertEqual(result["summary"]["retries"], 1)
        self.assertEqual(result["summary"]["agents"], ["critic", "investigator"])


if __name__ == "__main__":
    unittest.main()
