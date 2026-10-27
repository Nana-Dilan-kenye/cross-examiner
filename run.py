#!/usr/bin/env python3
"""Cross-Examiner - the programmatic entry point.

Three ways to use it, so a judge never has to click through a screen:

    python3 run.py                  # the HTTP service on 0.0.0.0:8000
    python3 run.py --health         # one health check, as JSON
    python3 run.py --once request.json

``--once`` runs a single investigation from a JSON request and prints the
structured result. The request may be written either way:

    {"question": "...", "country": "Cameroon", "antigen": "MCV1", "year": "2020"}

or in the wrapped form:

    {"run_id": "...", "input": {...}, "options": {...}}

The response carries the run id, the status, the output, the agents that
took part, the trace id, the log file and how long it took. A request
that cannot be honoured comes back as a structured error, not a stack
trace.

Secrets come from the environment. Set SAMPLE_MODE=true to run without
credentials and without a network.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.app import health, run_payload  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Cross-Examiner: reconcile conflicting coverage figures.",
    )
    parser.add_argument(
        "--once",
        metavar="REQUEST.json",
        help="run one investigation from a JSON request and print the result",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="print the health report as JSON and exit",
    )
    parser.add_argument(
        "--host", default=os.environ.get("HOST", "0.0.0.0"),
        help="the address to bind (default 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", "8000")),
        help="the port to listen on (default 8000)",
    )
    return parser.parse_args(argv)


def once(path):
    """Run one investigation and print the result."""
    try:
        request = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        print(json.dumps({
            "status": "error",
            "error": {
                "type": "request_not_readable",
                "message": f"cannot read {path}: {exc}",
                "recoverable": True,
            },
        }, indent=2))
        return 2
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "status": "error",
            "error": {
                "type": "invalid_json",
                "message": f"{path} is not valid JSON: {exc}",
                "recoverable": True,
            },
        }, indent=2))
        return 2

    try:
        payload = run_payload(request, echo="stderr")
    except ValueError as exc:
        print(json.dumps({
            "status": "error",
            "error": {
                "type": "invalid_request",
                "message": str(exc),
                "recoverable": True,
            },
        }, indent=2))
        return 2
    except Exception as exc:  # pragma: no cover - the failure path
        print(json.dumps({
            "status": "error",
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "recoverable": False,
            },
        }, indent=2))
        return 1

    print(json.dumps(payload, indent=2))
    return 0 if payload.get("status") != "abstained" else 0


def main(argv=None):
    args = parse_args(argv)

    if args.health:
        print(json.dumps(health(), indent=2))
        return 0

    if args.once:
        return once(args.once)

    from src.app import serve
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
