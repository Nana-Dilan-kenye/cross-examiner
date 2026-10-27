"""The Cross-Examiner HTTP API.

    GET  /health          what is available, and whether it is reachable
    POST /run             run an investigation
    GET  /traces/<run_id> the trace of one run
    GET  /examples        the example requests

The API is built on the standard library only. The project installs
nothing at run time, so there is no web framework to depend on.

Two modes:

``live``
    The deployed Zetaris semantic layer answers, and the memory store
    is read and written.

``SAMPLE_MODE=true``
    No credentials, no network. The local files answer, and the response
    says so in ``mode`` and in every finding's ``data_kind``. Generated
    records are never evidence in either mode.
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import source_registry  # noqa: E402
from src.runner import (  # noqa: E402
    SOURCE_CHOICES,
    run_investigation,
    sample_mode,
)
from src.tracing import TRACE_DIR, read_trace  # noqa: E402

DEFAULT_PORT = 8000
MAX_BODY_BYTES = 256 * 1024

# The investigation page is static files under ui/, served by this same
# server, so the browser calls the API it was loaded from. Nothing outside
# ui/ is ever served.
UI_DIR = ROOT / "ui"
UI_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}
# The page uses no inline script, style or event handler, so the policy
# can be strict.
UI_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def health():
    """What the service can do right now."""
    from src.zetaris_source import USL_TABLE

    report = {
        "status": "ok",
        "mode": "sample" if sample_mode() else "live",
        "sample_mode": sample_mode(),
        "components": {},
        "semantic_layer": USL_TABLE,
        "ui": "/ui/",
    }

    # The semantic layer.
    layer = {"object": USL_TABLE, "reachable": False, "rows": None}
    if not sample_mode():
        try:
            from src.zetaris_source import load_with_trace
            rows, trace = load_with_trace()
            layer["reachable"] = trace.get("path") == "zetaris_usl"
            layer["rows"] = len(rows)
            layer["source_ids"] = trace.get("source_ids")
        except Exception as exc:
            layer["error"] = f"{type(exc).__name__}: {exc}"
    else:
        layer["reachable"] = False
        layer["note"] = "sample mode reads the local files"
    report["components"]["zetaris_usl"] = layer

    # The memory store.
    memory = {"available": False}
    if not sample_mode():
        try:
            from src.memory_bridge import query
            result = query("cross-examiner health check")
            memory["available"] = bool(result.get("available"))
            memory["error"] = result.get("error")
        except Exception as exc:
            memory["error"] = f"{type(exc).__name__}: {exc}"
    else:
        memory["note"] = "sample mode does not use the memory store"
    report["components"]["memory"] = memory

    # The registry.
    report["components"]["registry"] = {
        "sources": len(source_registry.registry_rows()),
        "path": "data/sources.json",
    }

    return report


def _finding_payload(finding, decision, evidence, uncertainties, mode):
    """One finding, with everything a reader needs to check it."""
    lineage = []
    for observation in finding.get("observations") or []:
        item = observation.get("lineage") or {}
        lineage.append({
            "measure": observation.get("measure"),
            "value": observation.get("value"),
            "origin": observation.get("origin"),
            "origin_label": observation.get("origin_label"),
            "measurement_kind": observation.get("measurement_kind"),
            "source_id": observation.get("source_id") or item.get("source_id"),
            "source_type": observation.get("source_type") or item.get("source_type"),
            "source_name": observation.get("source", {}).get("name")
            or item.get("source_name"),
            "source_ref": observation.get("source", {}).get("url")
            or item.get("source_ref"),
            "is_derived": observation.get("is_derived"),
            "is_synthetic": observation.get("is_synthetic"),
            "independent_capable": observation.get("independent_capable"),
            "verification_scope": observation.get("verification_scope"),
        })

    data_kind = "synthetic" if finding.get("synthetic") else "observed"
    if mode == "sample":
        data_kind = f"sample:{data_kind}"

    return {
        "country": finding.get("country"),
        "antigen": finding.get("antigen"),
        "year": finding.get("year"),
        "data_kind": data_kind,
        "status": finding.get("status"),
        "review_status": decision.get("disposition"),
        "confidence": _confidence(decision),
        "decision": decision.get("decision"),
        "reason": decision.get("reason"),
        "measures": {
            "a": {"measure": finding.get("measure_a"), "value": finding.get("value_a")},
            "b": {"measure": finding.get("measure_b"), "value": finding.get("value_b")},
        },
        "gap_percentage_points": finding.get("gap_percentage_points"),
        "recommendation": decision.get("recommendation"),
        "conflicts": (decision.get("critic") or {}).get("conflicts") or [],
        "lineage": lineage,
        "evidence": evidence,
        "uncertainties": uncertainties,
        "memory_recall": decision.get("memory_recall"),
    }


def _confidence(decision):
    from src.runner import confidence_for
    return confidence_for(decision)


def unwrap(request):
    """Accept both request shapes.

    The flat form: ``{"question": ..., "country": ...}``. The wrapped
    form: ``{"run_id": ..., "input": {...}, "options": {...}}``.
    """
    if not isinstance(request, dict):
        raise ValueError("the request body must be a JSON object")

    inner = request.get("input")
    options = request.get("options")
    if isinstance(inner, dict) or isinstance(options, dict):
        merged = {}
        if isinstance(inner, dict):
            merged.update(inner)
        if isinstance(options, dict):
            merged.update(options)
        merged.setdefault("run_id", request.get("run_id"))
        return merged
    return request


def run_payload(request, echo=True):
    """Run an investigation and build the response.

    ``echo`` decides where the run's log goes: stdout for the service,
    stderr for a one-shot command whose stdout carries the result.
    """
    request = unwrap(request)
    question = request.get("question")
    country = request.get("country")
    antigen = request.get("antigen")
    year = request.get("year")

    if not isinstance(question, (str, type(None))):
        raise ValueError("'question' must be a string")
    for name, value in (("country", country), ("antigen", antigen), ("year", year)):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"'{name}' must be a string")
    if not question and not (country and antigen and year):
        raise ValueError(
            "give a 'question', or a 'country', 'antigen' and 'year' to "
            "investigate"
        )

    source = request.get("source") or ("local" if sample_mode() else "auto")
    if source not in SOURCE_CHOICES:
        raise ValueError(
            f"'source' must be one of {', '.join(SOURCE_CHOICES)}"
        )
    model = request.get("model") or ("off" if sample_mode() else "auto")
    if model not in ("auto", "off") and "/" not in model and ":" not in model:
        raise ValueError("'model' must be 'auto', 'off' or a model id")

    threshold = request.get("threshold", 5)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        raise ValueError("'threshold' must be a number")
    if threshold <= 0:
        raise ValueError("'threshold' must be greater than zero")

    max_iterations = request.get("max_iterations", 4)
    try:
        max_iterations = int(max_iterations)
    except (TypeError, ValueError):
        raise ValueError("'max_iterations' must be a whole number")
    if max_iterations < 1 or max_iterations > 20:
        raise ValueError("'max_iterations' must be between 1 and 20")

    started = time.time()
    result = run_investigation(
        question=question,
        country=country,
        antigen=antigen,
        year=year,
        source=source,
        model=model,
        use_memory=bool(request.get("use_memory", True)),
        remember=bool(request.get("remember", False)),
        threshold=threshold,
        max_iterations=max_iterations,
        include_synthetic=bool(request.get("include_synthetic", False)),
        echo=echo,
    )

    # The mode follows what actually answered: the local files make it a
    # sample run even when the service itself is in live mode.
    mode = "sample" if (sample_mode() or source == "local") else "live"
    ledger = result["evidence_ledger"]
    uncertainties = result["uncertainties"] or {}

    findings = []
    for index, finding in enumerate(result["findings"]):
        decision = (
            result["decisions"][index]
            if index < len(result["decisions"]) else {}
        )
        label = (
            f"{finding.get('country', '')} {finding.get('antigen', '')} "
            f"({finding.get('year', '')})"
        )
        evidence = [
            {
                "evidence_id": item.get("evidence_id"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "url": item.get("url"),
                "status": item.get("status"),
                "scope": item.get("scope"),
                "findings": item.get("findings"),
            }
            for item in ledger
        ]
        findings.append(_finding_payload(
            finding,
            decision,
            evidence,
            uncertainties.get(label) or [],
            mode,
        ))

    dispositions = [item for item in result["dispositions"] if item]
    if not findings:
        status = "no_findings"
    elif "ABSTAIN" in dispositions:
        status = "abstained"
    elif all(item in ("ACCEPT", "REJECT") for item in dispositions):
        status = "resolved"
    else:
        status = "review"

    agents = sorted({
        event.get("agent_name")
        for event in read_trace(result["run_id"])
        if event.get("agent_name")
    })

    return {
        "run_id": result["run_id"],
        "status": status,
        "mode": mode,
        "sample_mode": sample_mode(),
        "question": question,
        "semantic_layer": result["evidence_trace"],
        "findings": findings,
        "evidence": [
            {
                "evidence_id": item.get("evidence_id"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "url": item.get("url"),
                "status": item.get("status"),
                "scope": item.get("scope"),
            }
            for item in ledger
        ],
        "executed_actions": result["executed_actions"],
        "memory": {
            "available": result["memory_context"]["available"],
            "memories": result["memory_context"]["memories"],
            "stored": len(result["remembered"]),
            "error": result["memory_context"]["error"],
        },
        "stop_reason": result["stop_reason"],
        "stop_detail": result["stop_detail"],
        "model": {
            "status": result["model"].get("status"),
            "model": result["model"].get("model"),
            "calls": result["model"].get("calls"),
            "note": result["model"].get("note"),
        },
        "trace": result["trace_file"],
        "trace_id": result["run_id"],
        "log_file": result["trace_file"],
        "agents": agents,
        "output": {
            "findings": findings,
            "evidence": [
                {
                    "evidence_id": item.get("evidence_id"),
                    "kind": item.get("kind"),
                    "name": item.get("name"),
                    "url": item.get("url"),
                    "status": item.get("status"),
                    "scope": item.get("scope"),
                }
                for item in ledger
            ],
            "stop_reason": result["stop_reason"],
            "uncertainties": uncertainties,
        },
        "execution_time_seconds": round(time.time() - started, 3),
        "programme_checks": [
            {
                "code": flag.get("code"),
                "district": flag.get("district"),
                "antigen": flag.get("antigen"),
                "year": flag.get("year"),
                "detail": flag.get("detail"),
                "data_kind": "synthetic",
            }
            for flag in result.get("programme_checks") or []
        ],
        "elapsed_seconds": round(time.time() - started, 3),
    }


def ui_file(name):
    """The file under ``ui/`` that a request names, or ``None``.

    The name is resolved and must stay inside ``ui/``, so ``..``, encoded
    separators and absolute paths cannot reach the rest of the repository.
    """
    name = (name or "").lstrip("/") or "index.html"
    if "\\" in name or "\x00" in name:
        return None
    try:
        root = UI_DIR.resolve()
        path = (root / name).resolve()
    except (OSError, ValueError):
        return None
    if root not in path.parents or not path.is_file():
        return None
    return path


class Handler(BaseHTTPRequestHandler):
    server_version = "CrossExaminer/1.0"

    def _send(self, status, payload):
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        # The page's asset links are relative, so /ui without the slash
        # resolves them at the repository root and they 404. /ui names
        # nothing else, so redirect it once to /ui/ and stop. The raw path
        # is matched exactly: /ui/ (the page itself) never redirects, or
        # the two spellings would chase each other.
        if parsed.path == "/ui":
            location = "/ui/" + ("?" + parsed.query if parsed.query else "")
            self.send_response(301)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        route = parsed.path.rstrip("/") or "/"

        if route in ("/", "/health"):
            self._send(200, health())
            return

        if route == "/ui" or route.startswith("/ui/"):
            self._send_ui(unquote(route[len("/ui/"):]))
            return

        if route == "/examples":
            self._send(200, {
                "requests": _example_requests(),
            })
            return

        if route.startswith("/traces/"):
            run_id = route.split("/traces/", 1)[1]
            records = read_trace(run_id)
            if not records:
                self._send(404, {
                    "error": f"no trace for run {run_id}",
                    "hint": "the trace lives in logs/trace-<run_id>.jsonl",
                })
                return
            self._send(200, {"run_id": run_id, "events": records})
            return

        self._send(404, {"error": f"no route {route}"})

    def _send_ui(self, name):
        path = ui_file(name)
        if path is None:
            self._send(404, {
                "error": f"no UI file {name or 'index.html'}",
                "hint": "the investigation page is at /ui/",
            })
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type", UI_TYPES.get(path.suffix, "application/octet-stream")
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", UI_POLICY)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        route = urlparse(self.path).path.rstrip("/") or "/"

        if route != "/run":
            self._send(404, {"error": f"no route {route}"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._send(413, {"error": "the request body is too large"})
            return
        raw = self.rfile.read(length) if length else b"{}"

        try:
            request = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(400, {
                "error": "the request body is not valid JSON",
                "detail": str(exc),
            })
            return

        if not isinstance(request, dict):
            self._send(400, {"error": "the request body must be a JSON object"})
            return

        try:
            payload = run_payload(request)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - the failure path
            self._send(500, {
                "error": "the investigation could not be completed",
                "detail": f"{type(exc).__name__}: {exc}",
            })
            return

        self._send(200, payload)

    def log_message(self, format, *args):
        sys.stderr.write(
            "%s - %s\n" % (self.address_string(), format % args)
        )


def _example_requests():
    """The example requests, read from the repository."""
    directory = ROOT / "input_examples"
    examples = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                examples.append({
                    "file": f"input_examples/{path.name}",
                    "request": json.loads(path.read_text(encoding="utf-8")),
                })
            except (OSError, json.JSONDecodeError):
                continue
    return examples


def serve(host="0.0.0.0", port=None):
    """Run the API."""
    port = int(port or os.environ.get("PORT") or DEFAULT_PORT)
    server = ThreadingHTTPServer((host, port), Handler)
    mode = "sample" if sample_mode() else "live"
    print(f"Cross-Examiner API on http://{host}:{port} ({mode} mode)")
    print(f"  GET  /health")
    print(f"  POST /run")
    print(f"  GET  /traces/<run_id>")
    print(f"  GET  /ui/            the investigation page")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
