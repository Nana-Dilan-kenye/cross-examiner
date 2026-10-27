import json
import subprocess
import unittest
from unittest.mock import patch

from src import memory_bridge


class MemoryBridgeFailureTests(unittest.TestCase):
    def _failing_run(self, *args, **kwargs):
        raise subprocess.CalledProcessError(
            1, "npx tsx", output="", stderr="SyntaxError: Unexpected token '.'"
        )

    def test_query_degrades_when_the_bridge_fails(self):
        with patch.object(memory_bridge.subprocess, "run", self._failing_run):
            result = memory_bridge.query("Cameroon MCV1")

        self.assertFalse(result["available"])
        self.assertEqual(result["memories"], [])
        self.assertTrue(result["error"])

    def test_remember_reports_failure_instead_of_raising(self):
        with patch.object(memory_bridge.subprocess, "run", self._failing_run):
            result = memory_bridge.remember("content", "source")

        self.assertFalse(result["ok"])
        self.assertIsNone(result["id"])
        self.assertTrue(result["error"])

    def test_missing_executable_is_reported(self):
        def raise_os_error(*args, **kwargs):
            raise OSError("npx not found")

        with patch.object(memory_bridge.subprocess, "run", raise_os_error):
            result = memory_bridge.query("Cameroon MCV1")

        self.assertFalse(result["available"])
        self.assertIn("npx not found", result["error"])

    def test_successful_query_is_marked_available(self):
        payload = {
            "context": "context",
            "memories": [{"id": "mem-1", "content": "x"}],
            "trace": {"strategy": "comprehensive"},
        }

        class FakeResult:
            stdout = json.dumps(payload)

        with patch.object(
            memory_bridge.subprocess, "run", lambda *a, **k: FakeResult()
        ):
            result = memory_bridge.query("Cameroon MCV1")

        self.assertTrue(result["available"])
        self.assertEqual(result["memories"][0]["id"], "mem-1")
        self.assertIsNone(result["error"])

    def test_failure_message_stays_short(self):
        noisy = (
            "file:///very/long/minified.js " + ("x" * 5000)
            + "\nSyntaxError: Unexpected token '.'\n"
        )

        message = memory_bridge._diagnose(noisy)

        self.assertLessEqual(len(message), 400)
        self.assertIn("SyntaxError", message)


if __name__ == "__main__":
    unittest.main()
