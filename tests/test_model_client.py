import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from src.model_client import (
    MeterlessClient,
    ModelInvalidResponse,
    ModelUnavailable,
    parse_json_object,
    redact,
    strip_reasoning,
)

FAKE_KEY = "test-secret-token-value"


class FakeResponse:
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload):
        if isinstance(payload, bytes):
            self._data = payload
        else:
            self._data = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if size is not None and size >= 0:
            return self._data[:size]
        return self._data


def completion(content, model="test/model"):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
    }


def make_client(opener, **kwargs):
    options = {
        "base_url": "http://runtime.test/v1",
        "api_key": FAKE_KEY,
        "model": "test/model",
        "timeout": 5,
        "opener": opener,
        # Keep the real .env.local out of the test process.
        "env_file": "/nonexistent/.env.local",
        # No retries unless a test asks for them.
        "max_retries": 0,
        # Use the mocked HTTP transport; the Windows transport has its own tests.
        "transport": "http",
    }
    options.update(kwargs)
    return MeterlessClient(**options)


class ModelClientTests(unittest.TestCase):
    def test_chat_returns_assistant_text(self):
        def opener(_request, timeout=None):
            return FakeResponse(completion("hello"))

        client = make_client(opener)
        self.assertEqual(client.chat([{"role": "user", "content": "hi"}]), "hello")

    def test_chat_json_returns_parsed_object(self):
        def opener(_request, timeout=None):
            return FakeResponse(completion('{"action": "STOP"}'))

        client = make_client(opener)
        payload = client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(payload, {"action": "STOP"})

    def test_reasoning_tags_are_stripped(self):
        def opener(_request, timeout=None):
            return FakeResponse(completion("<think>reasoning here</think>answer"))

        client = make_client(opener)
        self.assertEqual(client.chat([{"role": "user", "content": "hi"}]), "answer")

    def test_json_wrapped_in_prose_is_recovered(self):
        parsed = parse_json_object('Here you go: {"a": 1} hope that helps')
        self.assertEqual(parsed, {"a": 1})

    def test_non_json_reply_raises_invalid_response(self):
        def opener(_request, timeout=None):
            return FakeResponse(completion("not json at all"))

        client = make_client(opener)
        with self.assertRaises(ModelInvalidResponse):
            client.chat_json([{"role": "user", "content": "hi"}])

    def test_empty_completion_raises_invalid_response(self):
        def opener(_request, timeout=None):
            return FakeResponse(completion("   "))

        client = make_client(opener)
        with self.assertRaises(ModelInvalidResponse):
            client.chat([{"role": "user", "content": "hi"}])

    def test_unauthorized_raises_model_unavailable(self):
        def opener(_request, timeout=None):
            raise HTTPError(
                "http://runtime.test/v1/chat/completions",
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"error":"unauthorized"}'),
            )

        client = make_client(opener)
        with self.assertRaises(ModelUnavailable):
            client.chat([{"role": "user", "content": "hi"}])

    def test_connection_failure_raises_model_unavailable(self):
        def opener(_request, timeout=None):
            raise URLError("connection refused")

        client = make_client(opener)
        with self.assertRaises(ModelUnavailable):
            client.chat([{"role": "user", "content": "hi"}])

    def test_timeout_raises_model_unavailable(self):
        def opener(_request, timeout=None):
            raise TimeoutError("timed out")

        client = make_client(opener)
        with self.assertRaises(ModelUnavailable):
            client.chat([{"role": "user", "content": "hi"}])

    def test_runtime_error_payload_raises_model_unavailable(self):
        def opener(_request, timeout=None):
            return FakeResponse({"error": {"message": "model not ready"}})

        client = make_client(opener)
        with self.assertRaises(ModelUnavailable):
            client.chat([{"role": "user", "content": "hi"}])

    def test_probe_reports_false_when_unreachable(self):
        def opener(_request, timeout=None):
            raise URLError("connection refused")

        client = make_client(opener)
        self.assertFalse(client.probe())

    def test_probe_reports_true_when_reachable(self):
        def opener(_request, timeout=None):
            return FakeResponse({"data": [{"id": "meterless/auto"}]})

        client = make_client(opener)
        self.assertTrue(client.probe())
        self.assertEqual(client.list_models(), ["meterless/auto"])

    def test_api_key_never_appears_in_config_or_errors(self):
        def opener(_request, timeout=None):
            raise HTTPError(
                "http://runtime.test/v1/chat/completions",
                401,
                "Unauthorized",
                {},
                io.BytesIO(FAKE_KEY.encode()),
            )

        client = make_client(opener)
        self.assertNotIn(FAKE_KEY, json.dumps(client.config()))
        self.assertNotIn(FAKE_KEY, repr(client))

        with self.assertRaises(ModelUnavailable) as caught:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertNotIn(FAKE_KEY, str(caught.exception))

    def test_redact_removes_secret(self):
        self.assertNotIn(FAKE_KEY, redact(f"key={FAKE_KEY}", FAKE_KEY))

    def test_strip_reasoning_handles_dangling_tag(self):
        self.assertEqual(strip_reasoning("answer</think>"), "answer")

    def test_gateway_timeout_is_retried_once(self):
        attempts = []

        def opener(_request, timeout=None):
            attempts.append(timeout)
            if len(attempts) == 1:
                raise HTTPError(
                    "http://runtime.test/v1/chat/completions",
                    504,
                    "Gateway Timeout",
                    {},
                    io.BytesIO(b"first token limit"),
                )
            return FakeResponse(completion("recovered"))

        client = make_client(opener, max_retries=1)
        with patch("src.model_client.time.sleep"):
            answer = client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(answer, "recovered")
        self.assertEqual(len(attempts), 2)

    def test_ttfb_header_is_sent_when_configured(self):
        seen = {}

        def opener(request, timeout=None):
            seen.update(request.headers)
            return FakeResponse(completion("ok"))

        client = make_client(opener, ttfb_ms=120000)
        client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(seen.get("Meterless-ttfb-ms"), "120000")


class WindowsTransportTests(unittest.TestCase):
    """The Windows curl transport, with curl itself mocked."""

    def _client(self, **kwargs):
        options = {
            "base_url": "http://runtime.test/v1",
            "windows_base_url": "http://127.0.0.1:8088/v1",
            "api_key": FAKE_KEY,
            "model": "test/model",
            "timeout": 5,
            "opener": lambda *a, **k: self.fail("HTTP transport must not be used"),
            "env_file": "/nonexistent/.env.local",
            "max_retries": 0,
            "transport": "windows-curl",
        }
        options.update(kwargs)
        return MeterlessClient(**options)

    def test_request_goes_through_curl_with_the_body_on_stdin(self):
        seen = {}

        def fake_run(argv, input=None, capture_output=None, timeout=None):
            seen["argv"] = argv
            seen["input"] = input
            seen["config"] = Path(argv[argv.index("--config") + 1]).read_text()
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=(json.dumps(completion("from curl")).encode()
                        + b"\n__HTTP_STATUS__200"),
                stderr=b"",
            )

        with patch("src.model_client.find_windows_curl", return_value="/fake/curl.exe"), \
                patch("src.model_client.subprocess.run", fake_run):
            answer = self._client().chat([{"role": "user", "content": "hi"}])

        self.assertEqual(answer, "from curl")
        self.assertIn(b'"hi"', seen["input"])
        self.assertNotIn(FAKE_KEY, " ".join(seen["argv"]))
        self.assertIn(FAKE_KEY, seen["config"])

    def test_config_file_is_removed_afterwards(self):
        paths = []

        def fake_run(argv, input=None, capture_output=None, timeout=None):
            paths.append(Path(argv[argv.index("--config") + 1]))
            return subprocess.CompletedProcess(
                argv, 0, stdout=b'{"choices": []}\n__HTTP_STATUS__200', stderr=b""
            )

        with patch("src.model_client.find_windows_curl", return_value="/fake/curl.exe"), \
                patch("src.model_client.subprocess.run", fake_run):
            with self.assertRaises(ModelInvalidResponse):
                self._client().chat([{"role": "user", "content": "hi"}])

        self.assertTrue(paths)
        self.assertFalse(paths[0].exists())

    def test_http_error_status_is_reported(self):
        def fake_run(argv, input=None, capture_output=None, timeout=None):
            return subprocess.CompletedProcess(
                argv, 0, stdout=b'{"error":"nope"}\n__HTTP_STATUS__502', stderr=b""
            )

        with patch("src.model_client.find_windows_curl", return_value="/fake/curl.exe"), \
                patch("src.model_client.subprocess.run", fake_run):
            with self.assertRaises(ModelUnavailable):
                self._client().chat([{"role": "user", "content": "hi"}])

    def test_transport_order_prefers_windows_curl_when_present(self):
        with patch("src.model_client.find_windows_curl", return_value="/fake/curl.exe"):
            client = self._client(transport="auto")
            self.assertEqual(
                client.available_transports(), ["windows-curl", "http"]
            )

    def test_transport_order_without_curl_is_http_only(self):
        with patch("src.model_client.find_windows_curl", return_value=None):
            client = self._client(transport="auto")
            self.assertEqual(client.available_transports(), ["http"])

    def test_falls_back_to_http_when_curl_transport_fails(self):
        def fake_run(argv, input=None, capture_output=None, timeout=None):
            return subprocess.CompletedProcess(
                argv, 7, stdout=b"", stderr=b"cannot start"
            )

        def opener(_request, timeout=None):
            return FakeResponse(completion("from python"))

        with patch("src.model_client.find_windows_curl", return_value="/fake/curl.exe"), \
                patch("src.model_client.subprocess.run", fake_run):
            client = self._client(transport="auto", opener=opener)
            answer = client.chat([{"role": "user", "content": "hi"}])

        self.assertEqual(answer, "from python")
        self.assertEqual(client.last_transport, "http")


if __name__ == "__main__":
    unittest.main()
