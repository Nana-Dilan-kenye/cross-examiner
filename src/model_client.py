"""OpenAI-compatible client for the Meterless Runtime.

The runtime exposes a standard ``/v1/chat/completions`` endpoint. This module
is transport only: it sends a prompt and returns text or a parsed JSON object.
It makes no decisions about evidence and never touches the arbiter.

Configuration is read from the environment, with an optional gitignored
``.env.local`` fallback (same convention the Zetaris tooling uses):

    METERLESS_BASE_URL           direct HTTP transport (default http://127.0.0.1:8088/v1)
    METERLESS_BASE_URL_WINDOWS   Windows loopback transport (default http://127.0.0.1:8088/v1)
    METERLESS_API_KEY            bearer token (fallback: METERLESS_TOKEN)
    METERLESS_MODEL              default meterless/auto
    METERLESS_TIMEOUT            default 90 seconds
    METERLESS_TRANSPORT          auto | http | windows-curl (default auto)
    METERLESS_TTFB_MS            optional cloud first-token budget header
    METERLESS_MAX_RETRIES        optional retry count for transient failures

Why two transports: the runtime binds ``127.0.0.1:8088`` on Windows. WSL has
its own loopback, so a direct request from WSL cannot reach it unless the
runtime temporarily opens a hotspot listener on the host's LAN address (it
opens and closes that on its own schedule). When that happens the Windows
``curl.exe`` is used instead: it runs on the Windows side, where the loopback
address does work.

The API key is never returned by :meth:`MeterlessClient.config`, never
included in an exception message, and never written to stdout. For the
Windows transport the key is written to a short-lived 0600 config file
instead of the process command line.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_MODEL = "meterless/auto"
DEFAULT_TIMEOUT = 90
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
RETRY_BACKOFF_SECONDS = 2

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_NAME = ".env.local"

WINDOWS_CURL_CANDIDATES = (
    "/mnt/c/Windows/System32/curl.exe",
    "C:/Windows/System32/curl.exe",
)

# Reasoning models sometimes emit <think> blocks or a dangling close tag.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_DANGLING_TAGS = re.compile(r"</?think>", re.IGNORECASE)


class ModelUnavailable(RuntimeError):
    """The runtime could not be reached or refused the request."""


class ModelInvalidResponse(RuntimeError):
    """The runtime answered, but the answer was not usable."""


class ModelRequestFailed(ModelUnavailable):
    """The runtime answered with an error (HTTP error or provider error).

    The runtime was reached, so another transport would fail the same way:
    callers must not retry this through a different transport.
    """


def redact(text, secret):
    """Remove the API key from any text that may be surfaced to a user."""
    if not text:
        return text
    text = str(text)
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


def find_windows_curl():
    """Locate the Windows curl binary, if this machine has one."""
    for path in WINDOWS_CURL_CANDIDATES:
        if os.path.isfile(path):
            return path
    return shutil.which("curl.exe")


def load_env_file(path=None):
    """Load KEY=VALUE pairs from a gitignored env file into os.environ.

    Existing environment variables win, so an explicit export always beats
    the file. Returns the path that was loaded, or None.
    """
    candidates = [Path(path)] if path else [Path.cwd() / ENV_FILE_NAME, REPO_ROOT / ENV_FILE_NAME]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
        return candidate
    return None


def strip_reasoning(text):
    """Remove <think> blocks and dangling think tags from a completion."""
    if not text:
        return ""
    text = _THINK_BLOCK.sub("", str(text))
    return _DANGLING_TAGS.sub("", text).strip()


class MeterlessClient:
    """Minimal OpenAI-compatible chat client for the Meterless Runtime."""

    def __init__(self, base_url=None, api_key=None, model=None, timeout=None,
                 opener=None, env_file=None, ttfb_ms=None, max_retries=None,
                 transport=None, windows_base_url=None):
        if env_file is not None or os.environ.get("METERLESS_BASE_URL") is None:
            load_env_file(env_file)

        self.base_url = str(
            base_url or os.environ.get("METERLESS_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.windows_base_url = str(
            windows_base_url
            or os.environ.get("METERLESS_BASE_URL_WINDOWS")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("METERLESS_RUNTIME_TOKEN")
            or os.environ.get("METERLESS_API_KEY")
            or os.environ.get("METERLESS_TOKEN")
            or ""
        )
        self.model = model or os.environ.get("METERLESS_MODEL") or DEFAULT_MODEL
        self.timeout = float(timeout or os.environ.get("METERLESS_TIMEOUT") or DEFAULT_TIMEOUT)
        self.ttfb_ms = (
            int(ttfb_ms) if ttfb_ms is not None
            else int(os.environ.get("METERLESS_TTFB_MS") or 0)
        )
        self.max_retries = (
            int(max_retries) if max_retries is not None
            else int(os.environ.get("METERLESS_MAX_RETRIES") or 1)
        )
        self.transport = (transport or os.environ.get("METERLESS_TRANSPORT") or "auto").lower()
        self._opener = opener or urlopen
        self.last_transport = None

    # -- introspection -----------------------------------------------------

    def config(self):
        """Safe description of the client. Never includes the API key."""
        return {
            "base_url": self.base_url,
            "windows_base_url": self.windows_base_url,
            "model": self.model,
            "timeout": self.timeout,
            "ttfb_ms": self.ttfb_ms,
            "transport": self.transport,
            "transports_available": self.available_transports(),
            "has_api_key": bool(self.api_key),
        }

    def __repr__(self):
        return f"MeterlessClient(base_url={self.base_url!r}, model={self.model!r})"

    def available_transports(self):
        """Transport names this client can use right now."""
        if self.transport == "http":
            return ["http"]
        if self.transport == "windows-curl":
            return ["windows-curl"] if find_windows_curl() else []
        order = []
        if find_windows_curl():
            order.append("windows-curl")
        order.append("http")
        return order

    # -- requests ----------------------------------------------------------

    # The runtime identifies the application, and scopes a chat request to
    # the signed-in user. Both are part of the official runtime contract.
    APP_NAME = "cross-examiner"

    def _contract_headers(self, path):
        """The headers the runtime contract asks for."""
        headers = {"meterless-app": self.APP_NAME}
        if "/chat/completions" in str(path):
            headers["meterless-scope"] = "user"
        return headers

    def _request(self, path, payload=None, method="GET"):
        """Send a request over the first transport that can reach the runtime."""
        errors = []
        for transport in self.available_transports():
            try:
                if transport == "windows-curl":
                    result = self._windows_curl_request(path, payload, method)
                else:
                    result = self._http_request(path, payload, method)
            except ModelInvalidResponse:
                raise
            except ModelRequestFailed as exc:
                # The runtime answered, so another transport would fail too.
                raise
            except ModelUnavailable as exc:
                errors.append(f"{transport}: {exc}")
                continue
            self.last_transport = transport
            return result

        if not errors:
            raise ModelUnavailable(
                "No usable transport for the Meterless Runtime "
                "(set METERLESS_TRANSPORT or install curl.exe)."
            )
        raise ModelUnavailable(" | ".join(errors))

    def _http_request(self, path, payload=None, method="GET"):
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"User-Agent": "CrossExaminer/0.1", "Accept": "application/json"}
        headers.update(self._contract_headers(path))
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.ttfb_ms:
            # Lets the runtime give a slow cloud model longer to emit its
            # first token instead of stopping the lane.
            headers["meterless-ttfb-ms"] = str(self.ttfb_ms)

        request = Request(url, data=body, method=method, headers=headers)

        attempts = max(1, self.max_retries + 1)
        for attempt in range(attempts):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                break
            except HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read(2048).decode(errors="replace")
                except Exception:
                    detail = ""
                message = redact(
                    f"HTTP {exc.code} from {url}: {detail}".strip(), self.api_key
                )
                if exc.code in (503, 504) and attempt < attempts - 1:
                    time.sleep(RETRY_BACKOFF_SECONDS)
                    continue
                raise ModelRequestFailed(message) from None
            except (URLError, TimeoutError, OSError) as exc:
                message = redact(
                    f"Cannot reach {url}: {getattr(exc, 'reason', exc)}", self.api_key
                )
                if attempt < attempts - 1:
                    time.sleep(RETRY_BACKOFF_SECONDS)
                    continue
                raise ModelUnavailable(message) from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ModelUnavailable(
                f"Response from {url} exceeded {MAX_RESPONSE_BYTES} bytes"
            )
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelInvalidResponse(
                redact(f"Non-JSON response from {url}: {exc}", self.api_key)
            ) from None

    def _windows_curl_request(self, path, payload=None, method="GET"):
        """Run the request through the Windows curl binary.

        WSL cannot reach the Windows loopback, but a Windows process can. The
        request configuration (including the bearer token) is written to a
        short-lived 0600 file so the token never appears in the command line.
        """
        curl = find_windows_curl()
        if not curl:
            raise ModelUnavailable(
                "curl.exe was not found, so the Windows transport is unavailable."
            )

        url = f"{self.windows_base_url}{path}"
        body = json.dumps(payload).encode() if payload is not None else b""

        config_lines = [
            f'url = "{url}"',
            f'request = "{method}"',
            'header = "Accept: application/json"',
        ]
        for name, value in self._contract_headers(path).items():
            config_lines.append(f'header = "{name}: {value}"')
        if self.api_key:
            config_lines.append(f'header = "Authorization: Bearer {self.api_key}"')
        if payload is not None:
            config_lines.append('header = "Content-Type: application/json"')
            config_lines.append('data = "@-"')
        if self.ttfb_ms:
            config_lines.append(f'header = "meterless-ttfb-ms: {self.ttfb_ms}"')

        handle, config_path = tempfile.mkstemp(suffix=".curlcfg")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as config_file:
                config_file.write("\n".join(config_lines) + "\n")
            os.chmod(config_path, 0o600)

            attempts = max(1, self.max_retries + 1)
            for attempt in range(attempts):
                try:
                    completed = subprocess.run(
                        [
                            curl, "-sS",
                            "-m", str(int(self.timeout)),
                            "--write-out", "\n__HTTP_STATUS__%{http_code}",
                            "--config", config_path,
                        ],
                        input=body,
                        capture_output=True,
                        timeout=self.timeout + 30,
                    )
                except (subprocess.TimeoutExpired, OSError) as exc:
                    message = redact(f"Windows transport failed: {exc}", self.api_key)
                    if attempt < attempts - 1:
                        time.sleep(RETRY_BACKOFF_SECONDS)
                        continue
                    raise ModelUnavailable(message) from None

                if completed.returncode != 0:
                    message = redact(
                        "Windows transport failed: "
                        f"{completed.stderr.decode(errors='replace').strip()}",
                        self.api_key,
                    )
                    if attempt < attempts - 1:
                        time.sleep(RETRY_BACKOFF_SECONDS)
                        continue
                    raise ModelUnavailable(message) from None

                raw, status = self._split_curl_output(completed.stdout)
                if status >= 400:
                    message = redact(
                        f"HTTP {status} from {url}: {raw[:400]}".strip(), self.api_key
                    )
                    if status in (503, 504) and attempt < attempts - 1:
                        time.sleep(RETRY_BACKOFF_SECONDS)
                        continue
                    raise ModelRequestFailed(message) from None
                break
        finally:
            try:
                os.unlink(config_path)
            except OSError:
                pass

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelInvalidResponse(
                redact(f"Non-JSON response from {url}: {exc}", self.api_key)
            ) from None

    @staticmethod
    def _split_curl_output(raw):
        """Split curl's stdout into the body and the HTTP status code."""
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        marker = "\n__HTTP_STATUS__"
        if marker not in text:
            return text, 0
        body, status = text.rsplit(marker, 1)
        try:
            return body, int(status.strip())
        except ValueError:
            return body, 0

    def list_models(self):
        """Return the model ids the runtime advertises."""
        payload = self._request("/models")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ModelInvalidResponse("Runtime did not return a model list")
        return [
            item.get("id")
            for item in data
            if isinstance(item, dict) and item.get("id")
        ]

    def probe(self):
        """True when the runtime answers and the token is accepted."""
        try:
            self.list_models()
        except (ModelUnavailable, ModelInvalidResponse):
            return False
        return True

    def chat(self, messages, max_tokens=400, temperature=0.2, json_mode=False):
        """Send a chat completion request and return the assistant text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = self._request("/chat/completions", payload, method="POST")

        if isinstance(response, dict) and response.get("error"):
            error = response["error"]
            detail = error.get("message") if isinstance(error, dict) else str(error)
            raise ModelRequestFailed(
                redact(f"Runtime error: {detail}", self.api_key)
            )

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ModelInvalidResponse(
                "Runtime response had no assistant message"
            ) from None

        text = strip_reasoning(content)
        if not text:
            raise ModelInvalidResponse("Runtime returned an empty completion")
        return text

    def chat_json(self, messages, max_tokens=400, temperature=0.2):
        """Send a chat completion request and return a parsed JSON object.

        The runtime is asked for JSON mode. If the model still wraps the
        object in prose or code fences, the first balanced JSON object is
        extracted. Anything else raises :class:`ModelInvalidResponse`.
        """
        text = self.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
        return parse_json_object(text)


def parse_json_object(text):
    """Parse a JSON object from model output, tolerating minor wrapping."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                parsed = None

    if not isinstance(parsed, dict):
        raise ModelInvalidResponse(
            "Model response did not contain a JSON object"
        )
    return parsed
