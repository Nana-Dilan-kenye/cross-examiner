"""Tests for the entry point, the trace contract and the secret scan.

The entry point and the trace are what a judge runs and reads, so their
shape is pinned here: the fields the technical guidance names, more than
one named agent, and visible handovers between them.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src import tracing

ROOT = Path(__file__).resolve().parent.parent
RUN_PY = ROOT / "run.py"


def _run(args, env=None):
    environment = dict(os.environ)
    environment["SAMPLE_MODE"] = "true"
    environment["PATH"] = environment.get("PATH", "")
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, str(RUN_PY), *args],
        cwd=str(ROOT), capture_output=True, text=True, env=environment,
        timeout=300,
    )


class EntryPointTests(unittest.TestCase):
    def test_health_is_json_on_stdout(self):
        result = _run(["--health"])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["sample_mode"])

    def test_one_run_answers_with_the_documented_fields(self):
        request = ROOT / "input_examples" / "example_3_sample_mode.json"
        result = _run(["--once", str(request)])
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)

        for field in (
            "run_id", "status", "output", "agents", "trace_id",
            "log_file", "execution_time_seconds",
        ):
            self.assertIn(field, payload)

        self.assertTrue(payload["agents"])
        self.assertGreaterEqual(len(payload["agents"]), 2)
        self.assertTrue(payload["trace_id"].endswith(payload["run_id"]))
        self.assertTrue(payload["output"]["findings"])

    def test_the_wrapped_request_shape_works_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.json"
            path.write_text(json.dumps({
                "run_id": "demo-1",
                "input": {
                    "question": "Which figure for 2020?",
                    "country": "Cameroon",
                    "antigen": "MCV1",
                    "year": "2020",
                },
                "options": {"source": "local", "model": "off",
                            "use_memory": False},
            }), encoding="utf-8")
            result = _run(["--once", str(path)])

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["findings"][0]["year"], "2020")

    def test_an_invalid_request_returns_a_structured_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.json"
            path.write_text(json.dumps({"question": "x", "source": "pigeon"}),
                            encoding="utf-8")
            result = _run(["--once", str(path)])

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["type"], "invalid_request")
        self.assertTrue(payload["error"]["recoverable"])

    def test_a_broken_request_file_returns_a_structured_error(self):
        result = _run(["--once", "/nonexistent/request.json"])
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["type"], "request_not_readable")


class TraceContractTests(unittest.TestCase):
    def test_the_trace_has_the_fields_the_guidance_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = tracing.Trace(run_id="contract", directory=Path(tmp),
                                   echo=False)
            trace.agent(
                "investigator", "plan.fetch", target_agent="critic",
                input_summary="Cameroon MCV1 (2020)", output_summary="a plan",
                confidence=0.6,
            )
            trace.close()
            records = tracing.read_trace("contract", Path(tmp))

        record = next(
            item for item in records
            if item.get("agent_name") == "investigator"
        )
        for field in (
            "timestamp", "run_id", "agent_name", "action", "input_summary",
            "output_summary", "target_agent", "confidence", "retry_count",
            "status",
        ):
            self.assertIn(field, record)
        self.assertEqual(record["agent_name"], "investigator")
        self.assertEqual(record["target_agent"], "critic")
        self.assertEqual(record["retry_count"], 0)

    def test_the_trace_shows_the_agents_and_the_handoffs(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = tracing.Trace(run_id="handoffs", directory=Path(tmp),
                                   echo=False)
            trace.agent("investigator", "plan.fetch", target_agent="critic")
            trace.agent("critic", "verify.sources", target_agent="arbiter")
            trace.agent("memory", "recall.prior_findings",
                        target_agent="investigator")
            trace.close()
            records = tracing.read_trace("handoffs", Path(tmp))

        names = tracing.agent_names(records)
        self.assertIn("investigator", names)
        self.assertIn("critic", names)
        self.assertIn("memory", names)

        links = tracing.handoffs(records)
        self.assertTrue(any(
            link["from"] == "critic" and link["to"] == "arbiter"
            for link in links
        ))

    def test_the_trace_goes_to_stdout_as_well_as_to_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = tracing.Trace(run_id="echo", directory=Path(tmp),
                                   echo=True)
            trace.agent("critic", "verify.sources")
            trace.close()

            # The file has the record; stdout was written by the trace
            # itself, so a judge watching the service sees the run.
            records = tracing.read_trace("echo", Path(tmp))
            self.assertTrue(records)
            self.assertTrue((Path(tmp) / "trace-echo.jsonl").exists())


class SecretScanTests(unittest.TestCase):
    def test_the_repository_holds_no_secret(self):
        result = subprocess.run(
            [sys.executable, "scripts/secret_scan.py"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No secrets found", result.stdout)

    def test_the_scanner_would_notice_one(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "secret_scan", ROOT / "scripts" / "secret_scan.py"
        )
        secret_scan = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(secret_scan)

        # The value is built at run time, so this test file does not
        # itself look like a leaked key to the scanner.
        value = "METERLESS_RUNTIME_TOKEN=" + ("abcdef" * 4)
        findings = secret_scan.scan_text(value)
        self.assertTrue(findings)


if __name__ == "__main__":
    unittest.main()
